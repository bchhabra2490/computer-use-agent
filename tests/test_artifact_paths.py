from pathlib import Path
from unittest.mock import patch

from artifact_paths import default_output_dir, ensure_output_dir, output_rule
from context import format_not_to_do


def test_default_output_dir_is_documents_folder() -> None:
    with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home", return_value=Path("/Users/test")):
        assert default_output_dir() == Path("/Users/test/Documents/Computer Use Agent")


def test_env_overrides_default_output_dir() -> None:
    with patch.dict("os.environ", {"AGENT_OUTPUT_DIR": "~/Exports"}, clear=True), patch(
        "pathlib.Path.home", return_value=Path("/Users/test")
    ):
        assert default_output_dir() == Path("/Users/test/Exports")


def test_ensure_output_dir_creates_folder(tmp_path: Path) -> None:
    target = tmp_path / "Computer Use Agent"
    with patch.dict("os.environ", {"AGENT_OUTPUT_DIR": str(target)}, clear=True):
        assert ensure_output_dir() == target
        assert target.is_dir()


def test_output_rule_covers_generated_images_and_explicit_override() -> None:
    rule = output_rule()
    assert "PNG" in rule
    assert "SVG" in rule
    assert "explicitly specifies a different destination" in rule


def test_always_on_policy_includes_output_rule(tmp_path: Path) -> None:
    policy = tmp_path / "policy.md"
    policy.write_text("# Policy\n\n- Keep safe.\n", encoding="utf-8")
    text = format_not_to_do(path=policy)
    assert "Documents/Computer Use Agent" in text
    assert "Desktop/Downloads" in text

