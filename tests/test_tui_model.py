"""The terminal interface's text side (no Textual needed): posts as lines, commands."""

from fedtail import i18n
from fedtail.frontends.tui import model

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


class TuiModelTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_post_lines(self):
        core, w = self.make()
        parent = status("001", ME, minute=1, text="what do you think?")
        st = status("002", BOB, "001", "ME", minute=2, text="I think yes<br>and more")
        st["media_attachments"] = [{"type": "image"}]
        st["favourites_count"] = 3
        shown = model.show_post(core, st, "a3f", unread=True, parent=parent, width=40)
        kinds = dict(shown.head)
        self.assertEqual(kinds["alias"], "#a3f")
        self.assertEqual(kinds["who"], "@bob@social.example")
        self.assertIn("unread", kinds)
        self.assertEqual(shown.context, "↳ @veresk: what do you think?")
        self.assertEqual(shown.body, ["I think yes", "and more"])
        self.assertIn("[1 attachment]", shown.foot)
        self.assertIn("☆ 3", shown.foot)
        gone = model.show_post(core, st, parent="missing")
        self.assertIn("deleted", gone.context)
        core.cfg["tui"]["show_context"] = False
        self.assertEqual(model.show_post(core, st, parent=parent).context, "")
        # in a thread: the /N number instead of the context line
        self.assertEqual(model.show_post(core, st, number=2, parent=parent).head[0],
                         ("num", "/2"))

    def test_cw_folds_unless_expand(self):
        core, _w = self.make(ui={"expand_cw": False})
        st = status("003", BOB, minute=3, text="spoiler")
        st["spoiler_text"] = "careful"
        shown = model.show_post(core, st)
        self.assertEqual((shown.cw, shown.body), ("⚠ careful", []))

    def test_commands(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        alias = core.short_ids([core.store.get_status("001")])["001"]
        c = model.Commands(core)
        fut, _msg = c.run(f"#{alias} hello")
        self.assertEqual(fut.result(), i18n._("sent"))
        self.assertEqual(w.posted[-1][2], "001")
        self.assertTrue(w.posted[-1][0].startswith("@bob@social.example hello"))
        fut, _msg = c.run(f"#{alias}")
        self.assertEqual(fut.result(), ("thread", "001"))
        fut, _msg = c.run(f"! #{alias}")
        self.assertEqual(fut.result(), i18n._("cmd_boosted"))
        fut, msg = c.run("#zzz9 hi")
        self.assertIsNone(fut)
        self.assertIn("zzz9", msg)
        fut, msg = c.run("?")
        self.assertEqual(msg, i18n._("cmd_help"))
        fut, _msg = c.run("just a post")
        fut.result()
        self.assertEqual(w.posted[-1][0], "just a post")

    def test_lane_label(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(model.lane_label(core, "people"), ("Home", 1))
        title, _n = model.lane_label(core, "people", width=4)
        self.assertLessEqual(len(title), 4)
