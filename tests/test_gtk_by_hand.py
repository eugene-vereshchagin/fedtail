"""The GTK window driven as a person drives it: the real pointer drags a file from another
window, the real keyboard types and presses Tab (xdotool under Xvfb). The smoke tests
call the handlers themselves, so a widget that takes the event first is never seen:
a picture dropped on the editor went into its text as "file:///…", Tab put a tab
character in instead of completing a #tag (20.11) — and every test was green.

Skipped without xdotool or an X display (Wayland has no XTest); CI installs xdotool and
runs it under xvfb-run, where a skip would hide exactly this, so there it fails instead.
"""

import os
import shutil
import struct
import subprocess
import unittest
import zlib
from pathlib import Path

from .fakes import BOB, status
from .test_gtk_smoke import HAVE_GTK, _GtkBase, pump

X11 = HAVE_GTK and bool(os.environ.get("DISPLAY")) and not os.environ.get("WAYLAND_DISPLAY")
CAN = X11 and shutil.which("xdotool") is not None
IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))


def _png(path):
    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
        ">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(
            b"\x00\x10\x20\x30")) + chunk(b"IEND", b""))
    return path


def xdo(*args):
    out = subprocess.run(["xdotool", *map(str, args)], capture_output=True, text=True,
                         timeout=10).stdout.strip()
    pump(timeout=0.03)
    return out


class _ByHand:
    """The pointer and the keys for a _GtkBase test."""

    def setUp(self):
        if not CAN:
            if IN_CI:
                self.fail("xdotool and an X display are needed here (CI installs them)")
            self.skipTest("no xdotool or no X display")
        super().setUp()
        from gi.repository import Gdk, Gio, GLib, Gtk
        self.Gtk, self.Gdk = Gtk, Gdk
        self.pic = _png(Path(self._tmp.name) / "drop.png")
        # a window to drag from: a file manager's file as GTK offers one — the file
        # list, its address as uri-list and as text (which a text field takes)
        src = self.src = Gtk.Window(title="drag source")
        src.set_default_size(120, 120)
        label = Gtk.Label(label="drag me")
        src.set_child(label)
        drag = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        uri = Gio.File.new_for_path(str(self.pic)).get_uri()

        def prepare(*_a):
            files = Gdk.FileList.new_from_list([Gio.File.new_for_path(str(self.pic))])
            return Gdk.ContentProvider.new_union([
                Gdk.ContentProvider.new_for_value(files),
                Gdk.ContentProvider.new_for_bytes("text/uri-list",
                                                  GLib.Bytes.new(f"{uri}\r\n".encode())),
                Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8",
                                                  GLib.Bytes.new(uri.encode()))])
        drag.connect("prepare", prepare)
        label.add_controller(drag)
        src.present()
        self.win.set_default_size(900, 700)
        pump(lambda: src.get_mapped() and self.win.get_mapped(), 3)
        xdo("windowmove", self._xid(src), 0, 0)
        xdo("windowmove", self._xid(self.win), 200, 0)
        pump(timeout=0.3)

    def tearDown(self):
        src = getattr(self, "src", None)
        if src is not None:
            src.destroy()
        super().tearDown()

    @staticmethod
    def _xid(window):
        return window.get_surface().get_xid()

    def _at(self, widget, dx=10, dy=10):
        """Where on the screen a point of `widget` is."""
        from gi.repository import Graphene
        root = widget.get_root()
        ok, p = widget.compute_point(root, Graphene.Point().init(dx, dy))
        self.assertTrue(ok, "the widget isn't in its window")
        sx, sy = root.get_surface_transform()
        geo = xdo("getwindowgeometry", "--shell", self._xid(root))
        pos = dict(line.split("=", 1) for line in geo.splitlines() if "=" in line)
        return int(int(pos["X"]) + sx + p.x), int(int(pos["Y"]) + sy + p.y)

    def drag_to(self, widget, dx=10, dy=10):
        """The file dragged from the source window onto a point of `widget`, by the
        pointer, in small steps (as a hand does: GTK starts a drag after a few pixels)."""
        x0, y0 = self._at(self.src.get_child(), 5, 5)
        x1, y1 = self._at(widget, dx, dy)
        xdo("mousemove", x0, y0)
        xdo("mousedown", 1)
        for i in range(1, 25):
            xdo("mousemove", x0 + (x1 - x0) * i // 24, y0 + (y1 - y0) * i // 24)
        pump(timeout=0.3)
        xdo("mouseup", 1)
        pump(timeout=0.5)

    def type_into(self, widget, text, *keys):
        root = widget.get_root()
        xdo("windowfocus", "--sync", self._xid(root))
        widget.grab_focus()
        pump(lambda: widget.has_focus(), 2)
        xdo("type", "--delay", 30, text)
        pump(timeout=0.3)
        for k in keys:
            xdo("key", k)
            pump(timeout=0.3)

    def text_of(self, view):
        buf = view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def add_tagged_post(self):
        st = status("090", BOB, minute=30, text="#georgia")
        st["tags"] = [{"name": "georgia"}]
        self.world.add(st, home=True)
        self.core.poll_once()  # not built here: the editor gets it ready (GTK's never did)

    def counts_ready(self):
        self.assertTrue(pump(lambda: self.core.store.tag_counts(compute=False), 3),
                        "the editor opened, what tags complete from never prepared")


class GtkByHandTest(_ByHand, _GtkBase):
    def test_a_picture_dropped_on_the_editors_text_is_attached(self):
        dlg = self.win.compose()
        pump(lambda: dlg.text.get_mapped(), 3)
        self.drag_to(dlg.text)
        self.assertTrue(pump(lambda: [m[0] for m in dlg.media] == [str(self.pic)], 3),
                        f"not attached; the text has {self.text_of(dlg.text)!r}")
        self.assertNotIn("file://", self.text_of(dlg.text))

    def test_a_picture_dropped_on_a_lane_starts_a_post(self):
        lane = self.win.lane_views["home"]
        pump(lambda: lane.get_mapped(), 3)
        self.drag_to(lane, 60, 60)
        self.assertTrue(pump(lambda: self.win.composer is not None and
                             [m[0] for m in self.win.composer.media] == [str(self.pic)], 3))

    def test_tab_completes_a_tag(self):
        self.add_tagged_post()
        self.assertIsNone(self.core.store.tag_counts(compute=False))  # nothing asked yet
        dlg = self.win.compose()
        pump(lambda: dlg.text.get_mapped(), 3)
        self.counts_ready()
        self.type_into(dlg.text, "hi #geo")
        self.assertTrue(pump(lambda: dlg.suggest.get_visible(), 3), "no suggestion shown")
        self.assertIn("#georgia", dlg.suggest.get_text())
        self.type_into(dlg.text, "", "Tab")
        self.assertEqual(self.text_of(dlg.text), "hi #georgia ")


class GtkSplitByHandTest(_ByHand, _GtkBase):
    UI = {"layout": "split"}

    def test_tab_completes_a_tag_in_the_input_line(self):
        self.add_tagged_post()
        dock = self.win.dock
        pump(lambda: dock.text.get_mapped(), 3)
        self.counts_ready()
        self.type_into(dock.text, "#geo")
        self.assertTrue(pump(lambda: dock.suggest.get_visible(), 3), "no suggestion shown")
        self.type_into(dock.text, "", "Tab")
        self.assertEqual(self.text_of(dock.text), "#georgia ")


if __name__ == "__main__":
    unittest.main()
