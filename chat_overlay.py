"""Floating desktop chat window (macOS AppKit).

Sidebar of saved chats, model popup, Claude-style composer (screenshot / mic / send icons).
History lives in SQLite (``chat_store``); screenshots under ``.runtime/chat/screenshots``.

Shown from the menu-bar **Chat** item or ``cua chat on|off``.
Hides during computer-use screenshots (``overlay_hidden``).
"""

from __future__ import annotations

import os
import threading
from typing import Any

from app_status import pid_alive, read_status, set_chat_overlay_enabled

_OFF = {"0", "false", "no", "off"}

# Fraction of the visible screen when CHAT_OVERLAY_WIDTH / HEIGHT unset.
_DEFAULT_WIDTH_FRAC = 0.55
_DEFAULT_HEIGHT_FRAC = 0.72
_MIN_WIDTH = 720
_MIN_HEIGHT = 480
SIDEBAR_W = int(os.environ.get("CHAT_SIDEBAR_WIDTH", "252"))
SIDEBAR_ROW_H = 52.0


def _env_int(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


CHAT_MARGIN = int(os.environ.get("CHAT_OVERLAY_MARGIN", "24"))
THUMB_MAX_W = int(os.environ.get("CHAT_THUMB_WIDTH", "280"))
THUMB_MAX_H = int(os.environ.get("CHAT_THUMB_HEIGHT", "160"))
AVATAR_SIZE = 36.0
BUBBLE_PAD_X = 12.0
BUBBLE_PAD_Y = 8.0
ROW_GAP = 12.0
STACK_PAD = 10.0

# AppKit helper classes — created once. Nested class defs inside ChatOverlay._build
# break on the second open (PyObjC class already registered / stale overlay ptr).
_ChatActions = None
_SidebarData = None
_FlippedView = None


def _objc_helpers():
    """Lazily register AppKit helper classes once per process."""
    global _ChatActions, _SidebarData, _FlippedView
    if _ChatActions is not None and _SidebarData is not None and _FlippedView is not None:
        return _ChatActions, _SidebarData, _FlippedView

    import objc
    from AppKit import NSView  # type: ignore
    from Foundation import NSObject

    class ChatActions(NSObject):
        overlay = objc.ivar()

        def send_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov.submit()

        def dictate_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov.toggle_dictation()

        def modelChanged_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov._on_model_changed()

        def newChat_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov.start_new_chat()

        def screenshotToggled_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov._on_screenshot_toggled()

        def hideChat_(self, _sender) -> None:
            set_chat_overlay_enabled(False)
            ov = self.overlay
            if ov is not None:
                ov.hide()

        def closeZoom_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov.close_zoom()

        def openInPreview_(self, _sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov.open_zoom_in_preview()

        def transcriptResized_(self, _notif) -> None:
            ov = self.overlay
            if ov is not None:
                ov._relayout_stack()

        def openShot_(self, sender) -> None:
            ov = self.overlay
            if ov is None:
                return
            path = ""
            try:
                path = str(sender.toolTip() or "")
            except Exception:
                path = ""
            if path:
                ov.open_zoom(path)

        def chatRowMenu_(self, sender) -> None:
            ov = self.overlay
            if ov is not None:
                ov._show_chat_row_menu(sender)

        def deleteChat_(self, sender) -> None:
            ov = self.overlay
            if ov is None:
                return
            chat_id = ""
            try:
                chat_id = str(sender.representedObject() or "")
            except Exception:
                chat_id = ""
            if chat_id:
                ov.delete_chat(chat_id)

        def windowShouldClose_(self, _sender) -> bool:
            # Red traffic-light on chat: hide + clear flag; never destroy.
            set_chat_overlay_enabled(False)
            ov = self.overlay
            if ov is not None:
                ov.hide()
            return False

        def windowWillClose_(self, _notif) -> None:
            set_chat_overlay_enabled(False)
            ov = self.overlay
            if ov is not None:
                ov._closed = True
                ov.window = None

    class SidebarData(NSObject):
        overlay = objc.ivar()

        def numberOfRowsInTableView_(self, _table) -> int:
            ov = self.overlay
            if ov is None:
                return 0
            return len(ov._chat_rows)

        def tableView_objectValueForTableColumn_row_(self, _table, _col, row) -> str:
            ov = self.overlay
            if ov is None or row < 0 or row >= len(ov._chat_rows):
                return ""
            return ov._chat_rows[row].get("title") or "Chat"

        def tableView_heightOfRow_(self, _table, _row) -> float:
            return SIDEBAR_ROW_H

        def tableView_viewForTableColumn_row_(self, table, _col, row):
            ov = self.overlay
            if ov is None or row < 0 or row >= len(ov._chat_rows):
                return None
            return ov._sidebar_cell(table, row)

        def tableViewSelectionDidChange_(self, _notif) -> None:
            ov = self.overlay
            if ov is not None:
                ov._on_sidebar_select()

    class FlippedView(NSView):
        def isFlipped(self) -> bool:
            return True

    _ChatActions = ChatActions
    _SidebarData = SidebarData
    _FlippedView = FlippedView
    return _ChatActions, _SidebarData, _FlippedView


def _user_avatar_image(size: int = 64):
    """Blue circle + person silhouette for the user side."""
    from AppKit import NSBezierPath, NSColor, NSImage, NSMakeRect  # type: ignore

    img = NSImage.alloc().initWithSize_((float(size), float(size)))
    img.lockFocus()
    try:
        s = float(size)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.28, 0.48, 0.86, 1.0).setFill()
        clip = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(0, 0, s, s))
        clip.addClip()
        clip.fill()
        NSColor.whiteColor().setFill()
        head = s * 0.22
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect((s - head) / 2.0, s * 0.50, head, head)
        ).fill()
        shoulders = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(s * 0.22, s * 0.08, s * 0.56, s * 0.42)
        )
        shoulders.fill()
    finally:
        img.unlockFocus()
    return img


def _measure_text(text: str, font, max_width: float) -> tuple[float, float]:
    from AppKit import NSFontAttributeName  # type: ignore
    from Foundation import NSAttributedString, NSMakeSize

    attrs = {NSFontAttributeName: font}
    astr = NSAttributedString.alloc().initWithString_attributes_(text or " ", attrs)
    # NSStringDrawingUsesLineFragmentOrigin = 1 << 1
    rect = astr.boundingRectWithSize_options_context_(
        NSMakeSize(max_width, 100000.0),
        1 << 1,
        None,
    )
    return max(1.0, float(rect.size.width)), max(float(font.pointSize()) + 2.0, float(rect.size.height))


def _nsimage_from_png(png: bytes):
    from AppKit import NSImage  # type: ignore
    from Foundation import NSData

    data = NSData.dataWithBytes_length_(png, len(png))
    return NSImage.alloc().initWithData_(data)


def relative_chat_time(iso: str, *, now=None) -> str:
    """Compact relative time for sidebar rows (Just now, 5m ago, Yesterday)."""
    from datetime import datetime, timezone

    raw = (iso or "").strip()
    if not raw:
        return ""
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:10]
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = current - stamp.astimezone(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 45:
        return "Just now"
    if secs < 3600:
        return f"{max(1, secs // 60)}m ago"
    if secs < 86400:
        return f"{max(1, secs // 3600)}h ago"
    days = secs // 86400
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days}d ago"
    local = stamp.astimezone()
    if local.year == current.astimezone().year:
        return f"{local.strftime('%b')} {local.day}"
    return f"{local.strftime('%b')} {local.day}, {local.year}"


def _model_short(model_id: str | None) -> str:
    if not model_id:
        return ""
    name = model_id.split(":", 1)[-1]
    if name.startswith("deepseek-"):
        name = name[len("deepseek-") :]
    if name.startswith("gpt-"):
        return name
    return name[:18]


def _scaled_thumb(image, max_w: int = THUMB_MAX_W, max_h: int = THUMB_MAX_H):
    """Return a copy of ``image`` scaled to fit inside max_w × max_h."""
    from AppKit import NSImage  # type: ignore
    from Foundation import NSMakeSize

    if image is None:
        return None
    size = image.size()
    w, h = float(size.width), float(size.height)
    if w <= 0 or h <= 0:
        return image
    scale = min(max_w / w, max_h / h, 1.0)
    tw, th = max(1.0, w * scale), max(1.0, h * scale)
    thumb = NSImage.alloc().initWithSize_(NSMakeSize(tw, th))
    thumb.lockFocus()
    try:
        image.drawInRect_fromRect_operation_fraction_(
            ((0, 0), (tw, th)),
            ((0, 0), (w, h)),
            2,  # NSCompositingOperationCopy
            1.0,
        )
    finally:
        thumb.unlockFocus()
    return thumb


def _accent_color():
    from AppKit import NSColor  # type: ignore

    return NSColor.colorWithCalibratedRed_green_blue_alpha_(0.92, 0.48, 0.28, 1.0)


def _muted_icon_color():
    from AppKit import NSColor  # type: ignore

    return NSColor.colorWithCalibratedWhite_alpha_(0.48, 1.0)


def _symbol_image(name: str, fallback: str | None = None, point_size: float = 15.0):
    from AppKit import NSImage, NSImageSymbolConfiguration  # type: ignore

    img = None
    try:
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, name)
        if img is None and fallback:
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                fallback, fallback
            )
    except Exception:
        img = None
    if img is None:
        return None
    try:
        cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            point_size, 0.0
        )
        configured = img.imageWithSymbolConfiguration_(cfg)
        if configured is not None:
            img = configured
    except Exception:
        pass
    try:
        img.setTemplate_(True)
    except Exception:
        pass
    return img


def _style_icon_button(btn, *, tooltip: str, symbol: str, fallback: str, tint) -> None:
    from AppKit import NSImageOnly  # type: ignore

    btn.setBordered_(False)
    btn.setToolTip_(tooltip)
    img = _symbol_image(symbol, fallback)
    if img is not None:
        btn.setImage_(img)
        btn.setTitle_("")
        btn.setImagePosition_(NSImageOnly)
    else:
        btn.setTitle_(fallback[:1].upper() if fallback else "•")
    try:
        btn.setContentTintColor_(tint)
    except Exception:
        pass


def chat_overlay_env_enabled() -> bool:
    return os.environ.get("CHAT_OVERLAY", "0").strip().lower() not in _OFF


def chat_overlay_enabled(data: dict[str, Any] | None = None) -> bool:
    """True when the chat window should exist (tray toggle / CHAT_OVERLAY)."""
    snap = data if data is not None else read_status()
    val = snap.get("chat_overlay_enabled")
    if val is None:
        return chat_overlay_env_enabled()
    return bool(val)


def chat_should_show(data: dict[str, Any] | None = None) -> bool:
    snap = data if data is not None else read_status()
    if not chat_overlay_enabled(snap):
        return False
    if snap.get("overlay_hidden"):
        return False
    return pid_alive(snap.get("orchestrator_pid")) or pid_alive(snap.get("agent_pid")) or pid_alive(
        snap.get("tray_pid")
    )


def cmd_chat(mode: str | None) -> int:
    """``cua chat`` / ``on`` / ``off`` / ``toggle``."""
    key = (mode or "status").strip().lower()
    if key in {"on", "show", "1", "true"}:
        set_chat_overlay_enabled(True)
        try:
            from status_tray import ensure_tray_running

            ensure_tray_running()
        except Exception:
            pass
        print("chat window on")
        return 0
    if key in {"off", "hide", "0", "false"}:
        set_chat_overlay_enabled(False)
        print("chat window off")
        return 0
    if key in {"toggle", ""}:
        now = chat_overlay_enabled()
        set_chat_overlay_enabled(not now)
        if not now:
            try:
                from status_tray import ensure_tray_running

                ensure_tray_running()
            except Exception:
                pass
        print("chat window " + ("off" if now else "on"))
        return 0
    if key == "status":
        print("chat window " + ("on" if chat_overlay_enabled() else "off") + " (⌘⌥C)")
        return 0
    print("usage: cua chat [on|off|toggle|status]  (hotkey ⌘⌥C)")
    return 2


class ChatOverlay:
    """Interactive NSPanel. Construct only on the AppKit main thread."""

    def __init__(self) -> None:
        from chat_llm import ChatSession
        from chat_store import PREF_SCREENSHOT_ON, get_store

        self.window = None
        self.transcript = None  # alias: transcript_stack
        self.transcript_scroll = None
        self.transcript_stack = None
        self.input = None
        self.screen_btn = None
        self.model_popup = None
        self.mic_btn = None
        self.send_btn = None
        self.status_label = None
        self.sidebar_table = None
        self.sidebar_empty = None
        self.new_chat_btn = None
        self._sidebar_data = None
        self._chat_rows: list[dict[str, str]] = []
        self._thinking_row = None
        self._assistant_avatar = None
        self._user_avatar = None
        self._relayouting = False
        self._zoom_window = None
        self._zoom_image_view = None
        self._zoom_scroll = None
        self._zoom_path: str | None = None
        self.session = ChatSession()
        self.store = get_store()
        self.chat_id: str | None = None
        self._busy = False
        self._dictating = False
        self._closed = False
        self._controller = None
        self._screenshot_pref = self.store.get_pref(PREF_SCREENSHOT_ON, "1") != "0"
        self._build()
        self._bootstrap_chat()

    def _build(self) -> None:
        from AppKit import (  # type: ignore
            NSBackingStoreBuffered,
            NSBezelStyleRegularSquare,
            NSButton,
            NSColor,
            NSFloatingWindowLevel,
            NSFont,
            NSImage,
            NSImageOnly,
            NSMakeRect,
            NSPanel,
            NSPopUpButton,
            NSScrollView,
            NSTableColumn,
            NSTableView,
            NSTextField,
            NSView,
            NSViewHeightSizable,
            NSViewMaxXMargin,
            NSViewMaxYMargin,
            NSViewMinXMargin,
            NSViewMinYMargin,
            NSViewWidthSizable,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowSharingNone,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskMiniaturizable,
            NSWindowStyleMaskResizable,
            NSWindowStyleMaskTitled,
        )

        ChatActions, SidebarData, FlippedView = _objc_helpers()

        actions = ChatActions.alloc().init()
        actions.overlay = self
        self._controller = actions

        sidebar_ds = SidebarData.alloc().init()
        sidebar_ds.overlay = self
        self._sidebar_data = sidebar_ds
        self._refresh_avatars()

        frame = self._cocoa_frame()
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("CUA Chat")
        window.setLevel_(NSFloatingWindowLevel)
        window.setHidesOnDeactivate_(False)
        window.setReleasedWhenClosed_(False)
        window.setMinSize_((_MIN_WIDTH, _MIN_HEIGHT))
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        try:
            window.setSharingType_(NSWindowSharingNone)
        except Exception:
            pass
        window.setDelegate_(actions)
        # Red traffic-light must hide, not destroy — performClose can bypass
        # windowShouldClose on some NSPanel configs.
        try:
            from AppKit import NSWindowCloseButton  # type: ignore

            close_btn = window.standardWindowButton_(NSWindowCloseButton)
            if close_btn is not None:
                close_btn.setTarget_(actions)
                close_btn.setAction_("hideChat:")
        except Exception:
            pass

        content = NSView.alloc().initWithFrame_(window.contentView().bounds())
        content.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        content.setWantsLayer_(True)
        try:
            content.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedWhite_alpha_(0.10, 1.0).CGColor()
            )
        except Exception:
            pass
        window.setContentView_(content)
        bounds = content.bounds()
        w, h = float(bounds.size.width), float(bounds.size.height)
        sw = min(SIDEBAR_W, max(200, int(w * 0.28)))

        # --- Sidebar ---
        sidebar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, sw, h))
        sidebar.setAutoresizingMask_(NSViewHeightSizable | NSViewMaxXMargin)
        sidebar.setWantsLayer_(True)
        try:
            sidebar.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.12, 0.125, 0.145, 1.0
                ).CGColor()
            )
        except Exception:
            pass
        content.addSubview_(sidebar)

        header = NSTextField.alloc().initWithFrame_(NSMakeRect(14, h - 36, sw - 28, 18))
        header.setStringValue_("Chats")
        header.setBordered_(False)
        header.setEditable_(False)
        header.setDrawsBackground_(False)
        header.setFont_(NSFont.boldSystemFontOfSize_(13.0))
        header.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.92, 1.0))
        header.setAutoresizingMask_(NSViewMinYMargin | NSViewWidthSizable)
        sidebar.addSubview_(header)

        new_btn = NSButton.alloc().initWithFrame_(NSMakeRect(12, h - 76, sw - 24, 32))
        try:
            plus = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "plus", "New chat"
            )
            if plus is not None:
                new_btn.setImage_(plus)
                new_btn.setImagePosition_(2)  # NSImageLeft
        except Exception:
            pass
        new_btn.setTitle_(" New chat")
        new_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        try:
            new_btn.setWantsLayer_(True)
            new_btn.layer().setCornerRadius_(8.0)
            new_btn.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.20, 0.42, 0.78, 1.0
                ).CGColor()
            )
        except Exception:
            pass
        new_btn.setTarget_(actions)
        new_btn.setAction_("newChat:")
        new_btn.setAutoresizingMask_(NSViewMinYMargin | NSViewWidthSizable)
        sidebar.addSubview_(new_btn)
        self.new_chat_btn = new_btn

        side_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 8, sw, h - 88))
        side_scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        side_scroll.setHasVerticalScroller_(True)
        side_scroll.setAutohidesScrollers_(True)
        side_scroll.setBorderType_(0)
        side_scroll.setDrawsBackground_(False)
        table = NSTableView.alloc().initWithFrame_(side_scroll.contentView().bounds())
        col = NSTableColumn.alloc().initWithIdentifier_("title")
        col.setTitle_("Chats")
        col.setWidth_(sw - 8)
        col.setResizingMask_(1)  # NSTableColumnAutoresizingMask
        table.addTableColumn_(col)
        table.setHeaderView_(None)
        table.setRowHeight_(SIDEBAR_ROW_H)
        table.setIntercellSpacing_((0.0, 2.0))
        table.setDataSource_(sidebar_ds)
        table.setDelegate_(sidebar_ds)
        try:
            table.setAllowsColumnReordering_(False)
        except Exception:
            pass
        table.setBackgroundColor_(NSColor.clearColor())
        try:
            from AppKit import NSTableViewSelectionHighlightStyleSourceList  # type: ignore

            table.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleSourceList)
        except Exception:
            table.setSelectionHighlightStyle_(1)
        try:
            table.setStyle_(4)  # NSTableViewStyleSourceList (macOS 11+)
        except Exception:
            pass
        try:
            table.setFocusRingType_(1)  # NSFocusRingTypeNone
        except Exception:
            pass
        try:
            table.setColumnAutoresizingStyle_(1)
        except Exception:
            pass
        side_scroll.setDocumentView_(table)
        sidebar.addSubview_(side_scroll)
        self.sidebar_table = table

        empty = NSTextField.alloc().initWithFrame_(NSMakeRect(16, h / 2 - 40, sw - 32, 40))
        empty.setStringValue_("No chats yet")
        empty.setBordered_(False)
        empty.setEditable_(False)
        empty.setDrawsBackground_(False)
        empty.setAlignment_(1)  # center
        empty.setFont_(NSFont.systemFontOfSize_(12.0))
        empty.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.45, 1.0))
        empty.setAutoresizingMask_(NSViewMinYMargin | NSViewMaxYMargin | NSViewWidthSizable)
        empty.setHidden_(True)
        sidebar.addSubview_(empty)
        self.sidebar_empty = empty

        divider = NSView.alloc().initWithFrame_(NSMakeRect(sw - 1, 0, 1, h))
        divider.setAutoresizingMask_(NSViewHeightSizable | NSViewMinXMargin)
        divider.setWantsLayer_(True)
        try:
            divider.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedWhite_alpha_(0.22, 1.0).CGColor()
            )
        except Exception:
            pass
        sidebar.addSubview_(divider)

        # --- Main pane ---
        main = NSView.alloc().initWithFrame_(NSMakeRect(sw, 0, w - sw, h))
        main.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        content.addSubview_(main)
        mw, mh = float(main.bounds().size.width), float(main.bounds().size.height)

        from chat_llm import list_chat_models, selected_model_id

        models = list_chat_models()
        current = selected_model_id()
        popup_w = min(280.0, max(160.0, mw * 0.42))
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(12, mh - 40, popup_w, 28), False
        )
        popup.removeAllItems()
        select_idx = 0
        for i, m in enumerate(models):
            popup.addItemWithTitle_(m.label)
            popup.lastItem().setRepresentedObject_(m.id)
            if m.id == current:
                select_idx = i
        popup.selectItemAtIndex_(select_idx)
        popup.setTarget_(actions)
        popup.setAction_("modelChanged:")
        popup.setAutoresizingMask_(NSViewMinYMargin | NSViewMaxXMargin)
        main.addSubview_(popup)
        self.model_popup = popup

        status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(popup_w + 20, mh - 38, max(80.0, mw - popup_w - 32), 24)
        )
        status.setBordered_(False)
        status.setEditable_(False)
        status.setDrawsBackground_(False)
        status.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.55, 1.0))
        status.setFont_(NSFont.systemFontOfSize_(11.0))
        status.setStringValue_(self._idle_status())
        status.setAlignment_(2)  # right
        status.setAutoresizingMask_(NSViewMinYMargin | NSViewWidthSizable | NSViewMinXMargin)
        main.addSubview_(status)
        self.status_label = status

        transcript_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(12, 66, mw - 24, mh - 118)
        )
        transcript_scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        transcript_scroll.setHasVerticalScroller_(True)
        transcript_scroll.setAutohidesScrollers_(True)
        transcript_scroll.setBorderType_(0)
        transcript_scroll.setDrawsBackground_(False)
        try:
            transcript_scroll.setBackgroundColor_(NSColor.clearColor())
        except Exception:
            pass
        stack_w = max(100.0, mw - 24)
        stack = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, stack_w, 40))
        stack.setAutoresizingMask_(NSViewWidthSizable)
        transcript_scroll.setDocumentView_(stack)
        try:
            clip = transcript_scroll.contentView()
            clip.setPostsFrameChangedNotifications_(True)
            from Foundation import NSNotificationCenter

            NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
                actions,
                "transcriptResized:",
                "NSViewFrameDidChangeNotification",
                clip,
            )
        except Exception:
            pass
        main.addSubview_(transcript_scroll)
        self.transcript_scroll = transcript_scroll
        self.transcript_stack = stack
        self.transcript = stack

        composer = NSView.alloc().initWithFrame_(NSMakeRect(12, 12, mw - 24, 44))
        composer.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        composer.setWantsLayer_(True)
        try:
            composer.layer().setCornerRadius_(22.0)
            composer.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.16, 0.17, 0.20, 1.0
                ).CGColor()
            )
            composer.layer().setBorderWidth_(1.0)
            composer.layer().setBorderColor_(
                NSColor.colorWithCalibratedWhite_alpha_(0.28, 1.0).CGColor()
            )
        except Exception:
            pass
        main.addSubview_(composer)
        cw = float(composer.bounds().size.width)

        screen_btn = NSButton.alloc().initWithFrame_(NSMakeRect(6, 4, 36, 36))
        screen_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        screen_btn.setTarget_(actions)
        screen_btn.setAction_("screenshotToggled:")
        screen_btn.setAutoresizingMask_(NSViewMaxXMargin)
        composer.addSubview_(screen_btn)
        self.screen_btn = screen_btn
        self._sync_screenshot_icon()

        mic_btn = NSButton.alloc().initWithFrame_(NSMakeRect(42, 4, 36, 36))
        mic_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        _style_icon_button(
            mic_btn,
            tooltip="Dictate",
            symbol="mic.fill",
            fallback="mic",
            tint=_muted_icon_color(),
        )
        mic_btn.setTarget_(actions)
        mic_btn.setAction_("dictate:")
        mic_btn.setAutoresizingMask_(NSViewMaxXMargin)
        composer.addSubview_(mic_btn)
        self.mic_btn = mic_btn

        field = NSTextField.alloc().initWithFrame_(NSMakeRect(82, 8, max(80.0, cw - 130), 28))
        field.setPlaceholderString_("Message…")
        field.setBezeled_(False)
        field.setBordered_(False)
        field.setDrawsBackground_(False)
        field.setTextColor_(NSColor.whiteColor())
        field.setFont_(NSFont.systemFontOfSize_(14.0))
        try:
            field.setFocusRingType_(1)  # NSFocusRingTypeNone
        except Exception:
            pass
        field.setTarget_(actions)
        field.setAction_("send:")
        field.setAutoresizingMask_(NSViewWidthSizable)
        composer.addSubview_(field)
        self.input = field

        send_btn = NSButton.alloc().initWithFrame_(NSMakeRect(cw - 40, 4, 36, 36))
        send_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        send_btn.setBordered_(False)
        send_btn.setToolTip_("Send")
        send_btn.setTarget_(actions)
        send_btn.setAction_("send:")
        send_btn.setAutoresizingMask_(NSViewMinXMargin)
        send_btn.setWantsLayer_(True)
        try:
            send_btn.layer().setCornerRadius_(18.0)
            send_btn.layer().setBackgroundColor_(_accent_color().CGColor())
        except Exception:
            pass
        plane = _symbol_image("paperplane.fill", "paperplane", point_size=14.0)
        if plane is not None:
            send_btn.setImage_(plane)
            send_btn.setTitle_("")
            send_btn.setImagePosition_(NSImageOnly)
            try:
                send_btn.setContentTintColor_(NSColor.whiteColor())
            except Exception:
                pass
        else:
            send_btn.setTitle_("✈")
        composer.addSubview_(send_btn)
        self.send_btn = send_btn

        self.window = window
        self._closed = False
        window.makeKeyAndOrderFront_(None)

    def _bootstrap_chat(self) -> None:
        self.refresh_sidebar()
        if self._chat_rows:
            self._select_sidebar_row(0)
            self.load_chat(self._chat_rows[0]["id"])
        else:
            self.start_new_chat()

    def is_alive(self) -> bool:
        if self._closed or self.window is None:
            return False
        try:
            _ = self.window.isVisible()
            return True
        except Exception:
            return False

    def _cocoa_frame(self):
        from AppKit import NSMakeRect, NSScreen  # type: ignore

        screen = NSScreen.mainScreen()
        vis = screen.visibleFrame() if screen is not None else NSMakeRect(0, 0, 1440, 900)
        env_w = _env_int("CHAT_OVERLAY_WIDTH")
        env_h = _env_int("CHAT_OVERLAY_HEIGHT")
        width = env_w if env_w else int(vis.size.width * _DEFAULT_WIDTH_FRAC)
        height = env_h if env_h else int(vis.size.height * _DEFAULT_HEIGHT_FRAC)
        width = min(max(width, _MIN_WIDTH), max(_MIN_WIDTH, int(vis.size.width - 2 * CHAT_MARGIN)))
        height = min(
            max(height, _MIN_HEIGHT), max(_MIN_HEIGHT, int(vis.size.height - 2 * CHAT_MARGIN))
        )
        x = vis.origin.x + vis.size.width - width - CHAT_MARGIN
        y = vis.origin.y + CHAT_MARGIN
        return NSMakeRect(x, y, width, height)

    def _set_status(self, text: str) -> None:
        if self.status_label is not None:
            self.status_label.setStringValue_(text)

    def _refresh_avatars(self) -> None:
        """Assistant = current face blobatar; user = person glyph."""
        try:
            from face_overlay import render_blobatar_avatar

            self._assistant_avatar = render_blobatar_avatar(64, mood="wink")
        except Exception:
            self._assistant_avatar = None
        try:
            self._user_avatar = _user_avatar_image(64)
        except Exception:
            self._user_avatar = None

    def _stack_width(self) -> float:
        scroll = self.transcript_scroll
        if scroll is None:
            return 400.0
        try:
            return max(120.0, float(scroll.contentView().bounds().size.width))
        except Exception:
            return 400.0

    def _clear_stack(self) -> None:
        stack = self.transcript_stack
        if stack is None:
            return
        for sub in list(stack.subviews() or []):
            sub.removeFromSuperview()
        self._thinking_row = None

    def _strip_placeholder(self) -> None:
        stack = self.transcript_stack
        if stack is None:
            return
        for sub in list(stack.subviews() or []):
            try:
                if int(sub.tag()) == 3:
                    sub.removeFromSuperview()
            except Exception:
                pass

    def _scroll_transcript_to_bottom(self) -> None:
        stack = self.transcript_stack
        if stack is None:
            return
        try:
            subs = list(stack.subviews() or [])
            if subs:
                last = subs[-1]
                last.scrollRectToVisible_(last.bounds())
        except Exception:
            pass

    def _relayout_stack(self) -> None:
        from AppKit import NSMakeRect  # type: ignore

        stack = self.transcript_stack
        scroll = self.transcript_scroll
        if stack is None or self._relayouting:
            return
        self._relayouting = True
        try:
            width = self._stack_width()
            y = STACK_PAD
            for sub in list(stack.subviews() or []):
                try:
                    tag = int(sub.tag())
                except Exception:
                    tag = 0
                if tag == 1:
                    self._layout_message_row(sub, width)
                elif tag == 2:
                    self._layout_thinking_row(sub, width)
                elif tag == 3:
                    self._layout_placeholder_row(sub, width)
                row_h = float(sub.frame().size.height)
                sub.setFrame_(NSMakeRect(0.0, y, width, row_h))
                y += row_h + ROW_GAP
            clip_h = 40.0
            if scroll is not None:
                try:
                    clip_h = float(scroll.contentView().bounds().size.height)
                except Exception:
                    pass
            total_h = max(y + STACK_PAD, clip_h)
            stack.setFrame_(NSMakeRect(0.0, 0.0, width, total_h))
            self._scroll_transcript_to_bottom()
        finally:
            self._relayouting = False

    def _bubble_colors(self, role: str):
        from AppKit import NSColor  # type: ignore

        if role == "user":
            bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.18, 0.42, 0.78, 1.0)
            fg = NSColor.whiteColor()
        elif role == "error":
            bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.48, 0.18, 0.20, 1.0)
            fg = NSColor.colorWithCalibratedWhite_alpha_(0.95, 1.0)
        else:
            # assistant
            bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.22, 0.28, 1.0)
            fg = NSColor.colorWithCalibratedWhite_alpha_(0.95, 1.0)
        return bg, fg

    def _make_avatar_view(self, image, size: float = AVATAR_SIZE, *, circular: bool = True):
        from AppKit import NSImageView, NSMakeRect  # type: ignore

        view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, size, size))
        if image is not None:
            view.setImage_(image)
        view.setImageScaling_(3)  # NSImageScaleProportionallyUpOrDown
        try:
            view.setWantsLayer_(True)
            view.layer().setCornerRadius_(size / 2.0 if circular else 8.0)
            view.layer().setMasksToBounds_(True)
        except Exception:
            pass
        return view

    def _make_bubble_view(self, text: str, role: str, max_text_w: float):
        from AppKit import NSColor, NSFont, NSMakeRect, NSTextField, NSView  # type: ignore

        bg, fg = self._bubble_colors(role)
        font = NSFont.systemFontOfSize_(13.0)
        tw, th = _measure_text(text, font, max_text_w)
        tw = max(12.0, tw)
        th = max(float(font.pointSize()) + 4.0, th + 2.0)
        bw = tw + 2 * BUBBLE_PAD_X
        bh = th + 2 * BUBBLE_PAD_Y
        bubble = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, bw, bh))
        bubble.setWantsLayer_(True)
        try:
            bubble.layer().setCornerRadius_(14.0)
            bubble.layer().setBackgroundColor_(bg.CGColor())
        except Exception:
            pass
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(BUBBLE_PAD_X, BUBBLE_PAD_Y, tw, th)
        )
        label.setStringValue_(text)
        label.setBordered_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setDrawsBackground_(False)
        label.setFont_(font)
        label.setTextColor_(fg)
        try:
            label.cell().setWraps_(True)
            label.setPreferredMaxLayoutWidth_(max_text_w)
            label.setUsesSingleLineMode_(False)
        except Exception:
            pass
        bubble.addSubview_(label)
        return bubble, bw, bh

    def _make_shot_button(self, abs_path: str):
        from pathlib import Path

        from AppKit import NSButton, NSMakeRect  # type: ignore

        png = Path(abs_path).read_bytes() if Path(abs_path).is_file() else None
        if not png:
            return None, 0.0, 0.0
        image = _nsimage_from_png(png)
        thumb = _scaled_thumb(image)
        if thumb is None:
            return None, 0.0, 0.0
        size = thumb.size()
        tw, th = float(size.width), float(size.height)
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, tw, th))
        btn.setBordered_(False)
        btn.setImage_(thumb)
        btn.setImagePosition_(1)  # NSImageOnly
        btn.setTitle_("")
        resolved = str(Path(abs_path).resolve())
        try:
            btn.setIdentifier_("shot")
        except Exception:
            pass
        btn.setToolTip_(resolved)
        if self._controller is not None:
            btn.setTarget_(self._controller)
            btn.setAction_("openShot:")
        try:
            btn.setWantsLayer_(True)
            btn.layer().setCornerRadius_(8.0)
            btn.layer().setMasksToBounds_(True)
        except Exception:
            pass
        btn.setToolTip_(resolved)
        return btn, tw, th

    def _layout_message_row(self, row, width: float) -> None:
        from AppKit import NSMakeRect  # type: ignore

        avatar = None
        bubble = None
        shot = None
        for sub in list(row.subviews() or []):
            ident = ""
            try:
                ident = str(sub.identifier() or "")
            except Exception:
                pass
            if ident == "avatar":
                avatar = sub
            elif ident == "bubble":
                bubble = sub
            elif ident == "shot":
                shot = sub
        if avatar is None:
            return
        role = "assistant"
        try:
            rident = str(row.identifier() or "")
            if rident in {"user", "assistant", "error"}:
                role = rident
        except Exception:
            pass

        pad = STACK_PAD
        gap = 8.0
        av = AVATAR_SIZE
        bubble_h = float(bubble.frame().size.height) if bubble is not None else 0.0
        bubble_w = float(bubble.frame().size.width) if bubble is not None else 0.0
        shot_h = float(shot.frame().size.height) if shot is not None else 0.0
        shot_w = float(shot.frame().size.width) if shot is not None else 0.0
        col_h = bubble_h + (6.0 + shot_h if shot is not None else 0.0)
        row_h = max(av, col_h) + 4.0
        row.setFrameSize_((width, row_h))

        if role == "user":
            ax = width - pad - av
            avatar.setFrame_(NSMakeRect(ax, 0.0, av, av))
            bx = ax - gap - bubble_w
            if bubble is not None:
                bubble.setFrame_(NSMakeRect(bx, 0.0, bubble_w, bubble_h))
            if shot is not None:
                shot.setFrame_(
                    NSMakeRect(ax - gap - shot_w, bubble_h + 6.0, shot_w, shot_h)
                )
        else:
            avatar.setFrame_(NSMakeRect(pad, 0.0, av, av))
            bx = pad + av + gap
            if bubble is not None:
                bubble.setFrame_(NSMakeRect(bx, 0.0, bubble_w, bubble_h))
            if shot is not None:
                shot.setFrame_(NSMakeRect(bx, bubble_h + 6.0, shot_w, shot_h))

    def _layout_thinking_row(self, row, width: float) -> None:
        from AppKit import NSMakeRect  # type: ignore

        pad = STACK_PAD
        gap = 8.0
        av = AVATAR_SIZE
        avatar = None
        label = None
        for sub in list(row.subviews() or []):
            try:
                ident = str(sub.identifier() or "")
            except Exception:
                ident = ""
            if ident == "avatar":
                avatar = sub
            else:
                label = sub
        row.setFrameSize_((width, av))
        if avatar is not None:
            avatar.setFrame_(NSMakeRect(pad, 0, av, av))
        if label is not None:
            lw = max(80.0, width - pad - av - gap - pad)
            label.setFrame_(NSMakeRect(pad + av + gap, (av - 18.0) / 2.0, lw, 18.0))

    def _layout_placeholder_row(self, row, width: float) -> None:
        from AppKit import NSMakeRect  # type: ignore

        for sub in list(row.subviews() or []):
            sub.setFrame_(NSMakeRect(STACK_PAD, 8.0, max(40.0, width - 2 * STACK_PAD), 40.0))
        row.setFrameSize_((width, 56.0))

    def _add_message_row(
        self,
        role: str,
        text: str,
        *,
        screenshot_path: str | None = None,
        relayout: bool = True,
    ):
        from AppKit import NSMakeRect, NSView  # type: ignore

        stack = self.transcript_stack
        if stack is None:
            return None
        self._strip_placeholder()
        width = self._stack_width()
        max_text_w = max(120.0, min(420.0, width * 0.62) - 2 * BUBBLE_PAD_X)

        row = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, AVATAR_SIZE))
        try:
            row.setTag_(1)
            row.setIdentifier_(role)
        except Exception:
            pass

        avatar_img = self._assistant_avatar if role != "user" else self._user_avatar
        if role == "error" and self._assistant_avatar is None:
            avatar_img = self._user_avatar
        avatar = self._make_avatar_view(avatar_img, circular=(role == "user"))
        try:
            avatar.setIdentifier_("avatar")
        except Exception:
            pass
        row.addSubview_(avatar)

        body = (text or "").strip() or (" " if role == "user" else "")
        bubble, _bw, bh = self._make_bubble_view(body, role, max_text_w)
        try:
            bubble.setIdentifier_("bubble")
        except Exception:
            pass
        row.addSubview_(bubble)

        shot = None
        sw = sh = 0.0
        if screenshot_path:
            shot, sw, sh = self._make_shot_button(screenshot_path)
            if shot is not None:
                row.addSubview_(shot)

        col_h = bh + (6.0 + sh if shot is not None else 0.0)
        row_h = max(AVATAR_SIZE, col_h) + 4.0
        row.setFrameSize_((width, row_h))
        self._layout_message_row(row, width)
        stack.addSubview_(row)
        if relayout:
            self._relayout_stack()
        return row

    def _add_thinking_row(self, label: str, *, relayout: bool = True):
        from AppKit import NSColor, NSFont, NSMakeRect, NSTextField, NSView  # type: ignore

        stack = self.transcript_stack
        if stack is None:
            return None
        self._remove_thinking_row()
        width = self._stack_width()
        row = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, AVATAR_SIZE))
        try:
            row.setTag_(2)
            row.setIdentifier_("thinking")
        except Exception:
            pass
        avatar = self._make_avatar_view(self._assistant_avatar)
        try:
            avatar.setIdentifier_("avatar")
        except Exception:
            pass
        row.addSubview_(avatar)
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 18))
        field.setStringValue_(label)
        field.setBordered_(False)
        field.setEditable_(False)
        field.setDrawsBackground_(False)
        field.setFont_(NSFont.systemFontOfSize_(12.0))
        field.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.55, 1.0))
        try:
            field.cell().setWraps_(False)
        except Exception:
            pass
        row.addSubview_(field)
        self._layout_thinking_row(row, width)
        stack.addSubview_(row)
        self._thinking_row = row
        if relayout:
            self._relayout_stack()
        return row

    def _remove_thinking_row(self) -> None:
        row = self._thinking_row
        if row is not None:
            try:
                row.removeFromSuperview()
            except Exception:
                pass
        self._thinking_row = None

    def _add_placeholder_row(self, text: str) -> None:
        from AppKit import NSColor, NSFont, NSMakeRect, NSTextField, NSView  # type: ignore

        stack = self.transcript_stack
        if stack is None:
            return
        width = self._stack_width()
        row = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, 56))
        try:
            row.setTag_(3)
        except Exception:
            pass
        field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(STACK_PAD, 8, width - 2 * STACK_PAD, 40)
        )
        field.setStringValue_(text)
        field.setBordered_(False)
        field.setEditable_(False)
        field.setDrawsBackground_(False)
        field.setFont_(NSFont.systemFontOfSize_(13.0))
        field.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.5, 1.0))
        try:
            field.cell().setWraps_(True)
        except Exception:
            pass
        row.addSubview_(field)
        stack.addSubview_(row)

    def _set_transcript(self, text: str) -> None:
        """Empty / placeholder transcript."""
        if self.transcript_stack is None:
            return
        self._refresh_avatars()
        self._clear_stack()
        if text.strip():
            self._add_placeholder_row(text.strip())
        self._relayout_stack()

    def _render_messages(self, messages, *, thinking: str | None = None) -> None:
        """Rebuild bubble stack: assistant left, user right."""
        if self.transcript_stack is None:
            return
        self._refresh_avatars()
        self._clear_stack()
        if not messages:
            self._add_placeholder_row(
                "New chat — ask about what’s on screen.\nClick a screenshot to zoom."
            )
            self._relayout_stack()
            return

        for msg in messages:
            if msg.role == "user":
                role = "user"
            elif msg.role == "assistant":
                role = "assistant"
            else:
                role = "error"
            shot = None
            rel = getattr(msg, "screenshot_relpath", None)
            if rel:
                abs_path = self.store.screenshots_dir / rel
                if abs_path.is_file():
                    shot = str(abs_path)
            self._add_message_row(
                role,
                (msg.content or "").strip(),
                screenshot_path=shot,
                relayout=False,
            )

        if thinking:
            self._add_thinking_row(thinking, relayout=False)
        self._relayout_stack()

    def _reload_transcript(self, *, thinking: str | None = None) -> None:
        if not self.chat_id:
            self._set_transcript("")
            return
        self._render_messages(self.store.list_messages(self.chat_id), thinking=thinking)

    def _set_thinking(self, label: str) -> None:
        """Show or replace the inline thinking row under the last turn."""
        if self.transcript_stack is None:
            return
        self._add_thinking_row(label)

    def _append(self, who: str, text: str, *, screenshot_path: str | None = None) -> None:
        """Append one turn (optimistic user / error lines)."""
        if self.transcript_stack is None:
            return
        if who == "You":
            role = "user"
        elif who == "Assistant":
            role = "assistant"
        else:
            role = "error"
        self._remove_thinking_row()
        self._add_message_row(role, (text or "").strip(), screenshot_path=screenshot_path)

    def open_zoom(self, path: str) -> None:
        """Show a floating zoom window for a screenshot file."""
        from pathlib import Path

        from AppKit import (  # type: ignore
            NSBackingStoreBuffered,
            NSBezelStyleRegularSquare,
            NSButton,
            NSColor,
            NSFloatingWindowLevel,
            NSImageView,
            NSImageScaleNone,
            NSMakeRect,
            NSPanel,
            NSScrollView,
            NSView,
            NSViewHeightSizable,
            NSViewMinXMargin,
            NSViewMinYMargin,
            NSViewMaxXMargin,
            NSViewWidthSizable,
            NSWindowCloseButton,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskResizable,
            NSWindowStyleMaskTitled,
            NSScreen,
        )

        p = Path(path)
        if not p.is_file():
            self._set_status(f"Screenshot missing: {p.name}")
            return
        png = p.read_bytes()
        image = _nsimage_from_png(png)
        if image is None:
            self._set_status("Could not load screenshot")
            return

        self._zoom_path = str(p.resolve())
        screen = NSScreen.mainScreen()
        vis = screen.visibleFrame() if screen is not None else NSMakeRect(0, 0, 1280, 800)
        zw = min(900, max(480, int(vis.size.width * 0.7)))
        zh = min(700, max(360, int(vis.size.height * 0.75)))
        zx = vis.origin.x + (vis.size.width - zw) / 2
        zy = vis.origin.y + (vis.size.height - zh) / 2

        win = self._zoom_window
        if win is None:
            win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(zx, zy, zw, zh),
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskResizable,
                NSBackingStoreBuffered,
                False,
            )
            win.setTitle_("Screenshot")
            win.setLevel_(NSFloatingWindowLevel + 1)
            win.setReleasedWhenClosed_(False)
            win.setHidesOnDeactivate_(False)
            content = NSView.alloc().initWithFrame_(win.contentView().bounds())
            content.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            content.setWantsLayer_(True)
            try:
                content.layer().setBackgroundColor_(
                    NSColor.colorWithCalibratedWhite_alpha_(0.08, 1.0).CGColor()
                )
            except Exception:
                pass
            win.setContentView_(content)
            bw = float(content.bounds().size.width)
            bh = float(content.bounds().size.height)

            scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(12, 48, bw - 24, bh - 60))
            scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            scroll.setHasVerticalScroller_(True)
            scroll.setHasHorizontalScroller_(True)
            scroll.setAutohidesScrollers_(True)
            scroll.setBorderType_(0)
            try:
                scroll.setAllowsMagnification_(True)
                scroll.setMinMagnification_(0.25)
                scroll.setMaxMagnification_(8.0)
                scroll.setMagnification_(1.0)
            except Exception:
                pass

            iv = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, bw - 24, bh - 60))
            iv.setImageScaling_(NSImageScaleNone)
            iv.setAnimates_(False)
            scroll.setDocumentView_(iv)
            content.addSubview_(scroll)
            self._zoom_image_view = iv
            self._zoom_scroll = scroll

            preview_btn = NSButton.alloc().initWithFrame_(NSMakeRect(12, 12, 140, 28))
            preview_btn.setTitle_("Open in Preview")
            preview_btn.setBezelStyle_(NSBezelStyleRegularSquare)
            preview_btn.setTarget_(self._controller)
            preview_btn.setAction_("openInPreview:")
            preview_btn.setAutoresizingMask_(NSViewMinYMargin | NSViewMaxXMargin)
            content.addSubview_(preview_btn)

            close_btn = NSButton.alloc().initWithFrame_(NSMakeRect(bw - 84, 12, 72, 28))
            close_btn.setTitle_("Close")
            close_btn.setBezelStyle_(NSBezelStyleRegularSquare)
            close_btn.setTarget_(self._controller)
            close_btn.setAction_("closeZoom:")
            close_btn.setAutoresizingMask_(NSViewMinYMargin | NSViewMinXMargin)
            content.addSubview_(close_btn)

            try:
                traffic = win.standardWindowButton_(NSWindowCloseButton)
                if traffic is not None:
                    traffic.setTarget_(self._controller)
                    traffic.setAction_("closeZoom:")
            except Exception:
                pass

            self._zoom_window = win
        else:
            win.setFrame_display_(NSMakeRect(zx, zy, zw, zh), True)

        size = image.size()
        iv = self._zoom_image_view
        if iv is not None:
            iv.setImage_(image)
            iv.setFrame_(NSMakeRect(0, 0, float(size.width), float(size.height)))
        scroll = getattr(self, "_zoom_scroll", None)
        if scroll is not None:
            try:
                scroll.setMagnification_(1.0)
            except Exception:
                pass
        win.setTitle_(f"Screenshot — {p.name}")
        win.makeKeyAndOrderFront_(None)

    def close_zoom(self) -> None:
        win = self._zoom_window
        if win is not None:
            try:
                win.orderOut_(None)
            except Exception:
                pass

    def open_zoom_in_preview(self) -> None:
        from AppKit import NSWorkspace  # type: ignore
        from Foundation import NSURL

        if not self._zoom_path:
            return
        url = NSURL.fileURLWithPath_(self._zoom_path)
        NSWorkspace.sharedWorkspace().openURL_(url)

    def selected_model_id_ui(self) -> str:
        from chat_llm import selected_model_id

        popup = self.model_popup
        if popup is None:
            return selected_model_id()
        item = popup.selectedItem()
        if item is None:
            return selected_model_id()
        obj = item.representedObject()
        if obj:
            return str(obj)
        return selected_model_id()

    def _on_model_changed(self) -> None:
        from chat_llm import set_selected_model_id

        info = set_selected_model_id(self.selected_model_id_ui())
        if self.chat_id:
            self.store.touch_chat(self.chat_id, model_id=info.id)
        self._set_status(self._idle_status())

    def _on_screenshot_toggled(self) -> None:
        from chat_store import PREF_SCREENSHOT_ON

        self._screenshot_pref = not bool(self._screenshot_pref)
        self.store.set_pref(PREF_SCREENSHOT_ON, "1" if self._screenshot_pref else "0")
        self._sync_screenshot_icon()
        self._set_status(self._idle_status())

    def _sync_screenshot_icon(self) -> None:
        btn = self.screen_btn
        if btn is None:
            return
        on = self.screenshot_on()
        _style_icon_button(
            btn,
            tooltip="Screenshot on — attach the desktop" if on else "Screenshot off",
            symbol="camera.fill",
            fallback="camera",
            tint=_accent_color() if on else _muted_icon_color(),
        )

    def screenshot_on(self) -> bool:
        return bool(self._screenshot_pref)

    def _idle_status(self) -> str:
        from chat_llm import get_model

        info = get_model(self.selected_model_id_ui())
        shot = "on" if self.screenshot_on() else "off"
        vision = "vision" if info.vision else "text"
        return f"{info.label} ({vision}) · Screenshot {shot} · Enter sends"

    def refresh_sidebar(self) -> None:
        rows = self.store.list_chats()
        self._chat_rows = [
            {
                "id": c.id,
                "title": c.title or "New chat",
                "updated_at": c.updated_at,
                "model_id": c.model_id or "",
            }
            for c in rows
        ]
        table = self.sidebar_table
        if table is not None:
            table.reloadData()
        empty = self.sidebar_empty
        if empty is not None:
            empty.setHidden_(bool(self._chat_rows))

    def _sidebar_cell(self, table, row: int):
        """Two-line ChatGPT-style row: title + time · model, with a ⋯ menu."""
        from AppKit import (  # type: ignore
            NSBezelStyleRegularSquare,
            NSButton,
            NSColor,
            NSFont,
            NSImage,
            NSImageOnly,
            NSLineBreakByTruncatingTail,
            NSMakeRect,
            NSTableCellView,
            NSTextField,
            NSViewMinXMargin,
        )

        ident = "chatCell"
        cell = table.makeViewWithIdentifier_owner_(ident, None)
        if cell is None:
            cell = NSTableCellView.alloc().initWithFrame_(NSMakeRect(0, 0, 240, SIDEBAR_ROW_H))
            cell.setIdentifier_(ident)
            title = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 24, 188, 18))
            title.setBordered_(False)
            title.setEditable_(False)
            title.setDrawsBackground_(False)
            title.setTag_(11)
            title.setLineBreakMode_(NSLineBreakByTruncatingTail)
            try:
                title.setFont_(NSFont.systemFontOfSize_weight_(13.0, 0.23))
            except Exception:
                title.setFont_(NSFont.boldSystemFontOfSize_(13.0))
            cell.addSubview_(title)

            sub = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 8, 188, 14))
            sub.setBordered_(False)
            sub.setEditable_(False)
            sub.setDrawsBackground_(False)
            sub.setTag_(12)
            sub.setLineBreakMode_(NSLineBreakByTruncatingTail)
            sub.setFont_(NSFont.systemFontOfSize_(11.0))
            cell.addSubview_(sub)

            menu_btn = NSButton.alloc().initWithFrame_(NSMakeRect(204, 12, 28, 28))
            menu_btn.setTag_(13)
            menu_btn.setBordered_(False)
            menu_btn.setBezelStyle_(NSBezelStyleRegularSquare)
            menu_btn.setToolTip_("Chat options")
            menu_btn.setAutoresizingMask_(NSViewMinXMargin)
            try:
                dots = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    "ellipsis.circle", "Chat options"
                )
                if dots is None:
                    dots = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                        "ellipsis", "Chat options"
                    )
                if dots is not None:
                    menu_btn.setImage_(dots)
                    menu_btn.setTitle_("")
                    menu_btn.setImagePosition_(NSImageOnly)
                else:
                    menu_btn.setTitle_("⋯")
            except Exception:
                menu_btn.setTitle_("⋯")
            if self._controller is not None:
                menu_btn.setTarget_(self._controller)
                menu_btn.setAction_("chatRowMenu:")
            cell.addSubview_(menu_btn)

        item = self._chat_rows[row]
        title = cell.viewWithTag_(11)
        sub = cell.viewWithTag_(12)
        menu_btn = cell.viewWithTag_(13)
        selected = bool(table.isRowSelected_(row))
        try:
            w = float(table.bounds().size.width)
        except Exception:
            w = 240.0
        text_w = max(80.0, w - 48.0)
        if title is not None:
            title.setStringValue_(item.get("title") or "New chat")
            title.setTextColor_(
                NSColor.whiteColor()
                if selected
                else NSColor.colorWithCalibratedWhite_alpha_(0.93, 1.0)
            )
            title.setFrame_(NSMakeRect(12, 24, text_w, 18))
        if sub is not None:
            when = relative_chat_time(item.get("updated_at") or "")
            model = _model_short(item.get("model_id") or "")
            bits = [b for b in (when, model) if b]
            sub.setStringValue_(" · ".join(bits) if bits else "")
            sub.setTextColor_(
                NSColor.colorWithCalibratedWhite_alpha_(0.78 if selected else 0.48, 1.0)
            )
            sub.setFrame_(NSMakeRect(12, 8, text_w, 14))
        if menu_btn is not None:
            cid = item["id"]
            try:
                menu_btn.setIdentifier_(cid)
            except Exception:
                pass
            try:
                menu_btn.setRepresentedObject_(cid)
            except Exception:
                pass
            menu_btn.setToolTip_("Chat options")
            menu_btn.setFrame_(NSMakeRect(max(12.0, w - 36.0), 12.0, 28.0, 28.0))
        return cell

    def _show_chat_row_menu(self, sender) -> None:
        from AppKit import NSMenu, NSMenuItem  # type: ignore

        chat_id = ""
        for getter in (
            lambda: sender.representedObject(),
            lambda: sender.identifier(),
        ):
            try:
                chat_id = str(getter() or "")
            except Exception:
                chat_id = ""
            if chat_id:
                break
        if not chat_id or self._controller is None:
            return
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Delete", "deleteChat:", ""
        )
        item.setTarget_(self._controller)
        item.setRepresentedObject_(chat_id)
        menu.addItem_(item)
        try:
            h = float(sender.bounds().size.height)
            menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, h), sender)
        except Exception:
            from AppKit import NSApp  # type: ignore

            event = NSApp.currentEvent()
            if event is not None:
                NSMenu.popUpContextMenu_withEvent_forView_(menu, event, sender)

    def delete_chat(self, chat_id: str) -> None:
        """Remove one chat from the sidebar, DB, and screenshot files."""
        from chat_llm import ChatSession

        if not chat_id:
            return
        if self._busy:
            self._set_status("Wait until the current reply finishes.")
            return
        was_current = chat_id == self.chat_id
        self.store.delete_chat(chat_id)
        if was_current:
            self.chat_id = None
            self.session = ChatSession()
        self.refresh_sidebar()
        if was_current:
            if self._chat_rows:
                self._select_sidebar_row(0)
                self.load_chat(self._chat_rows[0]["id"])
            else:
                self.start_new_chat()
        else:
            for i, row in enumerate(self._chat_rows):
                if row["id"] == self.chat_id:
                    self._select_sidebar_row(i)
                    break
        self._set_status(self._idle_status())

    def _select_sidebar_row(self, row: int) -> None:
        table = self.sidebar_table
        if table is None or row < 0 or row >= len(self._chat_rows):
            return
        table.selectRowIndexes_byExtendingSelection_(
            __import__("Foundation").NSIndexSet.indexSetWithIndex_(row), False
        )

    def _on_sidebar_select(self) -> None:
        table = self.sidebar_table
        if table is None or self._busy:
            return
        row = int(table.selectedRow())
        if row < 0 or row >= len(self._chat_rows):
            return
        chat_id = self._chat_rows[row]["id"]
        if chat_id == self.chat_id:
            return
        self.load_chat(chat_id)

    def start_new_chat(self) -> None:
        from chat_llm import ChatSession

        if self._busy:
            return
        model_id = self.selected_model_id_ui()
        chat = self.store.create_chat(title="New chat", model_id=model_id)
        self.chat_id = chat.id
        self.session = ChatSession()
        self._reload_transcript()
        self.refresh_sidebar()
        # Select the new chat (top of list)
        if self._chat_rows and self._chat_rows[0]["id"] == chat.id:
            self._select_sidebar_row(0)
        self._set_status(self._idle_status())

    def load_chat(self, chat_id: str) -> None:
        from chat_llm import ChatSession, get_model, set_selected_model_id

        chat = self.store.get_chat(chat_id)
        if chat is None:
            return
        self.chat_id = chat.id
        messages = self.store.list_messages(chat.id)
        self.session = ChatSession.from_messages(messages)
        self._render_messages(messages)
        if chat.model_id:
            info = set_selected_model_id(chat.model_id)
            self._select_model_in_popup(info.id)
        else:
            get_model(self.selected_model_id_ui())
        self._set_status(self._idle_status())

    def _select_model_in_popup(self, model_id: str) -> None:
        popup = self.model_popup
        if popup is None:
            return
        for i in range(int(popup.numberOfItems())):
            item = popup.itemAtIndex_(i)
            if item is not None and str(item.representedObject() or "") == model_id:
                popup.selectItemAtIndex_(i)
                return

    def submit(self) -> None:
        if self._busy or self._dictating:
            return
        text = ""
        if self.input is not None:
            text = str(self.input.stringValue() or "").strip()
        want_shot = self.screenshot_on()
        if not text and not want_shot:
            self._set_status("Type a message, or turn Screenshot on.")
            return
        if not self.chat_id:
            self.start_new_chat()
        chat_id = self.chat_id
        if not chat_id:
            self._set_status("Could not create chat.")
            return
        if self.input is not None:
            self.input.setStringValue_("")
        model_id = self.selected_model_id_ui()
        self._busy = True
        # Optimistic user turn + thinking under it (not the bottom status bar).
        self._append("You", text or "(screenshot)")
        self._set_thinking("Capturing screen…" if want_shot else "Thinking…")
        self._set_status(self._idle_status())

        def work() -> None:
            err = None
            reply = ""
            try:
                from chat_llm import (
                    capture_desktop_png,
                    complete_chat,
                    generate_chat_title,
                    get_model,
                    make_chat_client,
                )

                info = get_model(model_id)
                client = make_chat_client(info.provider)
                png = capture_desktop_png() if want_shot else None
                relpath = None
                if png:
                    relpath = self.store.save_screenshot(chat_id, png)
                user_text = text.strip() or "(no text)"
                self.store.add_message(
                    chat_id, "user", user_text, screenshot_relpath=relpath
                )
                chat = self.store.get_chat(chat_id)
                needs_title = bool(chat and chat.title == "New chat")
                self.store.touch_chat(chat_id, model_id=info.id)

                from Foundation import NSOperationQueue as _Q

                def show_thinking() -> None:
                    if self._busy:
                        self._reload_transcript(thinking="Thinking…")

                _Q.mainQueue().addOperationWithBlock_(show_thinking)

                # Rebuild in-memory session without duplicating the user turn
                # complete_chat will append user+assistant; seed from DB except last user.
                from chat_llm import ChatSession

                prior = [
                    m
                    for m in self.store.list_messages(chat_id)
                    if m.role in {"user", "assistant"}
                ]
                # Drop the user message we just saved — complete_chat adds it again
                if prior and prior[-1].role == "user":
                    prior = prior[:-1]
                self.session = ChatSession.from_messages(prior)

                reply = complete_chat(
                    client,
                    self.session,
                    text,
                    png,
                    model_id=info.id,
                )
                self.store.add_message(chat_id, "assistant", reply)
                if needs_title:
                    title = generate_chat_title(
                        client,
                        model_id=info.id,
                        user_text=user_text,
                        assistant_text=reply,
                    )
                    self.store.touch_chat(chat_id, title=title, model_id=info.id)
            except Exception as e:
                err = str(e)
            from Foundation import NSOperationQueue

            def done() -> None:
                self._busy = False
                self.refresh_sidebar()
                # Keep selection on current chat
                for i, row in enumerate(self._chat_rows):
                    if row["id"] == chat_id:
                        self._select_sidebar_row(i)
                        break
                if err:
                    self._reload_transcript()
                    self._append("Error", err)
                    self._set_status(err[:120])
                else:
                    self._reload_transcript()
                    self._set_status(self._idle_status())

            NSOperationQueue.mainQueue().addOperationWithBlock_(done)

        threading.Thread(target=work, name="cua-chat-send", daemon=True).start()

    def _set_mic_icon(self, listening: bool) -> None:
        btn = self.mic_btn
        if btn is None:
            return
        if listening:
            _style_icon_button(
                btn,
                tooltip="Stop dictation",
                symbol="stop.fill",
                fallback="stop",
                tint=_accent_color(),
            )
        else:
            _style_icon_button(
                btn,
                tooltip="Dictate",
                symbol="mic.fill",
                fallback="mic",
                tint=_muted_icon_color(),
            )

    def toggle_dictation(self) -> None:
        if self._busy:
            return
        if self._dictating:
            try:
                from app_status import request_send

                request_send()
            except Exception:
                pass
            return
        try:
            from app_status import read_status as snap

            if snap().get("stt_active"):
                self._set_status("Mic is already in use (voice orchestrator).")
                return
        except Exception:
            pass
        self._dictating = True
        self._set_status("Listening… (pause or Enter in terminal to send)")
        self._set_mic_icon(True)

        def work() -> None:
            text = ""
            err = None
            try:
                from openai import OpenAI

                from stt import listen_once

                text = listen_once(
                    OpenAI(),
                    prompt="Chat dictation…",
                    mode="freeform",
                    max_attempts=1,
                    announce_retries=False,
                )
            except Exception as e:
                err = str(e)
            from Foundation import NSOperationQueue

            def done() -> None:
                self._dictating = False
                self._set_mic_icon(False)
                if err:
                    self._set_status(err[:120])
                    return
                if self.input is not None and text:
                    existing = str(self.input.stringValue() or "").strip()
                    self.input.setStringValue_(
                        f"{existing} {text}".strip() if existing else text
                    )
                self._set_status("Dictation added — press Send or Enter")

            NSOperationQueue.mainQueue().addOperationWithBlock_(done)

        threading.Thread(target=work, name="cua-chat-stt", daemon=True).start()

    def show(self) -> None:
        if not self.is_alive():
            return
        try:
            self.window.orderFrontRegardless()
        except Exception:
            pass
        try:
            self.window.makeKeyAndOrderFront_(None)
        except Exception:
            try:
                self.window.orderFront_(None)
            except Exception:
                self._closed = True
                self.window = None

    def hide(self) -> None:
        if not self.is_alive():
            return
        try:
            self.window.orderOut_(None)
        except Exception:
            self._closed = True
            self.window = None

    def apply_status(self, data: dict) -> None:
        if not self.is_alive():
            return
        if chat_should_show(data):
            self.show()
        else:
            self.hide()

    def destroy(self) -> None:
        self.close_zoom()
        zw = self._zoom_window
        self._zoom_window = None
        self._zoom_image_view = None
        if zw is not None:
            try:
                zw.close()
            except Exception:
                pass
        win = self.window
        self.window = None
        self._closed = True
        if win is not None:
            try:
                win.setDelegate_(None)
                win.orderOut_(None)
                win.close()
            except Exception:
                pass
