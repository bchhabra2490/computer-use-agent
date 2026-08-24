#!/usr/bin/env python3
"""Race TTS providers on the same sentence and log who finishes first.

Synthesizes the same text with openai / sarvam / piper / kokoro in parallel.
Times synthesis only (not playback). Optional warmup so local model load is
not counted; optional ``--play`` after the race.

Usage:
    python tts_race.py
    python tts_race.py --text "Who are you?"
    python tts_race.py --providers piper,kokoro --rounds 3
    python tts_race.py --no-warmup --play
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from envfile import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "tts_race.log"
DEFAULT_TEXT = "Who are you? Let's see how fast local speech is compared to the cloud."
ALL_PROVIDERS = ("openai", "sarvam", "piper", "kokoro")


@dataclass
class RaceResult:
    provider: str
    detail: str
    ms: float
    wav: bytes = b""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.wav)


def _wall() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _log(line: str, *, log_path: Path) -> None:
    print(line, flush=True)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"[tts-race] log write failed ({e})", file=sys.stderr, flush=True)


def _wav_seconds(wav: bytes) -> float:
    if not wav or wav[:4] != b"RIFF":
        return 0.0
    try:
        with wave.open(io.BytesIO(wav), "rb") as wf:
            n = wf.getnframes()
            rate = wf.getframerate() or 1
            return n / float(rate)
    except Exception:
        return 0.0


def _rtf(ms: float, audio_s: float) -> str:
    if audio_s <= 0:
        return "rtf=?"
    return f"rtf={ (ms / 1000.0) / audio_s :.2f}"


def _openai_voice() -> str:
    return (os.environ.get("TTS_VOICE") or "onyx").strip() or "onyx"


def _sarvam_voice() -> str:
    return (os.environ.get("SARVAM_TTS_VOICE") or os.environ.get("TTS_VOICE") or "shubh").strip() or "shubh"


def _piper_voice() -> str:
    from tts.piper import PIPER_VOICE

    return (os.environ.get("PIPER_VOICE") or PIPER_VOICE).strip() or "en_GB-alan-medium"


def _kokoro_voice() -> str:
    from tts.kokoro import KOKORO_VOICE

    return (os.environ.get("KOKORO_VOICE") or KOKORO_VOICE).strip() or "bm_george"


def _provider_ready(name: str) -> tuple[bool, str]:
    if name == "openai":
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            return False, "OPENAI_API_KEY not set"
        return True, f"voice={_openai_voice()} model=gpt-4o-mini-tts"
    if name == "sarvam":
        from stt.sarvam import sarvam_configured
        from tts.sarvam import SARVAM_TTS_MODEL

        if not sarvam_configured():
            return False, "SARVAM_API_KEY not set"
        return True, f"voice={_sarvam_voice()} model={SARVAM_TTS_MODEL}"
    if name == "piper":
        try:
            from tts.piper import _load_piper

            _load_piper()
        except Exception as e:
            return False, str(e)
        return True, f"voice={_piper_voice()}"
    if name == "kokoro":
        from tts.kokoro import KOKORO_MODEL, KOKORO_ONNX_MODEL, _mlx_available

        if KOKORO_ONNX_MODEL:
            path = Path(KOKORO_ONNX_MODEL).expanduser()
            if not path.is_file():
                return False, f"KOKORO_ONNX_MODEL missing ({path})"
            return True, f"backend=onnx voice={_kokoro_voice()}"
        if _mlx_available():
            try:
                from tts.kokoro import _ensure_misaki_en

                _ensure_misaki_en()
            except Exception as e:
                return False, str(e)
            return True, f"backend=mlx model={KOKORO_MODEL} voice={_kokoro_voice()}"
        return False, "mlx-audio not installed (pip install mlx-audio) and no KOKORO_ONNX_MODEL"
    return False, f"unknown provider {name!r}"


def _run_openai(text: str) -> RaceResult:
    from openai import OpenAI

    from tts.openai import synthesize_wav

    voice = _openai_voice()
    detail = f"voice={voice}"
    t0 = time.perf_counter()
    try:
        wav = synthesize_wav(OpenAI(), text, voice)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("openai", detail, ms, wav)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("openai", detail, ms, error=str(e))


def _run_sarvam(text: str) -> RaceResult:
    from tts.sarvam import SARVAM_TTS_MODEL, synthesize_wav

    voice = _sarvam_voice()
    detail = f"voice={voice} model={SARVAM_TTS_MODEL}"
    t0 = time.perf_counter()
    try:
        wav = synthesize_wav(text, speaker=voice)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("sarvam", detail, ms, wav)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("sarvam", detail, ms, error=str(e))


def _run_piper(text: str) -> RaceResult:
    from tts.piper import synthesize_wav

    voice = _piper_voice()
    detail = f"voice={voice}"
    t0 = time.perf_counter()
    try:
        wav = synthesize_wav(text, voice=voice)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("piper", detail, ms, wav)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("piper", detail, ms, error=str(e))


def _run_kokoro(text: str) -> RaceResult:
    from tts.kokoro import synthesize_wav

    voice = _kokoro_voice()
    detail = f"voice={voice}"
    t0 = time.perf_counter()
    try:
        wav = synthesize_wav(text, voice=voice)
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("kokoro", detail, ms, wav)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return RaceResult("kokoro", detail, ms, error=str(e))


_RUNNERS = {
    "openai": _run_openai,
    "sarvam": _run_sarvam,
    "piper": _run_piper,
    "kokoro": _run_kokoro,
}


def _warmup(providers: list[str], log_path: Path) -> None:
    _log("[tts-race] warmup (not timed)…", log_path=log_path)
    for name in providers:
        t0 = time.perf_counter()
        result = _RUNNERS[name]("Ready.")
        ms = (time.perf_counter() - t0) * 1000
        if result.ok:
            _log(f"[tts-race] warmup {name} ok {ms:.0f}ms", log_path=log_path)
        else:
            _log(f"[tts-race] warmup {name} failed {ms:.0f}ms → {result.error}", log_path=log_path)


def race_once(
    text: str,
    providers: list[str],
    *,
    log_path: Path,
    round_n: int,
    save_dir: Path | None,
) -> list[RaceResult]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _log(
        f"[tts-race] --- round {round_n} {stamp} chars={len(text)} " f"providers={','.join(providers)} ---",
        log_path=log_path,
    )
    _log(f"[tts-race] text={text!r}", log_path=log_path)
    print(f"[tts-race] {_wall()} starting race…", flush=True)

    lock = threading.Lock()
    finish_rank = 0
    results: list[RaceResult] = []
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="tts-race") as pool:
        futures = {pool.submit(_RUNNERS[name], text): name for name in providers}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                elapsed = (time.perf_counter() - t_start) * 1000
                result = RaceResult(name, "", elapsed, error=str(e))
            with lock:
                finish_rank += 1
                rank = finish_rank
                results.append(result)
            since_start = (time.perf_counter() - t_start) * 1000
            audio_s = _wav_seconds(result.wav) if result.ok else 0.0
            if result.ok:
                line = (
                    f"[tts-race] #{rank} {result.provider} "
                    f"synth={result.ms:.0f}ms since_start={since_start:.0f}ms "
                    f"audio={audio_s:.2f}s {_rtf(result.ms, audio_s)} "
                    f"({result.detail}) bytes={len(result.wav)}"
                )
            else:
                line = (
                    f"[tts-race] #{rank} {result.provider} "
                    f"FAILED synth={result.ms:.0f}ms since_start={since_start:.0f}ms "
                    f"({result.detail}) → {result.error}"
                )
            _log(line, log_path=log_path)
            if result.ok and save_dir is not None:
                dest = save_dir / f"round{round_n}_{result.provider}.wav"
                dest.write_bytes(result.wav)

    ok = [r for r in results if r.ok]
    if ok:
        winner = min(ok, key=lambda r: r.ms)
        _log(
            f"[tts-race] winner (lowest synth ms): {winner.provider} {winner.ms:.0f}ms",
            log_path=log_path,
        )
    else:
        _log("[tts-race] no provider succeeded", log_path=log_path)
    return results


def _play_results(results: list[RaceResult]) -> None:
    from tts import play_wav

    ordered = sorted((r for r in results if r.ok), key=lambda r: r.ms)
    for result in ordered:
        print(f"[tts-race] playing {result.provider} ({result.ms:.0f}ms)…", flush=True)
        play_wav(result.wav)


def main() -> int:
    parser = argparse.ArgumentParser(description="Race TTS providers on one sentence")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Sentence to synthesize")
    parser.add_argument(
        "--providers",
        default=",".join(ALL_PROVIDERS),
        help=f"Comma list (default: {','.join(ALL_PROVIDERS)})",
    )
    parser.add_argument("--rounds", type=int, default=1, help="Repeat the race (default 1)")
    parser.add_argument(
        "--warmup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Load/synthesize 'Ready.' once before timing (default: on)",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="Play each successful WAV after the last round (fastest first)",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Directory for per-provider WAVs (default: recordings/tts_race_<ts>/)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"Append results here (default: {DEFAULT_LOG.name})",
    )
    args = parser.parse_args()

    text = (args.text or "").strip()
    if not text:
        print("[tts-race] empty --text", file=sys.stderr)
        return 2

    requested = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in requested if p not in _RUNNERS]
    if unknown:
        print(f"[tts-race] unknown providers: {', '.join(unknown)}", file=sys.stderr)
        return 2

    providers: list[str] = []
    for name in requested:
        ok, detail = _provider_ready(name)
        if ok:
            print(f"[tts-race] {name}: ready ({detail})", flush=True)
            providers.append(name)
        else:
            print(f"[tts-race] {name}: skip — {detail}", flush=True)
    if not providers:
        print("[tts-race] no providers ready", file=sys.stderr)
        return 1

    log_path = args.log.resolve()
    save_dir = args.save
    if save_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        save_dir = ROOT / "recordings" / f"tts_race_{ts}"
    save_dir = save_dir.resolve()
    save_dir.mkdir(parents=True, exist_ok=True)
    print(f"[tts-race] saving WAVs → {save_dir}", flush=True)

    if args.warmup:
        _warmup(providers, log_path)

    last: list[RaceResult] = []
    for n in range(1, max(1, args.rounds) + 1):
        last = race_once(text, providers, log_path=log_path, round_n=n, save_dir=save_dir)

    if args.play and last:
        _play_results(last)

    print(f"[tts-race] full log → {log_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
