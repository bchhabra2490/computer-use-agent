"""LLM-as-judge: fixture scoring (tests) and post-run log scoring."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import judge  # noqa: E402
from task_log import TaskLog  # noqa: E402


def _client(payload: dict) -> MagicMock:
    response = MagicMock()
    response.output_text = json.dumps(payload)
    response.output = []
    client = MagicMock()
    client.responses.create.return_value = response
    return client


class TestJudgeTests(unittest.TestCase):
    def test_parse_verdict_normalizes_scores(self) -> None:
        verdict = judge.parse_verdict(
            {
                "pass": True,
                "scores": {"goal": 9, "routing": "3", "tools": None},
                "findings": [" invented tool ", ""],
                "improvements": ["use open-meteo skill"],
            }
        )
        self.assertTrue(verdict.ok)
        self.assertTrue(verdict.pass_)
        self.assertEqual(verdict.scores["goal"], 5)
        self.assertEqual(verdict.scores["routing"], 3)
        self.assertEqual(verdict.scores["tools"], 0)
        self.assertEqual(verdict.findings, ["invented tool"])

    def test_fixture_invented_maps_tool_is_flagged(self) -> None:
        artifact = judge.load_fixture("invented_maps_tool.json")
        self.assertIn("open-google-maps", json.dumps(artifact))
        client = _client(
            {
                "pass": False,
                "scores": {
                    "goal": 2,
                    "routing": 0,
                    "tools": 0,
                    "looping": 5,
                    "safety": 5,
                },
                "findings": ["invented tool open-google-maps instead of weather skill"],
                "improvements": ["route weather to open-meteo-current-weather-report"],
            }
        )
        verdict = judge.score_artifact(artifact, client=client)
        self.assertTrue(verdict.ok)
        self.assertFalse(verdict.pass_)
        self.assertEqual(verdict.scores["routing"], 0)
        self.assertTrue(any("open-google-maps" in item for item in verdict.findings))
        client.responses.create.assert_called_once()
        prompt = str(client.responses.create.call_args.kwargs.get("input") or "")
        self.assertIn("open-google-maps", prompt)
        self.assertIn("Hyderabad", prompt)


class PostRunJudgeTests(unittest.TestCase):
    def test_score_run_dir_writes_judge_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog("What's the current weather in Hyderabad", logs_dir=Path(tmp))
            log.record(
                "message",
                "start_task",
                {"name": "open-google-maps"},
            )
            with patch.dict("os.environ", {"POST_RUN_JUDGE": "0"}, clear=False):
                log.finish("completed")
            client = _client(
                {
                    "pass": False,
                    "scores": {
                        "goal": 1,
                        "routing": 0,
                        "tools": 0,
                        "looping": 5,
                        "safety": 5,
                    },
                    "findings": ["wrong tool"],
                    "improvements": ["use Open-Meteo skill"],
                }
            )
            verdict = judge.score_run_dir(log.dir, client=client)
            self.assertTrue(verdict.ok)
            self.assertFalse(verdict.pass_)
            saved = json.loads((log.dir / "judge.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["pass"])
            self.assertEqual(saved["improvements"], ["use Open-Meteo skill"])

    def test_finish_schedules_post_run_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog("Open Notes", logs_dir=Path(tmp))
            with (
                patch.dict("os.environ", {"POST_RUN_JUDGE": "1"}, clear=False),
                patch("judge.schedule_post_run_judge") as scheduled,
            ):
                log.finish("completed")
            scheduled.assert_called_once()
            self.assertEqual(Path(scheduled.call_args.args[0]), log.dir)

    def test_finish_skips_post_run_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog("Open Notes", logs_dir=Path(tmp))
            with (
                patch.dict("os.environ", {"POST_RUN_JUDGE": "0"}, clear=False),
                patch("judge.schedule_post_run_judge") as scheduled,
            ):
                log.finish("completed")
            scheduled.assert_not_called()

    def test_schedule_does_not_raise_on_score_failure(self) -> None:
        started = MagicMock()

        def boom(*_args, **_kwargs):
            started()
            raise RuntimeError("judge down")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict("os.environ", {"POST_RUN_JUDGE": "1"}, clear=False),
                patch.object(judge, "score_run_dir", side_effect=boom),
            ):
                judge.schedule_post_run_judge(tmp)
                for _ in range(50):
                    if started.called:
                        break
                    import time

                    time.sleep(0.01)
            self.assertTrue(started.called)

    def test_load_run_dir_includes_prompts_tools_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog(
                "What's the weather in Hyderabad",
                logs_dir=Path(tmp),
                latency_trace_id="tid-judge",
            )
            log.record("message", "start_task", {"name": "open-google-maps"})
            with patch.dict("os.environ", {"POST_RUN_JUDGE": "0"}, clear=False):
                log.finish("completed")
            (log.dir / "llm_trace.jsonl").write_text(
                json.dumps(
                    {
                        "kind": "llm",
                        "lane": "agent",
                        "trace_id": "tid-judge",
                        "status": "ok",
                        "request": {
                            "model": "gpt-5-mini",
                            "instructions": "You are the computer agent. Prefer Open-Meteo.",
                            "input": "What's the weather in Hyderabad?",
                            "tools": [
                                {
                                    "name": "read_skill",
                                    "description": "Read a local skill file",
                                },
                                {"name": "open_url"},
                            ],
                        },
                        "response": {
                            "text": "",
                            "tool_calls": [
                                {
                                    "name": "open-google-maps",
                                    "arguments": '{"q":"Hyderabad"}',
                                }
                            ],
                        },
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "tool",
                        "name": "open-google-maps",
                        "status": "ok",
                        "args": {"q": "Hyderabad"},
                        "output": "opened Google Maps",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            artifact = judge.load_run_dir(log.dir)
            self.assertEqual(len(artifact["llm_trace"]), 2)
            prompt = judge._format_artifact(artifact)
            self.assertIn("You are the computer agent", prompt)
            self.assertIn("read_skill: Read a local skill file", prompt)
            self.assertIn("open-google-maps", prompt)
            self.assertIn("opened Google Maps", prompt)
            client = _client(
                {
                    "pass": False,
                    "scores": {
                        "goal": 1,
                        "routing": 0,
                        "tools": 0,
                        "looping": 5,
                        "safety": 5,
                    },
                    "findings": ["called open-google-maps which was not in the catalog"],
                    "improvements": ["use read_skill for Open-Meteo"],
                }
            )
            verdict = judge.score_artifact(artifact, client=client)
            self.assertTrue(verdict.ok)
            sent = str(client.responses.create.call_args.kwargs.get("input") or "")
            self.assertIn("Tools offered:", sent)
            self.assertIn("opened Google Maps", sent)


if __name__ == "__main__":
    unittest.main()
