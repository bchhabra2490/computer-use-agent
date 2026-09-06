"""Pytest defaults: do not write LLM traces or contact Phoenix."""

from __future__ import annotations

import os

os.environ["LLM_TRACE"] = "0"
os.environ["PHOENIX"] = "0"
