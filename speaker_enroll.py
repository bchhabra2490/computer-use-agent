"""Interactive speaker enrollment: read five passages (three long, two short), save voice profile."""

from __future__ import annotations

import argparse
import sys

from openai import OpenAI

from speaker_id import (
    ENROLLMENT_PASSAGES,
    LONG_PASSAGE_COUNT,
    delete_profile,
    enroll_speaker,
    list_profiles,
    slug_name,
    wav_has_min_speech,
)
from stt import record_until_enter


def _release_audio_for_capture() -> None:
    """Drop wake/TTS mic hooks so PortAudio can open the input device."""
    try:
        from wake import stop_persistent_wake

        stop_persistent_wake()
    except Exception:
        pass
    try:
        import sounddevice as sd

        sd.stop()
    except Exception:
        pass
    import time

    time.sleep(0.15)


def _speak_prompt(client: OpenAI, text: str) -> None:
    """TTS for enrollment — no wake/keyboard barge (avoids mic conflicts)."""
    from tts import play_wav, synthesize, tts_print

    tts_print(f"[tts] {text}")
    try:
        play_wav(synthesize(client, text))
    except Exception as e:
        print(f"[speaker] TTS skipped ({e})", flush=True)


def _record_passage(
    title: str,
    text: str,
    *,
    max_seconds: float,
    short: bool = False,
) -> bytes:
    print()
    print("=" * 60)
    print(title)
    print("-" * 60)
    for line in text.splitlines():
        print(line)
    print("-" * 60)
    if short:
        print("Say the short phrase aloud, then press Enter when you are done.")
    else:
        print("Read the passage aloud, then press Enter when you are done.")
    _release_audio_for_capture()
    wav = record_until_enter(
        prompt="Listening… press Enter when done",
        max_record_seconds=max_seconds,
        require_speech=not short,
    )
    if short and not wav_has_min_speech(wav):
        raise ValueError("Too little audio — say the phrase again, then press Enter.")
    return wav


def _save_speaker_test_recording(wav: bytes, match, scored) -> None:
    """Save test clip + identification result under recordings/."""
    from stt import save_recording

    if match is not None:
        kind = f"speaker-test-{match.name}"
        lines = [f"Speaker: {match.display_name} ({match.score:.0%} confidence)"]
    elif scored:
        top = scored[0]
        kind = "speaker-test-unknown"
        lines = ["Speaker: unknown " f"(closest: {top.display_name} at {top.score:.0%}, need {top.threshold:.0%})"]
    else:
        kind = "speaker-test"
        lines = ["Speaker: unknown (could not score audio)"]

    if scored:
        lines.extend(["", "Scores:"])
        for row in scored:
            mark = "  ← match" if row.matched and row is scored[0] else ""
            mode = "short" if row.short_clip else "long"
            lines.append(f"  {row.display_name}: {row.score:.0%} " f"(need {row.threshold:.0%}, {mode}){mark}")

    path = save_recording(wav, kind=kind, transcript="\n".join(lines))
    print(f"Recording saved: {path}", flush=True)


def cmd_enroll(name: str | None, *, max_seconds: float, speak_prompts: bool) -> int:
    display = (name or "").strip()
    if not display:
        display = input("Your name (for speaker ID): ").strip()
    if not display:
        print("Enrollment cancelled — no name given.", file=sys.stderr)
        return 1

    slug = slug_name(display)
    print(f"\nEnrolling speaker profile for {display!r} ({slug}).")
    print("You will read three long passages and two short phrases. " "Use the same mic you use with Jarvis.")

    if speak_prompts:
        client = OpenAI()
        _speak_prompt(
            client,
            f"Let's enroll your voice, {display}. " "I'll ask you to read three passages and two short phrases.",
        )
    else:
        client = None

    try:
        samples: list[bytes] = []
        for idx, (title, text) in enumerate(ENROLLMENT_PASSAGES):
            short = idx >= LONG_PASSAGE_COUNT
            passage_max = min(max_seconds, 15.0) if short else max_seconds
            if speak_prompts and client is not None:
                hint = "Say the short phrase on screen" if short else "Read the text on screen"
                _speak_prompt(client, f"{title}. {hint}, then press Enter when done.")
            try:
                samples.append(
                    _record_passage(
                        title,
                        text,
                        max_seconds=passage_max,
                        short=short,
                    )
                )
            except Exception as e:
                print(f"\nEnrollment failed on {title}: {e}", file=sys.stderr)
                return 1

        try:
            root = enroll_speaker(display, samples)
        except Exception as e:
            print(f"\nCould not save speaker profile: {e}", file=sys.stderr)
            return 1

        print(f"\nSpeaker enrolled: {display}")
        print(f"Profile saved to {root}")
        print("Restart the orchestrator (or wait for the next utterance) to use speaker ID.")
        return 0
    finally:
        _release_audio_for_capture()


def cmd_list() -> int:
    profiles = list_profiles()
    if not profiles:
        print("No enrolled speakers. Run: cua speaker enroll --name YourName")
        return 0
    for p in profiles:
        slug = p.get("slug") or p.get("name")
        display = p.get("display_name") or slug
        when = (p.get("enrolled_at") or "")[:19]
        threshold = p.get("threshold")
        print(f"- {display} ({slug})  threshold={threshold}  enrolled={when}")
    return 0


def cmd_delete(name: str) -> int:
    if delete_profile(name):
        print(f"Deleted speaker profile for {name!r}.")
        return 0
    print(f"No profile found for {name!r}.", file=sys.stderr)
    return 1


def cmd_test(
    max_seconds: float = 15.0,
    *,
    verbose: bool = False,
    speak_prompts: bool = False,
) -> int:
    """Record one clip and identify the speaker."""
    from speaker_id import SPEAKER_ID_ENABLED, SPEAKER_ID_MODEL, _identify_wav_bytes, list_profiles

    if not SPEAKER_ID_ENABLED:
        print("Speaker ID is disabled (set SPEAKER_ID=1 in .env).", file=sys.stderr)
        return 1
    if not list_profiles():
        print("No enrolled speakers. Run: cua speaker enroll --name YourName", file=sys.stderr)
        return 1

    compatible = [
        p
        for p in list_profiles()
        if (p.get("backend") or "mfcc") == "speakeronnx" and (p.get("model") or "") == SPEAKER_ID_MODEL
    ]
    if not compatible:
        print(
            "Enrolled speaker profile(s) use an old embedding backend. "
            "Re-enroll everyone: cua speaker enroll --name YourName",
            file=sys.stderr,
        )
        return 1

    print(f"Speaker model: {SPEAKER_ID_MODEL}")

    print("Say a short sentence or phrase, then press Enter when you are done.")
    try:
        _release_audio_for_capture()
        wav = record_until_enter(
            prompt="Listening… press Enter when done",
            max_record_seconds=max_seconds,
            require_speech=False,
        )
        if not wav_has_min_speech(wav):
            print(
                "\nSpeaker test failed: too little audio — speak a bit more, then press Enter.",
                file=sys.stderr,
            )
            return 1
        match, scored = _identify_wav_bytes(wav)
    except Exception as e:
        print(f"\nSpeaker test failed: {e}", file=sys.stderr)
        return 1
    finally:
        _release_audio_for_capture()

    _save_speaker_test_recording(wav, match, scored)

    print()
    if match is not None:
        print(f"Speaker: {match.display_name} ({match.score:.0%} confidence)")
    elif scored:
        top = scored[0]
        mode = "short" if top.short_clip else "long"
        print(
            f"Speaker: unknown "
            f"(closest: {top.display_name} at {top.score:.0%}, "
            f"need {top.threshold:.0%}, {mode})"
        )
    else:
        print("Speaker: unknown (could not score audio)", file=sys.stderr)
        return 1

    if verbose and scored:
        print("\nScores:")
        for row in scored:
            mark = "  ← match" if row.matched and row is scored[0] else ""
            mode = "short" if row.short_clip else "long"
            print(f"  {row.display_name}: {row.score:.0%}  " f"(need {row.threshold:.0%}, {mode}){mark}")

    if speak_prompts:
        client = OpenAI()
        greeting = f"Hey {match.display_name}" if match is not None else "Hey Stranger"
        _speak_prompt(client, greeting)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enroll speakers for voice recognition")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll_p = sub.add_parser(
        "enroll",
        help="Record five passages (3 long + 2 short) to create a voice profile",
    )
    enroll_p.add_argument("--name", default=None, help="Display name (e.g. Bharat)")
    enroll_p.add_argument(
        "--max-seconds",
        type=float,
        default=45.0,
        help="Max recording length per passage",
    )
    enroll_p.add_argument(
        "--speak-prompts",
        action="store_true",
        help="Speak short instructions via TTS before each passage",
    )

    sub.add_parser("list", help="List enrolled speakers")
    delete_p = sub.add_parser("delete", help="Remove an enrolled speaker")
    delete_p.add_argument("name", help="Name or slug to delete")
    test_p = sub.add_parser(
        "test",
        help="Record once and identify who is speaking",
    )
    test_p.add_argument("--max-seconds", type=float, default=15.0)
    test_p.add_argument(
        "--verbose",
        action="store_true",
        help="Print similarity scores for every enrolled speaker",
    )

    test_p.add_argument(
        "--speak-prompts",
        action="store_true",
        help="After identification, speak Hey <name> or Hey Stranger via TTS",
    )

    args = parser.parse_args(argv)
    if args.command == "enroll":
        return cmd_enroll(args.name, max_seconds=args.max_seconds, speak_prompts=args.speak_prompts)
    if args.command == "list":
        return cmd_list()
    if args.command == "delete":
        return cmd_delete(args.name)
    if args.command == "test":
        return cmd_test(
            max_seconds=args.max_seconds,
            verbose=args.verbose,
            speak_prompts=args.speak_prompts,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
