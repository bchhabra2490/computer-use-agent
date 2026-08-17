"""Tests for skill discovery and cua skills condense."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cua  # noqa: E402
import skills as sk  # noqa: E402


def _write_skill_md(root: Path, name: str, description: str, body: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: >-\n  {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


class DiscoverSkillsTests(unittest.TestCase):
    def test_parses_frontmatter_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "open-app", "Opens apps via Spotlight.", "## Steps\n\n1. Cmd+Space.\n")
            found = sk.discover_skills(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].name, "open-app")
            self.assertIn("Spotlight", found[0].description)
            self.assertIn("Cmd+Space", found[0].body)


class CondenseParseTests(unittest.TestCase):
    def test_needs_condense_uses_length(self) -> None:
        short = sk.Skill("a", "short desc", "tiny body", Path("a/SKILL.md"))
        long_body = "x" * 2000
        long = sk.Skill("b", "desc", long_body, Path("b/SKILL.md"))
        self.assertFalse(sk.skill_needs_condense(short, min_chars=1800))
        self.assertTrue(sk.skill_needs_condense(long, min_chars=1800))

    def test_parse_rejects_name_mismatch_and_unchanged(self) -> None:
        self.assertIsNone(
            sk.parse_condensed_skill(
                {"name": "other", "changed": True, "description": "d", "body": "b"},
                expected_name="open-app",
            )
        )
        self.assertIsNone(
            sk.parse_condensed_skill(
                {"name": "open-app", "changed": False, "description": "d", "body": "b"},
                expected_name="open-app",
            )
        )

    def test_parse_strips_frontmatter_from_body(self) -> None:
        parsed = sk.parse_condensed_skill(
            {
                "name": "open-app",
                "changed": True,
                "description": "Opens apps via Spotlight when asked to launch one.",
                "body": "---\nname: open-app\n---\n\n## Steps\n\n1. Cmd+Space.\n",
                "reason": "trimmed tips",
            },
            expected_name="open-app",
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["name"], "open-app")
        self.assertIn("## Steps", parsed["body"])
        self.assertNotIn("---", parsed["body"])
        self.assertEqual(parsed["reason"], "trimmed tips")

    def test_parse_accepts_skills_array_wrapper(self) -> None:
        parsed = sk.parse_condensed_skill(
            {
                "skills": [
                    {
                        "name": "open-app",
                        "changed": True,
                        "description": "Opens apps via Spotlight.",
                        "body": "## Steps\n\n1. Cmd+Space.\n",
                    }
                ]
            },
            expected_name="open-app",
        )
        self.assertIsNotNone(parsed)


class CondenseRunTests(unittest.TestCase):
    def test_rewrites_verbose_skill_and_skips_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(
                root,
                "verbose-skill",
                "Does a long thing.",
                "## Steps\n\n" + ("1. Repeat this filler sentence.\n" * 80),
            )
            _write_skill_md(root, "open-app", "Opens apps.", "## Steps\n\n1. Cmd+Space.\n")

            class _Resp:
                output_text = json.dumps(
                    {
                        "name": "verbose-skill",
                        "changed": True,
                        "description": "Does the thing when asked.",
                        "body": "## Steps\n\n1. Do the thing.\n",
                        "reason": "dropped filler",
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self
                    self.calls = 0

                def create(self, **_kwargs):
                    self.calls += 1
                    return _Resp()

            client = _Client()
            results = sk.condense_skills(client, skills_dir=root, min_chars=1800)
            self.assertEqual(client.calls, 1)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["written"])
            rewritten = sk.get_skill("verbose-skill", root)
            assert rewritten is not None
            self.assertIn("Do the thing", rewritten.body)
            self.assertNotIn("filler", rewritten.body)
            short = sk.get_skill("open-app", root)
            assert short is not None
            self.assertIn("Cmd+Space", short.body)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = "## Steps\n\n" + ("1. Repeat this filler sentence.\n" * 80)
            _write_skill_md(root, "verbose-skill", "Does a long thing.", original)

            class _Resp:
                output_text = json.dumps(
                    {
                        "name": "verbose-skill",
                        "changed": True,
                        "description": "Does the thing when asked.",
                        "body": "## Steps\n\n1. Do the thing.\n",
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.condense_skills(_Client(), skills_dir=root, dry_run=True)
            self.assertTrue(results[0]["changed"])
            self.assertFalse(results[0]["written"])
            skill = sk.get_skill("verbose-skill", root)
            assert skill is not None
            self.assertIn("filler", skill.body)

    def test_named_skill_rewrites_even_if_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "open-app", "Opens apps.", "## Steps\n\n1. Cmd+Space.\n")

            class _Resp:
                output_text = json.dumps(
                    {
                        "name": "open-app",
                        "changed": True,
                        "description": "Opens macOS apps via Spotlight.",
                        "body": "## Steps\n\n1. Press Cmd+Space.\n2. Type the app name.\n3. Press Enter.\n",
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.condense_skills(
                _Client(),
                skills_dir=root,
                names=["open-app"],
                min_chars=1800,
            )
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["written"])
            skill = sk.get_skill("open-app", root)
            assert skill is not None
            self.assertIn("Type the app name", skill.body)

    def test_unknown_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "open-app", "Opens apps.", "1. Cmd+Space.\n")
            with self.assertRaises(ValueError) as ctx:
                sk.condense_skills(object(), skills_dir=root, names=["nope"])
            self.assertIn("Unknown skill", str(ctx.exception))

    def test_does_not_create_a_new_skill_from_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "## Steps\n\n" + ("1. Repeat this filler sentence.\n" * 80)
            _write_skill_md(root, "verbose-skill", "Does a long thing.", body)

            class _Resp:
                output_text = json.dumps(
                    {
                        "name": "brand-new-skill",
                        "changed": True,
                        "description": "Invented.",
                        "body": "## Steps\n\n1. Nope.\n",
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.condense_skills(_Client(), skills_dir=root)
            self.assertFalse(results[0]["written"])
            self.assertIsNone(sk.get_skill("brand-new-skill", root))
            skill = sk.get_skill("verbose-skill", root)
            assert skill is not None
            self.assertIn("filler", skill.body)


class CuaSkillsCommandTests(unittest.TestCase):
    def test_skills_condense_dispatches(self) -> None:
        with patch.object(sk, "cmd_condense_skills", return_value=0) as cmd:
            self.assertEqual(
                cua.main(["skills", "condense", "--dry-run", "--name", "open-app"]),
                0,
            )
            cmd.assert_called_once_with(
                names=["open-app"],
                force=False,
                dry_run=True,
                min_chars=None,
            )

    def test_skills_merge_dispatches(self) -> None:
        with patch.object(sk, "cmd_merge_skills", return_value=0) as cmd:
            self.assertEqual(
                cua.main(["skills", "merge", "--dry-run", "--name", "yt-a", "--name", "yt-b"]),
                0,
            )
            cmd.assert_called_once_with(names=["yt-a", "yt-b"], dry_run=True)


class MergeParseTests(unittest.TestCase):
    def _skills(self, root: Path, *names: str) -> list[sk.Skill]:
        for name in names:
            _write_skill_md(root, name, f"{name} desc", f"## Steps\n\n1. {name}\n")
        return sk.discover_skills(root)

    def test_rejects_invented_keep_and_empty_drop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = self._skills(root, "yt-play", "yt-play-dup")
            self.assertEqual(
                sk.parse_merge_groups(
                    {
                        "merges": [
                            {
                                "keep": "brand-new",
                                "drop": ["yt-play-dup"],
                                "description": "d",
                                "body": "b",
                            }
                        ]
                    },
                    skills,
                ),
                [],
            )
            self.assertEqual(
                sk.parse_merge_groups(
                    {
                        "merges": [
                            {
                                "keep": "yt-play",
                                "drop": ["yt-play"],
                                "description": "d",
                                "body": "b",
                            }
                        ]
                    },
                    skills,
                ),
                [],
            )

    def test_skips_overlapping_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = self._skills(root, "a", "b", "c")
            groups = sk.parse_merge_groups(
                {
                    "merges": [
                        {
                            "keep": "a",
                            "drop": ["b"],
                            "description": "ab",
                            "body": "## Steps\n\n1. A then B.\n",
                            "reason": "same",
                        },
                        {
                            "keep": "b",
                            "drop": ["c"],
                            "description": "bc",
                            "body": "## Steps\n\n1. B then C.\n",
                        },
                    ]
                },
                skills,
            )
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["keep"].name, "a")
            self.assertEqual([d.name for d in groups[0]["drop"]], ["b"])


class MergeRunTests(unittest.TestCase):
    def test_writes_survivor_and_deletes_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "yt-play", "Play a YouTube video.", "## Steps\n\n1. Open YouTube.\n")
            _write_skill_md(
                root,
                "yt-play-dup",
                "Play a YouTube video in Chrome.",
                "## Steps\n\n1. Open Chrome.\n2. Open YouTube.\n",
            )
            extra = root / "yt-play-dup" / "notes.txt"
            extra.write_text("keep me\n", encoding="utf-8")

            class _Resp:
                output_text = json.dumps(
                    {
                        "merges": [
                            {
                                "keep": "yt-play",
                                "drop": ["yt-play-dup"],
                                "description": "Plays a YouTube video in the browser.",
                                "body": "## Steps\n\n1. Open Chrome.\n2. Open YouTube.\n3. Play the video.\n",
                                "reason": "same play flow",
                            }
                        ]
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.merge_skills(_Client(), skills_dir=root)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["written"])
            self.assertEqual(results[0]["deleted"], ["yt-play-dup"])
            self.assertIn("notes.txt", results[0]["moved"])
            self.assertIsNone(sk.get_skill("yt-play-dup", root))
            kept = sk.get_skill("yt-play", root)
            assert kept is not None
            self.assertIn("Open Chrome", kept.body)
            self.assertTrue((root / "yt-play" / "notes.txt").is_file())
            self.assertFalse((root / "yt-play-dup").exists())

    def test_dry_run_does_not_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "yt-play", "Play a YouTube video.", "1. Open YouTube.\n")
            _write_skill_md(root, "yt-play-dup", "Play a YouTube video.", "1. Open YouTube.\n")

            class _Resp:
                output_text = json.dumps(
                    {
                        "merges": [
                            {
                                "keep": "yt-play",
                                "drop": ["yt-play-dup"],
                                "description": "Plays a YouTube video.",
                                "body": "## Steps\n\n1. Open YouTube.\n",
                            }
                        ]
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.merge_skills(_Client(), skills_dir=root, dry_run=True)
            self.assertFalse(results[0]["written"])
            self.assertEqual(results[0]["deleted"], [])
            self.assertIsNotNone(sk.get_skill("yt-play-dup", root))

    def test_does_not_delete_when_keep_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_skill_md(root, "yt-play", "Play a YouTube video.", "1. Open YouTube.\n")
            _write_skill_md(root, "yt-play-dup", "Play a YouTube video.", "1. Open YouTube.\n")

            class _Resp:
                output_text = json.dumps(
                    {
                        "merges": [
                            {
                                "keep": "invented-skill",
                                "drop": ["yt-play", "yt-play-dup"],
                                "description": "Nope.",
                                "body": "## Steps\n\n1. Nope.\n",
                            }
                        ]
                    }
                )
                output = []

            class _Client:
                def __init__(self) -> None:
                    self.responses = self

                def create(self, **_kwargs):
                    return _Resp()

            results = sk.merge_skills(_Client(), skills_dir=root)
            self.assertEqual(results, [])
            self.assertIsNotNone(sk.get_skill("yt-play", root))
            self.assertIsNotNone(sk.get_skill("yt-play-dup", root))

    def test_delete_refuses_folder_outside_skills_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            other = Path(tmp) / "other"
            other.mkdir()
            _write_skill_md(root, "open-app", "Opens apps.", "1. Cmd+Space.\n")
            skill = sk.get_skill("open-app", root)
            assert skill is not None
            with self.assertRaises(PermissionError):
                sk.delete_skill_folder(skill, other)
            self.assertTrue((root / "open-app" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
