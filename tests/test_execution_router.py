from unittest.mock import patch

from execution_router import resolve_execution_route


def test_weather_does_not_claim_a_maps_recipe() -> None:
    route = resolve_execution_route(
        "Open Google Chrome and search current weather for Mulki, Karnataka, India."
    )
    assert route.recipe != "open-google-maps"
    assert route.lane == "integration"


def test_recipe_routes_to_fast_browser_lane() -> None:
    fake = (type("Recipe", (), {"name": "open-google-maps"})(), {}, "")
    with patch("recipes.find_matching_recipe", return_value=fake):
        route = resolve_execution_route("show national parks on Google Maps")
    assert route.path == "fast"
    assert route.lane == "browser"
    assert route.recipe == "open-google-maps"


def test_git_routes_to_terminal_fast_path() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("merge the feature branch into main")
    assert route.path == "fast"
    assert route.lane == "terminal"


def test_dense_cad_routes_to_visual_slow_path() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("route the PCB in EasyEDA")
    assert route.path == "slow"
    assert route.lane == "visual"


def test_browser_submission_uses_slow_path() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("fill and submit the website form")
    assert route.path == "slow"
    assert route.lane in {"browser", "visual"}


def test_prompt_block_names_path_and_lane() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        block = resolve_execution_route("open Notes").prompt_block()
    assert "path: fast" in block
    assert "specialist lane: desktop" in block
    assert "difficulty: easy" in block
    assert "safety verifier" in block
    assert "completion verifier" in block


def test_research_routes_to_research_lane() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("research and compare local speech models")
    assert route.path == "fast"
    assert route.lane == "research"
    assert route.difficulty == "easy"


def test_difficulty_fast_is_easy() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("open Notes")
    assert route.difficulty == "easy"


def test_difficulty_pcb_is_hard() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        route = resolve_execution_route("route the PCB in EasyEDA")
    assert route.difficulty == "hard"


def test_difficulty_form_and_unknown_are_medium() -> None:
    with patch("recipes.find_matching_recipe", return_value=None):
        form = resolve_execution_route("fill and submit the website form")
        unknown = resolve_execution_route("do the thing on the desktop")
    assert form.difficulty == "medium"
    assert unknown.difficulty == "medium"
