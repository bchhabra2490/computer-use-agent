"""Parameterized recipes: match templates, bind slots, skip unsafe URLs."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from task_log import TaskLog  # noqa: E402
import recipes as rc  # noqa: E402


def _log(task: str, commands: list[str], *, clicks: int = 0) -> TaskLog:
    tmp = tempfile.TemporaryDirectory()
    log = TaskLog(task, logs_dir=Path(tmp.name))
    for command in commands:
        log.record("run_terminal", command[:80], {"command": command})
    for _ in range(clicks):
        log.record("computer_actions", "click", {"actions": [{"type": "click", "x": 1, "y": 1}]})
    log._tmp = tmp  # type: ignore[attr-defined]
    return log


class MatchTemplateTests(unittest.TestCase):
    def test_place_and_leftover(self) -> None:
        hit = rc.match_template(
            "map of {{place}}",
            "Open a map of India and zoom to the Ganges",
        )
        self.assertIsNotNone(hit)
        params, leftover = hit  # type: ignore[misc]
        self.assertEqual(params["place"], "India")
        self.assertEqual(leftover, "zoom to the Ganges")

    def test_query_between_literals(self) -> None:
        hit = rc.match_template("play {{query}} on youtube", "play lag ja gale on youtube")
        self.assertIsNotNone(hit)
        params, leftover = hit  # type: ignore[misc]
        self.assertEqual(params["query"], "lag ja gale")
        self.assertEqual(leftover, "")

    def test_youtube_brief_uses_song_not_playable_clause(self) -> None:
        prompt = (
            "(VEVO / official channel) or the highest-quality audio result and start "
            "playback. 3) Ensure the tab/audio is unmuted and system volume is at a "
            "normal listening level. 4) If YouTube is not playable, try YouTube Music; "
            "if that fails, open Apple Music and play the track. When playback begins, "
            'speak a short mid-task update: "Now playing Thunderstruck by AC/DC."'
        )
        self.assertEqual(rc.extract_media_query(prompt), "Thunderstruck AC/DC")
        self.assertFalse(rc._valid_slot("query", "is not playable"))

    def test_long_agent_prompt_does_not_swallow_place(self) -> None:
        prompt = (
            "Open Chrome and go to Google Maps and load the map for the country "
            "Togo (for example: https://www.google.com/maps/place/Togo). Wait for "
            "the map to finish loading; if it stalls, reload once. Pan/zoom so the "
            "entire country of Togo is visible at a comfortable zoom level. Make "
            "the Chrome window frontmost and centered on the primary display. "
            "Capture a screenshot of the map area and save it."
        )
        self.assertEqual(rc.extract_maps_place(prompt), "Togo")
        hit = rc.match_template("google maps {{place}}", prompt)
        self.assertTrue(hit is None or rc._valid_slot("place", hit[0]["place"]))
        if hit is not None:
            self.assertLessEqual(len(hit[0]["place"].split()), 8)


class UrlSafetyTests(unittest.TestCase):
    def test_blocks_javascript(self) -> None:
        with self.assertRaises(rc.RecipeError):
            rc._safe_http_url("javascript:alert(1)")

    def test_blocks_file(self) -> None:
        with self.assertRaises(rc.RecipeError):
            rc._safe_http_url("file:///etc/passwd")

    def test_apply_params_encodes_query(self) -> None:
        url = rc.apply_params(
            "https://www.google.com/maps/search/?api=1&query={{place}}",
            {"place": "New Delhi"},
            url=True,
        )
        self.assertIn("New%20Delhi", url)


class RecipeRunTests(unittest.TestCase):
    def test_maps_completes_without_handoff(self) -> None:
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(
                "Open a map of India",
                recipes_dir=_seed_dir(self),
                settle=0,
            )
        opener.assert_called_once()
        self.assertIsInstance(result, str)
        self.assertIn("completed", result)
        self.assertIn("maps/search", opener.call_args[0][0])
        self.assertIn("India", opener.call_args[0][0])

    def test_maps_handoff_on_leftover(self) -> None:
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(
                "Open a map of India and zoom to the Ganges",
                recipes_dir=_seed_dir(self),
                settle=0,
            )
        opener.assert_called_once()
        self.assertIsInstance(result, rc.RecipeHit)
        assert isinstance(result, rc.RecipeHit)
        prompt = rc.handoff_prompt("Open a map of India and zoom to the Ganges", result)
        self.assertIn("RECIPE HANDOFF", prompt)
        self.assertIn("checklist", prompt.lower())
        self.assertIn("ganges", prompt.lower())

    def test_long_maps_prompt_binds_togo(self) -> None:
        prompt = (
            "Open Chrome and go to Google Maps and load the map for the country "
            "Togo (for example: https://www.google.com/maps/place/Togo). Wait for "
            "the map to finish loading; if it stalls, reload once. Pan/zoom so the "
            "entire country of Togo is visible at a comfortable zoom level. Make "
            "the Chrome window frontmost and centered on the primary display. "
            "Capture a screenshot of the map area and save it."
        )
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(prompt, recipes_dir=_seed_dir(self), settle=0)
        opener.assert_called_once()
        opened = opener.call_args[0][0]
        self.assertIn("query=Togo", opened)
        self.assertNotIn("Wait", opened)
        self.assertIsInstance(result, rc.RecipeHit)
        assert isinstance(result, rc.RecipeHit)
        self.assertEqual(result.params["place"], "Togo")
        self.assertNotIn("create a new tab", (result.leftover or "").lower())

    def test_verify_fail_still_handoffs(self) -> None:
        with (
            patch.object(rc, "open_url"),
            patch.object(rc, "open_app"),
            patch.object(rc, "verify_recipe", return_value=False),
            patch.object(rc.time, "sleep"),
        ):
            result = rc.try_recipe(
                "Open a map of India and zoom to the Ganges",
                recipes_dir=_seed_dir(self),
                settle=0,
            )
        self.assertIsInstance(result, rc.RecipeHit)

    def test_orchestrator_brief_does_not_replay_new_tab(self) -> None:
        prompt = (
            "Open Google Chrome, create a new tab, and navigate to "
            "https://www.google.com/maps/place/Togo. Wait for the page to finish "
            "loading and ensure the map is centered on the country of Togo. "
            "Capture a screenshot of the map and stop."
        )
        with (
            patch.object(rc, "open_url"),
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(prompt, recipes_dir=_seed_dir(self), settle=0)
        self.assertIsInstance(result, rc.RecipeHit)
        assert isinstance(result, rc.RecipeHit)
        self.assertEqual(result.params["place"], "Togo")
        blob = (result.leftover or "").lower()
        self.assertNotIn("create a new tab", blob)
        self.assertIn("screenshot", blob)

    def test_open_notes_does_not_match_url_recipe(self) -> None:
        with patch.object(rc, "open_url") as opener:
            result = rc.try_recipe("open notes", recipes_dir=_seed_dir(self), settle=0)
        opener.assert_not_called()
        self.assertIsNone(result)

    def test_youtube_always_handoffs(self) -> None:
        with (
            patch.object(rc, "open_url"),
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(
                "play lag ja gale on youtube",
                recipes_dir=_seed_dir(self),
                settle=0,
            )
        self.assertIsInstance(result, rc.RecipeHit)

    def test_youtube_try_recipe_searches_thunderstruck(self) -> None:
        prompt = (
            "If YouTube is not playable, try YouTube Music; if that fails, open "
            "Apple Music and play the track. When playback begins, speak a short "
            'mid-task update: "Now playing Thunderstruck by AC/DC."'
        )
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(prompt, recipes_dir=_seed_dir(self), settle=0)
        opener.assert_called_once()
        self.assertIn("Thunderstruck", opener.call_args[0][0])
        self.assertNotIn("playable", opener.call_args[0][0])
        self.assertIsInstance(result, rc.RecipeHit)


class _FakeResponsesClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0
        self.last_input = ""
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        self.last_input = str(kwargs.get("input") or "")
        part = SimpleNamespace(type="output_text", text=json.dumps(self.payload))
        return SimpleNamespace(output=[SimpleNamespace(type="message", content=[part])])


class LlmFillTests(unittest.TestCase):
    def test_llm_fills_togo_not_the_brief(self) -> None:
        prompt = (
            "Open Chrome and go to Google Maps and load the map for the country "
            "Togo (for example: https://www.google.com/maps/place/Togo). Wait for "
            "the map to finish loading; if it stalls, reload once."
        )
        client = _FakeResponsesClient(
            {"params": {"place": "Togo"}, "leftover": "screenshot the existing window"}
        )
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(
                prompt,
                recipes_dir=_seed_dir(self),
                settle=0,
                client=client,
            )
        self.assertEqual(client.calls, 1)
        self.assertIn("Togo", client.last_input)
        opener.assert_called_once()
        self.assertIn("query=Togo", opener.call_args[0][0])
        self.assertIsInstance(result, rc.RecipeHit)
        assert isinstance(result, rc.RecipeHit)
        self.assertEqual(result.params["place"], "Togo")

    def test_bad_llm_slot_falls_back_to_regex(self) -> None:
        prompt = (
            "If YouTube is not playable, try YouTube Music. "
            'When playback begins, speak: "Now playing Thunderstruck by AC/DC."'
        )
        client = _FakeResponsesClient(
            {"params": {"query": "is not playable"}, "leftover": ""}
        )
        with (
            patch.object(rc, "open_url") as opener,
            patch.object(rc, "verify_recipe", return_value=True),
        ):
            result = rc.try_recipe(
                prompt,
                recipes_dir=_seed_dir(self),
                settle=0,
                client=client,
            )
        self.assertEqual(client.calls, 1)
        opener.assert_called_once()
        self.assertIn("Thunderstruck", opener.call_args[0][0])
        self.assertNotIn("playable", opener.call_args[0][0])
        self.assertIsInstance(result, rc.RecipeHit)


class ProposeTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in list(self.__dict__):
            val = getattr(self, name)
            if isinstance(val, TaskLog) and hasattr(val, "_tmp"):
                val._tmp.cleanup()

    def test_heuristic_parameterizes_maps_url(self) -> None:
        log = _log(
            "Open a map of India",
            ['open "https://www.google.com/maps/search/?api=1&query=India"'],
        )
        self.addCleanup(log._tmp.cleanup)
        recipe = rc.propose_recipe_from_log("Open a map of India", log)
        self.assertIsNotNone(recipe)
        assert recipe is not None
        self.assertIn("{{place}}", recipe.prelude[0]["url"])
        self.assertFalse(recipe.handoff)

    def test_heuristic_handoff_when_clicks_follow(self) -> None:
        log = _log(
            "Open a map of India",
            ['open "https://www.google.com/maps/search/?api=1&query=India"'],
            clicks=1,
        )
        self.addCleanup(log._tmp.cleanup)
        recipe = rc.propose_recipe_from_log("Open a map of India", log)
        self.assertTrue(recipe and recipe.handoff)

    def test_skip_save_when_existing_matches(self) -> None:
        log = _log("Open a map of France", ['open "https://example.com"'])
        self.addCleanup(log._tmp.cleanup)
        path = rc._maybe_save_recipe_impl(
            None,
            log,
            "Open a map of France",
            recipes_dir=_seed_dir(self),
        )
        self.assertIsNone(path)


def _seed_dir(test: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    (root / "google-maps-place.json").write_text(
        __import__("json").dumps(
            {
                "name": "google-maps-place",
                "match_templates": ["map of {{place}}", "{{place}} on a map"],
                "params": ["place"],
                "prelude": [
                    {
                        "type": "open_url",
                        "url": "https://www.google.com/maps/search/?api=1&query={{place}}",
                    }
                ],
                "handoff": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "youtube-search.json").write_text(
        __import__("json").dumps(
            {
                "name": "youtube-search",
                "match_templates": ["play {{query}} on youtube", "{{query}} on youtube"],
                "params": ["query"],
                "prelude": [
                    {
                        "type": "open_url",
                        "url": "https://www.youtube.com/results?search_query={{query}}",
                    }
                ],
                "handoff": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "open-http-url.json").write_text(
        __import__("json").dumps(
            {
                "name": "open-http-url",
                "match": ["open"],
                "params": ["url"],
                "prelude": [{"type": "open_url", "url": "{{url}}"}],
                "handoff": False,
            }
        ),
        encoding="utf-8",
    )
    return root


if __name__ == "__main__":
    unittest.main()
