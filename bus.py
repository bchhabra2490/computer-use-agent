"""
ZeroMQ message bus: orchestrator → computer agent (while agent is running).

PUSH (orchestrator) / PULL (agent). Agent drains non-blocking each turn.

AskUserBridge: agent thread → orchestrator main-thread RPC so ask_user uses
the orchestrator's TTS/STT (single mic owner) instead of competing for the mic.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
import uuid
from typing import Any

import zmq

# ipc is fine on macOS/Linux; override with AGENT_BUS_ENDPOINT=tcp://127.0.0.1:5557
DEFAULT_ENDPOINT = os.environ.get(
    "AGENT_BUS_ENDPOINT",
    "ipc:///tmp/computer-use-agent-bus.ipc",
)


class AgentMessagePublisher:
    """Orchestrator side: enqueue user directives for a running agent."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT):
        self.endpoint = endpoint
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUSH)
        self._sock.setsockopt(zmq.LINGER, 0)
        # Drop rather than block if agent isn't pulling yet.
        self._sock.setsockopt(zmq.SNDHWM, 100)
        try:
            self._sock.bind(endpoint)
        except zmq.ZMQError:
            # Re-bind after a prior unclean exit on the same ipc path.
            if endpoint.startswith("ipc://"):
                path = endpoint.removeprefix("ipc://")
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._sock.bind(endpoint)
            else:
                raise
        # Let PULL sockets connect before first send.
        time.sleep(0.05)

    def send(self, text: str, *, kind: str = "steer") -> None:
        text = (text or "").strip()
        if not text:
            return
        from input_queues import normalize_bus_kind

        payload = {
            "type": normalize_bus_kind(kind),
            "text": text,
            "ts": time.time(),
        }
        try:
            self._sock.send_json(payload, flags=zmq.NOBLOCK)
        except zmq.Again:
            print(f"[bus] queue full — dropped: {text!r}", file=sys.stderr)
            return
        print(f"[bus] queued → agent ({payload['type']}): {text!r}")

    def close(self) -> None:
        try:
            self._sock.close(0)
        except Exception:
            pass


class AgentMessageInbox:
    """Agent side: non-blocking drain of queued orchestrator messages."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT):
        self.endpoint = endpoint
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PULL)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.setsockopt(zmq.RCVHWM, 100)
        self._sock.connect(endpoint)
        time.sleep(0.05)

    def drain(self) -> list[str]:
        """Legacy: return steer + follow_up texts only (next_run excluded)."""
        from input_queues import DrainBatch

        batch = self.drain_batch()
        return batch.all_texts("steer", "follow_up")

    def drain_batch(self):
        """Drain typed messages into steer / follow_up / next_run buckets."""
        from input_queues import BUS_KINDS, DrainBatch, QueuedMessage, normalize_bus_kind
        from events import emit

        batch = DrainBatch()
        while True:
            try:
                raw: dict[str, Any] = self._sock.recv_json(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            if not isinstance(raw, dict):
                print(f"[bus] agent ← ignored non-dict payload: {raw!r}", file=sys.stderr)
                continue
            kind_raw = raw.get("type")
            if kind_raw not in BUS_KINDS and kind_raw is not None:
                print(f"[bus] agent ← ignored type={kind_raw!r}", file=sys.stderr)
                continue
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            kind = normalize_bus_kind(str(kind_raw) if kind_raw else "steer")
            msg = QueuedMessage.make(text, kind=kind)
            ts = raw.get("ts")
            age = f" age={time.time() - float(ts):.1f}s" if ts is not None else ""
            print(f"[bus] agent ← {kind}{age}: {text!r}", flush=True)
            emit("queue_consume", lane="agent", kind=kind, text=text[:160], id=msg.id)
            if kind == "steer":
                batch.steer.append(msg)
            elif kind == "follow_up":
                batch.follow_up.append(msg)
            else:
                batch.next_run.append(msg)
        total = len(batch.steer) + len(batch.follow_up) + len(batch.next_run)
        if total:
            print(
                f"[bus] agent drained {total} message(s) "
                f"(steer={len(batch.steer)} follow_up={len(batch.follow_up)} "
                f"next_run={len(batch.next_run)})",
                flush=True,
            )
        return batch

    def close(self) -> None:
        try:
            self._sock.close(0)
        except Exception:
            pass


class AskUserBridge:
    """
    Blocking ask_user from the agent worker thread to the orchestrator main thread.

    Agent calls ask(); orchestrator polls with poll() and completes with reply()
    while supervising (owns the mic for TTS + listen).
    """

    def __init__(self) -> None:
        self._requests: queue.Queue[dict[str, str]] = queue.Queue()
        self._lock = threading.Lock()
        self._waiters: dict[str, threading.Event] = {}
        self._answers: dict[str, str] = {}

    def ask(self, question: str, *, timeout: float = 180.0) -> str:
        """Called from the agent worker thread. Blocks until orchestrator replies."""
        question = (question or "").strip()
        if not question:
            return "Error: empty question"
        qid = uuid.uuid4().hex
        done = threading.Event()
        with self._lock:
            self._waiters[qid] = done
        self._requests.put({"id": qid, "question": question})
        print(f"[bus] agent asks via orchestrator: {question!r}")
        if not done.wait(timeout):
            with self._lock:
                self._waiters.pop(qid, None)
                self._answers.pop(qid, None)
            return "Error: timed out waiting for the user to answer."
        with self._lock:
            self._waiters.pop(qid, None)
            return self._answers.pop(qid, "").strip()

    def has_pending(self) -> bool:
        """True if the agent has queued an ask_user the orchestrator hasn't taken yet."""
        return not self._requests.empty()

    def poll(self, timeout: float = 0.0) -> dict[str, str] | None:
        """Called from the orchestrator. Returns {id, question} or None."""
        try:
            if timeout <= 0:
                return self._requests.get_nowait()
            return self._requests.get(timeout=timeout)
        except queue.Empty:
            return None

    def reply(self, request_id: str, answer: str) -> None:
        """Called from the orchestrator after speaking/listening."""
        with self._lock:
            self._answers[request_id] = (answer or "").strip()
            waiter = self._waiters.get(request_id)
        if waiter is not None:
            waiter.set()
        print(f"[bus] orchestrator answered ask_user ({request_id[:8]}…)")


def strip_wake_prefix(utterance: str) -> str:
    """
    Remove a leading wake phrase from a transcript if STT captured it.
    Uses configured WAKE_PHRASES (comma-separated), not a hard-coded Jarvis.
    """
    try:
        from wake import strip_wake_phrase

        return strip_wake_phrase(utterance)
    except Exception:
        # Fallback if wake module unavailable.
        text = (utterance or "").strip()
        if not text:
            return ""
        match = re.match(
            r"^(?:hey\s+)?jarvis\b[\s,:\-]*(.*)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return text
        return match.group(1).strip()


def extract_jarvis_command(utterance: str) -> str | None:
    """
    Return the command after a leading wake phrase, or None if absent.
    Kept for compatibility; prefers configured WAKE_PHRASE.
    """
    text = (utterance or "").strip()
    if not text:
        return None
    stripped = strip_wake_prefix(text)
    if stripped == text:
        # No wake prefix detected.
        try:
            from wake import matches_wake_phrase

            if matches_wake_phrase(text):
                return ""
        except Exception:
            pass
        return None
    return stripped
