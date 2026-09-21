"""Offline tests for structured Accessibility snapshots (Jev step 2)."""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import accessibility as ax
from jev.models import ElementFrame, UIElement


@dataclass
class FakeApp:
    name: str = "Notes"
    bundle: str = "com.apple.Notes"
    pid: int = 4242

    def localizedName(self) -> str:
        return self.name

    def bundleIdentifier(self) -> str:
        return self.bundle

    def processIdentifier(self) -> int:
        return self.pid


@dataclass
class FakeNode:
    role: str = "AXGroup"
    title: str = ""
    value: str = ""
    description: str = ""
    label: str = ""
    subrole: str = ""
    enabled: bool = True
    focused: bool = False
    selected: bool = False
    frame: tuple[float, float, float, float] | None = None
    actions: tuple[str, ...] = ()
    children: list[FakeNode] = field(default_factory=list)
    contents: list[FakeNode] = field(default_factory=list)


def _fake_ax_get(element: Any, attr: str) -> Any:
    if not isinstance(element, FakeNode):
        return None
    mapping = {
        "AXRole": element.role,
        "AXSubrole": element.subrole,
        "AXTitle": element.title,
        "AXValue": element.value,
        "AXDescription": element.description,
        "AXLabel": element.label,
        "AXHelp": "",
        "AXRoleDescription": "",
        "AXEnabled": element.enabled,
        "AXFocused": element.focused,
        "AXSelected": element.selected,
        "AXChildren": list(element.children),
        "AXContents": list(element.contents) if element.contents else None,
        "AXActions": list(element.actions) if element.actions else None,
        "AXWindows": None,
        "AXMainWindow": None,
        "AXFocusedWindow": None,
        "AXFocusedUIElement": None,
    }
    return mapping.get(attr)


def _fake_ax_frame(element: Any) -> tuple[float, float, float, float] | None:
    if isinstance(element, FakeNode):
        return element.frame
    return None


def _fake_actions(element: Any) -> tuple[str, ...]:
    if isinstance(element, FakeNode):
        return tuple(element.actions)
    return ()


def _build_root(*, focused: FakeNode | None = None) -> FakeNode:
    password = FakeNode(
        role="AXSecureTextField",
        title="Password",
        value="hunter2-secret",
        frame=(10, 10, 120, 24),
        actions=("AXConfirm",),
    )
    button = FakeNode(
        role="AXButton",
        title="Save",
        frame=(20, 50, 80, 28),
        actions=("AXPress",),
        focused=focused is not None and focused.role == "AXButton",
    )
    link = FakeNode(
        role="AXLink",
        title="Docs",
        frame=(110, 50, 60, 20),
        actions=("AXPress",),
    )
    field = FakeNode(
        role="AXTextField",
        title="Name",
        value="Ada",
        frame=(10, 90, 160, 24),
        actions=("AXConfirm",),
        focused=focused is not None and focused.role == "AXTextField",
    )
    static = FakeNode(
        role="AXStaticText",
        value="Nearby hint",
        frame=(10, 130, 100, 16),
    )
    checkbox = FakeNode(
        role="AXCheckBox",
        title="Remember",
        value="1",
        selected=True,
        frame=(10, 160, 100, 20),
        actions=("AXPress",),
    )
    if focused is not None and focused.role == "AXTextField":
        field = focused
    elif focused is not None and focused.role == "AXButton":
        button = focused

    window = FakeNode(
        role="AXWindow",
        title="Login",
        children=[password, button, link, field, static, checkbox],
    )
    root = FakeNode(
        role="AXApplication",
        title="Notes",
        children=[window],
    )
    # Attach window/focus attributes via monkey side-channel on the root.
    root._main_window = window  # type: ignore[attr-defined]
    root._focused = field if focused is None else focused  # type: ignore[attr-defined]
    return root


def _ax_get_with_root(root: FakeNode):
    def getter(element: Any, attr: str) -> Any:
        if element is root and attr == "AXMainWindow":
            return root._main_window  # type: ignore[attr-defined]
        if element is root and attr == "AXWindows":
            return [root._main_window]  # type: ignore[attr-defined]
        if element is root and attr == "AXFocusedUIElement":
            return root._focused  # type: ignore[attr-defined]
        if element is root and attr == "AXFocusedWindow":
            return root._main_window  # type: ignore[attr-defined]
        if (
            isinstance(element, FakeNode)
            and attr == "AXTitle"
            and element is root._main_window
        ):
            return element.title
        return _fake_ax_get(element, attr)

    return getter


class CaptureUiSnapshotTests(unittest.TestCase):
    def _patch_tree(self, root: FakeNode, app: FakeApp | None = None):
        app = app or FakeApp()
        return (
            patch.object(ax, "accessibility_available", return_value=(True, "ok")),
            patch.object(ax, "_find_app", return_value=app),
            patch.object(ax, "_create_app_element", return_value=root),
            patch.object(ax, "_ax_get", side_effect=_ax_get_with_root(root)),
            patch.object(ax, "_ax_frame", side_effect=_fake_ax_frame),
            patch.object(ax, "_ax_action_names", side_effect=_fake_actions),
        )

    def test_actionable_elements_frames_and_actions(self) -> None:
        root = _build_root()
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            snap = ax.capture_ui_snapshot(max_nodes=50, max_depth=8)
        self.assertTrue(snap.available)
        self.assertEqual(snap.app_name, "Notes")
        self.assertEqual(snap.bundle_id, "com.apple.Notes")
        self.assertEqual(snap.process_id, 4242)
        self.assertEqual(snap.window_title, "Login")
        roles = {el.role for el in snap.elements}
        self.assertIn("AXButton", roles)
        self.assertIn("AXLink", roles)
        self.assertIn("AXTextField", roles)
        self.assertIn("AXSecureTextField", roles)
        self.assertIn("AXCheckBox", roles)
        self.assertIn("AXStaticText", roles)
        button = next(el for el in snap.elements if el.role == "AXButton")
        self.assertEqual(button.label, "Save")
        self.assertIsNotNone(button.frame)
        self.assertEqual(button.frame.width, 80)  # type: ignore[union-attr]
        self.assertIn("AXPress", button.supported_actions)
        self.assertTrue(all(el.id.startswith("ax_") for el in snap.elements))
        self.assertNotIn("0x", ",".join(el.id for el in snap.elements))

    def test_focused_element_detection(self) -> None:
        focused = FakeNode(
            role="AXTextField",
            title="Name",
            value="Ada",
            frame=(10, 90, 160, 24),
            actions=("AXConfirm",),
            focused=True,
        )
        root = _build_root(focused=focused)
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            snap = ax.capture_ui_snapshot()
        self.assertIsNotNone(snap.focused_element_id)
        focused_el = next(
            el for el in snap.elements if el.id == snap.focused_element_id
        )
        self.assertTrue(focused_el.focused)
        self.assertEqual(focused_el.role, "AXTextField")

    def test_secure_field_redaction(self) -> None:
        root = _build_root()
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            snap = ax.capture_ui_snapshot()
        secure = next(el for el in snap.elements if el.role == "AXSecureTextField")
        self.assertTrue(secure.sensitive)
        self.assertEqual(secure.value, "")
        self.assertNotIn("hunter2", repr(secure))
        public = snap.to_public_dict()
        blob = json.dumps(public)
        self.assertNotIn("hunter2", blob)
        secure_public = next(
            e for e in public["elements"] if e["role"] == "AXSecureTextField"
        )
        self.assertEqual(secure_public["value"], "")

    def test_native_handles_excluded_from_serialization(self) -> None:
        root = _build_root()
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            snap = ax.capture_ui_snapshot()
        self.assertGreater(snap.handle_count, 0)
        button = next(el for el in snap.elements if el.role == "AXButton")
        handle = snap.get_handle(button.id)
        self.assertIsInstance(handle, FakeNode)
        public = snap.to_public_dict()
        self.assertNotIn("_handles", public)
        self.assertNotIn("handles", public)
        self.assertNotIn(str(id(handle)), json.dumps(public))

    def test_stable_revision_and_change_detection(self) -> None:
        root = _build_root()
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            a = ax.capture_ui_snapshot()
            b = ax.capture_ui_snapshot()
        self.assertEqual(a.revision, b.revision)
        self.assertGreater(a.revision, 0)

        # Meaningful change: button label.
        button = root._main_window.children[1]  # type: ignore[attr-defined]
        button.title = "Cancel"
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            c = ax.capture_ui_snapshot()
        self.assertNotEqual(a.revision, c.revision)

    def test_empty_tree(self) -> None:
        root = FakeNode(role="AXApplication", title="Empty")
        root._main_window = None  # type: ignore[attr-defined]
        root._focused = None  # type: ignore[attr-defined]

        def getter(element: Any, attr: str) -> Any:
            if element is root and attr in {
                "AXMainWindow",
                "AXFocusedUIElement",
                "AXFocusedWindow",
            }:
                return None
            if element is root and attr == "AXWindows":
                return []
            return _fake_ax_get(element, attr)

        app = FakeApp(name="EmptyApp")
        with (
            patch.object(ax, "accessibility_available", return_value=(True, "ok")),
            patch.object(ax, "_find_app", return_value=app),
            patch.object(ax, "_create_app_element", return_value=root),
            patch.object(ax, "_ax_get", side_effect=getter),
            patch.object(ax, "_ax_frame", return_value=None),
            patch.object(ax, "_ax_action_names", return_value=()),
        ):
            snap = ax.capture_ui_snapshot()
        self.assertTrue(snap.available)
        self.assertEqual(snap.elements, ())
        self.assertEqual(snap.app_name, "EmptyApp")

    def test_node_and_depth_limits(self) -> None:
        kids = [
            FakeNode(
                role="AXButton",
                title=f"B{i}",
                frame=(float(i), 0, 10, 10),
                actions=("AXPress",),
            )
            for i in range(20)
        ]
        # Depth 1 visits the window and its direct children; nest buttons deeper.
        group = FakeNode(role="AXGroup", children=kids)
        window = FakeNode(role="AXWindow", title="Many", children=[group])
        root = FakeNode(role="AXApplication", children=[window])
        root._main_window = window  # type: ignore[attr-defined]
        root._focused = None  # type: ignore[attr-defined]
        patches = self._patch_tree(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            snap = ax.capture_ui_snapshot(max_nodes=5, max_depth=8)
        self.assertLessEqual(len(snap.elements), 5)

        # max_depth is clamped to >= 1 (same as read_ui_text): window + group only.
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            shallow = ax.capture_ui_snapshot(max_nodes=50, max_depth=1)
        self.assertTrue(all(el.role != "AXButton" for el in shallow.elements))

    def test_unavailable_accessibility(self) -> None:
        with patch.object(
            ax,
            "accessibility_available",
            return_value=(False, "Accessibility permission not granted."),
        ):
            snap = ax.capture_ui_snapshot()
        self.assertFalse(snap.available)
        self.assertIn("permission", snap.error.lower())
        self.assertEqual(snap.elements, ())

    def test_missing_app(self) -> None:
        with (
            patch.object(ax, "accessibility_available", return_value=(True, "ok")),
            patch.object(ax, "_find_app", return_value=None),
        ):
            snap = ax.capture_ui_snapshot(app="NoSuchApp")
        self.assertFalse(snap.available)
        self.assertIn("no running app matched", snap.error)

    def test_snapshot_revision_helper_ignores_sensitive_values(self) -> None:
        el = UIElement(
            id="ax_1",
            role="AXSecureTextField",
            label="Password",
            value="",
            sensitive=True,
            frame=ElementFrame(1, 2, 3, 4),
        )
        rev = ax.snapshot_revision(
            app_name="A",
            bundle_id="b",
            window_title="W",
            focused_element_id=None,
            elements=(el,),
        )
        # Fingerprint must not depend on a leaked secret (value stays empty).
        el2 = UIElement(
            id="ax_1",
            role="AXSecureTextField",
            label="Password",
            value="should-not-matter",
            sensitive=True,
            frame=ElementFrame(1, 2, 3, 4),
        )
        rev2 = ax.snapshot_revision(
            app_name="A",
            bundle_id="b",
            window_title="W",
            focused_element_id=None,
            elements=(el2,),
        )
        self.assertEqual(rev, rev2)


class ReadUiTextCompatTests(unittest.TestCase):
    def test_read_ui_text_still_returns_text_report(self) -> None:
        button = FakeNode(role="AXButton", title="OK", frame=(0, 0, 40, 20))
        window = FakeNode(role="AXWindow", title="Dialog", children=[button])
        root = FakeNode(role="AXApplication", children=[window])
        root._main_window = window  # type: ignore[attr-defined]
        root._focused = button  # type: ignore[attr-defined]
        app = FakeApp()

        def getter(element: Any, attr: str) -> Any:
            if element is root and attr == "AXMainWindow":
                return window
            if element is root and attr == "AXWindows":
                return [window]
            if element is root and attr == "AXFocusedUIElement":
                return button
            return _fake_ax_get(element, attr)

        with (
            patch.object(ax, "accessibility_available", return_value=(True, "ok")),
            patch.object(ax, "_find_app", return_value=app),
            patch.object(ax, "_create_app_element", return_value=root),
            patch.object(ax, "_ax_get", side_effect=getter),
            patch.object(ax, "_ax_frame", side_effect=_fake_ax_frame),
        ):
            text = ax.read_ui_text(max_nodes=50, max_depth=8)
        self.assertIn("App: Notes", text)
        self.assertIn("[AXButton]", text)
        self.assertIn('title="OK"', text)
        self.assertIn("Focused:", text)

    def test_read_ui_text_error_when_unavailable(self) -> None:
        with patch.object(
            ax,
            "accessibility_available",
            return_value=(False, "Accessibility permission not granted."),
        ):
            text = ax.read_ui_text()
        self.assertTrue(text.startswith("Error:"))


class FocusedEditInfoCompatTests(unittest.TestCase):
    def test_focused_edit_info_secure(self) -> None:
        secure = FakeNode(role="AXSecureTextField", title="Password", value="x")
        root = FakeNode(role="AXApplication")
        app = FakeApp()

        def getter(element: Any, attr: str) -> Any:
            if element is root and attr == "AXFocusedUIElement":
                return secure
            return _fake_ax_get(element, attr)

        with (
            patch.object(ax, "accessibility_available", return_value=(True, "ok")),
            patch.object(ax, "_frontmost_app", return_value=app),
            patch.object(ax, "_create_app_element", return_value=root),
            patch.object(ax, "_ax_get", side_effect=getter),
        ):
            info = ax.focused_edit_info()
        self.assertTrue(info["secure"])
        self.assertFalse(info["editable"])
        self.assertEqual(info["role"], "AXSecureTextField")


if __name__ == "__main__":
    unittest.main()
