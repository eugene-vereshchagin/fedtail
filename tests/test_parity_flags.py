"""The settings each interface has to apply itself — how a card looks, what its editor
offers — read by every interface that has the thing (or once in frontends/common/, which
all of them use). test_parity.py compares the interfaces' words; a switch has no words of
its own, so a flag honoured in one window and ignored in the others passed it: the web
page drew link cards and :emoji: whatever feed.link_cards and feed.custom_emoji said, GTK
never folded a tail of #tags, the terminal had no link cards at all (21.11).

A flag an interface rightly doesn't read is in EXEMPT with the reason."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "fedtail" / "frontends"
SOURCES = {
    "qt": [FRONT / "qt"],
    "gtk": [FRONT / "gtk"],
    "tui": [FRONT / "tui"],
    "web": [FRONT / "web" / "server.py", ROOT / "fedtail" / "data" / "web" / "app.js"],
}
COMMON = [FRONT / "common"]

# section.key — what an interface has to do itself
FLAGS = ["feed.link_cards", "feed.custom_emoji", "feed.text_markup", "feed.collapse_tags",
         "ui.alt_text", "ui.media_grid", "ui.post_keys", "post.cw_field", "post.focus_point",
         "post.drafts_autosave", "post.resize_images"]

EXEMPT = {
    ("tui", "feed.custom_emoji"): "a terminal draws text: :blobcat: stays a code",
    ("tui", "feed.text_markup"): "a terminal draws plain text: no strike-through",
    ("tui", "ui.alt_text"): "no hover in a terminal; v shows a picture with its words",
    ("tui", "ui.media_grid"): "a terminal shows a line per attachment, no grid",
    ("tui", "post.focus_point"): "the terminal's editor sets no focus point",
    ("tui", "ui.post_keys"): "the terminal is the keyboard: its letters are its only way",
}


def _text(paths):
    out = []
    for p in paths:
        files = [p] if p.is_file() else sorted(p.rglob("*.py"))
        out += [f.read_text("utf-8") for f in files]
    return "\n".join(out)


class FlagParityTest(unittest.TestCase):
    def test_every_interface_reads_its_flags(self):
        common = _text(COMMON)
        missing = []
        for flag in FLAGS:
            key = flag.split(".", 1)[1]
            word = re.compile(rf"\b{re.escape(key)}\b")
            if word.search(common):
                continue  # applied once for all of them
            for ui, paths in SOURCES.items():
                if (ui, flag) in EXEMPT:
                    continue
                if not word.search(_text(paths)):
                    missing.append(f"{ui}: {flag}")
        self.assertEqual(missing, [], "a flag one interface reads and this one ignores — "
                                      "honour it, or say why in EXEMPT")

    def test_the_exemptions_are_still_needed(self):
        for (ui, flag), why in EXEMPT.items():
            with self.subTest(ui=ui, flag=flag):
                self.assertTrue(why)
                key = flag.split(".", 1)[1]
                self.assertNotRegex(_text(SOURCES[ui]), rf"\b{re.escape(key)}\b",
                                    "read there now: the exemption goes")


if __name__ == "__main__":
    unittest.main()


# ---- every setting, every interface (21.11) --------------------------------------------
# A sweep of all ~340 settings through the five interfaces found ~40 a window honoured and
# the others ignored. This holds them all: a setting nothing shared applies (the core,
# frontends/common and the other shared modules below never read it) is each
# interface's own to apply — every one it is meant for has to read it, or ALL_EXEMPT says
# why not. A new setting read by one interface only fails here until the others do.

SHARED = [ROOT / "fedtail" / x for x in (
    "core", "protocols", "diag.py", "__main__.py", "desktop.py", "issue.py", "reportsend.py",
    "deps.py", "frontends/common", "frontends/cli.py", "frontends/notifytext.py",
    "frontends/richtext.py", "frontends/iconart.py", "frontends/iconpack.py",
    "frontends/themefile.py", "frontends/soundpack.py")]
ANDROID = [ROOT / "android" / "app" / "src" / "main" / "java",
           ROOT / "android" / "app" / "src" / "main" / "python"]
FIVE = ("qt", "gtk", "tui", "web", "android")
WINDOWS = ("qt", "gtk")

# whom a setting is for at all (the rest: all five)
FOR = {
    "tui": ("tui",), "phone": ("android",), "web": ("web",),  # whole sections
    "ui.adwaita": ("gtk",), "ui.accessibility": ("gtk",), "ui.gtk_headerbar": ("gtk",),
    # the desktop window's own: a tray, its keys, its tabs, its window and its watchdog
    **{k: WINDOWS for k in (
        "ui.hung_copy_seconds", "ui.tray", "ui.close_to_tray", "ui.esc", "ui.switch_closes",
        "ui.compose_size", "ui.sidebar_footer", "ui.whats_this", "ui.video_player",
        "ui.image_upscale", "ui.unload_hidden_minutes", "ui.keep_hidden_lanes",
        "ui.number_keys", "ui.pin_tabs", "debug.watchdog_seconds", "debug.stall_ms",
        "ui.roster_on_top", "ui.split_tabs", "ui.video_decode", "ui.gifv_max",
        "ui.gifv_fps")},
    "notify.seconds": ("qt", "gtk", "tui"),  # notify-send's timeout: the desktop's notes
}

ALL_EXEMPT = {
    # docs/src/parity.toml says each of these too
    ("gtk", "ui.roster_on_top"): "GTK 4 can't keep a window above others (window-above)",
    ("gtk", "ui.split_tabs"): "Qt's for now (window-above)",
    ("gtk", "ui.video_decode"): "GTK plays through GStreamer (player-tuning)",
    ("gtk", "ui.gifv_max"): "GTK loops three gifs, as Qt's default (player-tuning)",
    ("gtk", "ui.gifv_fps"): "GStreamer's own pace (player-tuning)",
    ("gtk", "notify.seconds"): "GTK's notifications go by the desktop's time (Gio)",
    ("tui", "ui.font_size"): "a terminal's own font and size (fonts-settings)",
    ("tui", "ui.mono_font"): "a terminal's own font and size (fonts-settings)",
    ("android", "ui.font_size"): "Android's own text size (fonts-settings)",
    ("android", "ui.mono_font"): "the theme's fonts on the phone (fonts-settings)",
    ("tui", "ui.compose"): "the terminal's editor is a screen of its own",
    ("tui", "ui.account_colors"): "the terminal marks the account with its name",
    ("tui", "ui.column_width"): "a terminal is one column wide",
    ("android", "ui.column_width"): "the phone's columns are phone.layout's",
    ("tui", "ui.image_viewer"): "the terminal's viewer is tui.viewer",
    ("tui", "ui.links_in_app"): "the terminal opens links in a browser always",
    ("tui", "ui.actions"): "no buttons under a post in a terminal (actions-look)",
    ("tui", "ui.post_keys"): "the terminal is the keyboard: its letters are its only way",
    ("android", "ui.post_keys"): "a phone has no keyboard keys over a post",
    ("android", "ui.additional_highlight"): "nothing hovers on a phone",
    ("tui", "ui.media_grid"): "a terminal shows a line per attachment, no grid",
    ("tui", "ui.alt_text"): "no hover in a terminal; v shows a picture with its words",
    ("tui", "feed.custom_emoji"): "a terminal draws text: :blobcat: stays a code",
    ("tui", "feed.text_markup"): "a terminal leaves struck text as written (terminal-text)",
    ("tui", "feed.show_moved"): "the terminal's profile has no head (profile-head)",
    ("tui", "feed.profile_pinned"): "the terminal's profile has no head (profile-head)",
    ("tui", "feed.profile_featured"): "the terminal's profile has no head (profile-head)",
    ("tui", "feed.sensitive_media"): "a terminal shows no pictures in a lane: N media",
    ("tui", "post.focus_point"): "the terminal's editor sets no focus point",
    ("qt", "ui.expand_cw"): "read through config.expand_cw (with ui.arts_mode)",
    ("gtk", "ui.expand_cw"): "read through config.expand_cw (with ui.arts_mode)",
    ("tui", "ui.expand_cw"): "read through config.expand_cw (with ui.arts_mode)",
    # the phone draws what the web server gives it: these are applied there for it
    **{("android", k): "the web server applies it to what the phone gets" for k in (
        "feed.custom_emoji", "feed.show_moved", "feed.collapse_tags", "feed.text_markup",
        "feed.profile_pinned", "feed.profile_featured", "post.alt_reminder",
        "post.send_in_background", "post.focus_point")},
}


def _keys():
    from fedtail.core.config import DEFAULTS
    return [f"{s}.{k}" for s, v in DEFAULTS.items() if isinstance(v, dict) for k in v]


def _read(paths, pats=("*.py",)):
    skip = re.compile(r"(config[a-z_]*|presets|settings[a-z_]*)\.(py|js|kt)$")
    out = []
    for p in paths:
        files = [p] if p.is_file() else [f for pat in pats for f in sorted(p.rglob(pat))]
        out += [f.read_text("utf-8") for f in files if not skip.search(f.name)]
    return "\n".join(out)


class EverySettingTest(unittest.TestCase):
    def test_each_is_read_where_it_is_meant_to_be(self):
        shared = _read(SHARED)
        ui = {n: _read(p, ("*.py", "*.js")) for n, p in SOURCES.items()}
        ui["web"] += _read([ROOT / "fedtail" / "data" / "web", FRONT / "web"], ("*.js", "*.py"))
        ui["android"] = _read(ANDROID, ("*.kt", "*.py"))
        missing = []
        for key in _keys():
            section, name = key.split(".", 1)
            word = re.compile(r"[\"']" + re.escape(name) + r"[\"']")
            if word.search(shared):
                continue  # applied once, for every one
            for one in FOR.get(key, FOR.get(section, FIVE)):
                if (one, key) not in ALL_EXEMPT and not word.search(ui[one]):
                    missing.append(f"{one}: {key}")
        self.assertEqual(missing, [], "a setting one interface applies and this one "
                                      "ignores — honour it, or say why in ALL_EXEMPT")

    def test_the_exemptions_still_hold(self):
        ui = {n: _read(p, ("*.py", "*.js")) for n, p in SOURCES.items()}
        ui["web"] += _read([ROOT / "fedtail" / "data" / "web", FRONT / "web"], ("*.js", "*.py"))
        ui["android"] = _read(ANDROID, ("*.kt", "*.py"))
        keys = set(_keys())
        for (one, key), why in ALL_EXEMPT.items():
            with self.subTest(ui=one, key=key):
                self.assertIn(key, keys, "no such setting any more")
                self.assertTrue(why)
                name = key.split(".", 1)[1]
                self.assertNotRegex(ui[one], r"[\"']" + re.escape(name) + r"[\"']",
                                    "read there now: the exemption goes")


class DocKeysTest(unittest.TestCase):
    NOT_KEYS = {"activity.wav", "web.key", "account.bot", "account.moved"}  # files, API

    def test_every_key_the_docs_name_is_there(self):
        """A key the feature list or parity.toml names is a key of the config file (its
        tables: [window], [card]…) or of config.DEFAULTS: `subs.replies_to_me` was
        described for months after it went (21.11)."""
        from fedtail.core.config import DEFAULTS
        have, sec = set(), None
        example = (ROOT / "fedtail" / "data" / "config.example.en.toml").read_text("utf-8")
        for line in example.splitlines():
            m = re.match(r"^\[([a-z_]+)\]", line)
            if m:
                sec = m.group(1)
                continue
            m = re.match(r"^#?\s*([a-z_]+)\s*=", line)
            if m and sec:
                have.add(f"{sec}.{m.group(1)}")
        have |= {f"{s}.{k}" for s, v in DEFAULTS.items() if isinstance(v, dict) for k in v}
        sections = {k.split(".")[0] for k in have}
        docs = sorted((ROOT / "docs" / "src" / "features").glob("*.toml")) + \
            [ROOT / "docs" / "src" / "parity.toml"]
        bad = set()
        for f in docs:
            for m in re.finditer(r"`([a-z_]+)\.([a-z_]+)(?:\s*=[^`]*)?`", f.read_text("utf-8")):
                key = f"{m.group(1)}.{m.group(2)}"
                if m.group(1) in sections and key not in have and key not in self.NOT_KEYS:
                    bad.add(f"{f.name}: {key}")
        self.assertEqual(sorted(bad), [])
