"""Parameterized desktop recipes: stable prefix, optional computer-use handoff.

A recipe opens a URL or app (with ``{{placeholders}}``), then either finishes
or hands leftover work to the vision agent. Matching recipes run before traces
and before the screenshot loop. Slot values are filled with regex first; EVAL_MODEL
only runs if bind fails. Screenshot-only leftover is saved here (no CU loop).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from task_log import TaskLog, _slugify
from task_spec import is_procedure_brief
from traces import (
    _HARD_TASK,
    _extract_urls,
    _norm,
    _phrase_in,
    frontmost_app_name,
    match_phrases_for,
)

RECIPES_DIR = Path(__file__).resolve().parent / "recipes"

RECIPE_REPLAY = os.environ.get("RECIPE_REPLAY", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RECIPE_RECORD = os.environ.get("RECIPE_RECORD", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RECIPE_SETTLE_SEC = float(os.environ.get("RECIPE_SETTLE_SEC", "0.8"))
RECIPE_AUTO_SAVE = os.environ.get("RECIPE_AUTO_SAVE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RECIPE_LLM_FILL = os.environ.get("RECIPE_LLM_FILL", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_ALLOWED_STEPS = frozenset({"open_url", "open_app"})
_APP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .+\-_]{0,79}$")
_OPEN_HTTP = re.compile(r"https?://[^\s'\"\\]+", re.I)
_MAPS_PLACE_URL = re.compile(
    r"maps/place/([^/?#\s)\"']+)",
    re.I,
)
_MAPS_QUERY_URL = re.compile(
    r"[?&](?:query|q)=([^&\s)\"']+)",
    re.I,
)
_SLOT_STOP = (
    r"and|then|wait|if|pan|zoom|make|capture|screenshot|reload|after|"
    r"before|using|until|while|please|when|once|is|not|try|or"
)
_SLOT_TOKEN = r"[^\s,.;:()/?#]+"
_NEEDS_VISION = re.compile(
    r"\b(zoom|pan|screenshot|capture|reload|frontmost|visible|wait for|play|unmute|volume)\b",
    re.I,
)
_INSTRUCTIONISH = re.compile(
    r"\b(wait for|screenshot|reload once|frontmost|comfortable zoom|"
    r"pan/zoom|report back|finish loading|is not playable|if that fails|"
    r"try youtube|open apple)\b",
    re.I,
)
_BAD_QUERY_START = re.compile(
    r"^(is|not|if|try|when|the track|it|that)\b",
    re.I,
)
_PLAY_BY = re.compile(
    r"(?:now\s+playing|play(?:ing)?)\s+"
    r"(?:the\s+(?:song|track|video)\s+)?"
    r"[\"']?([^.\n\"']{1,50}?)\s+by\s+[\"']?([A-Za-z0-9][^\"'\n.]{0,40})",
    re.I,
)
_PLAY_QUERY = re.compile(
    r"\b(?:play|playing|listen\s+to|put\s+on)\s+"
    r"(?:(?:some|the|an?)\s+)?"
    r"(?:song|songs|track|tracks|music|playlist|video|videos)?\s*"
    r"[\"']?(.+?)[\"']?\s*$",
    re.I,
)
_MEDIA_INTENT = re.compile(
    r"\b(play|playing|playlist|song|songs|music|track|tracks|youtube\s*music)\b",
    re.I,
)


class RecipeError(Exception):
    """Prelude failed; caller should fall through to computer-use."""


@dataclass
class Recipe:
    name: str
    match: list[str] = field(default_factory=list)
    match_templates: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    prelude: list[dict] = field(default_factory=list)
    handoff: bool = False
    leftover: str | None = None
    verify: dict = field(default_factory=dict)
    source_task: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "match": list(self.match),
            "params": list(self.params),
            "prelude": list(self.prelude),
            "handoff": bool(self.handoff),
            "verify": dict(self.verify),
            "source_task": self.source_task,
        }
        if len(self.match_templates) == 1:
            data["match_template"] = self.match_templates[0]
        elif self.match_templates:
            data["match_templates"] = list(self.match_templates)
        if self.leftover:
            data["leftover"] = self.leftover
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        templates: list[str] = []
        raw_t = data.get("match_templates")
        if isinstance(raw_t, list):
            templates.extend(str(t) for t in raw_t if str(t).strip())
        one = data.get("match_template")
        if isinstance(one, str) and one.strip():
            templates.append(one.strip())
        seen: set[str] = set()
        uniq: list[str] = []
        for item in templates:
            if item not in seen:
                seen.add(item)
                uniq.append(item)
        return cls(
            name=str(data.get("name") or "recipe"),
            match=[str(m) for m in (data.get("match") or []) if str(m).strip()],
            match_templates=uniq,
            params=[str(p) for p in (data.get("params") or []) if str(p).strip()],
            prelude=[a for a in (data.get("prelude") or []) if isinstance(a, dict)],
            handoff=bool(data.get("handoff")),
            leftover=(str(data.get("leftover")).strip() if data.get("leftover") else None),
            verify=dict(data.get("verify") or {}),
            source_task=str(data.get("source_task") or ""),
        )


@dataclass
class RecipeHit:
    recipe: Recipe
    params: dict[str, str]
    leftover: str
    opened: list[str]


def placeholders_in(text: str) -> list[str]:
    return _PLACEHOLDER.findall(text or "")


def apply_params(text: str, params: dict[str, str], *, url: bool = False) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in params:
            return match.group(0)
        value = params[key]
        if url:
            return quote(value, safe="")
        return value

    return _PLACEHOLDER.sub(repl, text or "")


def tokenize_template(template: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    last = 0
    for match in _PLACEHOLDER.finditer(template or ""):
        if match.start() > last:
            tokens.append(("lit", template[last : match.start()]))
        tokens.append(("ph", match.group(1)))
        last = match.end()
    if last < len(template or ""):
        tokens.append(("lit", template[last:]))
    return tokens


def match_template(template: str, utterance: str) -> tuple[dict[str, str], str] | None:
    """Bind ``{{slots}}``. A final slot is a short phrase, not the rest of the prompt."""
    tokens = tokenize_template(template)
    if not tokens:
        return None
    parts: list[str] = []
    names: list[str] = []
    short_last = (
        rf"(?P<NAME>(?!({_SLOT_STOP})\b){_SLOT_TOKEN}"
        rf"(?:\s+(?!(?:{_SLOT_STOP})\b){_SLOT_TOKEN}){{0,7}})"
        r"\s*(?P<_leftover>.*)?"
    )
    for i, (kind, value) in enumerate(tokens):
        if kind == "lit":
            words = (value or "").split()
            if not words:
                continue
            parts.append(r"\s+".join(re.escape(w) for w in words))
            parts.append(r"\s*")
            continue
        names.append(value)
        later_lit = any(k == "lit" and str(v).split() for k, v in tokens[i + 1 :])
        if later_lit:
            parts.append(rf"(?P<{value}>.+?)")
            parts.append(r"\s*")
        else:
            parts.append(short_last.replace("NAME", value))
    parts.append(r"\s*$")
    try:
        cre = re.compile("".join(parts), re.IGNORECASE)
    except re.error:
        return None
    found = cre.search((utterance or "").strip())
    if not found:
        return None
    params = {name: (found.group(name) or "").strip(" .,") for name in names}
    leftover = (found.groupdict().get("_leftover") or "").strip(" .,")
    leftover = re.sub(r"^(?:and|then)\s+", "", leftover, flags=re.I).strip()
    if any(not params.get(name) for name in names):
        return None
    if any(not _valid_slot(name, params[name]) for name in names):
        return None
    return params, leftover


def _safe_http_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise RecipeError(f"blocked URL scheme {parsed.scheme!r}")
    if not parsed.netloc:
        raise RecipeError("URL missing host")
    return raw


def _safe_app_name(app: str) -> str:
    name = (app or "").strip()
    if not _APP_NAME.match(name):
        raise RecipeError(f"invalid app name {name!r}")
    return name


def open_url(url: str, *, app: str | None = None) -> None:
    safe = _safe_http_url(url)
    if app:
        subprocess.run(["open", "-a", _safe_app_name(app), safe], check=True, timeout=20)
        return
    subprocess.run(["open", safe], check=True, timeout=20)


def open_app(app: str) -> None:
    name = _safe_app_name(app)
    subprocess.run(["open", "-a", name], check=True, timeout=20)


def run_prelude(
    recipe: Recipe,
    params: dict[str, str],
    *,
    settle: float | None = None,
) -> list[str]:
    opened: list[str] = []
    for step in recipe.prelude:
        kind = str(step.get("type") or "").strip()
        if kind not in _ALLOWED_STEPS:
            raise RecipeError(f"unsupported prelude step {kind!r}")
        if kind == "open_url":
            bound = apply_params(str(step.get("url") or ""), params, url=True)
            if placeholders_in(bound):
                raise RecipeError("unbound placeholder in URL")
            app = str(step.get("app") or "").strip() or None
            open_url(bound, app=app)
            opened.append(bound)
            continue
        bound_app = apply_params(str(step.get("app") or ""), params, url=False)
        if placeholders_in(bound_app):
            raise RecipeError("unbound placeholder in app")
        open_app(bound_app)
        opened.append(bound_app)
    wait = RECIPE_SETTLE_SEC if settle is None else float(settle)
    if wait > 0 and opened:
        _settle_open(recipe, timeout=wait)
    return opened


def verify_recipe(recipe: Recipe, *, quiet: bool = False) -> bool:
    want = str((recipe.verify or {}).get("ax_app") or "").strip()
    if not want:
        return True
    got = frontmost_app_name() or ""
    if not got:
        if not quiet:
            print("[recipe] verify skipped (no frontmost app name)", flush=True)
        return True
    ok = want.lower() in got.lower() or got.lower() in want.lower()
    if not quiet:
        print(f"[recipe] verify ax_app={want!r} frontmost={got!r} ok={ok}", flush=True)
    return ok


def _settle_open(recipe: Recipe, *, timeout: float) -> None:
    """Poll until the target app is frontmost, instead of a fixed sleep."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if verify_recipe(recipe, quiet=True):
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(0.12)


def load_recipes(recipes_dir: Path | None = None) -> list[Recipe]:
    root = recipes_dir or RECIPES_DIR
    if not root.is_dir():
        return []
    out: list[Recipe] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                recipe = Recipe.from_dict(data)
                if recipe.prelude:
                    out.append(recipe)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[recipe] skip {path.name}: {e}", flush=True)
    return out


def save_recipe(recipe: Recipe, recipes_dir: Path | None = None) -> Path:
    root = recipes_dir or RECIPES_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{recipe.name}.json"
    path.write_text(json.dumps(recipe.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"[recipe] saved {path.name}", flush=True)
    return path


def format_recipe_catalog(recipes: list[Recipe] | None = None) -> str:
    rows = recipes if recipes is not None else load_recipes()
    if not rows:
        return "(no recipes yet)"
    lines = []
    for recipe in rows:
        templates = "; ".join(recipe.match_templates) or ", ".join(recipe.match)
        lines.append(f"- {recipe.name}: {templates}")
    return "\n".join(lines)


def _valid_slot(name: str, value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if name == "url":
        probe = text if "://" in text else f"https://{text}"
        try:
            _safe_http_url(probe)
            return True
        except RecipeError:
            return False
    if re.search(r"https?://", text):
        return False
    if len(text) > 80 or len(text.split()) > 8:
        return False
    if _INSTRUCTIONISH.search(text):
        return False
    if name in {"query", "place"} and _BAD_QUERY_START.search(text):
        return False
    return True


def slot_grounded_in_utterance(utterance: str, value: str) -> bool:
    """True when the slot is actually present in this request (not a prior place)."""
    text = _norm(utterance)
    slot = _norm(value).replace(",", " ")
    if not text or not slot:
        return False
    if slot in text:
        return True
    words = [w for w in slot.split() if len(w) > 1]
    if not words:
        return False
    hay = set(text.split())
    return all(w in hay or w in text for w in words)


def params_grounded(utterance: str, params: dict[str, str]) -> bool:
    return all(slot_grounded_in_utterance(utterance, value) for value in params.values())


_MAPS_PLACE_TOO_NARROW = re.compile(
    r"national parks|wildlife sanctuary|openstreetmap|\bosm\b|" r"search for ['\"]|search for national",
    re.I,
)


def _has_map_word(text: str) -> bool:
    return bool(re.search(r"\bmaps?\b", text or "", re.I))


def recipe_covers_request(recipe: Recipe, utterance: str) -> bool:
    """False when this recipe would swallow a larger task (fall through to skills)."""
    if _prelude_is_maps(recipe) and recipe.params == ["place"]:
        if _MAPS_PLACE_TOO_NARROW.search(utterance or ""):
            return False
    return True


def extract_maps_place(utterance: str) -> str | None:
    found = _MAPS_PLACE_URL.search(utterance or "")
    if found:
        return unquote(found.group(1).replace("+", " ")).strip(" .,") or None
    found = _MAPS_QUERY_URL.search(utterance or "")
    if found:
        return unquote(found.group(1).replace("+", " ")).strip(" .,") or None
    return None


def extract_media_query(utterance: str) -> str | None:
    """Prefer 'play TITLE by ARTIST' / quoted titles / plain 'play … songs'."""
    found = _PLAY_BY.search(utterance or "")
    if found:
        title = found.group(1).strip(" \"'")
        artist = found.group(2).strip(" \"'")
        combined = f"{title} {artist}".strip()
        if _valid_slot("query", combined):
            return combined
    for quoted in re.findall(r"[\"']([^\"']{3,80})[\"']", utterance or ""):
        inner = re.sub(r"^(?:now\s+playing)\s+", "", quoted, flags=re.I).strip()
        play = _PLAY_BY.search(inner) or _PLAY_BY.search(f"play {inner}")
        if play:
            title = play.group(1).strip(" \"'")
            artist = play.group(2).strip(" \"'")
            combined = f"{title} {artist}".strip()
            if _valid_slot("query", combined):
                return combined
        if _valid_slot("query", inner) and not re.search(
            r"\b(youtube|chrome|tab|screenshot|playable)\b", inner, re.I
        ):
            return inner
    plain = _PLAY_QUERY.search((utterance or "").strip().rstrip(".!?"))
    if plain:
        query = plain.group(1).strip(" \"'")
        query = re.sub(
            r"\b(on\s+youtube(?:\s+music)?|in\s+(?:the\s+)?(?:browser|chrome)|please)\b",
            "",
            query,
            flags=re.I,
        ).strip(" ,.-")
        # Drop trailing filler like "for me"
        query = re.sub(r"\bfor\s+me\b", "", query, flags=re.I).strip(" ,.-")
        if _valid_slot("query", query) and not re.search(
            r"\b(chrome|tab|screenshot|playable|open\s+notes)\b", query, re.I
        ):
            return query
    return None


def _prelude_is_youtube_music(recipe: Recipe) -> bool:
    for step in recipe.prelude:
        url = str(step.get("url") or "").lower()
        if "music.youtube.com" in url and step.get("type") == "open_url":
            return True
    return False


def _prelude_is_youtube(recipe: Recipe) -> bool:
    for step in recipe.prelude:
        url = str(step.get("url") or "").lower()
        if "youtube.com" in url and step.get("type") == "open_url":
            return True
    return False


def _prelude_is_maps(recipe: Recipe) -> bool:
    for step in recipe.prelude:
        url = str(step.get("url") or "").lower()
        if "maps" in url and step.get("type") == "open_url":
            return True
    return False


def _task_needs_vision(utterance: str) -> bool:
    return bool(_NEEDS_VISION.search(utterance or ""))


def _vision_leftover(utterance: str) -> str:
    """Short remainder after a URL open — never 'create a new tab / navigate'."""
    bits: list[str] = []
    if re.search(r"\b(zoom|pan|center|visible)\b", utterance or "", re.I):
        bits.append("Adjust zoom or pan only if the place is not clearly visible.")
    if re.search(r"\b(screenshot|capture|save)\b", utterance or "", re.I):
        bits.append(
            "If a screenshot file was requested, capture the existing Chrome window. "
            "Do not open a new tab or type the URL again."
        )
    if re.search(r"\b(frontmost|bring.{0,20}front|retina display)\b", utterance or "", re.I):
        bits.append("Bring the existing Chrome window to the front if it is behind another app.")
    return " ".join(bits)


def _looks_like_agent_brief(text: str) -> bool:
    return is_procedure_brief(text)


def _bind_recipe(recipe: Recipe, utterance: str) -> tuple[dict[str, str], str] | None:
    if _prelude_is_maps(recipe) and "place" in (recipe.params or ["place"]):
        place = extract_maps_place(utterance)
        if place and _valid_slot("place", place):
            leftover = _vision_leftover(utterance) if _task_needs_vision(utterance) else ""
            return {"place": place}, leftover
    if _prelude_is_youtube(recipe) and "query" in (recipe.params or ["query"]):
        query = extract_media_query(utterance)
        if query:
            leftover = _vision_leftover(utterance) if recipe.handoff or _task_needs_vision(utterance) else ""
            return {"query": query}, leftover
    for template in recipe.match_templates:
        hit = match_template(template, utterance)
        if hit:
            return hit
    if not recipe.match_templates:
        bound = _bind_without_template(recipe, utterance)
        if bound is None:
            return None
        params, leftover = bound
        if any(not _valid_slot(name, params[name]) for name in params):
            return None
        return params, leftover
    return None


def _bind_without_template(recipe: Recipe, utterance: str) -> tuple[dict[str, str], str] | None:
    values: dict[str, str] = {}
    urls = _extract_urls(utterance)
    leftover = _norm(utterance)
    for phrase in recipe.match:
        leftover = leftover.replace(_norm(phrase), " ")
    leftover = re.sub(r"\s+", " ", leftover).strip()
    for name in recipe.params:
        if name == "url":
            if not urls:
                return None
            values[name] = urls[0]
            leftover = leftover.replace(_norm(urls[0]), " ")
            leftover = re.sub(r"\s+", " ", leftover).strip()
        else:
            if leftover:
                values[name] = leftover
                leftover = ""
            elif urls:
                values[name] = urls[0]
            else:
                return None
    return values, leftover


def score_recipe(recipe: Recipe, utterance: str) -> float:
    if recipe.match_templates:
        return 0.0
    if not recipe.match or not recipe.prelude:
        return 0.0
    hits = sum(1 for phrase in recipe.match if _phrase_in(utterance, phrase))
    if hits == 0:
        return 0.0
    return hits / float(len(recipe.match))


def find_matching_recipe(
    utterance: str,
    recipes: list[Recipe] | None = None,
    *,
    min_score: float = 1.0,
) -> tuple[Recipe, dict[str, str], str] | None:
    recipes = load_recipes() if recipes is None else recipes
    best: tuple[float, int, Recipe, dict[str, str], str] | None = None
    for recipe in recipes:
        if not recipe.prelude:
            continue
        bound: tuple[dict[str, str], str] | None = None
        score = 0.0
        bound = _bind_recipe(recipe, utterance)
        if bound is None:
            continue
        if recipe.match_templates or _prelude_is_maps(recipe):
            score = 1.0
        else:
            score = score_recipe(recipe, utterance)
            if score < min_score:
                continue
        params, leftover = bound
        if recipe.params and any(not params.get(name) for name in recipe.params):
            continue
        rank = (
            score,
            len(recipe.match_templates) + len(recipe.match),
            recipe,
            params,
            leftover,
        )
        if best is None or (rank[0], rank[1]) > (best[0], best[1]):
            best = rank
    if best is None:
        return None
    return best[2], best[3], best[4]


def _recipe_slot_names(recipe: Recipe) -> list[str]:
    names = list(recipe.params)
    for step in recipe.prelude:
        names.extend(placeholders_in(str(step.get("url") or "")))
        names.extend(placeholders_in(str(step.get("app") or "")))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def recipe_match_score(recipe: Recipe, utterance: str) -> float:
    """How well this recipe applies — literals/phrases only, no slot capture."""
    if not recipe.prelude:
        return 0.0
    text = utterance or ""
    if _prelude_is_maps(recipe) and (extract_maps_place(text) or _has_map_word(text)):
        return 2.0
    if _prelude_is_youtube(recipe) and _phrase_in(text, "youtube"):
        return 2.0
    # YouTube Music playlists/songs often omit the word "youtube" ("play old Hindi songs").
    if _prelude_is_youtube_music(recipe) and _MEDIA_INTENT.search(text) and extract_media_query(text):
        return 1.8
    best = 0.0
    for template in recipe.match_templates:
        lits = [
            " ".join((value or "").split())
            for kind, value in tokenize_template(template)
            if kind == "lit" and (value or "").split()
        ]
        if lits and all(_phrase_in(text, lit) for lit in lits):
            best = max(best, 1.5)
    if recipe.match:
        hits = sum(1 for phrase in recipe.match if _phrase_in(text, phrase))
        if hits == len(recipe.match):
            if recipe.params == ["url"] and not _extract_urls(text):
                return best
            best = max(best, 1.0)
    return best


def pick_matching_recipe(
    utterance: str,
    recipes: list[Recipe] | None = None,
) -> Recipe | None:
    recipes = load_recipes() if recipes is None else recipes
    best: tuple[float, int, Recipe] | None = None
    for recipe in recipes:
        score = recipe_match_score(recipe, utterance)
        if score <= 0:
            continue
        rank = (score, len(recipe.match_templates) + len(recipe.match), recipe)
        if best is None or (rank[0], rank[1]) > (best[0], best[1]):
            best = rank
    return None if best is None else best[2]


def fill_recipe_slots_llm(
    client: Any,
    recipe: Recipe,
    utterance: str,
) -> tuple[dict[str, str], str] | None:
    from evaluator import EVAL_MODEL

    names = _recipe_slot_names(recipe)
    prompt = f"""Fill placeholders for a desktop recipe from the task text.

Recipe: {recipe.name}
Placeholders: {names}
URL/app template: {json.dumps(recipe.prelude)}

Task:
{utterance}

Rules:
- Each placeholder value is SHORT: a place name, a song plus artist, or an http(s) URL.
- Use ONLY the Task text below. Do not reuse a place, song, or URL from a
  previous turn or from the desktop.
- If a placeholder value is not clearly present in the Task, do not guess.
- Do not copy fallback/instruction clauses ("is not playable", "create a new tab",
  "wait for the page", "if that fails").
- leftover is only UI work AFTER the URL/app is already open (zoom, click the
  official video, screenshot the existing window). Empty string if opening is enough.
- leftover must not tell the agent to open a new tab or type the same URL again.

JSON only (no markdown):
{{"params": {{"{names[0] if names else "query"}": "..."}}, "leftover": ""}}
"""
    response = client.responses.create(
        model=EVAL_MODEL,
        input=prompt,
        store=False,
    )
    text = ""
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    text += part.text
    data = _extract_json_object(text)
    if not isinstance(data, dict):
        return None
    raw = data.get("params")
    if not isinstance(raw, dict):
        return None
    params = {str(k): str(v).strip() for k, v in raw.items() if str(v).strip()}
    leftover = str(data.get("leftover") or "").strip()
    for name in names:
        if not params.get(name) or not _valid_slot(name, params[name]):
            print(f"[recipe] LLM fill rejected slot {name}={params.get(name)!r}", flush=True)
            return None
    if not params_grounded(utterance, {n: params[n] for n in names}):
        print(
            f"[recipe] LLM fill not in task params={params} task={utterance[:120]!r}",
            flush=True,
        )
        return None
    if _looks_like_agent_brief(leftover):
        leftover = _vision_leftover(utterance)
    print(f"[recipe] LLM fill {recipe.name} params={params} leftover={leftover!r}", flush=True)
    return params, leftover


def fill_recipe_slots(
    recipe: Recipe,
    utterance: str,
    *,
    client: Any | None = None,
) -> tuple[dict[str, str], str] | None:
    """Fill {{placeholders}}. Regex first; EVAL_MODEL only if bind fails."""
    bound = _bind_recipe(recipe, utterance)
    if bound is not None:
        params, leftover = bound
        if not params or params_grounded(utterance, params):
            return bound
        print(f"[recipe] regex fill not in task params={params}", flush=True)
    if client is not None and RECIPE_LLM_FILL and _recipe_slot_names(recipe):
        try:
            filled = fill_recipe_slots_llm(client, recipe, utterance)
            if filled is not None:
                return filled
        except Exception as e:
            print(f"[recipe] LLM fill failed ({e})", flush=True)
    return None


def leftover_text(recipe: Recipe, leftover: str, params: dict[str, str]) -> str:
    extra = (leftover or "").strip()
    if recipe.leftover:
        filled = apply_params(recipe.leftover, params, url=False).strip()
        if extra and extra.lower() not in filled.lower():
            return f"{filled} {extra}".strip()
        return filled or extra
    return extra


def leftover_is_screenshot_only(text: str) -> bool:
    """True when leftover is capture-the-window, not zoom/play/click."""
    blob = (text or "").strip().lower()
    if not blob or not re.search(r"\b(screenshot|capture)\b", blob):
        return False
    if re.search(r"\b(zoom|pan|play|click|unmute|search|type)\b", blob):
        return False
    return True


def save_recipe_screenshot(*, dest: Path | None = None) -> Path:
    from actions import DesktopController

    png = DesktopController().capture_screenshot()
    path = dest or (Path.home() / "Desktop" / f"jarvis-{int(time.time())}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"[recipe] saved screenshot {path}", flush=True)
    return path


def handoff_prompt(task: str, hit: RecipeHit) -> str:
    opened = "\n".join(f"- {item}" for item in hit.opened) or "- (prelude)"
    leftover = leftover_text(hit.recipe, hit.leftover, hit.params)
    finish = leftover or "Confirm the page matches the request, then mark_done."
    return (
        f"{finish}\n\n"
        "RECIPE HANDOFF — a prefix already ran. This is not a fresh desktop task.\n"
        "1. Look at the screenshot and occupancy first. Decide what is already true "
        "(app open, URL/page loaded, search done).\n"
        "2. If you read a skill, treat it as a checklist of remaining work, not a "
        "script. Skip every step whose outcome is already on screen. Do not start "
        "from skill step 1 (no Spotlight, no retyping the URL, no new Maps search "
        "if the place is already visible).\n"
        "3. Only act on leftover visual work (zoom, pick a result, save a screenshot "
        "of the window that is already open). Do not create a new tab. Do not type "
        "the URL again. If the leftover is already done, mark_done.\n"
        f"Already done:\n{opened}\n"
        f"Original request: {task}"
    )


def try_recipe(
    task: str,
    *,
    recipes_dir: Path | None = None,
    settle: float | None = None,
    client: Any | None = None,
) -> RecipeHit | str | None:
    """
    Run a matching recipe prelude.

    Returns a status string when the recipe finished the task, a RecipeHit when
    the vision agent should continue, or None to fall through.
    """
    if not RECIPE_REPLAY:
        return None
    recipes = load_recipes(recipes_dir)
    recipe = pick_matching_recipe(task, recipes)
    if recipe is None:
        return None
    if not recipe_covers_request(recipe, task):
        print(
            f"[recipe] {recipe.name} too narrow for this request — falling back to agent",
            flush=True,
        )
        return None
    bound = fill_recipe_slots(recipe, task, client=client)
    if bound is None:
        print(f"[recipe] {recipe.name} could not fill placeholders — falling back", flush=True)
        return None
    params, leftover = bound
    if _looks_like_agent_brief(leftover) or _looks_like_agent_brief(task):
        leftover = _vision_leftover(task)
    print(f"[recipe] {recipe.name} params={params} leftover={leftover!r}", flush=True)
    try:
        opened = run_prelude(recipe, params, settle=settle)
    except RecipeError as e:
        print(f"[recipe] prelude failed ({e}) — falling back", flush=True)
        return None
    except Exception as e:
        print(f"[recipe] prelude failed ({e}) — falling back", flush=True)
        return None
    if not verify_recipe(recipe):
        want = str((recipe.verify or {}).get("ax_app") or "").strip()
        if want:
            try:
                open_app(want)
                time.sleep(0.6)
            except Exception as e:
                print(f"[recipe] could not focus {want!r} ({e})", flush=True)
        if not verify_recipe(recipe):
            print(
                "[recipe] verify still failed — handing off anyway (prelude already ran)",
                flush=True,
            )
    hit = RecipeHit(recipe=recipe, params=params, leftover=leftover, opened=opened)
    extra = leftover_text(recipe, leftover, params)
    if leftover_is_screenshot_only(extra) and not recipe.handoff:
        try:
            shot = save_recipe_screenshot()
            return f"completed\nResult:\nOpened {opened[0] if opened else recipe.name}. " f"Saved screenshot {shot}."
        except Exception as e:
            print(f"[recipe] screenshot leftover failed ({e}) — handing off", flush=True)
    if extra or recipe.handoff:
        return hit
    return f"completed\nResult:\nOpened {opened[0] if opened else recipe.name}."


def collect_logged_commands(log: TaskLog) -> list[str]:
    if not log.steps_path.exists():
        return []
    out: list[str] = []
    for line in log.steps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") != "run_terminal":
            continue
        data = entry.get("data") or {}
        command = str(data.get("command") or "")
        if command:
            out.append(command)
    return out


def _computer_action_count(log: TaskLog) -> int:
    if not log.steps_path.exists():
        return 0
    n = 0
    for line in log.steps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if json.loads(line).get("kind") == "computer_actions":
            n += 1
    return n


def parameterize_opened_url(url: str, task: str) -> tuple[str, list[str]]:
    """Replace task-specific bits in an opened URL with placeholders."""
    decoded = unquote(url)
    urls = _extract_urls(task)
    if urls and _norm(urls[0]) in _norm(decoded):
        return "{{url}}", ["url"]
    quoted = re.findall(r"[\"']([^\"']{2,})[\"']", task or "")
    slot = "place" if re.search(r"\bmap\b", task or "", re.I) else "query"
    candidates: list[tuple[str, str]] = []
    for item in quoted:
        candidates.append((slot, item))
    leftover_words = match_phrases_for(task, urls + quoted)
    skip = {
        "open",
        "chrome",
        "safari",
        "google",
        "maps",
        "map",
        "youtube",
        "search",
        "please",
        "show",
        "me",
        "go",
        "the",
    }
    phrase = " ".join(w for w in leftover_words if w not in skip)
    if phrase:
        candidates.append((slot, phrase))
    used: list[str] = []
    templated = url
    for name, value in candidates:
        if not value or name in used:
            continue
        encoded = quote(value, safe="")
        if value.lower() in decoded.lower() or encoded.lower() in templated.lower():
            updated = re.sub(
                re.escape(encoded),
                "{{" + name + "}}",
                templated,
                count=1,
                flags=re.I,
            )
            if updated == templated:
                updated = re.sub(
                    re.escape(value),
                    "{{" + name + "}}",
                    templated,
                    count=1,
                    flags=re.I,
                )
            if "{{" + name + "}}" in updated:
                templated = updated
                used.append(name)
    return templated, used


def _default_templates(task: str, params: list[str]) -> list[str]:
    if params == ["url"]:
        return ["open {{url}}"]
    if not params:
        return []
    slot = "{{" + params[0] + "}}"
    if re.search(r"\bmap\b", task or "", re.I):
        return [f"map of {slot}", f"{slot} on a map"]
    if re.search(r"youtube", task or "", re.I):
        return [f"youtube {slot}", f"{slot} on youtube", f"play {slot} on youtube"]
    return [f"open {slot}"]


def propose_recipe_from_log(task: str, log: TaskLog) -> Recipe | None:
    if _HARD_TASK.search(task or ""):
        return None
    opened: list[str] = []
    for command in collect_logged_commands(log):
        for match in _OPEN_HTTP.finditer(command):
            opened.append(match.group(0).rstrip(".,);"))
    if len(opened) != 1:
        return None
    url = opened[0]
    try:
        _safe_http_url(url)
    except RecipeError:
        return None
    templated, params = parameterize_opened_url(url, task)
    name = _slugify(" ".join(match_phrases_for(task, _extract_urls(task))) or "open-url")
    match = match_phrases_for(task, list(params))
    return Recipe(
        name=name or "open-url",
        match=match[:8],
        match_templates=_default_templates(task, params),
        params=params,
        prelude=[{"type": "open_url", "url": templated}],
        handoff=_computer_action_count(log) >= 1,
        verify={"ax_app": "Google Chrome"},
        source_task=task,
    )


def recipe_exists(recipe: Recipe, existing: list[Recipe]) -> bool:
    want = {t.lower() for t in recipe.match_templates}
    for other in existing:
        if other.name == recipe.name:
            return True
        other_t = {t.lower() for t in other.match_templates}
        if want and want & other_t:
            return True
        if recipe.prelude and other.prelude and recipe.prelude == other.prelude:
            return True
    return False


def validate_recipe(recipe: Recipe) -> str | None:
    if not recipe.name or not recipe.prelude:
        return "missing name or prelude"
    for step in recipe.prelude:
        kind = str(step.get("type") or "")
        if kind not in _ALLOWED_STEPS:
            return f"unsupported step {kind}"
        if kind == "open_url":
            raw = str(step.get("url") or "").strip()
            if not raw:
                return "empty url"
            names = placeholders_in(raw)
            filled = apply_params(
                raw,
                {name: "https://example.com" if name == "url" else "example" for name in names},
                url=False,
            )
            try:
                _safe_http_url(filled)
            except RecipeError:
                return "prelude URL is not http(s)"
        if kind == "open_app":
            app = str(step.get("app") or "")
            if placeholders_in(app):
                continue
            try:
                _safe_app_name(app)
            except RecipeError:
                return "invalid app name"
    return None


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _recipe_from_proposal(data: dict[str, Any], task: str) -> Recipe | None:
    templates = data.get("match_templates") or data.get("match_template")
    prelude = data.get("prelude")
    if not isinstance(prelude, list) or not prelude:
        return None
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    return Recipe.from_dict(
        {
            "name": name,
            "match": data.get("match") or [],
            "match_template": templates if isinstance(templates, str) else None,
            "match_templates": templates if isinstance(templates, list) else [],
            "params": data.get("params") or [],
            "prelude": prelude,
            "handoff": bool(data.get("handoff")),
            "leftover": data.get("leftover"),
            "verify": data.get("verify") or {"ax_app": "Google Chrome"},
            "source_task": task,
        }
    )


def propose_recipe_llm(client: Any, task: str, log: TaskLog) -> Recipe | None:
    from evaluator import EVAL_MODEL

    existing = format_recipe_catalog()
    prompt = f"""You review a completed Mac desktop task. Propose a reusable RECIPE
only if the first steps are opening a URL or an app, with placeholders for
the bits that change next time (place, query, url).

A recipe has a prelude of open_url / open_app only (no clicks, no shell).
Set handoff=true when leftover UI work remained after the page opened.

Do NOT create a recipe when:
- An existing recipe already covers it
- The task is CAD, checkout, DMs, or one-off
- The useful work was only clicking around with no stable URL

Existing recipes:
{existing}

Original task:
{task}

Steps taken:
{log.steps_for_prompt()}

Respond with JSON only (no markdown fences):
{{
  "create": true or false,
  "reason": "short explanation",
  "name": "lowercase-hyphen-name or null",
  "match": ["phrase", "..."],
  "match_templates": ["map of {{{{place}}}}"],
  "params": ["place"],
  "prelude": [{{"type": "open_url", "url": "https://...{{{{place}}}}"}}],
  "handoff": true or false,
  "leftover": "optional leftover instruction or null",
  "verify": {{"ax_app": "Google Chrome"}}
}}
"""
    print("\n[recipe] reviewing run for a new recipe…")
    response = client.responses.create(model=EVAL_MODEL, input=prompt)
    text = ""
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    text += part.text
    proposal = _extract_json_object(text)
    if not proposal or not proposal.get("create"):
        if proposal:
            print(f"[recipe] no new recipe ({proposal.get('reason', 'not needed')})")
        return None
    recipe = _recipe_from_proposal(proposal, task)
    if recipe is None:
        print("[recipe] proposal missing fields; skipping.")
        return None
    err = validate_recipe(recipe)
    if err:
        print(f"[recipe] invalid proposal ({err}); skipping.")
        return None
    return recipe


def _maybe_save_recipe_impl(
    client: Any | None,
    log: TaskLog,
    task: str,
    *,
    recipes_dir: Path | None = None,
) -> Path | None:
    if not RECIPE_RECORD:
        return None
    existing = load_recipes(recipes_dir)
    if find_matching_recipe(task, existing) is not None:
        print("[recipe] existing recipe already matches this task; skip save.")
        return None
    recipe = None
    if client is not None:
        try:
            recipe = propose_recipe_llm(client, task, log)
        except Exception as e:
            print(f"[recipe] LLM review failed ({e})", flush=True)
    if recipe is None:
        recipe = propose_recipe_from_log(task, log)
    if recipe is None:
        return None
    if recipe_exists(recipe, existing):
        print(f"[recipe] {recipe.name!r} already covered; skip save.")
        return None
    err = validate_recipe(recipe)
    if err:
        print(f"[recipe] skip save ({err})")
        return None
    if not RECIPE_AUTO_SAVE:
        print(f"[recipe] not saved (RECIPE_AUTO_SAVE=0): {recipe.name}")
        return None
    path = save_recipe(recipe, recipes_dir)
    log.record("recipe_create", f"wrote {recipe.name}", {"path": str(path)})
    return path


def maybe_save_recipe(
    client: Any | None,
    log: TaskLog,
    task: str,
    *,
    background: bool = True,
    recipes_dir: Path | None = None,
) -> Path | None:
    """After a successful run, maybe persist an open_url recipe. Default: daemon."""
    if background:

        def _work() -> None:
            try:
                _maybe_save_recipe_impl(client, log, task, recipes_dir=recipes_dir)
            except Exception as e:
                print(f"[recipe] review failed: {e}", flush=True)

        threading.Thread(target=_work, name="recipe-review", daemon=True).start()
        print("[recipe] reviewing run for a new recipe in background…", flush=True)
        return None
    return _maybe_save_recipe_impl(client, log, task, recipes_dir=recipes_dir)
