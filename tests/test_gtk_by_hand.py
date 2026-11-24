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


    def test_a_picture_dropped_on_an_edit_leaves_it_open(self):
        """An edit sends no new pictures: a drop on it said nothing and closed it, a
        new post opening in its place (21.11) — now the edit stays and says so."""
        from fedtail.i18n import _

        from .fakes import ME
        mine = self.world.add(status("121", ME, text="моё"), home=True)
        self.core.store.put_statuses([mine])
        ed = self.win.compose_panel(edit=self.view.by_id("121"))
        self.assertTrue(pump(lambda: ed.text.get_mapped() and self.text_of(ed.text) == "моё",
                             5))
        self.drag_to(ed.text)
        pump(timeout=0.5)
        self.assertIs(self.win.composer, ed)
        self.assertFalse(ed.closed)
        self.assertEqual(ed.media, [])
        self.assertEqual(ed.hint.get_text(), _("edit_media_kept"))

    def test_esc_gives_the_keys_back(self):
        """The editor closed by Esc: the keys go back where they were — GTK handed them
        to the sidebar's menu button, and the next Space opened it (21.11)."""
        entry = self.win.cmdline.entry
        xdo("windowfocus", "--sync", self._xid(self.win))
        entry.grab_focus()
        pump(lambda: self.win.get_focus() is not None and
             (self.win.get_focus() is entry or self.win.get_focus().is_ancestor(entry)), 2)
        dlg = self.win.compose()
        pump(lambda: dlg.text.has_focus(), 3)
        self.type_into(dlg.text, "", "Escape")
        self.assertTrue(pump(lambda: dlg.closed, 2))
        f = self.win.get_focus()
        self.assertTrue(f is entry or (f is not None and f.is_ancestor(entry)),
                        f"the keys went to {type(f).__name__}")

    def test_esc_closes_a_window_of_its_own(self):
        """About, Settings, a page: Esc closes them, as Qt's dialogs (a plain Gtk.Window
        has no such key: they stayed open, 21.11)."""
        from fedtail.frontends.gtk import about
        from fedtail.frontends.gtk.dialogs import Page
        for make in (lambda: about.show(self.win),
                     lambda: Page(self.win, "page", "<p>text</p>")):
            dlg = make()
            dlg.present()
            self.assertTrue(pump(lambda d=dlg: d.get_mapped(), 3))
            xdo("windowfocus", "--sync", self._xid(dlg))
            xdo("key", "Escape")
            self.assertTrue(pump(lambda d=dlg: not d.get_mapped(), 2),
                            f"{type(dlg).__name__} stayed open")

    def test_the_keys_of_the_posts(self):
        """A card clicked, then j / k walk the posts and f likes the one under the
        cursor, as in Qt, the terminal and the web page (GTK had none: 21.11)."""
        lane = self.win.lane_views["home"]
        self.win.select_lane("home")
        self.assertTrue(pump(lambda: lane.get_mapped() and lane.rows, 3))
        x, y = self._at(lane.list, 200, 20)
        xdo("windowfocus", "--sync", self._xid(self.win))
        xdo("mousemove", x, y)
        xdo("click", 1)
        pump(timeout=0.3)
        posts = lane._posts()
        xdo("key", "j")
        pump(timeout=0.3)
        first = lane.cursor_key
        self.assertIn(first, posts)
        self.assertIn("ft-keyed", lane.rows[first].get_css_classes())
        xdo("key", "j")
        pump(timeout=0.3)
        self.assertNotEqual(lane.cursor_key, first)
        xdo("key", "k")
        pump(timeout=0.3)
        self.assertEqual(lane.cursor_key, first)
        sid = lane.specs[first].post.id
        xdo("key", "f")
        self.assertTrue(pump(lambda: self.world.statuses[sid].get("favourited"), 3))

    def test_the_keys_of_a_thread(self):
        """A thread's tab clicked: j / k walk its posts, ] / [ go to the next / previous
        top comment, - folds the branch and shows it again (common/postkeys) — the tab
        had no keys at all, only the lane (23.11)."""
        self.world.add(status("8000", BOB, minute=1, text="root"), home=True)
        for i, parent in ((1, "8000"), (2, "8000"), (3, "8001"), (4, "8000")):
            self.world.add(status(f"800{i}", BOB, parent, "B", minute=1 + i, text=f"c{i}"))
        self.win.open_thread("8000")
        page = self.win.threads["8000"]
        self.assertTrue(pump(lambda: len(page.items) == 5 and page.get_mapped(), 5))
        pump(timeout=0.3)
        keys = page.keys
        got = []
        real_press = keys.press
        keys.press = lambda name: got.append(name) or real_press(name)
        x, y = self._at(page, 200, 20)
        xdo("windowfocus", "--sync", self._xid(self.win))
        xdo("mousemove", x, y)
        xdo("click", 1)
        pump(timeout=0.3)
        xdo("key", "j")
        pump(timeout=0.3)
        self.assertIsNotNone(keys.cursor, (got, self.win.get_focus(),
                                           self.win.is_active()))
        keys.put_cursor("8000")
        for k, want in (("bracketright", "8001"), ("bracketright", "8002"),
                        ("bracketleft", "8001")):
            xdo("key", k)
            pump(timeout=0.3)
            self.assertEqual(keys.cursor, want, k)
        deep = keys._card("8003")
        xdo("key", "minus")
        self.assertTrue(pump(lambda: not deep.get_visible(), 2))
        xdo("key", "j")
        pump(timeout=0.3)
        self.assertEqual(keys.cursor, "8002")  # the folded one stepped over
        xdo("key", "k")
        xdo("key", "minus")
        self.assertTrue(pump(lambda: deep.get_visible(), 2))
        # "to the next new one" into a folded branch shows the branch again (24.11)
        xdo("key", "minus")
        self.assertTrue(pump(lambda: not deep.get_visible(), 2))
        page.new = {"8003"}
        self.win.thread_next_new("8000")
        self.assertTrue(pump(lambda: deep.get_visible(), 2))
        self.assertEqual(keys.hidden, set())
        # the keys are the config's ([keys]): another's own letter does it, the old doesn't
        self.win.cfg["keys"]["next_comment"] = "n"
        keys.put_cursor("8001")
        xdo("key", "bracketright")
        pump(timeout=0.3)
        self.assertEqual(keys.cursor, "8001")
        xdo("key", "n")
        pump(timeout=0.3)
        self.assertEqual(keys.cursor, "8002")

    def test_the_editor_follows_the_window(self):
        """The window resized by hand: the editor stays in its middle — placed on the
        window's size, not on every frame (a tick kept the clock going, 21.11)."""
        dlg = self.win.compose()
        self.assertTrue(pump(lambda: dlg.get_mapped(), 3))
        pump(timeout=0.5)
        self.assertFalse(getattr(dlg, "_ticking", 0))
        xdo("windowsize", self._xid(self.win), 1300, 900)

        def centred():
            ov = self.win.overlay
            w = ov.get_width()
            return w >= 1200 and abs(dlg.get_margin_start() - dlg.get_margin_end()) <= 2 \
                and dlg.get_margin_start() > 100
        self.assertTrue(pump(centred, 5), (self.win.overlay.get_width(),
                                           dlg.get_margin_start(), dlg.get_margin_end()))

    def test_ctrl_enter_sends(self):
        """Ctrl+Enter in the editor's text sends (the text field put a new line in, the
        editor never heard the key: 21.11)."""
        dlg = self.win.compose()
        pump(lambda: dlg.text.get_mapped(), 3)
        self.type_into(dlg.text, "hello", "ctrl+Return")
        self.assertTrue(pump(lambda: self.world.posted, 5), "not sent")
        self.assertEqual(self.world.posted[-1][0], "hello")

    def test_ctrl_k_makes_a_link(self):
        self.core.cfg["account"]["markdown"] = "on"
        dlg = self.win.compose()
        pump(lambda: dlg.text.get_mapped(), 3)
        self.assertIsNotNone(dlg.format_bar)
        self.type_into(dlg.text, "hi", "ctrl+a", "ctrl+k")
        self.assertEqual(self.text_of(dlg.text), "[hi](https://)")


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
