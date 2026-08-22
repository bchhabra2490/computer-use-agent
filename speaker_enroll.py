"""Interactive speaker enrollment: read three passages, record, save voice profile."""

from __future__ import annotations

import argparse
import sys

from openai import OpenAI

from speaker_id import (
    ENROLLMENT_PASSAGES,
    delete_profile,
    enroll_speaker,
    list_profiles,
    slug_name,
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
    from tts import play_wav, synthesize

    print(f"[tts] {text}", flush=True)
    try:
        play_wav(synthesize(client, text))
    except Exception as e:
        print(f"[speaker] TTS skipped ({e})", flush=True)


def _record_passage(title: str, text: str, *, max_seconds: float) -> bytes:
    print()
    print("=" * 60)
    print(title)
    print("-" * 60)
    for line in text.splitlines():
        print(line)
    print("-" * 60)
    print("Read the passage aloud, then press Enter when you are done.")
    _release_audio_for_capture()
    wav = record_until_enter(
        prompt="Listening… press Enter when done",
        max_record_seconds=max_seconds,
        require_speech=True,
    )
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
        lines = [
            "Speaker: unknown "
            f"(closest: {top.display_name} at {top.score:.0%}, need {top.threshold:.0%})"
        ]
    else:
        kind = "speaker-test"
        lines = ["Speaker: unknown (could not score audio)"]

    if scored:
        lines.extend(["", "Scores:"])
        for row in scored:
            mark = "  ← match" if row.matched and row is scored[0] else ""
            lines.append(
                f"  {row.display_name}: {row.score:.0%} (need {row.threshold:.0%}){mark}"
            )

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
    print("You will read three short passages. Use the same mic you use with Jarvis.")

    if speak_prompts:
        client = OpenAI()
        _speak_prompt(
            client,
            f"Let's enroll your voice, {display}. I'll ask you to read three short passages.",
        )
    else:
        client = None

    try:
        samples: list[bytes] = []
        for title, text in ENROLLMENT_PASSAGES:
            if speak_prompts and client is not None:
                _speak_prompt(
                    client,
                    title.replace(" of 3", "")
                    + ". Read the text on screen, then press Enter when done.",
                )
            try:
                samples.append(_record_passage(title, text, max_seconds=max_seconds))
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


def cmd_test(max_seconds: float = 15.0, *, verbose: bool = False) -> int:
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
        if (p.get("backend") or "mfcc") == "speakeronnx"
        and (p.get("model") or "") == SPEAKER_ID_MODEL
    ]
    if not compatible:
        print(
            "Enrolled speaker profile(s) use an old embedding backend. "
            "Re-enroll everyone: cua speaker enroll --name YourName",
            file=sys.stderr,
        )
        return 1

    print(f"Speaker model: {SPEAKER_ID_MODEL}")

    print("Say a short sentence, then press Enter when you are done.")
    try:
        _release_audio_for_capture()
        wav = record_until_enter(
            prompt="Listening… press Enter when done",
            max_record_seconds=max_seconds,
            require_speech=True,
        )
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
        print(
            f"Speaker: unknown "
            f"(closest: {top.display_name} at {top.score:.0%}, "
            f"need {top.threshold:.0%})"
        )
    else:
        print("Speaker: unknown (could not score audio)", file=sys.stderr)
        return 1

    if verbose and scored:
        print("\nScores:")
        for row in scored:
            mark = "  ← match" if row.matched and row is scored[0] else ""
            print(
                f"  {row.display_name}: {row.score:.0%}  "
                f"(need {row.threshold:.0%}){mark}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enroll speakers for voice recognition")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll_p = sub.add_parser("enroll", help="Record three passages and save a voice profile")
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

    args = parser.parse_args(argv)
    if args.command == "enroll":
        return cmd_enroll(args.name, max_seconds=args.max_seconds, speak_prompts=args.speak_prompts)
    if args.command == "list":
        return cmd_list()
    if args.command == "delete":
        return cmd_delete(args.name)
    if args.command == "test":
        return cmd_test(max_seconds=args.max_seconds, verbose=args.verbose)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
