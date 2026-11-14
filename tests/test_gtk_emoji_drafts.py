"""GTK editor: the emoji picker and "New draft" (set a draft aside), and Drafts → Open
into an editor that is open already."""

import unittest

from .test_gtk_smoke import HAVE_GTK, _GtkBase, pump


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkEmojiDraftsTest(_GtkBase):
    def _picked(self, dlg, flow_box):
        """Click the first button of the first FlowBox in a picker tab."""
        flow = flow_box.get_first_child()
        while flow is not None and not hasattr(flow, "get_child_at_index"):
            flow = flow.get_next_sibling()
        flow.get_child_at_index(0).get_child().emit("clicked")

    def test_standard_emoji_goes_in_at_the_cursor(self):
        dlg = self.win.compose()
        dlg.buffer.set_text("ab")
        dlg.buffer.place_cursor(dlg.buffer.get_iter_at_offset(1))
        pick = dlg.emoji_pop
        pick._shown()
        self.assertIsNotNone(pick.standard)
        pick.search.set_text("smile")
        pick.refresh()
        self._picked(dlg, pick.standard)
        text = dlg._text()
        self.assertTrue(text.startswith("a") and text.endswith("b") and len(text) > 2, text)

    def test_server_emoji_as_codes(self):
        self.world.emoji.append({"shortcode": "blobcat", "url": "", "static_url": "",
                                 "category": "cats", "visible_in_picker": True})
        dlg = self.win.compose()
        pick = dlg.emoji_pop
        pick._shown()
        self.assertTrue(pump(lambda: pick.items, 3))
        self._picked(dlg, pick.server)
        self.assertEqual(dlg._text(), ":blobcat: ")
        pick.search.set_text("zzzz")
        pick.refresh()
        self.assertIsNone(pick.server.get_first_child().get_next_sibling())

    def test_standard_off_leaves_the_server_tab(self):
        self.core.cfg["post"]["emoji_standard"] = False
        dlg = self.win.compose()
        self.assertIsNone(dlg.emoji_pop.standard)
        self.assertEqual(dlg.emoji_pop.tabs.get_n_pages(), 1)

    def test_new_draft_sets_aside_and_clears(self):
        self.core.cfg["post"]["drafts_place"] = True
        dlg = self.win.compose()
        self.assertTrue(dlg.shelve_btn.get_visible())
        dlg.buffer.set_text("first thought")
        dlg.cw.set_text("cw")
        dlg.shelve()
        self.assertEqual(dlg._text(), "")
        self.assertEqual(dlg.cw.get_text(), "")
        self.assertFalse(self.view.get_draft("new"))
        kept = [k for k, d, _u in self.view.drafts() if k.startswith("new:")]
        self.assertEqual(len(kept), 1)
        self.assertTrue(dlg.hint.get_label())
        pump(timeout=0.2)
        self.assertFalse(self.view.get_draft("new"))  # nothing empty saved

    def test_new_draft_only_for_a_new_post(self):
        self.core.cfg["post"]["drafts_place"] = True
        dlg = self.win.compose(reply_to=self.view.by_id("011"))
        self.assertFalse(dlg.shelve_btn.get_visible())

    def test_open_from_drafts_replaces_an_open_editor(self):
        dlg = self.win.compose()
        dlg.buffer.set_text("typed now")
        self.core.store.save_draft("new", {"text": "from drafts", "cw": "", "media": []})
        again = self.win.compose(text="from drafts")
        self.assertIs(again, dlg)
        self.assertEqual(dlg._text(), "from drafts")
        pump(timeout=0.2)
        dlg.save_draft()
        self.assertEqual(self.view.get_draft("new")["text"], "from drafts")


if __name__ == "__main__":
    unittest.main()
