"""Real pictures and video in the terminal: what the terminal can (tui/termcaps.py), the
picture viewer and mpv chosen and run with the app suspended, textual-image's sixel or
kitty widget in the lane and full screen (tui/pictures.py, tui/app.py). Programs and
textual-image are stood in for: nothing is run, nothing installed is needed."""

import io
import sys
import types
import unittest
from contextlib import contextmanager
from unittest import mock

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import rich  # noqa: F401 — the half blocks are rich Text: pictures.py needs it
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

from fedtail.core import config
from fedtail.frontends.tui import termcaps

from .fakes import BOB, status


def which_of(*have):
    return lambda name: f"/usr/bin/{name}" if name in have else None


class TermcapsTest(unittest.TestCase):
    def caps(self, **env):
        return termcaps.detect(env, platform="linux")

    def test_terminals(self):
        for env, name, graphics in (
                ({"KITTY_WINDOW_ID": "1"}, "kitty", "kitty"),
                ({"TERM": "xterm-kitty"}, "kitty", "kitty"),
                ({"TERM_PROGRAM": "ghostty"}, "Ghostty", "kitty"),
                ({"KONSOLE_VERSION": "250401"}, "Konsole", "sixel"),
                ({"KONSOLE_DBUS_SESSION": "/x"}, "Konsole", "sixel"),
                ({"WEZTERM_PANE": "0"}, "WezTerm", "sixel"),
                ({"TERM_PROGRAM": "iTerm.app"}, "iTerm.app", "sixel"),
                ({"WT_SESSION": "x"}, "Windows Terminal", "sixel"),
                ({"TERM": "foot-extra"}, "foot", "sixel"),
                ({"VTE_VERSION": "7800"}, "VTE (GNOME Terminal…)", None),
                ({"TERM": "linux"}, "Linux console", None),
                ({"TERM": "xterm-256color"}, "xterm-256color", None),
                ({}, "?", None)):
            with self.subTest(env=env):
                c = self.caps(**env)
                self.assertEqual((c.name, c.graphics), (name, graphics))
        # tmux in between: graphics pass only if it was set up — none assumed
        c = self.caps(KONSOLE_VERSION="1", TMUX="/tmp/x")
        self.assertEqual((c.name, c.graphics, c.tmux), ("Konsole", None, True))

    def test_display(self):
        self.assertFalse(self.caps().display)
        self.assertTrue(self.caps(DISPLAY=":0").display)
        self.assertTrue(self.caps(WAYLAND_DISPLAY="wayland-0").display)
        self.assertTrue(termcaps.detect({}, platform="win32").display)
        self.assertIsInstance(termcaps.detect(), termcaps.Caps)  # this process's own

    def test_viewer(self):
        kitty = self.caps(KITTY_WINDOW_ID="1")
        konsole = self.caps(KONSOLE_VERSION="1")
        plain = self.caps(TERM="xterm")
        self.assertEqual(termcaps.viewer(kitty, which_of("kitten", "chafa")).name, "kitten")
        self.assertEqual(termcaps.viewer(konsole, which_of("kitten", "chafa")).name, "chafa")
        self.assertEqual(termcaps.viewer(plain, which_of("timg")).name, "timg")
        self.assertEqual(termcaps.viewer(konsole, which_of("img2sixel")).name, "img2sixel")
        self.assertIsNone(termcaps.viewer(plain, which_of("img2sixel")))
        self.assertIsNone(termcaps.viewer(plain, which_of()))

    def test_viewer_arguments(self):
        T = termcaps.Tool
        self.assertEqual(T("kitten", "/k", "kitty").argv("f", 80, 20),
                         ["/k", "icat", "--align", "left", "f"])
        self.assertEqual(T("chafa", "/c", "sixel").argv("f", 80, 20),
                         ["/c", "-f", "sixels", "--size", "80x20", "--animate", "off", "f"])
        self.assertIn("symbols", T("chafa", "/c", None).argv("f", 0, 0))
        self.assertIn("1x1", T("chafa", "/c", "kitty").argv("f", 0, 0))
        self.assertEqual(T("timg", "/t", "kitty").argv("f", 10, 5), ["/t", "-pk", "-g10x5", "f"])
        self.assertEqual(T("timg", "/t", None).argv("f", 10, 5)[1], "-pq")
        self.assertEqual(T("img2sixel", "/i", "sixel").argv("f", 10, 5), ["/i", "f"])

    def test_video(self):
        desk = termcaps.detect({"DISPLAY": ":0", "KONSOLE_VERSION": "1"}, platform="linux")
        ssh = termcaps.detect({"KONSOLE_VERSION": "1"}, platform="linux")
        kitty = termcaps.detect({"KITTY_WINDOW_ID": "1"}, platform="linux")
        plain = termcaps.detect({"TERM": "xterm"}, platform="linux")
        mpv = which_of("mpv")
        self.assertEqual(termcaps.video(desk, "auto", which_of()), ("browser", None))
        self.assertEqual(termcaps.video(desk, "browser", mpv), ("browser", None))
        # Konsole on a desktop shows sixel: the console player, not a window over it
        how, argv = termcaps.video(desk, "auto", mpv, loop=True)
        self.assertEqual((how, argv[-2]), ("terminal", "--vo=sixel"))
        self.assertIn("--loop-file=inf", argv)
        self.assertIn("--term-osd-bar=yes", argv)
        desk_plain = termcaps.detect({"DISPLAY": ":0", "TERM": "xterm"}, platform="linux")
        how, argv = termcaps.video(desk_plain, "auto", mpv)  # no pictures there: a window
        self.assertEqual(how, "window")
        self.assertIn("--force-window=immediate", argv)
        self.assertEqual(termcaps.video(desk, "window", mpv)[0], "window")
        self.assertEqual(termcaps.video(ssh, "window", mpv)[0], "window")
        for caps, vo in ((ssh, "sixel"), (kitty, "kitty"), (plain, "tct")):
            how, argv = termcaps.video(caps, "auto", mpv)
            self.assertEqual((how, argv[-2]), ("terminal", f"--vo={vo}"))
        self.assertEqual(termcaps.video(desk, "terminal", mpv)[0], "terminal")
        self.assertEqual(set(termcaps.VIDEO_MODES), config.CHOICES[("tui", "video")])

    def test_summary(self):
        lines = termcaps.summary({"KONSOLE_VERSION": "1"}, which_of("chafa", "mpv"), "linux")
        text = "\n".join(lines)
        self.assertIn("terminal: Konsole", text)
        self.assertIn("graphics: sixel", text)
        self.assertIn("picture viewer: chafa", text)
        self.assertIn("a video plays: terminal", text)
        fake = types.ModuleType("textual_image")
        with mock.patch.dict(sys.modules, {"textual_image": fake}):
            text = "\n".join(termcaps.summary({"TMUX": "x"}, which_of(), "linux"))
        self.assertIn("textual-image: installed", text)
        self.assertIn("(inside tmux)", text)
        self.assertIn("none (the app", text)
        self.assertIn("mpv: not found", text)
        with mock.patch.dict(sys.modules, {"textual_image": None}):
            self.assertIn("textual-image: not installed",
                          "\n".join(termcaps.summary({}, which_of(), "linux")))


class Tty(io.StringIO):
    def isatty(self):
        return True


def fake_textual_image(kind):
    """A stand-in for textual_image.widget as it comes out in a terminal of `kind`."""
    pkg = types.ModuleType("textual_image")
    widget = types.ModuleType("textual_image.widget")

    class SixelImage:
        pass

    class TGPRenderable:
        pass
    TGPRenderable.__name__ = "Image"
    TGPRenderable.__module__ = "textual_image.renderable.tgp"

    class HalfRenderable:
        pass
    HalfRenderable.__name__ = "Image"
    HalfRenderable.__module__ = "textual_image.renderable.halfcell"

    class AutoImage:
        _Renderable = TGPRenderable if kind == "kitty" else HalfRenderable
    widget.SixelImage = SixelImage
    widget.Image = SixelImage if kind == "sixel" else AutoImage
    pkg.widget = widget
    return {"textual_image": pkg, "textual_image.widget": widget}


@unittest.skipUnless(Image is not None and HAVE_RICH, "Pillow or rich is not installed")
class PicturesTest(unittest.TestCase):
    def setUp(self):
        from fedtail.frontends.tui import pictures
        self.p = pictures
        self.addCleanup(pictures._graphics.update, cls=None, kind=None)

    def png(self, w=40, h=20):
        buf = io.BytesIO()
        Image.new("RGBA", (w, h), (0, 200, 0, 128)).save(buf, "PNG")
        return buf.getvalue()

    def test_mode(self):
        self.assertEqual(self.p.mode({"tui": {"pictures": "inline"}}), "auto")
        self.assertEqual(self.p.mode({"tui": {"pictures": "key"}}), "key")
        self.assertEqual(self.p.mode({}), "auto")
        self.assertEqual(set(self.p.MODES) | {"inline"}, config.CHOICES[("tui", "pictures")])

    def test_prepare(self):
        p = self.p
        for kind in ("sixel", "kitty"):
            with mock.patch.dict(sys.modules, fake_textual_image(kind)):
                self.assertEqual(p.prepare("auto", Tty()), kind)
                self.assertEqual(p.graphics(), kind)
        with mock.patch.dict(sys.modules, fake_textual_image("half")):
            self.assertIsNone(p.prepare("inline", Tty()))  # its half cells: ours instead
        self.assertIsNone(p.graphics())
        with mock.patch.dict(sys.modules, {"textual_image": None}):
            self.assertIsNone(p.prepare("auto", Tty()))  # not installed
        with mock.patch.dict(sys.modules, fake_textual_image("sixel")):
            self.assertIsNone(p.prepare("blocks", Tty()))  # not asked for
            self.assertIsNone(p.prepare("auto", io.StringIO()))  # not a terminal
            with mock.patch.object(p.sys, "__stdout__", None):
                self.assertIsNone(p.prepare("auto"))
            with mock.patch.object(p, "Image", None):
                self.assertIsNone(p.prepare("auto", Tty()))

    def test_graphic_and_opened(self):
        p = self.p
        self.assertIsNone(p.graphic(self.png(), 4))  # nothing prepared

        class Widget:
            def __init__(self, img, **kw):
                self.img, self.kw = img, kw
                self.styles = types.SimpleNamespace()
        p._graphics.update(cls=Widget, kind="sixel")
        w = p.graphic(self.png(), 6, 30, id="x")
        self.assertEqual((w.styles.height, w.styles.width, w.kw), (6, 30, {"id": "x"}))
        self.assertEqual(w.img.mode, "RGB")  # transparency flattened on black
        self.assertEqual(p.graphic(self.png(), 6).styles.width, "auto")
        self.assertIsNone(p.graphic(b"not a picture", 6))
        self.assertIsNone(p.opened(b""))
        with mock.patch.object(p, "MAX_PIXELS", 10):
            self.assertIsNone(p.opened(self.png()))
        self.assertEqual(p.opened(self.png(), (8, 8)).mode, "RGB")


@unittest.skipUnless(HAVE_TEXTUAL and Image is not None, "Textual or Pillow is missing")
class RunTest(unittest.TestCase):
    def test_textual_image_is_asked_before_the_app(self):
        from fedtail.frontends import tui
        core = mock.Mock()
        core.cfg = {"tui": {"pictures": "inline"}}
        order = []
        with mock.patch("fedtail.frontends.tui.pictures.prepare",
                        side_effect=lambda m: order.append(("prepare", m))), \
                mock.patch("fedtail.frontends.tui.app.FedtailApp") as App:
            App.return_value.run.side_effect = lambda: order.append(("run", None))
            App.return_value.return_code = None
            App.return_value.relaunch = None  # a Mock's is truthy: a profile switch
            self.assertEqual(tui.run(core, None, []), 0)
        self.assertEqual(order, [("prepare", "auto"), ("run", None)])
        core.shutdown.assert_called_once()


if HAVE_TEXTUAL:
    from .test_cov_tui_app import png, with_picture
    from .test_cov_tui_host import Base, done
else:  # pragma: no cover — the class below is skipped
    Base, done = unittest.IsolatedAsyncioTestCase, None


@contextmanager
def suspended(log):
    log.append("suspend")
    yield
    log.append("resume")


@unittest.skipUnless(HAVE_TEXTUAL and Image is not None, "Textual or Pillow is missing")
class AppMediaTest(Base):
    def setUp(self):
        super().setUp()
        from fedtail.frontends.tui import pictures
        self.addCleanup(pictures._graphics.update, cls=None, kind=None)

    def posts(self, w):
        w.add(with_picture(status("001", BOB, minute=1, text="cat", vis="public")), home=True)
        w.add(with_picture(status("002", BOB, minute=2, text="video", vis="public"),
                           kind="video"), home=True)
        w.add(with_picture(status("003", BOB, minute=3, text="no address", vis="public"),
                           kind="gifv", url=False), home=True)

    async def to(self, pilot, app, sid):
        from textual.widgets import ListView
        posts = app.query_one("#posts", ListView)
        await self.wait(pilot, lambda: sid in [getattr(x, "entry", None) and x.entry.id
                                               for x in posts.children])
        posts.focus()
        posts.index = [getattr(x, "entry", None) and x.entry.id
                       for x in posts.children].index(sid)
        await pilot.pause(0.05)

    async def test_video_goes_to_mpv_a_window_the_terminal_or_the_browser(self):
        from fedtail.frontends.tui import app as app_mod
        core, w = self.make(tui={"pictures": "off"})
        self.posts(w)
        app = self.app_of(core)
        async with app.run_test(size=(100, 30)) as pilot:
            await self.started(pilot, app)
            await self.to(pilot, app, "002")
            # a desktop's terminal without pictures: mpv's window; one with sixel
            # (Konsole, here or over ssh): the console player, in the terminal itself
            desk = app_mod.termcaps.Caps("xterm", None, True)
            ssh = app_mod.termcaps.Caps("Konsole", "sixel", True)
            with mock.patch.object(app_mod.termcaps.shutil, "which", which_of("mpv")), \
                    mock.patch.object(app_mod.subprocess, "Popen") as popen, \
                    mock.patch.object(app_mod.subprocess, "run") as run:
                app.caps = lambda: desk
                app.action_pictures()  # a post of videos only: it plays
                argv = popen.call_args[0][0]
                self.assertEqual(argv[0], "/usr/bin/mpv")
                self.assertEqual(argv[-1], "https://example.test/002.png")
                self.assertTrue(popen.call_args[1]["start_new_session"])
                self.assertIn(app_mod._("tui_playing"), self.notes)
                # sixel there: into this terminal, the app suspended
                app.caps = lambda: ssh
                log = []
                with mock.patch.object(type(app), "is_headless", False), \
                        mock.patch.object(app, "suspend", lambda: suspended(log)):
                    app.action_pictures()
                self.assertEqual(log, ["suspend", "resume"])
                self.assertIn("--vo=sixel", run.call_args[0][0])
                # can't suspend (a test, Textual Web): the browser
                app.action_pictures()
                self.browser.assert_called_with("https://example.test/002.png")
            with mock.patch.object(app_mod.termcaps.shutil, "which", which_of()):
                app.action_pictures()  # no mpv: the browser, and it says so
            self.assertIn(app_mod._("tui_video_browser"), self.notes)
            await self.to(pilot, app, "003")
            app.action_pictures()  # a gif with no address at all
            self.assertIn(app_mod._("tui_no_video"), self.notes)

    async def test_run_outside(self):
        from fedtail.frontends.tui import app as app_mod
        core, _w = self.make(tui={"pictures": "off"})
        app = self.app_of(core)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.started(pilot, app)
            self.assertFalse(app.run_outside(["x"]))  # headless: never suspended
            log = []
            with mock.patch.object(type(app), "is_headless", False), \
                    mock.patch.object(app, "suspend", lambda: suspended(log)), \
                    mock.patch.object(app_mod.subprocess, "run") as run, \
                    mock.patch("builtins.input", side_effect=EOFError) as ask:
                self.assertTrue(app.run_outside(["prog", "a"], wait=True))
                run.assert_called_once()
                ask.assert_called_once()

                def broken():
                    raise RuntimeError("SuspendNotSupported")
                with mock.patch.object(app, "suspend", broken):
                    self.assertFalse(app.run_outside(["prog"]))

    async def test_pictures_by_a_viewer_outside_the_app(self):
        from fedtail.frontends.tui import app as app_mod
        from fedtail.frontends.tui.app import PictureScreen
        core, w = self.make(tui={"pictures": "off"})
        self.posts(w)
        app = self.app_of(core)
        view = app.core
        seen = []

        def run(argv, **_kw):
            with open(argv[-1], "rb") as f:
                seen.append((argv[:3], f.read()))
        answers = {"https://example.test/001.png": done(png())}
        with mock.patch.object(type(view), "media_bytes",
                               lambda _s, url: answers.get(url, done(error=OSError("x")))):
            async with app.run_test(size=(100, 30)) as pilot:
                await self.started(pilot, app)
                await self.to(pilot, app, "001")
                konsole = app_mod.termcaps.Caps("Konsole", "sixel", True)
                app.caps = lambda: konsole
                log = []
                with mock.patch.object(type(app), "is_headless", False), \
                        mock.patch.object(app, "suspend", lambda: suspended(log)), \
                        mock.patch.object(app_mod.termcaps.shutil, "which",
                                          which_of("chafa")), \
                        mock.patch.object(app_mod.subprocess, "run", side_effect=run), \
                        mock.patch("builtins.input", return_value=""):
                    app.action_pictures()
                    await self.wait(pilot, lambda: log == ["suspend", "resume"])
                    self.assertEqual(seen[0][0], ["/usr/bin/chafa", "-f", "sixels"])
                    self.assertEqual(seen[0][1], png())
                    import glob
                    import tempfile
                    self.assertEqual(glob.glob(tempfile.gettempdir() + "/fedtail-*.img"), [])

                    # the viewer fails: the app's own view instead
                    def broken():
                        raise RuntimeError("no")
                    with mock.patch.object(app, "suspend", broken):
                        app.action_pictures()
                        await self.wait(pilot, lambda: isinstance(app.screen, PictureScreen))
                    app.pop_screen()
                    # nothing came: said, nothing suspended
                    answers.clear()
                    log.clear()
                    app.action_pictures()
                    await self.wait(pilot, lambda: app_mod._("tui_picture_failed", err="?")
                                    in self.notes)
                    self.assertEqual(log, [])
                # no viewer program, or asked for the app's own view: in the app
                with mock.patch.object(app_mod.termcaps.shutil, "which", which_of()), \
                        mock.patch.object(type(app), "is_headless", False):
                    self.assertFalse(app.show_outside([]))
                del app.caps
                self.assertIsInstance(app.caps(), app_mod.termcaps.Caps)  # this terminal
                app.core.cfg["tui"]["viewer"] = "app"
                self.assertFalse(app.show_outside([]))

    async def test_real_pictures_in_the_lane_and_full_screen(self):
        from textual.widgets import Static

        from fedtail.frontends.tui import pictures
        from fedtail.frontends.tui.app import PictureScreen, PostItem

        class Shown(Static):
            def __init__(self, img, **kw):
                super().__init__("[picture]", **kw)
                self.img = img
        pictures._graphics.update(cls=Shown, kind="sixel")
        core, w = self.make(tui={"pictures": "auto", "picture_rows": 4})
        self.posts(w)
        app = self.app_of(core)
        view = app.core
        with mock.patch.object(type(view), "media_bytes", lambda _s, url: done(png())):
            async with app.run_test(size=(100, 30)) as pilot:
                await self.started(pilot, app)
                posts = app.query_one("#posts")
                await self.wait(pilot, lambda: any(isinstance(getattr(x, "graphic", None), Shown)
                                                   for x in posts.children),
                                what="a real picture in the lane")
                await app.refresh_posts()  # from the cache: the bytes, a new widget
                await self.wait(pilot, lambda: any(isinstance(getattr(x, "graphic", None),
                                                              Shown) for x in posts.children))
                item = next(x for x in posts.children if isinstance(x, PostItem))
                item.set_graphic(None)
                self.assertFalse(item.has_picture)
                detached = PostItem(view.by_id("001"), "x")
                app._put_graphic(detached, png(), 4)  # not on screen: left alone
                self.assertIsNone(detached.graphic)
                with mock.patch.object(pictures, "graphic", return_value=None):
                    app._put_graphic(item, png(), 4)  # not a picture: nothing mounted

                media = list(view.by_id("001").media) + list(view.by_id("002").media)
                s = PictureScreen(media)
                app.push_screen(s)
                await self.wait(pilot, lambda: s.query(".pic-img"), what="full screen")
                self.assertFalse(s.query_one("#pic").display)
                s._put_graphic(99, png(), 10, 5)  # an answer for another picture
                with mock.patch.object(pictures, "graphic", return_value=None):
                    s._put_graphic(s.at, png(), 10, 5)
                    self.assertIn("?", str(s.query_one("#pic").render()))
                s.action_play()  # a picture: nothing to play
                played = []
                app.play = played.append
                s.action_step(1)
                await pilot.pause(0.1)
                # the video's still frame, and how to play it
                self.assertIn("mpv", str(s.query_one("#pic-title").render()))
                s.action_play()
                self.assertEqual([m.kind for m in played], ["video"])
                app.pop_screen()
                s._put_graphic(s.at, png(), 10, 5)  # closed meanwhile: nothing


if __name__ == "__main__":
    unittest.main()
