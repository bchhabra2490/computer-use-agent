#!/usr/bin/env python3
"""Race STT providers on the same clip and log who finishes first.

Records once (or loads ``--wav``), then runs openai / sarvam / whisperflow
file transcription in parallel. As each returns, prints rank + latency + text.

Usage:
    python stt_race.py
    python stt_race.py --wav recordings/some.wav
    python stt_race.py --providers sarvam,whisperflow
    python stt_race.py --rounds 3
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from envfile import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "stt_race.log"
ALL_PROVIDERS = ("openai", "sarvam", "whisperflow")


@dataclass
class RaceResult:
    provider: str
    detail: str
    ms: float
    text: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _wall() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _log(line: str, *, log_path: Path) -> None:
    print(line, flush=True)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"[stt-race] log write failed ({e})", file=sys.stderr, flush=True)


def _openai_model() -> str:
    # File API — not the Realtime live model.
    return (os.environ.get("STT_REFINE_MODEL") or "gpt-4o-transcribe").strip() or "gpt-4o-transcribe"


def _provider_ready(name: str) -> tuple[bool, str]:
    if name == "openai":
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            return False, "OPENAI_API_KEY not set"
        return True, f"model={_openai_model()}"
    if name == "sarvam":
        from stt.sarvam import SARVAM_STT_MODEL, sarvam_configured

        if not sarvam_configured():
            return False, "SARVAM_API_KEY not set"
        return True, f"model={SARVAM_STT_MODEL}"
    if name == "whisperflow":
        try:
            from stt.whisperflow import WHISPERFLOW_MODEL, resolve_backend

            backend = resolve_backend()
            return True, f"backend={backend} model={WHISPERFLOW_MODEL}"
        except Exception as e:
            return False, str(e)
    return False, f"unknown provider {name!r}"


def _run_openai(wav: bytes) -> RaceResult:
    from openai import OpenAI

    from stt.openai import transcribe_wav

    model = _openai_model()
    t0 = time.perf_counter()
    try:
        text = transcribe_wav(OpenAI(), wav, model=model)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("openai", f"model={model}", ms, text or "")
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("openai", f"model={model}", ms, "", error=str(e))


def _run_sarvam(wav: bytes) -> RaceResult:
    from stt.sarvam import SARVAM_STT_MODEL, transcribe_wav

    t0 = time.perf_counter()
    try:
        text = transcribe_wav(wav)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("sarvam", f"model={SARVAM_STT_MODEL}", ms, text or "")
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("sarvam", f"model={SARVAM_STT_MODEL}", ms, "", error=str(e))


def _run_whisperflow(wav: bytes) -> RaceResult:
    from stt.whisperflow import WHISPERFLOW_MODEL, resolve_backend, transcribe_wav

    detail = f"backend={resolve_backend()} model={WHISPERFLOW_MODEL}"
    t0 = time.perf_counter()
    try:
        text = transcribe_wav(wav)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("whisperflow", detail, ms, text or "")
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("whisperflow", detail, ms, "", error=str(e))


_RUNNERS = {
    "openai": _run_openai,
    "sarvam": _run_sarvam,
    "whisperflow": _run_whisperflow,
}


def _record_clip(*, idle: float, max_seconds: float) -> bytes:
    from stt import record_until_silence

    print(
        f"[stt-race] Speak now… (sends after {idle:g}s silence, max {max_seconds:g}s)",
        flush=True,
    )
    return record_until_silence(
        silence_seconds=idle,
        max_record_seconds=max_seconds,
        require_speech=True,
        prompt="Listening for race clip…",
        end_on_enter=True,
    )


def _load_wav(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF":
        raise SystemExit(f"Not a WAV file: {path}")
    return data


def _save_clip(wav: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(wav)
    print(f"[stt-race] saved clip → {dest} ({len(wav)} bytes)", flush=True)


def race_once(
    wav: bytes,
    providers: list[str],
    *,
    log_path: Path,
    round_n: int,
) -> list[RaceResult]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _log(
        f"[stt-race] --- round {round_n} {stamp} clip={len(wav)} bytes " f"providers={','.join(providers)} ---",
        log_path=log_path,
    )
    print(f"[stt-race] {_wall()} starting race…", flush=True)

    lock = threading.Lock()
    finish_rank = 0
    results: list[RaceResult] = []
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="stt-race") as pool:
        futures = {pool.submit(_RUNNERS[name], wav): name for name in providers}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                elapsed = (time.perf_counter() - t_start) * 1000
                result = RaceResult(name, "", elapsed, "", error=str(e))
            with lock:
                finish_rank += 1
                rank = finish_rank
                results.append(result)
            since_start = (time.perf_counter() - t_start) * 1000
            if result.ok:
                line = (
                    f"[stt-race] #{rank} {result.provider} "
                    f"api={result.ms:.0f}ms since_start={since_start:.0f}ms "
                    f"({result.detail}) → {result.text!r}"
                )
            else:
                line = (
                    f"[stt-race] #{rank} {result.provider} "
                    f"FAILED api={result.ms:.0f}ms since_start={since_start:.0f}ms "
                    f"({result.detail}) → {result.error}"
                )
            _log(line, log_path=log_path)

    ok = [r for r in results if r.ok]
    if ok:
        winner = min(ok, key=lambda r: r.ms)
        _log(
            f"[stt-race] winner (lowest API ms): {winner.provider} " f"{winner.ms:.0f}ms → {winner.text!r}",
            log_path=log_path,
        )
    else:
        _log("[stt-race] no provider succeeded", log_path=log_path)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Race STT providers on one shared speech clip",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        help="Reuse an existing WAV instead of recording",
    )
    parser.add_argument(
        "--providers",
        default=",".join(ALL_PROVIDERS),
        help=f"Comma list (default: {','.join(ALL_PROVIDERS)})",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="How many times to race the same clip (default 1)",
    )
    parser.add_argument(
        "--idle",
        type=float,
        default=float(os.environ.get("STT_IDLE_SECONDS", "2")),
        help="Silence seconds before ending mic capture",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=28.0,
        help="Max record length (Sarvam sync cap is ~30s)",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Where to save the recorded clip (default: recordings/stt_race_<ts>.wav)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"Append results here (default: {DEFAULT_LOG.name})",
    )
    args = parser.parse_args()

    requested = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in requested if p not in _RUNNERS]
    if unknown:
        print(f"[stt-race] unknown providers: {', '.join(unknown)}", file=sys.stderr)
        return 2

    providers: list[str] = []
    for name in requested:
        ok, detail = _provider_ready(name)
        if ok:
            print(f"[stt-race] {name}: ready ({detail})", flush=True)
            providers.append(name)
        else:
            print(f"[stt-race] {name}: skip — {detail}", flush=True)
    if not providers:
        print("[stt-race] no providers ready", file=sys.stderr)
        return 1

    if args.wav:
        wav = _load_wav(args.wav.resolve())
        print(f"[stt-race] loaded {args.wav} ({len(wav)} bytes)", flush=True)
    else:
        try:
            wav = _record_clip(idle=args.idle, max_seconds=args.max_seconds)
        except KeyboardInterrupt:
            print("\n[stt-race] cancelled", flush=True)
            return 130
        except Exception as e:
            print(f"[stt-race] record failed: {e}", file=sys.stderr)
            return 1
        dest = args.save
        if dest is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = ROOT / "recordings" / f"stt_race_{ts}.wav"
        _save_clip(wav, dest.resolve())

    log_path = args.log.resolve()
    for n in range(1, max(1, args.rounds) + 1):
        race_once(wav, providers, log_path=log_path, round_n=n)

    print(f"[stt-race] full log → {log_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
