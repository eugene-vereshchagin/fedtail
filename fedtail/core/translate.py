"""Translation: on a click (the server's /translate, or LibreTranslate), and by itself
(feed.translate_auto) for posts in languages I neither read nor write."""

import logging
from collections import OrderedDict
from html import escape as html_escape

import requests

from ..version import USER_AGENT
from . import proto, remote
from .model import real

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class TranslateMixin:
    """A part of Core (core/app.py): see the module's words."""

    def translate(self, status):
        """The post in the interface's language, by my server — or by LibreTranslate
        (feed.translate_backend) — a future of {content, detected_source_language,
        provider}."""
        from ..i18n import current_language
        if self._own_translator():
            st = real(status)
            return self.submit(lambda: self._libre(st, current_language()))
        return self.call_api("translate", real(status)["id"], current_language())

    def _own_translator(self):
        feed = self.cfg["feed"]
        return feed.get("translate_backend") == "libretranslate" and \
            str(feed.get("translate_url") or "").startswith(("https://", "http://"))

    def _libre(self, st, into):
        """LibreTranslate's /translate: the post's HTML (and its warning) into `into`."""
        feed = self.cfg["feed"]
        url = str(feed["translate_url"]).rstrip("/")
        if not url.endswith("/translate"):
            url += "/translate"
        if url.startswith("http://") and not remote.cleartext_ok(url):
            from ..i18n import _
            raise ValueError(_("translate_insecure"))

        def one(text, fmt):
            body = {"q": text, "source": "auto", "target": into, "format": fmt}
            if feed.get("translate_key"):
                body["api_key"] = feed["translate_key"]
            r = requests.post(url, json=body, timeout=(10, 60),
                              headers={"User-Agent": USER_AGENT})
            if r.status_code >= 400:
                try:
                    why = r.json().get("error") or r.reason
                except ValueError:
                    why = r.reason
                raise proto.ServerError(r.status_code, str(why)[:200])  # not the protocol's
            got = r.json()
            return str(got.get("translatedText") or ""), \
                str((got.get("detectedLanguage") or {}).get("language") or "")
        content, lang = one(st.get("content") or "", "html")
        spoiler = one(st["spoiler_text"], "text")[0] if st.get("spoiler_text") else ""
        return {"content": content, "spoiler_text": spoiler,
                "detected_source_language": lang or st.get("language") or "",
                "provider": "LibreTranslate"}

    def auto_translation(self, st):
        """The post with its translation in place of its text, when feed.translate_auto
        wants it translated and it is done; None otherwise — then it is asked for (in
        the background, a few at a time) and the card is drawn anew when it comes."""
        if not self.cfg["feed"].get("translate_auto") or not isinstance(st, dict):
            return None
        inner = st.get("reblog") if isinstance(st.get("reblog"), dict) else st
        if not self._wants_translation(inner):
            return None
        cache = self.__dict__.setdefault("_translated", OrderedDict())
        done = cache.get(inner.get("id"))
        if done is None:
            self._ask_translation(inner)
            return None
        if not done:  # it failed: the post as it is
            return None
        from ..i18n import _
        mark = _("translated_auto", lang=done.get("detected_source_language") or "?")
        text = f"<p><small>🌐 {html_escape(mark)}</small></p>" + (done.get("content") or "")
        out = dict(inner, content=text, _fedtail_translated=True)
        if done.get("spoiler_text"):
            out["spoiler_text"] = done["spoiler_text"]
        return dict(st, reblog=out) if inner is not st else out

    def _wants_translation(self, st):
        from ..i18n import current_language
        from . import langs
        lang = langs.base(st.get("language"))
        if not lang or not (st.get("content") or "").strip():
            return False
        if self._own_translator() and st.get("visibility") not in ("public", "unlisted"):
            # by itself, no private post goes to a translator outside the server (the
            # server's own /translate refuses them too): such a one only on a click
            return False
        mine = {langs.base(current_language())} | {
            langs.base(x) for x in (self.cfg["post"].get("languages") or [])} | {
            langs.base(self.cfg["post"].get("language"))}
        return lang not in mine and (self._own_translator() or
                                     getattr(self.caps, "translation", False))

    AUTO_TRANSLATE_AT_ONCE = 4

    def _ask_translation(self, st):
        sid = st.get("id")
        asking = self.__dict__.setdefault("_translating", set())
        if not sid or sid in asking or len(asking) >= self.AUTO_TRANSLATE_AT_ONCE:
            return
        asking.add(sid)

        def job():
            from ..i18n import current_language
            try:
                got = self._libre(st, current_language()) if self._own_translator() else \
                    self.api.translate(sid, current_language())
            except Exception as e:  # noqa: BLE001 — not translated: the post as it is
                log.info("auto translation of %s: %s", sid, e)
                got = {}
            cache = self.__dict__.setdefault("_translated", OrderedDict())
            cache[sid] = got if isinstance(got, dict) and got.get("content") else {}
            while len(cache) > 500:
                cache.popitem(last=False)
            asking.discard(sid)
            if cache[sid]:
                self._lane_cache.clear()
                self.emit("status_updated", st)
                self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
        self.bg.submit(job)
