"""Accuracy-first fastlane: deterministic + local tool routes."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fastlane as fl  # noqa: E402


SAMPLE_NODES = [
    {
        "node": "office",
        "name": "Office board",
        "online": True,
        "components": {
            "lamp": {"id": "lamp", "type": "relay", "actions": ["on", "off"], "state": "off"},
            "fan": {"id": "fan", "type": "relay", "actions": ["on", "off"], "state": "off"},
        },
    }
]


class FastlaneParseTests(unittest.TestCase):
    def setUp(self) -> None:
        fl.clear_catalog_cache()
        self.devices = fl.parse_devices_payload({"ok": True, "nodes": SAMPLE_NODES})

    def test_lane_a_office_lamp_off(self) -> None:
        hit = fl.match_lane_a("Turn off the office lamp now.", self.devices)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.lane, "A")
        self.assertEqual(hit.node, "office")
        self.assertEqual(hit.component, "lamp")
        self.assertEqual(hit.action, "off")

    def test_lane_a_office_light_on(self) -> None:
        hit = fl.match_lane_a("turn on the office light", self.devices)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.component, "lamp")
        self.assertEqual(hit.action, "on")

    def test_ambiguous_lamp_falls_through(self) -> None:
        # Two lamps → "the lamp" is ambiguous
        nodes = [
            SAMPLE_NODES[0],
            {
                "node": "lab",
                "name": "Lab board",
                "online": True,
                "components": {
                    "lamp": {"id": "lamp", "actions": ["on", "off"]},
                },
            },
        ]
        devices = fl.parse_devices_payload({"ok": True, "nodes": nodes})
        self.assertIsNone(fl.match_lane_a("turn off the lamp", devices))

    def test_complex_falls_through(self) -> None:
        self.assertIsNone(
            fl.match_lane_a("turn off the office lamp and then dim it", self.devices)
        )
        self.assertIsNone(
            fl.match_lane_a("why is the office lamp on", self.devices)
        )

    def test_offline_falls_through(self) -> None:
        nodes = [
            {
                "node": "office",
                "name": "Office board",
                "online": False,
                "components": {"lamp": {"id": "lamp", "actions": ["on", "off"]}},
            }
        ]
        devices = fl.parse_devices_payload({"ok": True, "nodes": nodes})
        self.assertIsNone(fl.match_lane_a("turn off the office lamp", devices))

    def test_execute_success(self) -> None:
        hit = fl.FastHit("A", "office", "lamp", "off", "OK")

        def execute(server, tool, arguments):
            self.assertEqual(server, "hardware")
            self.assertEqual(tool, "control_hardware")
            return json.dumps({"ok": True, "state": "off"})

        ok, spoken = fl.execute_hit(hit, execute=execute)
        self.assertTrue(ok)
        self.assertIn("off", spoken)

    def test_execute_failure_does_not_claim_success(self) -> None:
        hit = fl.FastHit("A", "office", "lamp", "off", "OK")

        def execute(server, tool, arguments):
            return json.dumps({"ok": False, "message": "broker_unreachable"})

        ok, spoken = fl.execute_hit(hit, execute=execute)
        self.assertFalse(ok)
        self.assertIn("Could not", spoken)

    def test_lane_b_validates_catalog(self) -> None:
        payload = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "control_hardware",
                            "arguments": {
                                "node": "office",
                                "component": "lamp",
                                "action": "on",
                            },
                        }
                    }
                ],
            }
        }
        with (
            patch.object(fl, "FASTLANE", True),
            patch.object(fl, "FASTLANE_LOCAL", True),
            patch.object(fl, "_ollama_chat", return_value=payload),
        ):
            hit = fl.match_lane_b("flip the office lamp please", self.devices)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.lane, "B")
        self.assertEqual(hit.action, "on")

    def test_lane_b_rejects_unknown_device(self) -> None:
        payload = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "control_hardware",
                            "arguments": {
                                "node": "garage",
                                "component": "lamp",
                                "action": "on",
                            },
                        }
                    }
                ],
            }
        }
        with (
            patch.object(fl, "FASTLANE", True),
            patch.object(fl, "FASTLANE_LOCAL", True),
            patch.object(fl, "_ollama_chat", return_value=payload),
        ):
            self.assertIsNone(fl.match_lane_b("turn on garage lamp", self.devices))

    def test_lane_b_rejects_unsure(self) -> None:
        payload = {"message": {"role": "assistant", "content": "UNSURE"}}
        with (
            patch.object(fl, "FASTLANE", True),
            patch.object(fl, "FASTLANE_LOCAL", True),
            patch.object(fl, "_ollama_chat", return_value=payload),
        ):
            self.assertIsNone(fl.match_lane_b("do something with the light", self.devices))

    def test_list_format_components(self) -> None:
        nodes = [
            {
                "node": "office",
                "name": "Office board",
                "online": True,
                "components": [
                    {"id": "lamp", "type": "relay", "actions": ["on", "off"], "state": "off"}
                ],
            }
        ]
        devices = fl.parse_devices_payload({"ok": True, "nodes": nodes})
        hit = fl.match_lane_a("turn on office lamp", devices)
        self.assertIsNotNone(hit)

        with patch.object(fl, "load_catalog", return_value=self.devices):
            hit = fl.try_fastlane("turn off the office lamp")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.lane, "A")


if __name__ == "__main__":
    unittest.main()
