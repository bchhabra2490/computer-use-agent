"""Accuracy-first fast lanes for simple smart-home (and similar) commands.

Lane A — deterministic parse against the live hardware catalog (no LLM).
Lane B — local Ollama tool-caller with a tiny tool set; args must validate.
Lane C — caller falls through to the cloud orchestrator.

Any ambiguity, extra intent, offline device, or failed validation → no match.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

FASTLANE = os.environ.get("FASTLANE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
FASTLANE_LOCAL = os.environ.get("FASTLANE_LOCAL", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
FASTLANE_MODEL = os.environ.get("FASTLANE_MODEL", "qwen3:8b").strip() or "qwen3:8b"
FASTLANE_OLLAMA_URL = (
    os.environ.get("FASTLANE_OLLAMA_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    or "http://127.0.0.1:11434"
)
FASTLANE_LOCAL_TIMEOUT = float(os.environ.get("FASTLANE_LOCAL_TIMEOUT", "8"))
FASTLANE_CATALOG_TTL = float(os.environ.get("FASTLANE_CATALOG_TTL", "10"))

# Force cloud when the utterance looks like more than a single on/off.
_COMPLEX = re.compile(
    r"\b("
    r"why|how|which|what|when|where|status|state|online|offline|"
    r"dim|bright|brightness|color|colour|scene|schedule|timer|"
    r"remind|after|minutes?|seconds?|hours?|"
    r"all|every|both|and then|also|plus|except|instead|"
    r"if |unless|while|during|check|verify|confirm|"
    r"open|close|play|pause|search|browser|chrome|maps|"
    r"whatsapp|instagram|youtube|email|message"
    r")\b",
    re.I,
)
_ACTION = re.compile(
    r"\b(?P<verb>turn|switch|power|set|put)\s+(?P<action>on|off)\b|"
    r"\b(?P<action2>on|off)\b",
    re.I,
)
_SMART_HINT = re.compile(
    r"\b(lamp|light|lights|fan|bulb|relay|switch|office|board|hardware|device)\b",
    re.I,
)
_STRIP = re.compile(
    r"\b("
    r"hey\s+jarvis|hey\s+rekha|please|can you|could you|would you|"
    r"now|right now|for me|the|a|an|my|our"
    r")\b",
    re.I,
)

ExecuteFn = Callable[[str, str, dict[str, Any]], str]
CatalogFn = Callable[[], list[dict[str, Any]]]


@dataclass(frozen=True)
class DeviceRef:
    node: str
    component: str
    aliases: tuple[str, ...]
    online: bool
    actions: tuple[str, ...]


@dataclass(frozen=True)
class FastHit:
    lane: str  # "A" | "B"
    node: str
    component: str
    action: str
    spoken: str
    detail: str = ""


_catalog_cache: tuple[float, list[DeviceRef]] | None = None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _alias_tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for part in parts:
        raw = _norm(part)
        if not raw:
            continue
        out.add(raw)
        out.add(re.sub(r"[^a-z0-9]+", " ", raw).strip())
        words = [w for w in re.split(r"[^a-z0-9]+", raw) if w]
        if words:
            out.add(" ".join(words))
        if len(words) >= 2:
            out.add(words[-1])  # "office lamp" → also "lamp"
    out.discard("")
    return out


def parse_devices_payload(raw: str | dict | list) -> list[DeviceRef]:
    """Build DeviceRef list from hardware list_devices JSON."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        data = raw
    if isinstance(data, dict) and data.get("ok") is False:
        return []
    nodes = []
    if isinstance(data, dict):
        nodes = data.get("nodes") or []
    elif isinstance(data, list):
        nodes = data
    devices: list[DeviceRef] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node") or node.get("id") or "").strip()
        if not node_id:
            continue
        node_name = str(node.get("name") or "").strip()
        online = bool(node.get("online"))
        comps = node.get("components") or {}
        if isinstance(comps, list):
            comp_iter = [
                (str(c.get("id") or ""), c) for c in comps if isinstance(c, dict)
            ]
        elif isinstance(comps, dict):
            comp_iter = [(str(k), v) for k, v in comps.items()]
        else:
            continue
        for cid, comp in comp_iter:
            if isinstance(comp, dict):
                comp_id = str(comp.get("id") or cid).strip()
                actions = tuple(
                    str(a).strip().lower()
                    for a in (comp.get("actions") or ["on", "off"])
                    if str(a).strip()
                )
            else:
                comp_id = str(cid).strip()
                actions = ("on", "off")
            if not comp_id:
                continue
            aliases = _alias_tokens(
                comp_id,
                f"{node_id} {comp_id}",
                f"{node_name} {comp_id}" if node_name else "",
                f"{node_id} {comp_id}".replace("_", " "),
                # Common spoken forms
                f"{node_id} lamp" if comp_id == "lamp" else "",
                f"{node_id} light" if comp_id in {"lamp", "light"} else "",
                f"{node_name} lamp" if node_name and comp_id == "lamp" else "",
                f"{node_name} light" if node_name and comp_id in {"lamp", "light"} else "",
                "office lamp" if node_id == "office" and comp_id == "lamp" else "",
                "office light" if node_id == "office" and comp_id == "lamp" else "",
            )
            # Optional env aliases: office_lamp=office:lamp
            extra = os.environ.get("FASTLANE_ALIASES", "")
            for piece in extra.split(","):
                piece = piece.strip()
                if not piece or "=" not in piece:
                    continue
                alias, target = piece.split("=", 1)
                target = target.strip().lower()
                if target in {f"{node_id}:{comp_id}", f"{node_id}/{comp_id}"}:
                    aliases |= _alias_tokens(alias)
            devices.append(
                DeviceRef(
                    node=node_id,
                    component=comp_id,
                    aliases=tuple(sorted(aliases)),
                    online=online,
                    actions=actions or ("on", "off"),
                )
            )
    return devices


def load_catalog(fetch: CatalogFn | None = None) -> list[DeviceRef]:
    global _catalog_cache
    now = time.monotonic()
    if _catalog_cache and now - _catalog_cache[0] < FASTLANE_CATALOG_TTL:
        return list(_catalog_cache[1])
    if fetch is None:
        from tools_registry import run_shared_tool

        def fetch() -> list[dict[str, Any]]:
            raw = run_shared_tool(
                "mcp_call",
                {"server": "hardware", "tool": "list_devices", "arguments": {}},
            )
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return []
            if isinstance(data, dict):
                return list(data.get("nodes") or [])
            return []

    try:
        nodes = fetch()
        devices = parse_devices_payload({"ok": True, "nodes": nodes})
    except Exception as e:
        print(f"[fastlane] catalog failed: {e}", flush=True)
        devices = []
    _catalog_cache = (now, devices)
    return list(devices)


def clear_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


def looks_complex(utterance: str) -> bool:
    return bool(_COMPLEX.search(utterance or ""))


def looks_smart_home(utterance: str) -> bool:
    return bool(_SMART_HINT.search(utterance or ""))


def _extract_action(utterance: str) -> str | None:
    text = _norm(utterance)
    # Prefer explicit "turn/switch … on/off"
    m = re.search(
        r"\b(?:turn|switch|power|set|put)\s+(?:the\s+)?(?:\S+\s+){0,4}?(on|off)\b",
        text,
    )
    if m:
        return m.group(1)
    m = re.search(r"\b(?:turn|switch|power)\s+(on|off)\b", text)
    if m:
        return m.group(1)
    # "office lamp off" / "lamp on"
    m = re.search(r"\b(on|off)\s*$", text)
    if m and re.search(r"\b(turn|switch|power|set|put|lamp|light|fan)\b", text):
        return m.group(1)
    return None


def _device_mention_span(utterance: str, action: str) -> str:
    text = _norm(utterance)
    text = _STRIP.sub(" ", text)
    text = re.sub(rf"\b(?:turn|switch|power|set|put)\s+{action}\b", " ", text)
    text = re.sub(rf"\b{action}\b", " ", text)
    return _norm(text)


def match_lane_a(utterance: str, devices: list[DeviceRef]) -> FastHit | None:
    """Deterministic unique (device, action) only — else None."""
    if not FASTLANE or not utterance or not devices:
        return None
    if looks_complex(utterance):
        return None
    action = _extract_action(utterance)
    if action not in {"on", "off"}:
        return None
    mention = _device_mention_span(utterance, action)
    if not mention:
        return None

    hits: list[DeviceRef] = []
    for dev in devices:
        if action not in dev.actions:
            continue
        for alias in dev.aliases:
            if not alias:
                continue
            # Alias must appear as a whole phrase in the mention.
            if re.search(rf"(?:^|\b){re.escape(alias)}(?:\b|$)", mention):
                hits.append(dev)
                break

    # Deduplicate by node/component
    uniq: dict[tuple[str, str], DeviceRef] = {}
    for h in hits:
        uniq[(h.node, h.component)] = h
    if len(uniq) != 1:
        return None
    dev = next(iter(uniq.values()))
    if not dev.online:
        # Accuracy: don't guess / don't silently fail — cloud can explain offline.
        return None
    spoken = f"OK — {dev.node} {dev.component} {action}."
    return FastHit(
        lane="A",
        node=dev.node,
        component=dev.component,
        action=action,
        spoken=spoken,
        detail="deterministic",
    )


def _ollama_chat(messages: list[dict], tools: list[dict]) -> dict[str, Any] | None:
    payload = {
        "model": FASTLANE_MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 128},
        "think": False,
    }
    req = urllib.request.Request(
        f"{FASTLANE_OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=FASTLANE_LOCAL_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"[fastlane] local model error: {e}", flush=True)
        return None


def _hardware_tools_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "control_hardware",
                "description": (
                    "Turn a known hardware component on or off. "
                    "Only use when the user clearly wants that single action."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node": {"type": "string"},
                        "component": {"type": "string"},
                        "action": {"type": "string", "enum": ["on", "off"]},
                    },
                    "required": ["node", "component", "action"],
                },
            },
        }
    ]


def match_lane_b(utterance: str, devices: list[DeviceRef]) -> FastHit | None:
    """Local tool-caller; only accept one validated control_hardware call."""
    if not FASTLANE or not FASTLANE_LOCAL or not utterance:
        return None
    if looks_complex(utterance):
        return None
    if not looks_smart_home(utterance):
        return None
    online = [d for d in devices if d.online]
    if not online:
        return None

    catalog_lines = [
        f"- node={d.node!r} component={d.component!r} aliases={list(d.aliases)[:6]}"
        for d in online
    ]
    system = (
        "You control home hardware. Call control_hardware for a clear on/off request. "
        "Use ONLY nodes/components from the catalog. If unsure, ambiguous, multiple "
        "devices, or not a hardware command, reply with exactly: UNSURE\n\n"
        "Catalog:\n" + "\n".join(catalog_lines)
    )
    raw = _ollama_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": utterance.strip()},
        ],
        _hardware_tools_schema(),
    )
    if not raw:
        return None
    msg = raw.get("message") or {}
    content = str(msg.get("content") or "").strip()
    if content.upper().startswith("UNSURE"):
        return None
    tool_calls = msg.get("tool_calls") or []
    if len(tool_calls) != 1:
        # Accuracy: refuse free-form answers and multi-tool dumps.
        return None
    call = tool_calls[0]
    fn = call.get("function") if isinstance(call, dict) else None
    if not isinstance(fn, dict) or fn.get("name") != "control_hardware":
        return None
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None
    if not isinstance(args, dict):
        return None
    node = str(args.get("node") or "").strip()
    component = str(args.get("component") or "").strip()
    action = str(args.get("action") or "").strip().lower()
    if action not in {"on", "off"} or not node or not component:
        return None
    match = next(
        (d for d in online if d.node == node and d.component == component),
        None,
    )
    if match is None or action not in match.actions:
        return None
    return FastHit(
        lane="B",
        node=node,
        component=component,
        action=action,
        spoken=f"OK — {node} {component} {action}.",
        detail=f"local:{FASTLANE_MODEL}",
    )


def execute_hit(hit: FastHit, *, execute: ExecuteFn | None = None) -> tuple[bool, str]:
    """Run control_hardware; return (ok, message_for_user)."""
    if execute is None:
        from tools_registry import run_shared_tool

        def execute(server: str, tool: str, arguments: dict[str, Any]) -> str:
            return run_shared_tool(
                "mcp_call",
                {"server": server, "tool": tool, "arguments": arguments},
            )

    raw = execute(
        "hardware",
        "control_hardware",
        {"node": hit.node, "component": hit.component, "action": hit.action},
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False, "The hardware controller returned an invalid response."
    if not isinstance(data, dict):
        return False, "The hardware controller returned an invalid response."
    if data.get("ok"):
        state = str(data.get("state") or hit.action).strip() or hit.action
        return True, f"Done — {hit.node} {hit.component} is {state}."
    err = str(data.get("message") or data.get("error") or "command failed").strip()
    return False, f"Could not change {hit.node} {hit.component}: {err}"


def try_fastlane(
    utterance: str,
    *,
    catalog_fetch: CatalogFn | None = None,
    execute: ExecuteFn | None = None,
    allow_local: bool = True,
) -> FastHit | None:
    """
    Attempt Lane A, then Lane B. Returns a hit ready to execute, or None → cloud.

    Does not execute; caller runs execute_hit so it can speak / log.
    """
    if not FASTLANE:
        return None
    text = (utterance or "").strip()
    if not text or looks_complex(text):
        return None
    devices = load_catalog(catalog_fetch)
    if not devices:
        return None
    hit = match_lane_a(text, devices)
    if hit is not None:
        return hit
    if allow_local and FASTLANE_LOCAL:
        return match_lane_b(text, devices)
    return None


def warmup_local() -> None:
    """Load the local model into memory (best-effort)."""
    if not FASTLANE or not FASTLANE_LOCAL:
        return
    try:
        _ollama_chat(
            [{"role": "user", "content": "ping"}],
            [],
        )
        print(f"[fastlane] warmed {FASTLANE_MODEL}", flush=True)
    except Exception as e:
        print(f"[fastlane] warmup skipped: {e}", flush=True)
