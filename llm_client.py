"""OpenAI-compatible LLM clients for orchestrator / agent reasoning.

``OpenAI()`` stays the default. DeepSeek uses the same SDK against
``DEEPSEEK_BASE_URL`` (Responses API + function tools).

STT/TTS keep their own clients — do not point the audio ``OpenAI()`` at DeepSeek.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

DEEPSEEK_BASE_URL = (
    os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
).strip() or "https://api.deepseek.com"
DEEPSEEK_VISION_DEFAULT = (
    os.environ.get("DEEPSEEK_VISION_MODEL")
    or os.environ.get("ORCHESTRATOR_VISION_MODEL")
    or "deepseek-v4-flash-vision-exp"
).strip() or "deepseek-v4-flash-vision-exp"


def _norm_provider(raw: str | None) -> str | None:
    key = (raw or "").strip().lower()
    if key in {"", "auto", "default"}:
        return None
    if key in {"ds", "deepseek"}:
        return "deepseek"
    if key in {"openai", "oa"}:
        return "openai"
    return key


def provider_for_model(
    model: str | None,
    *,
    explicit: str | None = None,
) -> str:
    """``openai`` or ``deepseek``. Explicit env wins; else infer from the model id."""
    forced = _norm_provider(explicit)
    if forced in {"openai", "deepseek"}:
        return forced
    name = (model or "").strip().lower()
    if name.startswith("deepseek") or "deepseek" in name:
        return "deepseek"
    return "openai"


def orchestrator_provider() -> str:
    return provider_for_model(
        os.environ.get("ORCHESTRATOR_MODEL", "gpt-5-mini"),
        explicit=os.environ.get("ORCHESTRATOR_BACKEND"),
    )


def agent_provider(model: str | None = None) -> str:
    return provider_for_model(
        model or os.environ.get("AGENT_MODEL") or os.environ.get("AGENT_MODEL_HARD"),
        explicit=os.environ.get("AGENT_BACKEND"),
    )


def vision_model(model: str | None, *, provider: str | None = None) -> str:
    """Model id to use when the request includes an image."""
    name = (model or "").strip() or "gpt-4o-mini"
    kind = provider_for_model(name, explicit=provider)
    if kind != "deepseek":
        return name
    env = (
        os.environ.get("ORCHESTRATOR_VISION_MODEL")
        or os.environ.get("AGENT_VISION_MODEL")
        or os.environ.get("DEEPSEEK_VISION_MODEL")
        or ""
    ).strip()
    if env:
        return env
    if "vision" in name.lower():
        return name
    return DEEPSEEK_VISION_DEFAULT


def input_has_image(payload: Any) -> bool:
    """True if a Responses ``input`` tree contains an ``input_image`` part."""
    if payload is None:
        return False
    if isinstance(payload, dict):
        if str(payload.get("type") or "") == "input_image":
            return True
        if payload.get("image_url"):
            t = str(payload.get("type") or "")
            if t in {"input_image", "image_url", ""}:
                url = payload.get("image_url")
                if isinstance(url, str) and url.startswith("data:image"):
                    return True
        return any(input_has_image(v) for v in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(input_has_image(item) for item in payload)
    return False


def model_for_request(
    model: str | None,
    *,
    has_image: bool = False,
    provider: str | None = None,
) -> str:
    name = (model or "").strip() or "gpt-5-mini"
    if has_image:
        return vision_model(name, provider=provider)
    return name


def supports_previous_response_id(
    model: str | None = None,
    *,
    provider: str | None = None,
) -> bool:
    """DeepSeek Responses is stateless and ignores ``previous_response_id``."""
    return provider_for_model(model, explicit=provider) != "deepseek"


def function_call_input_items(response: Any) -> list[dict[str, Any]]:
    """Replay ``function_call`` items so a stateless API can pair tool outputs."""
    items: list[dict[str, Any]] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        items.append(
            {
                "type": "function_call",
                "call_id": (
                    getattr(item, "call_id", None)
                    or getattr(item, "id", None)
                    or ""
                ),
                "name": getattr(item, "name", "") or "",
                "arguments": getattr(item, "arguments", None) or "",
            }
        )
    return items


def merge_tool_followup_input(response: Any, extra: Any) -> list[Any]:
    """``function_call`` items immediately followed by their outputs (DeepSeek)."""
    calls = function_call_input_items(response)
    if extra is None:
        return calls
    if isinstance(extra, dict):
        extras: list[Any] = [extra]
    elif isinstance(extra, list):
        extras = list(extra)
    else:
        extras = [{"role": "user", "content": str(extra)}]

    outputs = [
        e
        for e in extras
        if isinstance(e, dict) and e.get("type") == "function_call_output"
    ]
    other = [
        e
        for e in extras
        if not (isinstance(e, dict) and e.get("type") == "function_call_output")
    ]
    # Streaming sometimes leaves empty call_id on function_call items while the
    # tool runner stored call_00_… on the output — align by order.
    aligned_outs: list[dict[str, Any]] = []
    for i, out in enumerate(outputs):
        if i < len(calls):
            cid = (calls[i].get("call_id") or out.get("call_id") or "").strip()
            if cid:
                calls[i]["call_id"] = cid
                out = {**out, "call_id": cid}
        aligned_outs.append(out)
    return [*calls, *aligned_outs, *other]


def _item_type(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("type") or "")
    return str(getattr(item, "type", "") or "")


def _item_call_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("call_id") or "")
    return str(getattr(item, "call_id", "") or "")


def _item_output_text(item: Any) -> str:
    if isinstance(item, dict):
        out = item.get("output")
    else:
        out = getattr(item, "output", None)
    if out is None:
        return ""
    if isinstance(out, str):
        return out
    return str(out)


def fold_orphan_tool_outputs(payload: Any) -> Any:
    """DeepSeek rejects ``function_call_output`` without a matching ``function_call``.

    Leftover outputs from a prior OpenAI-style ``previous_response_id`` turn are
    folded into the user message as plain text.
    """
    if not isinstance(payload, list):
        return payload
    call_ids = {
        _item_call_id(item)
        for item in payload
        if _item_type(item) == "function_call" and _item_call_id(item)
    }
    kept: list[Any] = []
    orphan_bits: list[str] = []
    for item in payload:
        if _item_type(item) == "function_call_output":
            cid = _item_call_id(item)
            if cid and cid not in call_ids:
                text = _item_output_text(item).strip()
                if text:
                    orphan_bits.append(text[:3000])
                continue
        kept.append(item)
    if not orphan_bits:
        return kept
    note = "Recent tool results (already applied):\n" + "\n".join(
        f"- {bit}" for bit in orphan_bits
    )
    for i in range(len(kept) - 1, -1, -1):
        item = kept[i]
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            kept[i] = {**item, "content": f"{note}\n\n{content}"}
            return kept
        if isinstance(content, list):
            kept[i] = {
                **item,
                "content": [{"type": "input_text", "text": note}, *content],
            }
            return kept
    return [{"role": "user", "content": note}, *kept]


def make_llm_client(
    *,
    model: str | None = None,
    provider: str | None = None,
) -> OpenAI:
    """SDK client for reasoning. DeepSeek needs ``DEEPSEEK_API_KEY``."""
    kind = provider_for_model(model, explicit=provider)
    if kind == "deepseek":
        key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required when using DeepSeek models "
                "(ORCHESTRATOR_MODEL / AGENT_MODEL)."
            )
        return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
    return OpenAI()
