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
    ("tui", "post.cw_field"): "the terminal's editor always shows the warning's field",
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
