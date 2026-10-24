"""feed.translate_all ("Translate" on every post, as Fedilab) and ui.tray (no tray icon;
the icon gone at every exit — Windows kept dead ones until hovered)."""

import copy
import unittest

from fedtail import i18n
from fedtail.core import config
from fedtail.frontends.common import actions

from .fakes import BOB
from .test_cov_common_parts import CFG, post


class TranslateEveryPostTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("ru")
        self.addCleanup(i18n.setup, "en")

    def labels(self, p, every):
        cfg = copy.deepcopy(CFG)
        cfg.setdefault("feed", {})["translate_all"] = every
        ctx = actions.Ctx(cfg=cfg, me_id="ME", translate=True)
        return [i.label for i in actions.menu(p, ctx)]

    def test_only_other_languages_by_default(self):
        word = i18n._("translate")
        self.assertIn(word, self.labels(post("1", BOB, lang="ka"), False))
        self.assertNotIn(word, self.labels(post("1", BOB, lang="ru"), False))
        self.assertNotIn(word, self.labels(post("1", BOB, lang=""), False))

    def test_every_post_when_asked(self):
        word = i18n._("translate")
        for lang in ("ru", "", "ka"):
            self.assertIn(word, self.labels(post("1", BOB, lang=lang), True), lang)

    def test_never_without_the_server(self):
        cfg = copy.deepcopy(CFG)
        cfg.setdefault("feed", {})["translate_all"] = True
        ctx = actions.Ctx(cfg=cfg, me_id="ME", translate=False)
        self.assertNotIn(i18n._("translate"),
                         [i.label for i in actions.menu(post("1", BOB, lang="ka"), ctx)])

    def test_config(self):
        cfg, _w = config.validate({"feed": {"translate_all": True}, "ui": {"tray": False}})
        self.assertTrue(cfg["feed"]["translate_all"])
        self.assertFalse(cfg["ui"]["tray"])
        with self.assertRaises(config.ConfigError):
            config.validate({"ui": {"tray": "no"}})


if __name__ == "__main__":
    unittest.main()
