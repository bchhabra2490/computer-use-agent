"""Single owner for wake, STT, TTS, and barge-in.

The capture implementations stay in ``wake.py`` / ``stt/`` / ``tts/``. This
session decides who has the mic and projects phase onto ``Session``.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from openai import OpenAI

from app_status import (
    consume_utterance,
    set_reply_sink,
    set_reply_tts,
    speak_pending,
    utterance_pending,
)
from bus import strip_wake_prefix
from session import Session, get_session
from stt import POST_TTS_COOLDOWN, ask_user, listen_for_utterance
from tts import speak, speak_later
from wake import (
    ensure_persistent_wake,
    format_wake_phrases,
    get_last_wake,
    get_wake_remainder,
    stop_persistent_wake,
    wait_for_wake,
)

MicOwner = str  # "none" | "wake" | "stt" | "tts"


class AudioSession:
    """Coordinate the audio devices for one orchestrator run."""

    def __init__(
        self,
        client: OpenAI,
        *,
        session: Session | None = None,
    ) -> None:
        self.client = client
        self.session = session
        self.mic_owner: MicOwner = "none"
        self.cooldown_s = POST_TTS_COOLDOWN

    def _phase(self, phase: str, detail: str = "", *, log: bool = False) -> None:
        sess = self.session if self.session is not None else get_session()
        if log and detail:
            sess.enter_and_log(phase, detail)
        else:
            sess.enter(phase, detail)

    def arm_wake(self) -> Any:
        self.mic_owner = "wake"
        return ensure_persistent_wake()

    def stop(self) -> None:
        try:
            stop_persistent_wake()
        finally:
            self.mic_owner = "none"

    def cooldown(self) -> None:
        time.sleep(self.cooldown_s)

    def wait_for_wake(
        self,
        *,
        should_stop: Callable[[], bool] | None = None,
        prompt: str | None = None,
    ) -> bool:
        self.mic_owner = "wake"
        self._phase("waiting", prompt or f"Waiting for {format_wake_phrases()}")
        return wait_for_wake(should_stop=should_stop, prompt=prompt)

    def listen(self, prompt: str | None = None) -> str:
        self.mic_owner = "stt"
        self._phase("listening", prompt or "Listening…")
        try:
            return listen_for_utterance(self.client, prompt=prompt)
        finally:
            self.mic_owner = "wake"

    def listen_after_barge(self, *, prompt: str = "Listening…") -> str | None:
        """Capture a command after TTS barge-in (no second wake)."""
        time.sleep(0.15)
        try:
            utterance = self.listen(prompt)
        except Exception as e:
            print(f"[audio] listen after barge-in failed: {e}")
            return None
        command = strip_wake_prefix(utterance).strip()
        if not command:
            print("[audio] barge-in heard but no command — listening again…")
            try:
                utterance = self.listen("Still listening…")
            except Exception as e:
                print(f"[audio] follow-up listen after barge-in failed: {e}")
                return None
            command = strip_wake_prefix(utterance).strip()
        return command or None

    def listen_command(
        self,
        *,
        should_stop: Callable[[], bool] | None = None,
        wake_prompt: str | None = None,
        listen_prompt: str | None = None,
        quit_check: Callable[[], bool] | None = None,
    ) -> str | None:
        """Wake word → one cloud STT utterance. Returns None if stopped or empty."""

        def _stop() -> bool:
            if utterance_pending():
                return True
            if speak_pending():
                return True
            if quit_check is not None:
                try:
                    if quit_check():
                        return True
                except Exception:
                    return True
            if should_stop is not None:
                try:
                    return bool(should_stop())
                except Exception:
                    return True
            return False

        queued = consume_utterance()
        if queued:
            try:
                from speaker_id import clear_last_speaker

                clear_last_speaker()
            except Exception:
                pass
            return queued

        if not self.wait_for_wake(should_stop=_stop, prompt=wake_prompt):
            return consume_utterance()
        if quit_check is not None and quit_check():
            return None
        hit = get_last_wake()
        heard = hit.label if hit else "Wake word"
        self._phase("listening", f"{heard} heard — listening", log=True)
        remainder = get_wake_remainder()
        if remainder:
            try:
                from speaker_id import clear_last_speaker

                clear_last_speaker()
            except Exception:
                pass
            set_reply_sink("mac")
            set_reply_tts(True)
            return strip_wake_prefix(remainder).strip() or remainder
        try:
            utterance = self.listen(listen_prompt or "Listening…")
        except Exception as e:
            from stt import ListenCancelled

            if isinstance(e, ListenCancelled):
                print("[audio] listen cancelled", flush=True)
            else:
                print(f"[audio] listen after wake failed: {e}")
            return None
        command = strip_wake_prefix(utterance).strip()
        if not command:
            print("[audio] wake heard but no command — listening again…")
            try:
                utterance = self.listen("Still listening for your command…")
                command = strip_wake_prefix(utterance).strip()
            except Exception as e:
                from stt import ListenCancelled

                if isinstance(e, ListenCancelled):
                    print("[audio] listen cancelled", flush=True)
                else:
                    print(f"[audio] follow-up listen failed: {e}")
                return None
        set_reply_sink("mac")
        set_reply_tts(True)
        return command or None

    def speak(self, text: str) -> str | None:
        """Speak ``text``. On barge-in, listen and return the new command."""
        if not text:
            return None
        self.mic_owner = "tts"
        self._phase("speaking", text[:100])
        interrupted = speak(self.client, text)
        if interrupted:
            self._phase("listening", "barge-in")
            return self.listen_after_barge()
        self.mic_owner = "wake"
        return None

    def speak_later(self, text: str) -> None:
        if not text:
            return
        self._phase("speaking", text[:100])
        speak_later(self.client, text)

    def ask(self, question: str) -> str:
        self.mic_owner = "stt"
        self._phase("ask", f"Agent asks: {question[:160]}", log=True)
        try:
            return ask_user(self.client, question)
        finally:
            self.mic_owner = "wake"


_active: AudioSession | None = None


def bind_audio(audio: AudioSession | None) -> AudioSession | None:
    global _active
    previous = _active
    _active = audio
    return previous


def get_audio() -> AudioSession | None:
    return _active
