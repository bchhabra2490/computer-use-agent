"""Tests for evidence-backed graph memory storage."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import memory_graph as graph  # noqa: E402


class GraphMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.observation = {
            "focus": {"app": "Code", "title": "computer-use-agent", "url": ""},
            "segments": [
                {
                    "events": [
                        {"t": "2026-09-03T10:00:00+00:00", "kind": "click"},
                        {"t": "2026-09-03T10:05:00+00:00", "kind": "scroll"},
                    ]
                }
            ],
        }
        self.changes = {
            "graph_changes": {
                "entities": [
                    {"id": "person:self", "type": "person", "label": "User"},
                    {
                        "id": "project:computer-use-agent",
                        "type": "project",
                        "label": "computer-use-agent",
                    },
                ],
                "claims": [
                    {
                        "subject_id": "person:self",
                        "predicate": "WORKS_ON",
                        "object_id": "project:computer-use-agent",
                        "epistemic_status": "observed",
                        "confidence": 0.9,
                        "evidence": "VS Code focused on the project",
                    }
                ],
            }
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_applies_and_searches_auto_accepted_claim(self) -> None:
        result = graph.apply_observation_graph(
            "obs-one", self.observation, self.changes, memory_dir=self.root
        )
        self.assertEqual(result, {"observations": 1, "entities": 2, "claims": 1})
        hits = graph.search_graph("computer use agent", memory_dir=self.root)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["predicate"], "WORKS_ON")
        self.assertEqual(hits[0]["epistemic_status"], "observed")
        export = self.root / "graph" / "graphify-out" / "graph.json"
        self.assertTrue(export.is_file())
        payload = json.loads(export.read_text(encoding="utf-8"))
        self.assertTrue(payload["directed"])
        self.assertEqual(payload["links"][0]["relation"], "works_on")

    def test_reapply_is_idempotent_and_adds_evidence(self) -> None:
        graph.apply_observation_graph("obs-one", self.observation, self.changes, memory_dir=self.root)
        graph.apply_observation_graph("obs-two", self.observation, self.changes, memory_dir=self.root)
        with graph._connect(self.root) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM claims").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0], 2)

    def test_rejects_unknown_predicate_and_secret_labels(self) -> None:
        changes = {
            "graph_changes": {
                "entities": [
                    {"id": "person:self", "type": "person", "label": "User"},
                    {"id": "project:x", "type": "project", "label": "api_key: secret-value"},
                ],
                "claims": [
                    {
                        "subject_id": "person:self",
                        "predicate": "BELIEVES_WITHOUT_EVIDENCE",
                        "object_id": "project:x",
                        "confidence": 0.9,
                    }
                ],
            }
        }
        normalized = graph.normalize_graph_changes(changes)
        self.assertEqual([e["id"] for e in normalized["entities"]], ["person:self"])
        self.assertEqual(normalized["claims"], [])

    def test_finds_directed_path(self) -> None:
        changes = {
            "graph_changes": {
                "entities": [
                    {"id": "person:self", "type": "person", "label": "User"},
                    {"id": "project:x", "type": "project", "label": "X"},
                    {"id": "concept:memory", "type": "concept", "label": "Memory"},
                ],
                "claims": [
                    {"subject_id": "person:self", "predicate": "WORKS_ON", "object_id": "project:x", "confidence": 1},
                    {"subject_id": "project:x", "predicate": "RELATED_TO", "object_id": "concept:memory", "confidence": 0.8},
                ],
            }
        }
        graph.apply_observation_graph("obs-path", self.observation, changes, memory_dir=self.root)
        path = graph.find_path("person:self", "concept:memory", memory_dir=self.root)
        self.assertEqual([edge["predicate"] for edge in path], ["WORKS_ON", "RELATED_TO"])

    def test_compaction_summarizes_raw_payload_and_caps_evidence(self) -> None:
        clock = datetime(2026, 9, 3, tzinfo=timezone.utc)
        for index in range(4):
            graph.apply_observation_graph(
                f"obs-{index}", self.observation, self.changes, memory_dir=self.root
            )
        old = (clock - timedelta(days=60)).isoformat()
        with graph._connect(self.root) as db:
            db.execute("UPDATE observations SET created_at=?", (old,))
        result = graph.compact_graph(
            memory_dir=self.root,
            raw_retention_days=30,
            evidence_per_claim=2,
            orphan_retention_days=7,
            now=clock,
        )
        self.assertEqual(result["payloads_compacted"], 4)
        self.assertEqual(result["evidence_pruned"], 2)
        self.assertEqual(result["observations_deleted"], 2)
        with graph._connect(self.root) as db:
            rows = db.execute("SELECT payload_json FROM observations").fetchall()
            evidence = db.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0]
        self.assertEqual(len(rows), 2)
        self.assertEqual(evidence, 2)
        self.assertTrue(all(json.loads(row[0])["compacted"] for row in rows))

    def test_automatic_compaction_uses_write_interval(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ", {"MEMORY_GRAPH_COMPACT_EVERY": "2"}
        ):
            graph.apply_observation_graph("obs-a", self.observation, {}, memory_dir=self.root)
            graph.apply_observation_graph("obs-b", self.observation, {}, memory_dir=self.root)
        with graph._connect(self.root) as db:
            value = db.execute(
                "SELECT value FROM graph_meta WHERE key='writes_since_compact'"
            ).fetchone()[0]
            compacted = db.execute(
                "SELECT value FROM graph_meta WHERE key='last_compacted_at'"
            ).fetchone()
        self.assertEqual(value, "0")
        self.assertIsNotNone(compacted)


if __name__ == "__main__":
    unittest.main()
