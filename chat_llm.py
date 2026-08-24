"""Desktop chat: OpenAI / DeepSeek replies, optional screenshot on each send."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any

from chat_store import PREF_SELECTED_MODEL, get_store

CHAT_SYSTEM = (
    "You are a desktop assistant on the user's Mac. "
    "If a screenshot is attached, use it to answer what is on screen. "
    "Be concise. Do not claim you clicked or typed unless you actually did "
    "(you cannot control the computer from this chat)."
)

HISTORY_KEEP = int(os.environ.get("CHAT_HISTORY_KEEP", "40"))

DEEPSEEK_BASE_URL = (
    os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
).strip() or "https://api.deepseek.com"

# Legacy env aliases still honored for defaults / extras.
_DEFAULT_OPENAI = (
    os.environ.get("CHAT_MODEL") or os.environ.get("ORCHESTRATOR_MODEL") or "gpt-4o-mini"
).strip() or "gpt-4o-mini"
_DEFAULT_DEEPSEEK = (
    os.environ.get("CHAT_DEEPSEEK_MODEL")
    or os.environ.get("AGENT_DEEPSEEK_MODEL")
    or "deepseek-v4-pro"
).strip() or "deepseek-v4-pro"
_DEEPSEEK_VISION = (
    os.environ.get("CHAT_DEEPSEEK_VISION_MODEL") or "deepseek-v4-flash-vision-exp"
).strip() or "deepseek-v4-flash-vision-exp"


@dataclass(frozen=True)
class ChatModelInfo:
    """One selectable model in the chat UI."""

    id: str  # stable key, e.g. openai:gpt-4o-mini
    label: str
    provider: str  # openai | deepseek
    model: str  # API model name
    vision: bool = False


def _builtin_models() -> list[ChatModelInfo]:
    models = [
        ChatModelInfo(
            id=f"openai:{_DEFAULT_OPENAI}",
            label=f"OpenAI · {_DEFAULT_OPENAI}",
            provider="openai",
            model=_DEFAULT_OPENAI,
            vision=True,
        ),
        ChatModelInfo(
            id="openai:gpt-4o",
            label="OpenAI · gpt-4o",
            provider="openai",
            model="gpt-4o",
            vision=True,
        ),
        ChatModelInfo(
            id=f"deepseek:{_DEFAULT_DEEPSEEK}",
            label=f"DeepSeek · {_DEFAULT_DEEPSEEK}",
            provider="deepseek",
            model=_DEFAULT_DEEPSEEK,
            vision=False,
        ),
        ChatModelInfo(
            id="deepseek:deepseek-v4-flash",
            label="DeepSeek · deepseek-v4-flash",
            provider="deepseek",
            model="deepseek-v4-flash",
            vision=False,
        ),
        ChatModelInfo(
            id=f"deepseek:{_DEEPSEEK_VISION}",
            label=f"DeepSeek · {_DEEPSEEK_VISION}",
            provider="deepseek",
            model=_DEEPSEEK_VISION,
            vision=True,
        ),
    ]
    # De-dupe if CHAT_MODEL already is gpt-4o
    seen: set[str] = set()
    out: list[ChatModelInfo] = []
    for m in models:
        if m.id in seen:
            continue
        seen.add(m.id)
        out.append(m)
    return out


def _extra_models_from_env() -> list[ChatModelInfo]:
    """``CHAT_MODELS=openai:gpt-4.1,deepseek:custom-id``."""
    raw = (os.environ.get("CHAT_MODELS") or "").strip()
    if not raw:
        return []
    extras: list[ChatModelInfo] = []
    for part in raw.split(","):
        token = part.strip()
        if not token or ":" not in token:
            continue
        provider, model = token.split(":", 1)
        provider = provider.strip().lower()
        model = model.strip()
        if provider not in {"openai", "deepseek"} or not model:
            continue
        mid = f"{provider}:{model}"
        vision = provider == "openai" or "vision" in model.lower()
        extras.append(
            ChatModelInfo(
                id=mid,
                label=f"{provider.title()} · {model}",
                provider=provider,
                model=model,
                vision=vision,
            )
        )
    return extras


def list_chat_models() -> list[ChatModelInfo]:
    seen: set[str] = set()
    out: list[ChatModelInfo] = []
    for m in _builtin_models() + _extra_models_from_env():
        if m.id in seen:
            continue
        seen.add(m.id)
        out.append(m)
    return out


def get_model(model_id: str | None) -> ChatModelInfo:
    models = list_chat_models()
    by_id = {m.id: m for m in models}
    if model_id and model_id in by_id:
        return by_id[model_id]
    key = (model_id or "").strip().lower()
    if key in {"ds", "deepseek"} or (
        key.startswith("deepseek") and ":" not in key and key != "deepseek"
    ):
        # Bare provider / legacy backend name
        for m in models:
            if m.provider == "deepseek" and not m.vision:
                return m
        for m in models:
            if m.provider == "deepseek":
                return m
    if key in {"openai", "oai"}:
        for m in models:
            if m.provider == "openai":
                return m
    # Match by API model name alone (e.g. gpt-4o-mini)
    for m in models:
        if m.model == model_id or m.id.endswith(f":{model_id}"):
            return m
    # Legacy CHAT_BACKEND default
    backend = (os.environ.get("CHAT_BACKEND") or "").strip().lower()
    if backend in {"ds", "deepseek"}:
        for m in models:
            if m.provider == "deepseek" and not m.vision:
                return m
        for m in models:
            if m.provider == "deepseek":
                return m
    return models[0]


def selected_model_id() -> str:
    stored = get_store().get_pref(PREF_SELECTED_MODEL)
    return get_model(stored).id


def set_selected_model_id(model_id: str) -> ChatModelInfo:
    info = get_model(model_id)
    get_store().set_pref(PREF_SELECTED_MODEL, info.id)
    return info


def api_model_name(info: ChatModelInfo, *, has_image: bool) -> str:
    """API model for this send; DeepSeek text models auto-upgrade for images."""
    if has_image and not info.vision and info.provider == "deepseek":
        return _DEEPSEEK_VISION
    return info.model


def make_chat_client(provider: str | None = None) -> Any:
    from openai import OpenAI

    key_provider = (provider or "openai").strip().lower()
    if key_provider == "deepseek":
        key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
    return OpenAI()


# --- Back-compat helpers (tests / older call sites) ---

CHAT_MODEL = _DEFAULT_OPENAI
CHAT_BACKEND = (os.environ.get("CHAT_BACKEND") or "openai").strip().lower()
CHAT_DEEPSEEK_MODEL = _DEFAULT_DEEPSEEK
CHAT_DEEPSEEK_VISION_MODEL = _DEEPSEEK_VISION


def chat_backend(name: str | None = None) -> str:
    key = (name if name is not None else CHAT_BACKEND).strip().lower()
    if key in {"ds", "deepseek"}:
        return "deepseek"
    if name and ":" in name:
        return name.split(":", 1)[0].strip().lower()
    info = get_model(name)
    return info.provider


def chat_model(backend: str | None = None, *, has_image: bool = False) -> str:
    if backend and ":" in backend:
        info = get_model(backend)
        return api_model_name(info, has_image=has_image)
    info = get_model(
        f"deepseek:{_DEFAULT_DEEPSEEK}"
        if chat_backend(backend) == "deepseek"
        else f"openai:{_DEFAULT_OPENAI}"
    )
    return api_model_name(info, has_image=has_image)


@dataclass
class ChatTurn:
    role: str  # user | assistant
    text: str
    screenshot: bool = False
    screenshot_relpath: str | None = None


@dataclass
class ChatSession:
    turns: list[ChatTurn] = field(default_factory=list)

    def add(
        self,
        role: str,
        text: str,
        *,
        screenshot: bool = False,
        screenshot_relpath: str | None = None,
    ) -> None:
        self.turns.append(
            ChatTurn(
                role=role,
                text=text,
                screenshot=screenshot or bool(screenshot_relpath),
                screenshot_relpath=screenshot_relpath,
            )
        )
        if len(self.turns) > HISTORY_KEEP:
            self.turns = self.turns[-HISTORY_KEEP:]

    def clear(self) -> None:
        self.turns.clear()

    @classmethod
    def from_messages(cls, messages: list[Any]) -> ChatSession:
        session = cls()
        for msg in messages:
            role = getattr(msg, "role", None) or msg.get("role")  # type: ignore[union-attr]
            content = getattr(msg, "content", None) or msg.get("content")  # type: ignore[union-attr]
            rel = getattr(msg, "screenshot_relpath", None)
            if rel is None and isinstance(msg, dict):
                rel = msg.get("screenshot_relpath")
            if role not in {"user", "assistant"}:
                continue
            session.add(str(role), str(content or ""), screenshot_relpath=rel)
        return session


def user_content(text: str, screenshot_png: bytes | None) -> Any:
    """Responses API user content (text, optional PNG)."""
    note = (text or "").strip() or "(no text)"
    if not screenshot_png:
        return note
    b64 = base64.b64encode(screenshot_png).decode("ascii")
    return [
        {
            "type": "input_text",
            "text": note + "\n\nA screenshot of the Mac display(s) is attached.",
        },
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{b64}",
            "detail": "high",
        },
    ]


def session_input(
    session: ChatSession, user_text: str, screenshot_png: bytes | None
) -> list[dict[str, Any]]:
    """Full Responses API ``input`` for this send (history + new user turn)."""
    items: list[dict[str, Any]] = [{"role": "system", "content": CHAT_SYSTEM}]
    for turn in session.turns:
        if turn.role == "user":
            note = turn.text
            if turn.screenshot:
                note = f"{note}\n\n(screenshot was attached to this earlier message)"
            items.append({"role": "user", "content": note})
        else:
            items.append({"role": "assistant", "content": turn.text})
    items.append({"role": "user", "content": user_content(user_text, screenshot_png)})
    return items


def extract_output_text(response: Any) -> str:
    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                text = (getattr(part, "text", None) or "").strip()
                if text:
                    parts.append(text)
    if parts:
        return "\n".join(parts).strip()
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()
    return ""


def complete_chat(
    client: Any,
    session: ChatSession,
    user_text: str,
    screenshot_png: bytes | None,
    *,
    backend: str | None = None,
    model_id: str | None = None,
) -> str:
    """Call the selected model and append both turns to ``session``."""
    info = get_model(model_id or backend)
    model = api_model_name(info, has_image=bool(screenshot_png))
    payload = session_input(session, user_text, screenshot_png)
    response = client.responses.create(model=model, input=payload)
    reply = extract_output_text(response) or "(empty reply)"
    session.add("user", user_text.strip() or "(no text)", screenshot=bool(screenshot_png))
    session.add("assistant", reply)
    return reply


def capture_desktop_png() -> bytes:
    """Screenshot with overlays hidden (log, face, chat)."""
    from actions import DesktopController
    from log_overlay import pause_overlay_for_capture

    with pause_overlay_for_capture():
        return DesktopController().capture_screenshot()


def title_from_text(text: str, fallback: str = "New chat") -> str:
    line = (text or "").strip().replace("\n", " ")
    if not line:
        return fallback
    if len(line) > 48:
        return line[:45].rstrip() + "…"
    return line


def _clean_title(raw: str, fallback: str = "New chat") -> str:
    line = (raw or "").strip().replace("\n", " ")
    # Models sometimes wrap titles in quotes.
    if len(line) >= 2 and line[0] == line[-1] and line[0] in "\"'“”":
        line = line[1:-1].strip()
    line = line.lstrip("# ").strip()
    if not line:
        return fallback
    if len(line) > 60:
        return line[:57].rstrip() + "…"
    return line


def generate_chat_title(
    client: Any,
    *,
    model_id: str | None,
    user_text: str,
    assistant_text: str = "",
) -> str:
    """Ask the selected model for a short sidebar title; fall back to truncating user text."""
    fallback = title_from_text(user_text)
    info = get_model(model_id)
    # Title is text-only — don't upgrade to vision / attach images.
    model = info.model
    user_snip = (user_text or "").strip()[:500] or "(screenshot only)"
    asst_snip = (assistant_text or "").strip()[:400]
    prompt = (
        "Write a short chat title (3–7 words) for this conversation. "
        "No quotes, no punctuation at the end, no emoji. "
        "Return only the title.\n\n"
        f"User: {user_snip}\n"
    )
    if asst_snip:
        prompt += f"Assistant: {asst_snip}\n"
    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "You name chats. Reply with only a concise title.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return _clean_title(extract_output_text(response), fallback)
    except Exception:
        return fallback
