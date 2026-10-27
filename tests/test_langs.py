"""core/langs.py — a post's language when its author didn't tag it or tagged it wrong — and
the lanes' languages filter (lanes.languages, languages_in, detect_language)."""

import copy
import sys
import types
import unittest

from fedtail.core import config, lanes, langs

LONG_EN = "This is a long enough English post about mountains rivers and roads in the Caucasus"
LONG_DE = "Das ist ein ziemlich langer deutscher Beitrag über Berge Flüsse und Straßen im Kaukasus"


class FakeDetect:
    """langdetect's detect_langs: German for texts with 'deutscher', English otherwise."""

    def __init__(self, sure=0.99):
        self.sure, self.calls = sure, 0

    def __call__(self, text):
        self.calls += 1
        if "nothing" in text:
            raise ValueError("No features in text.")
        lang = "de" if "deutscher" in text else "zh-cn" if "zh" in text else "en"
        return [types.SimpleNamespace(lang=lang, prob=self.sure)]


class LangsBase(unittest.TestCase):
    def setUp(self):
        self._saved = langs._detector
        langs._cache.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        langs._detector = self._saved
        langs._cache.clear()

    def with_detector(self, sure=0.99):
        langs._detector = FakeDetect(sure)
        return langs._detector

    def without_detector(self):
        langs._detector = False


class ScriptTest(LangsBase):
    def test_scripts(self):
        for text, lang in (("这是中文帖子", "zh"), ("これは日本語です", "ja"),
                           ("日本語の文章です", "ja"),
                           ("한국어 게시물", "ko"), ("هذا منشور عربي", "ar"), ("זה פוסט", "he"),
                           ("ეს ქართული პოსტია", "ka"), ("Սա հայերեն է", "hy"),
                           ("นี่คือโพสต์", "th"), ("Αυτό είναι ελληνικά", "el"),
                           ("यह हिंदी है", "hi"), ("Привет, как дела", "cyrillic"),
                           ("Привіт, як справи? Їжак", "uk"), ("Прывітанне, як справы ў вас", "be"),
                           ("Hello there", "latin"), ("123 !!!", None), ("", None),
                           ("Hi 你好 مرحبا Привет", None)):
            with self.subTest(text=text):
                self.assertEqual(langs.by_script(text), lang)

    def test_base(self):
        self.assertEqual(langs.base("en-US"), "en")
        self.assertEqual(langs.base("zh_CN"), "zh")
        self.assertEqual(langs.base(" RU "), "ru")
        self.assertIsNone(langs.base(None))
        self.assertIsNone(langs.base(""))


class GuessTest(LangsBase):
    def test_short_and_long(self):
        self.without_detector()
        self.assertEqual(langs.guess("这是中文"), "zh")
        self.assertEqual(langs.guess("Привет"), "ru")
        self.assertIsNone(langs.guess("Hello"))
        self.assertIsNone(langs.guess(LONG_EN))   # no langdetect: Latin stays unknown
        self.assertFalse(langs.available())
        d = self.with_detector()
        self.assertTrue(langs.available())
        self.assertIsNone(langs.guess("Hello there"))  # too short for words
        self.assertEqual(d.calls, 0)
        self.assertEqual(langs.guess(LONG_EN), "en")
        self.assertEqual(langs.guess(LONG_DE), "de")
        self.assertEqual(langs.guess(LONG_EN, min_words=50), None)
        self.assertEqual(langs.guess("Какой-то длинный русский пост про горы реки дороги и "
                                     "перевалы на Кавказе осенью"), "en")  # the words decide
        self.assertEqual(langs.guess("Привет как дела", min_words=3), "en")

    def test_unsure_or_failing(self):
        self.with_detector(sure=0.5)
        self.assertIsNone(langs.guess(LONG_EN))
        self.assertEqual(langs.guess("Длинный русский текст " * 5), "ru")  # Cyrillic fallback
        self.with_detector()
        self.assertIsNone(langs.by_words("nothing " * 20))

    def test_loads_langdetect(self):
        langs._detector = None
        fake = types.ModuleType("langdetect")
        factory = types.SimpleNamespace(seed=None)
        fake.DetectorFactory, fake.detect_langs = factory, FakeDetect()
        sys.modules["langdetect"] = fake
        self.addCleanup(sys.modules.pop, "langdetect", None)
        self.assertTrue(langs.available())
        self.assertEqual(factory.seed, 0)
        langs._detector = None
        sys.modules["langdetect"] = None  # import fails
        self.assertFalse(langs.available())


class PostLanguageTest(LangsBase):
    def post(self, content, language=None, sid="1", **kw):
        return dict(id=sid, content=f"<p>{content}</p>", language=language, **kw)

    def test_modes(self):
        self.with_detector()
        en_tag_ru = self.post("Привет, это пост по-русски", "en")
        self.assertEqual(langs.post_language(en_tag_ru, "off"), "en")
        self.assertEqual(langs.post_language(en_tag_ru, "untagged"), "ru")
        zh = self.post("这是中文帖子", "en", sid="2")
        self.assertEqual(langs.post_language(zh), "zh")
        ok = self.post(LONG_DE, "de", sid="3")
        self.assertEqual(langs.post_language(ok), "de")
        wrong_latin = self.post(LONG_DE, "ru", sid="4")
        self.assertEqual(langs.post_language(wrong_latin), "de")
        short_wrong = self.post("Hallo", "ru", sid="5")
        self.assertIsNone(langs.post_language(short_wrong))
        lies = self.post(LONG_DE, "en", sid="6")
        self.assertEqual(langs.post_language(lies, "untagged"), "en")  # Latin, Latin: trusted
        self.assertEqual(langs.post_language(lies, "always"), "de")
        untagged = self.post("Привет", None, sid="7")
        self.assertEqual(langs.post_language(untagged), "ru")
        bg = self.post("Здравей", "bg", sid="8")
        self.assertEqual(langs.post_language(bg), "bg")
        self.assertEqual(langs.post_language(self.post("你好", "zh-TW", sid="9")), "zh")
        self.assertEqual(langs.post_language(self.post("你好", "ja", sid="10")), "zh")
        mixed = self.post("Hi 你好 مرحبا Привет", "fr", sid="11")
        self.assertEqual(langs.post_language(mixed), "fr")
        nothing = self.post("", None, sid="12", spoiler_text="")
        self.assertIsNone(langs.post_language(nothing, "always"))
        tagged_always = self.post("Hi", "fr", sid="13")
        self.assertEqual(langs.post_language(tagged_always, "always"), "fr")

    def test_cache(self):
        d = self.with_detector()
        p = self.post(LONG_EN, None)
        self.assertEqual(langs.post_language(p), "en")
        self.assertEqual(langs.post_language(p), "en")
        self.assertEqual(d.calls, 1)
        no_id = {"content": LONG_EN}
        langs.post_language(no_id)
        langs.post_language(no_id)
        self.assertEqual(d.calls, 3)
        old = langs._CACHE_MAX
        langs._CACHE_MAX = 1
        self.addCleanup(setattr, langs, "_CACHE_MAX", old)
        langs.post_language(self.post(LONG_EN, None, sid="other"))
        self.assertEqual(len(langs._cache), 1)

    def test_cw_counts(self):
        self.without_detector()
        p = {"id": "c", "content": "", "spoiler_text": "这是中文"}
        self.assertEqual(langs.post_language(p), "zh")

    def test_wanted(self):
        self.without_detector()
        self.assertTrue(langs.wanted(self.post("这是中文"), ()))
        self.assertFalse(langs.wanted(self.post("这是中文", sid="z"), {"ru", "en"}))
        self.assertTrue(langs.wanted(self.post("Привет", sid="r"), {"ru", "en"}))
        self.assertTrue(langs.wanted(self.post("Hello", sid="u"), {"ru"}))  # unknown stays


def st(sid, content, language=None, acc="2"):
    return {"id": sid, "content": f"<p>{content}</p>", "language": language,
            "account": {"id": acc, "acct": "x@y"}, "visibility": "public"}


class LaneFilterTest(LangsBase):
    def ctx(self, **kw):
        base = dict(me_id="1", extra_bots=(), languages=frozenset({"ru", "en"}),
                    languages_in=frozenset({"federated", "local", "tags"}))
        base.update(kw)
        return lanes.LaneContext(**base)

    def test_lanes(self):
        self.without_detector()
        zh, ru = st("1", "这是中文"), st("2", "Привет")
        fed, home = lanes.LANES["federated"], lanes.LANES["home"]
        self.assertFalse(lanes.keeps(fed, zh, self.ctx()))
        self.assertTrue(lanes.keeps(fed, ru, self.ctx()))
        self.assertTrue(lanes.keeps(home, zh, self.ctx()))          # Home: read whole
        self.assertTrue(lanes.keeps(fed, zh, self.ctx(languages=frozenset())))
        boost = {"id": "3", "account": {"id": "9"}, "reblog": zh}
        self.assertFalse(lanes.keeps(fed, boost, self.ctx()))       # the original's language
        tags = lanes.tag_lane({"name": "g", "any": ["грузия"]})
        self.assertFalse(lanes.keeps(tags, zh, self.ctx()))
        lst = lanes.list_lane(7)
        self.assertTrue(lanes.keeps(lst, zh, self.ctx()))
        self.assertFalse(lanes.keeps(lst, zh, self.ctx(languages_in=frozenset({"lists"}))))

    def test_in_scope(self):
        self.assertTrue(lanes.in_scope("local", {"local"}))
        self.assertTrue(lanes.in_scope("list:3", {"lists"}))
        self.assertFalse(lanes.in_scope("list:3", {"tags"}))
        self.assertFalse(lanes.in_scope("home", {"lists", "tags"}))


class ConfigTest(unittest.TestCase):
    def check(self, **lanes_kw):
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg["lanes"].update(lanes_kw)
        return config.validate(cfg)

    def test_defaults(self):
        d = config.DEFAULTS["lanes"]
        self.assertEqual((d["languages"], d["detect_language"], d["detect_min_words"]),
                         ([], "untagged", 12))
        self.assertEqual(d["languages_in"], ["federated", "local", "tags"])

    def test_bad_values(self):
        for kw in ({"languages": ["Russian"]}, {"languages": [5]},
                   {"languages_in": ["nowhere"]}, {"detect_language": "maybe"}):
            with self.subTest(kw=kw):
                with self.assertRaises(config.ConfigError):
                    self.check(**kw)

    def test_good_values(self):
        cfg, _ = self.check(languages=["ru", "en"], languages_in=["global", "lists", "home"],
                            detect_language="always")
        self.assertEqual(cfg["lanes"]["languages_in"], ["federated", "lists", "home"])


if __name__ == "__main__":
    unittest.main()
