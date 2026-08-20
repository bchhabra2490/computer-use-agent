"""web_search combines DDG instant answers + HTML results."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools_registry as tr  # noqa: E402
import web_search as ws  # noqa: E402


class WebSearchTests(unittest.TestCase):
    def test_empty_query(self) -> None:
        self.assertIn("query is required", ws.search_web("  "))

    def test_json_answer(self) -> None:
        payload = json.dumps({"Answer": "32 C", "AbstractText": "", "RelatedTopics": []})
        html = (
            '<a class="result__a" href="https://example.com/w">Mohali weather</a>'
            '<a class="result__snippet">High 34 Low 24</a>'
        )
        with patch(
            "web_search.fetch_https",
            side_effect=["Mohali: +32C", payload, html],
        ):
            out = ws.search_web("Mohali weather")
        self.assertIn("32 C", out)
        self.assertIn("Mohali weather", out)

    def test_currency_fallback(self) -> None:
        fx = json.dumps({"amount": 1.0, "base": "USD", "date": "2026-08-19", "rates": {"INR": 95.76}})
        with patch("web_search.fetch_https", side_effect=[fx, "{}", "blocked page"]):
            out = ws.search_web("USD to INR exchange rate today")
        self.assertIn("95.76", out)
        self.assertIn("USD", out)
        self.assertIn("INR", out)

    def test_weather_fallback(self) -> None:
        with patch(
            "web_search.fetch_https",
            side_effect=["Mohali: +30°C", "{}", "blocked"],
        ) as fetch:
            out = ws.search_web("Mohali weather today")
        self.assertIn("Mohali", out)
        self.assertIn("30", out)
        fetch.assert_any_call(
            "https://wttr.in/Mohali?format=3",
            max_chars=500,
            strip_html=False,
            user_agent=ws._WTTR_UA,
        )

    def test_usd_and_inr_phrasing(self) -> None:
        fx = json.dumps({"amount": 1.0, "base": "USD", "date": "2026-08-19", "rates": {"INR": 95.76}})
        with patch("web_search.fetch_https", side_effect=[fx, "{}", "blocked"]):
            out = ws.search_web("what's the conversion rate today of USD and INR")
        self.assertIn("95.76", out)

    def test_shared_dispatch(self) -> None:
        with patch("web_search.search_web", return_value="1. ok") as search:
            out = tr.run_shared_tool("web_search", {"query": "mohali weather", "max_results": 5})
        self.assertEqual(out, "1. ok")
        search.assert_called_once()
