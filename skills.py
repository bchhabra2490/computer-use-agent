"""
Load project skills from the `skills/` directory.

Each skill is a folder containing SKILL.md with YAML frontmatter (`name`,
`description`) and markdown instructions the computer-use agent can follow.

``cua skills condense`` rewrites verbose playbooks in place.
``cua skills merge`` folds duplicate playbooks into one and deletes the extras.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path

    @property
    def full_text(self) -> str:
        return f"# Skill: {self.name}\n\n{self.description}\n\n{self.body}".strip()


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw.strip()

    meta: dict[str, str] = {}
    lines = match.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" not in line or line.startswith(" ") or line.startswith("\t"):
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Folded/literal block scalars: description: >-  /  |
        if value in (">", ">-", "|", "|-"):
            block: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                block.append(lines[i].strip())
                i += 1
            meta[key] = " ".join(block).strip()
            continue

        meta[key] = value.strip("\"'")
        i += 1

    return meta, match.group(2).strip()


def discover_skills(skills_dir: Path | None = None) -> list[Skill]:
    """Scan `skills/*/SKILL.md` and return parsed skills, sorted by name."""
    root = skills_dir or SKILLS_DIR
    if not root.is_dir():
        return []

    skills: list[Skill] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        raw = skill_md.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        name = meta.get("name") or skill_md.parent.name
        description = meta.get("description") or "(no description)"
        skills.append(
            Skill(
                name=name,
                description=description,
                body=body,
                path=skill_md,
            )
        )
    return skills


def get_skill(name: str, skills_dir: Path | None = None) -> Skill | None:
    """Look up a skill by frontmatter name or folder name (case-insensitive)."""
    needle = name.strip().lower()
    for skill in discover_skills(skills_dir):
        if skill.name.lower() == needle or skill.path.parent.name.lower() == needle:
            return skill
    return None


def list_skill_files(name: str, skills_dir: Path | None = None) -> list[str]:
    """Relative paths of extra files inside a skill folder (excluding SKILL.md)."""
    skill = get_skill(name, skills_dir)
    if skill is None:
        return []
    root = skill.path.parent
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SKILL.md":
            files.append(str(path.relative_to(root)))
    return files


def read_skill_file(name: str, relative_path: str, skills_dir: Path | None = None) -> str:
    """Read a companion file from a skill folder. Rejects path traversal."""
    skill = get_skill(name, skills_dir)
    if skill is None:
        raise FileNotFoundError(f"Unknown skill: {name}")

    root = skill.path.parent.resolve()
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root) + "/") and target != root:
        raise PermissionError("Skill file path escapes the skill folder.")
    if not target.is_file():
        raise FileNotFoundError(f"No file {relative_path!r} in skill {name!r}")
    return target.read_text(encoding="utf-8")


def format_skill_catalog(skills: list[Skill] | None = None) -> str:
    """Compact catalog for the agent’s starting prompt."""
    skills = discover_skills() if skills is None else skills
    if not skills:
        return "No skills installed yet. Add skills under skills/<name>/SKILL.md."

    lines = ["Available skills (call read_skill to load full instructions):"]
    for skill in skills:
        lines.append(f"  - {skill.name}: {skill.description}")
    return "\n".join(lines)


_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sanitize_skill_name(name: str) -> str:
    """Normalize to lowercase hyphenated skill id."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug or not _SKILL_NAME_RE.match(slug):
        raise ValueError(f"Invalid skill name: {name!r}")
    if len(slug) > 64:
        raise ValueError(f"Skill name too long: {slug!r}")
    return slug


def write_skill(
    name: str,
    description: str,
    body: str,
    *,
    skills_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Create `skills/<name>/SKILL.md`. Raises if it already exists unless overwrite."""
    name = sanitize_skill_name(name)
    description = " ".join(description.split()).strip()
    body = body.strip()
    if not description:
        raise ValueError("Skill description is required.")
    if not body:
        raise ValueError("Skill body is required.")

    root = (skills_dir or SKILLS_DIR) / name
    skill_md = root / "SKILL.md"
    if skill_md.exists() and not overwrite:
        raise FileExistsError(f"Skill already exists: {name}")

    root.mkdir(parents=True, exist_ok=True)
    # Escape description for single-line YAML if it contains special chars — use folded block.
    content = f"---\n" f"name: {name}\n" f"description: >-\n" f"  {description}\n" f"---\n\n" f"{body}\n"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


def skill_condense_model() -> str:
    return (
        os.environ.get("SKILL_CONDENSE_MODEL")
        or os.environ.get("MEMORY_CONDENSE_MODEL")
        or os.environ.get("EVAL_MODEL")
        or os.environ.get("ORCHESTRATOR_MODEL")
        or "gpt-5-mini"
    ).strip() or "gpt-5-mini"


_DEFAULT_CONDENSE_MIN_CHARS = 1800


def skill_condense_min_chars() -> int:
    raw = os.environ.get("SKILL_CONDENSE_MIN_CHARS", str(_DEFAULT_CONDENSE_MIN_CHARS))
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_CONDENSE_MIN_CHARS


def skill_needs_condense(skill: Skill, *, min_chars: int | None = None) -> bool:
    """True when the playbook is long enough that a rewrite is worth an LLM call."""
    threshold = skill_condense_min_chars() if min_chars is None else min_chars
    return (len(skill.description) + len(skill.body)) >= threshold


def _parse_json_object(text: str) -> Any | None:
    blob = (text or "").strip()
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", blob, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _response_output_text(response: Any) -> str:
    text = (getattr(response, "output_text", None) or "").strip()
    if text:
        return text
    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                parts.append(getattr(part, "text", "") or "")
    return "".join(parts).strip()


def parse_condensed_skill(payload: Any, *, expected_name: str) -> dict[str, str] | None:
    """Normalize one condense JSON object. Name must match the skill being rewritten."""
    if not isinstance(payload, dict):
        return None
    row = payload
    if isinstance(payload.get("skills"), list) and payload["skills"]:
        first = payload["skills"][0]
        if isinstance(first, dict):
            row = first
    name = str(row.get("name") or "").strip()
    if name.lower() != expected_name.strip().lower():
        return None
    changed = row.get("changed")
    if changed is False or (isinstance(changed, str) and changed.strip().lower() in {"false", "0", "no"}):
        return None
    description = str(row.get("description") or "").strip()
    body = str(row.get("body") or "").strip()
    if not description or not body:
        return None
    if body.lstrip().startswith("---"):
        _, body = _parse_frontmatter(body)
        body = body.strip()
        if not body:
            return None
    reason = str(row.get("reason") or "").strip()
    return {
        "name": expected_name,
        "description": description,
        "body": body,
        "reason": reason,
    }


_CONDENSE_PROMPT = """You rewrite one computer-use skill so the agent can follow it with fewer tokens.

The skill is a Mac desktop playbook (mouse, keyboard, screenshots, tools).

Rules:
- Keep every unique step, hotkey, URL, tool name, filename, and safety rule.
- Drop repetition, restated tips, and example-specific values that should be placeholders.
- Keep the same `name`. Tighten the third-person description (what + when).
- Body: markdown with ## Steps (numbered) and optional ## Tips. No YAML frontmatter in body.
- Do not add capabilities, new tools, or extra apps.
- Do not add sleep-for-duration, macOS `say`, or waiting in the shell until media finishes.
- Do not remove confirmation gates, ask_user pauses, or "do not checkout / do not store passwords".
- If the skill is already compact, set changed to false and omit description/body.

Skill name: <<<NAME>>>
Description:
<<<DESCRIPTION>>>
Body:
<<<BODY>>>

Respond with JSON only (no markdown fences):
{"name": "<same name>", "changed": true or false, "description": "...", "body": "...", "reason": "why"}
"""


def _condense_one_skill(
    client: Any,
    skill: Skill,
    *,
    skills_dir: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Rewrite one SKILL.md. Returns a result dict; never creates a new skill."""
    prompt = (
        _CONDENSE_PROMPT.replace("<<<NAME>>>", skill.name)
        .replace("<<<DESCRIPTION>>>", skill.description)
        .replace("<<<BODY>>>", skill.body)
    )
    before = len(skill.description) + len(skill.body)
    result: dict[str, Any] = {
        "name": skill.name,
        "changed": False,
        "written": False,
        "chars_before": before,
        "chars_after": before,
        "reason": "",
        "path": str(skill.path),
    }
    response = client.responses.create(
        model=skill_condense_model(),
        input=prompt,
    )
    payload = _parse_json_object(_response_output_text(response))
    parsed = parse_condensed_skill(payload, expected_name=skill.name)
    if parsed is None:
        result["reason"] = "unchanged"
        return result
    after = len(parsed["description"]) + len(parsed["body"])
    result["changed"] = True
    result["chars_after"] = after
    result["reason"] = parsed["reason"] or "rewritten"
    if dry_run:
        return result
    path = write_skill(
        skill.path.parent.name,
        parsed["description"],
        parsed["body"],
        skills_dir=skills_dir or skill.path.parent.parent,
        overwrite=True,
    )
    result["written"] = True
    result["path"] = str(path)
    return result


def condense_skills(
    client: Any,
    *,
    skills_dir: Path | None = None,
    names: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    min_chars: int | None = None,
) -> list[dict[str, Any]]:
    """
    Rewrite verbose skills in place. Only existing SKILL.md files are updated.

    ``names`` limits the run (those skills are condensed even if under the
    length threshold). ``force`` includes every skill. ``dry_run`` calls the
    model but does not write.
    """
    root = skills_dir or SKILLS_DIR
    if names:
        targets = _select_skills(root, names)
    elif force:
        targets = discover_skills(root)
    else:
        threshold = skill_condense_min_chars() if min_chars is None else min_chars
        targets = [s for s in discover_skills(root) if skill_needs_condense(s, min_chars=threshold)]

    results: list[dict[str, Any]] = []
    for skill in targets:
        print(f"[skills] condensing {skill.name}…", flush=True)
        try:
            results.append(
                _condense_one_skill(
                    client,
                    skill,
                    skills_dir=root,
                    dry_run=dry_run,
                )
            )
        except Exception as e:
            print(f"[skills] condense failed for {skill.name}: {e}", flush=True)
            results.append(
                {
                    "name": skill.name,
                    "changed": False,
                    "written": False,
                    "chars_before": len(skill.description) + len(skill.body),
                    "chars_after": len(skill.description) + len(skill.body),
                    "reason": f"error: {e}",
                    "path": str(skill.path),
                    "error": str(e),
                }
            )
    return results


def cmd_condense_skills(
    *,
    names: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    min_chars: int | None = None,
) -> int:
    """CLI entry for ``cua skills condense``. Loads ``.env`` and calls the model."""
    from envfile import load_dotenv
    from openai import OpenAI

    load_dotenv()
    try:
        client = OpenAI()
        results = condense_skills(
            client,
            names=names,
            force=force,
            dry_run=dry_run,
            min_chars=min_chars,
        )
    except ValueError as e:
        print(str(e), flush=True)
        return 1
    except Exception as e:
        print(f"[skills] condense failed: {e}", flush=True)
        return 1

    if not results:
        print("[skills] nothing to condense (playbooks already compact; use --force or --name)")
        return 0

    rewritten = [r for r in results if r.get("changed")]
    written = [r for r in results if r.get("written")]
    errors = [r for r in results if r.get("error")]
    prefix = "would rewrite" if dry_run else "rewrote"
    for row in results:
        before = row.get("chars_before", 0)
        after = row.get("chars_after", before)
        reason = row.get("reason") or ""
        if row.get("error"):
            print(f"  {row['name']}: failed ({reason})")
            continue
        if row.get("changed"):
            print(f"  {row['name']}: {prefix} {before} → {after} chars ({reason})")
        else:
            print(f"  {row['name']}: left unchanged")
    if dry_run:
        print(f"[skills] dry-run: {len(rewritten)} of {len(results)} would change")
    else:
        print(f"[skills] condensed {len(written)} of {len(results)} skill(s)")
    return 1 if errors else 0


def _skill_lookup(skills: list[Skill]) -> dict[str, Skill]:
    index: dict[str, Skill] = {}
    for skill in skills:
        index[skill.name.lower()] = skill
        index[skill.path.parent.name.lower()] = skill
    return index


def _select_skills(
    skills_dir: Path,
    names: list[str] | None = None,
) -> list[Skill]:
    all_skills = discover_skills(skills_dir)
    if not names:
        return all_skills
    selected: list[Skill] = []
    missing: list[str] = []
    for needle in names:
        skill = get_skill(needle, skills_dir)
        if skill is None:
            missing.append(needle)
        elif skill not in selected:
            selected.append(skill)
    if missing:
        available = ", ".join(s.name for s in all_skills) or "(none)"
        raise ValueError(f"Unknown skill(s): {', '.join(missing)}. Available: {available}")
    return selected


def _skill_folder(skill: Skill, skills_dir: Path) -> Path:
    folder = skill.path.parent.resolve()
    root = skills_dir.resolve()
    if folder.parent != root:
        raise PermissionError(f"Skill folder is not under {root}: {folder}")
    return folder


def _format_skills_for_merge(skills: list[Skill], *, max_body: int = 1200, max_chars: int = 40_000) -> str:
    parts: list[str] = []
    used = 0
    for skill in skills:
        body = skill.body.strip()
        if len(body) > max_body:
            body = body[:max_body].rstrip() + "\n… (truncated)"
        extras = list_skill_files(skill.name, skill.path.parent.parent)
        extra_line = f"Extra files: {', '.join(extras)}\n" if extras else ""
        chunk = (
            f"### {skill.name}  (folder: {skill.path.parent.name})\n"
            f"{skill.description}\n"
            f"{extra_line}"
            f"{body}\n"
        )
        if used + len(chunk) > max_chars:
            parts.append("… (further skills omitted)")
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts).strip() or "(none)"


def parse_merge_groups(payload: Any, skills: list[Skill]) -> list[dict[str, Any]]:
    """Validate merge proposals. Keep/drop must already exist; no overlapping groups."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("merges") or payload.get("groups") or []
    if not isinstance(raw, list):
        return []
    index = _skill_lookup(skills)
    used: set[str] = set()
    groups: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        keep_key = str(row.get("keep") or row.get("name") or "").strip().lower()
        drop_raw = row.get("drop") or row.get("remove") or row.get("duplicates") or []
        if not isinstance(drop_raw, list):
            continue
        keep = index.get(keep_key)
        if keep is None:
            continue
        drops: list[Skill] = []
        seen_drop: set[str] = set()
        for item in drop_raw:
            other = index.get(str(item).strip().lower())
            if other is None:
                continue
            folder = other.path.parent.name
            if folder == keep.path.parent.name or folder in seen_drop:
                continue
            drops.append(other)
            seen_drop.add(folder)
        if not drops:
            continue
        members = [keep.path.parent.name, *seen_drop]
        if any(name in used for name in members):
            continue
        description = str(row.get("description") or "").strip()
        body = str(row.get("body") or "").strip()
        if not description or not body:
            continue
        if body.lstrip().startswith("---"):
            _, body = _parse_frontmatter(body)
            body = body.strip()
        if not body:
            continue
        for name in members:
            used.add(name)
        groups.append(
            {
                "keep": keep,
                "drop": drops,
                "description": description,
                "body": body,
                "reason": str(row.get("reason") or "").strip(),
            }
        )
    return groups


def _relocate_skill_files(src: Path, dest: Path) -> list[str]:
    """Move companion files from a dropped skill folder into the kept one."""
    moved: list[str] = []
    if not src.is_dir() or src.resolve() == dest.resolve():
        return moved
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        rel = path.relative_to(src)
        target = dest / rel
        if target.exists():
            target = dest / rel.parent / f"{src.name}-{rel.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moved.append(str(target.relative_to(dest)))
    return moved


def delete_skill_folder(skill: Skill, skills_dir: Path) -> Path:
    """Remove an existing skill directory. Refuses paths outside skills_dir."""
    folder = _skill_folder(skill, skills_dir)
    shutil.rmtree(folder)
    return folder


_MERGE_PROMPT = """You merge duplicate computer-use skills so the catalog has one playbook per workflow.

Each skill is a Mac desktop playbook (mouse, keyboard, screenshots, tools).

Merge ONLY when two or more skills are the same workflow: same app and same outcome,
differing only by wording, optional extra steps, or example values.

Do NOT merge when:
- The outcome differs (search vs checkout, comments vs submit, play music vs play a tutorial).
- They share an app but not the task (Chrome open-URL vs copy-tab-URL).
- One is a general helper another skill already references (open-app, read-memory, web-search).
When unsure, leave them separate.

For each merge:
- `keep` must be an existing skill name (prefer the shorter/more general existing name).
- `drop` is the other existing names to delete after the merge.
- Write a combined description (what + when) and compact ## Steps / ## Tips body.
- Keep every unique step, hotkey, URL, tool name, filename, and safety rule from the group.
- Do not invent a new keep name. Do not add capabilities the originals lacked.

Skills:
<<<SKILLS>>>

Respond with JSON only (no markdown fences):
{"merges": [{"keep": "existing-name", "drop": ["other-existing-name"], "description": "...", "body": "...", "reason": "why"}]}
If nothing should merge, return {"merges": []}.
"""


def merge_skills(
    client: Any,
    *,
    skills_dir: Path | None = None,
    names: list[str] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Fold duplicate skills into one SKILL.md and delete the extras.

    ``names`` limits the candidate set (only those skills may be keep or drop).
    ``dry_run`` calls the model but does not write or delete.
    """
    root = skills_dir or SKILLS_DIR
    candidates = _select_skills(root, names)
    if len(candidates) < 2:
        return []

    prompt = _MERGE_PROMPT.replace("<<<SKILLS>>>", _format_skills_for_merge(candidates))
    print("[skills] looking for duplicate playbooks…", flush=True)
    response = client.responses.create(
        model=skill_condense_model(),
        input=prompt,
    )
    payload = _parse_json_object(_response_output_text(response))
    groups = parse_merge_groups(payload, candidates)
    results: list[dict[str, Any]] = []
    for group in groups:
        keep: Skill = group["keep"]
        drops: list[Skill] = group["drop"]
        drop_names = [d.path.parent.name for d in drops]
        row: dict[str, Any] = {
            "keep": keep.path.parent.name,
            "drop": drop_names,
            "reason": group["reason"] or "duplicate workflow",
            "written": False,
            "deleted": [],
            "moved": [],
        }
        print(
            f"[skills] merge {row['keep']} ← {', '.join(drop_names)}"
            + (f" ({row['reason']})" if row["reason"] else ""),
            flush=True,
        )
        if dry_run:
            results.append(row)
            continue
        try:
            write_skill(
                keep.path.parent.name,
                group["description"],
                group["body"],
                skills_dir=root,
                overwrite=True,
            )
            row["written"] = True
            keep_folder = _skill_folder(keep, root)
            moved: list[str] = []
            deleted: list[str] = []
            for dropped in drops:
                src = _skill_folder(dropped, root)
                moved.extend(_relocate_skill_files(src, keep_folder))
                delete_skill_folder(dropped, root)
                deleted.append(dropped.path.parent.name)
            row["moved"] = moved
            row["deleted"] = deleted
        except Exception as e:
            print(f"[skills] merge failed for {row['keep']}: {e}", flush=True)
            row["error"] = str(e)
        results.append(row)
    return results


def cmd_merge_skills(
    *,
    names: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    """CLI entry for ``cua skills merge``. Loads ``.env`` and calls the model."""
    from envfile import load_dotenv
    from openai import OpenAI

    load_dotenv()
    try:
        client = OpenAI()
        results = merge_skills(client, names=names, dry_run=dry_run)
    except ValueError as e:
        print(str(e), flush=True)
        return 1
    except Exception as e:
        print(f"[skills] merge failed: {e}", flush=True)
        return 1

    if not results:
        print("[skills] no duplicate playbooks to merge")
        return 0

    errors = [r for r in results if r.get("error")]
    verb = "would merge" if dry_run else "merged"
    for row in results:
        drops = ", ".join(row.get("drop") or [])
        reason = row.get("reason") or ""
        if row.get("error"):
            print(f"  {row['keep']} ← {drops}: failed ({row['error']})")
            continue
        extra = f" ({reason})" if reason else ""
        print(f"  {verb} {row['keep']} ← {drops}{extra}")
        if row.get("deleted"):
            print(f"    deleted: {', '.join(row['deleted'])}")
        if row.get("moved"):
            print(f"    moved files: {', '.join(row['moved'])}")
    if dry_run:
        print(f"[skills] dry-run: {len(results)} merge(s); nothing deleted")
    else:
        deleted = sum(len(r.get("deleted") or []) for r in results)
        print(f"[skills] merged {len(results) - len(errors)} group(s), deleted {deleted} skill(s)")
    return 1 if errors else 0
