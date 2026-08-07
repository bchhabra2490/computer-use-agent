"""
Load project skills from the `skills/` directory.

Each skill is a folder containing SKILL.md with YAML frontmatter (`name`,
`description`) and markdown instructions the computer-use agent can follow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
    content = (
        f"---\n"
        f"name: {name}\n"
        f"description: >-\n"
        f"  {description}\n"
        f"---\n\n"
        f"{body}\n"
    )
    skill_md.write_text(content, encoding="utf-8")
    return skill_md
