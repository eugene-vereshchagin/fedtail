"""Writing: a post, a reply, a chain of them, an edit (and its history), a redraft; its
visibility, the accounts it may go from, what the editor completes (tags, people,
emoji, a link's quote); drafts; my profile."""

import logging
import re
import time

import requests

from .model import interaction_policy, looks_sent, narrower, real, send_key
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)
from .proto import ServerError

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class MaybeSent(Exception):
    """The server didn't answer a send in time, and couldn't say whether the post was
    made: it may be out, or not. Retrying blindly may post it twice."""
    maybe_sent = True

    def __init__(self, cause):
        from ..i18n import _
        super().__init__(_("post_maybe_sent", err=cause.__class__.__name__))


def _post_print(media, sensitive, poll, extra):
    """What besides its words makes a post the one it is, for its Idempotency-Key: its
    files (path, size, words), sensitive, poll, quote, language."""
    import os
    files = []
    for m in media or ():
        try:
            size = os.path.getsize(m[0])
        except OSError:
            size = -1
        files.append((str(m[0]), size) + tuple(str(x) for x in m[1:]))
    return repr((files, bool(sensitive), poll, extra.get("quoted_status_id"),
                 extra.get("language")))


def _mentions_of(st, me):
    """@user@server of whom a post I made names, me aside."""
    mine = str((me or {}).get("id") or "")
    return [m["acct"] for m in st.get("mentions") or []
            if m.get("acct") and str(m.get("id") or "") != mine]


def _named(text, accts):
    """`text` with those of `accts` it doesn't name yet put before it."""
    def names(a):  # @bob@server, or @bob as typed (the server took it so)
        user = re.escape(a.split("@")[0])
        return re.search(rf"(?<![\w@])@{user}(@{re.escape(a.split('@', 1)[1])})?(?![\w@-])(?!\.\w)"
                         if "@" in a else rf"(?<![\w@])@{user}(?![\w@-])(?!\.\w)", text, re.I)
    lead = [f"@{a}" for a in accts if not names(a)]
    return " ".join(lead + [text]) if lead else text


class WritingMixin:
    """A part of Core (core/app.py): see the module's words."""

    def prepare_completion(self):
        """Everything the editor's completion needs (#tags, @names, :emoji:), warmed in
        the background — once a run: the counts then keep themselves up to date. Every
        editor of every interface asks as it opens, and the suggestions ask themselves,
        so none can forget (GTK's and the terminal's never had any: 20.11)."""
        if getattr(self, "_completion_warm", False):
            return
        self._completion_warm = True
        self.prepare_tags()
        self.prepare_people()
        if self.cfg["post"].get("complete_emoji", True):
            self.prepare_emoji()

    def prepare_tags(self):
        """Warm up what tag_suggestions() needs, in the background: the tags of the
        stored posts and the tags you follow."""
        self.bg.submit(self.store.tag_counts)
        if getattr(self, "_followed_tag_names", None) is None:
            self._followed_tag_names = set()

            def followed():
                try:
                    self._followed_tag_names = {t["name"] for t in self.api.followed_tags()
                                                if t.get("name")}
                except Exception as e:  # noqa: BLE001 — only suggestions are missing then
                    log.info("followed tags: %s", e)
            self.bg.submit(followed)

    def prepare_people(self):
        self.bg.submit(self.store.people_counts)

    def prepare_emoji(self):
        """The server's own emoji, once a run, for emoji_suggestions()."""
        if getattr(self, "_emoji", None) is not None or not self.api:
            return
        self._emoji = []

        def job():
            try:
                self._emoji = [e for e in self.api.custom_emojis()
                               if e.get("shortcode") and e.get("visible_in_picker", True)]
            except Exception as e:  # noqa: BLE001 — only suggestions are missing then
                log.info("custom emoji: %s", e)
        self.bg.submit(job)

    def emoji_all(self):
        """Future: every emoji of my server the picker shows ([emoji dict], by category
        and shortcode) — fetched now if not yet (prepare_emoji fetches in the
        background: a picker opened first must not be empty)."""
        def job():
            have = getattr(self, "_emoji", None)
            if not have and self.api:
                try:
                    have = [e for e in self.api.custom_emojis()
                            if e.get("shortcode") and e.get("visible_in_picker", True)]
                except Exception as e:  # noqa: BLE001 — said by the caller
                    log.info("custom emoji: %s", e)
                    raise
                self._emoji = have
            return sorted(have or (), key=lambda e: (str(e.get("category") or ""),
                                                      e["shortcode"].casefold()))
        return self.submit(job)

    def emoji_suggestions(self, prefix, limit=8):
        """The server's emoji whose shortcode has prefix (no ":"): starting with it
        first, then containing it. [(shortcode, emoji dict)]."""
        self.prepare_completion()
        p = prefix.casefold()
        if not p:
            return []
        every = getattr(self, "_emoji", None) or []
        starts = [e for e in every if e["shortcode"].casefold().startswith(p)]
        within = [e for e in every if p in e["shortcode"].casefold() and e not in starts]
        best = sorted(starts, key=lambda e: e["shortcode"].casefold()) + \
            sorted(within, key=lambda e: e["shortcode"].casefold())
        return [(e["shortcode"], e) for e in best[:limit]]

    def emoji_standard(self, words=""):
        """The picker's "Standard" tab: every Unicode emoji (core/emojis.picker), or those
        `words` find, the best first; [] with post.emoji_standard off."""
        from . import emojis
        if not self.cfg["post"].get("emoji_standard", True):
            return []
        return emojis.picker(words)

    def emoji_standard_suggestions(self, prefix, limit=8):
        """The standard emoji for `:smi` as one types: [(the emoji, ":smile: label")]."""
        from . import emojis
        if not self.cfg["post"].get("emoji_standard", True) or len(prefix) < 2:
            return []
        return emojis.suggestions(prefix, limit)

    def mention_suggestions(self, prefix, limit=8):
        """People whose address or name starts with prefix (no "@"), the most seen
        first: [(acct, display name)]. Never yourself."""
        self.prepare_completion()
        p = prefix.casefold()
        if not p:
            return []
        me = (self.me or {}).get("acct", "").casefold()
        found = []
        for key, (acct, name, n) in (self.store.people_counts(compute=False) or {}).items():
            if key == me:
                continue
            words = [key, key.split("@")[0]] + [w.casefold() for w in (name or "").split()]
            if any(w.startswith(p) for w in words):
                found.append((-n, acct.casefold(), acct, name))
        found.sort()
        return [(acct, name) for _n, _k, acct, name in found[:limit]]

    def tag_suggestions(self, prefix, limit=8):
        """Tags starting with prefix (no "#"): the ones you follow first, then the
        most used in the posts fedtail has seen."""
        self.prepare_completion()
        p = prefix.casefold()
        if not p:
            return []
        followed = getattr(self, "_followed_tag_names", None) or set()
        counts = self.store.tag_counts(compute=False) or {}
        score = {}
        for key, (name, n) in counts.items():
            if key.startswith(p):
                score[key] = [name, n]
        for name in followed:
            if name.casefold().startswith(p):
                score.setdefault(name.casefold(), [name, 0])[1] += 1_000_000
        best = sorted(score.values(), key=lambda x: (-x[1], x[0].casefold()))
        return [name for name, _n in best[:limit]]

    _LAST_LINK = re.compile(r"\s*(https?://\S+)\s*$")

    def _link_quote(self, text):
        """post.link_quote: the text ends with a post's address → (the text without it,
        the post's id here) when its author lets it be quoted; else (text, None)."""
        m = self._LAST_LINK.search(text or "")
        if not m:
            return text, None
        try:
            got = self.api.search(m.group(1), kind="statuses", resolve=True, limit=1)
        except Exception as e:  # noqa: BLE001 — the link stays a link
            log.debug("link quote: %s", e)
            return text, None
        st = (got.get("statuses") or [None])[0] if isinstance(got, dict) else None
        policy = ((st or {}).get("quote_approval") or {}).get("current_user")
        if not st or policy not in ("automatic", "manual"):
            return text, None
        self.store.put_statuses([st])
        rest = text[:m.start()].rstrip()
        log.info("link quote: %s quoted", st["id"])
        return (rest or text), st["id"]

    def my_profile(self):
        """My account as the editor needs it (bio and fields as typed)."""
        return self.call_api("verify_credentials")

    def update_profile(self, **changes):
        def job():
            me = self.api.update_credentials(**changes)
            self.me = me
            self.emit("me_updated", me)
            return me
        return self.submit(job)

    def default_visibility(self):
        """post.default_visibility; "server" — what's set on the server's web side."""
        v = self.cfg["post"]["default_visibility"]
        if v == "server":
            v = self.server_prefs.get("posting:default:visibility") or "public"
            if v not in ("public", "unlisted", "private", "direct"):
                v = "public"
        return v

    def reply_visibility(self, parent):
        default = self.default_visibility()
        if parent is None:
            return default
        pv = real(parent).get("visibility", "public")
        if self.cfg["post"]["reply_never_wider"]:
            return narrower(pv, default)
        return default

    def post_accounts(self, reply_to=None):
        """The editor's "From": one account here — nothing to choose (core/merged.py has
        the window with all of them)."""
        return [], ""

    def media_refused(self, paths):
        """The attachments my server says it won't take (its supported_mime_types), as
        words to show, or "" — all fine, the server doesn't say, or post.check_media_types
        is off. Asked before anything is uploaded: no wait for a 422."""
        if not self.cfg["post"].get("check_media_types", True):
            return ""
        from pathlib import Path

        from ..i18n import _
        from ..protocols.base import media_taken
        types = list(getattr(self.caps, "media_types", None) or [])
        bad = [Path(str(p)).name for p in paths if not media_taken(p, types)]
        if not bad:
            return ""
        return _("filetype_refused", names=", ".join(bad), kinds=self._media_kinds(types))

    @staticmethod
    def _media_kinds(types):
        """A server's MIME types in short words: "pictures, video, sound, .pdf"."""
        from ..i18n import _
        from ..protocols.base import MEDIA_TYPES
        words, rest = [], []
        for key, major in (("filetype_image", "image/"), ("filetype_video", "video/"),
                           ("filetype_audio", "audio/")):
            if any(str(t).lower().startswith(major) for t in types):
                words.append(_(key))
        by_type = {}
        for ext, kind in MEDIA_TYPES.items():
            by_type.setdefault(kind, ext)
        for t in types:
            t = str(t).lower()
            if not t.startswith(("image/", "video/", "audio/")):
                ext = by_type.get(t) or t
                if ext not in rest:
                    rest.append(ext)
        return ", ".join(words + rest[:12])

    def _media_taken(self, media):
        refused = self.media_refused([m[0] for m in media])
        if refused:
            raise ValueError(refused)

    def post(self, text, visibility, reply_to=None, spoiler="", media=(), draft_key=None,
             language=None, sensitive=False, poll=None, quote=None, scheduled_at=None,
             account=None):
        """media: [(path, description)], [(path, description, (x, y) focus point)] or
        [(path, description, focus or None, cover picture's path)].
        language: ISO 639 code, None — post.language,
        "" — none (the server's default). The draft is dropped once the post is out,
        even if the window that sent it is gone by then. The future is done once the
        post is made and stored — its bookkeeping (read marks, lanes, threads) goes on
        after; `.settled` is the future of all of it."""
        lang = self.cfg["post"]["language"] if language is None else language
        from . import rss
        if rss.is_rss(str(reply_to or "")) or rss.is_rss(str(quote or "")):
            from ..i18n import _
            raise ValueError(_("rss_local_only"))
        from .model import chain_parts
        parts = chain_parts(text) if self.cfg["post"].get("chain", True) and \
            not scheduled_at else [text]
        if len(parts) > 1:
            text, rest = parts[0], parts[1:]
        else:
            rest = []

        def job():
            nonlocal text
            self._media_taken(media)
            ids = [(self.api.upload_media(m[0], m[1], m[2] if len(m) > 2 else None,
                                          thumbnail=m[3]) if len(m) > 3 and m[3] else
                    self.api.upload_media(m[0], m[1], m[2] if len(m) > 2 else None))["id"]
                   for m in media]
            extra = {"language": lang} if lang else {}
            if sensitive and ids:
                extra["sensitive"] = True
            if poll and not ids:  # a server takes either pictures or a poll
                extra["poll"] = poll
            if not quote and self.cfg["post"].get("link_quote"):  # a post's link at the end
                text, found = self._link_quote(text)
                if found:
                    extra["quoted_status_id"] = found
            if quote:
                extra["quoted_status_id"] = quote
            if self.cfg["post"].get("quote_policy"):
                extra["quote_policy"] = self.cfg["post"]["quote_policy"]
            policy = interaction_policy(self.cfg["post"])
            if policy and self.caps.software == "gotosocial":
                extra["interaction_policy"] = policy
            if scheduled_at:
                extra["scheduled_at"] = scheduled_at
                st = self.api.post_status(text, visibility, reply_to, spoiler, ids,
                                          self.markdown, **extra)
                if draft_key:
                    self.delete_draft(draft_key)
                log.info("scheduled for %s", scheduled_at)
                return dict(st or {}, scheduled=True)
            started = time.time()
            wait = max(10, int(self.cfg["post"].get("send_timeout", 90)))
            key = self._send_key(text, reply_to, visibility, spoiler,
                                 _post_print(media, sensitive, poll, extra))
            try:
                st = self.api.post_status(
                    text, visibility, reply_to, spoiler, ids, self.markdown,
                    idempotency_key=key, timeout=(10, wait), **extra)
            except (requests.Timeout, requests.ConnectionError) as e:
                # the request may well have got there and the post been made, only the
                # answer was lost: look before saying "not sent" (a retry = a double)
                st = self._find_sent(text, reply_to, started)
                if st is None:
                    raise MaybeSent(e) from e
                log.info("send: no answer (%s), but the post is there: %s",
                         e.__class__.__name__, st.get("id"))
            log.debug("posted %s", st.get("id"))
            self._note_send_key(st.get("id"), key)
            chain, prev = [st], st
            # a chain to a few (direct, followers only): each part names whom the first
            # did — a part naming nobody reached no one (21.11)
            who = _mentions_of(st, self.me) if visibility in ("direct", "private") else []
            more = {"language": lang} if lang else {}
            for k in ("interaction_policy", "quote_policy"):
                if k in extra:
                    more[k] = extra[k]
            for i, part in enumerate(rest):  # the rest of a chain: each answering the last
                part = _named(part, who)
                pkey = self._send_key(part, prev["id"], visibility, spoiler)
                begun = time.time()
                try:
                    try:
                        prev = self.api.post_status(part, visibility, prev["id"], spoiler,
                                                    [], self.markdown, idempotency_key=pkey,
                                                    timeout=(10, wait), **more)
                    except (requests.Timeout, requests.ConnectionError) as e:
                        found = self._find_sent(part, prev["id"], begun)
                        if found is None:
                            raise MaybeSent(e) from e
                        prev = found
                    self._note_send_key(prev.get("id"), pkey)
                    chain.append(prev)
                except (ApiError, ServerError, MaybeSent, requests.RequestException) as e:
                    # the first part is out: a part that failed ends the chain there, and
                    # says so — the send isn't a failure (again = the parts out twice)
                    log.warning("chain: part %d of %d failed: %s", i + 2, len(rest) + 1,
                                e.__class__.__name__)
                    self.emit("error", f"{len(chain)} / {len(rest) + 1}: {e}")
                    break
            if rest:
                log.info("chain: %d posts", len(chain))
            # the post is out; nothing below may turn that into a reported failure
            made = dict(st, chain=len(chain)) if rest else st
            try:
                self.sound_moment("sent")
                if draft_key:
                    self.delete_draft(draft_key)
                self.store.put_statuses(chain)
            except Exception:
                log.exception("storing the post sent failed")
            # the window hears now: what follows (read marks, the lanes counted anew on
            # their events) took 3 s and more, the editor standing open all the while
            # over a post already in the lanes and boosted (16.11)
            if not out.done():
                out.set_result(made)
            try:
                self.mark_read([x["id"] for x in chain] + ([reply_to] if reply_to else []))
                if self._carry_my_direct(chain):  # the dialogue: mine at once
                    self.emit("lanes_updated", {n: [] for n in self.private_lanes()})
                self._auto_subscribe([st])
                q = extra.get("quoted_status_id")
                if q:  # threads.auto = "quotes": the thread of the post I quoted
                    self._follow_for("quotes", self.store.get_status(str(q)) or {"id": q})
                if reply_to:
                    # "you replied" under the post answered: the lanes it is in look again
                    # now (it changed no lane's list of posts, so nothing else tells them)
                    self.emit("parents")
                    # and a thread open on it takes my answer in: stored already, the
                    # next round doesn't count it new
                    self._answers_in_open_threads(
                        [(x["id"], x.get("in_reply_to_id")) for x in chain])
            except Exception:
                log.exception("bookkeeping after post failed")
            self.poll_now()
            return made

        def run():
            try:
                res = job()
            except BaseException as e:
                if not out.done():
                    out.set_exception(e)
                raise
            if not out.done():
                out.set_result(res)
            return res
        from concurrent.futures import Future
        out = Future()  # the post made (or the error) — before its bookkeeping
        out.settled = self.submit(run)  # …and once that is done too (tests, the CLI)
        if out.settled.cancelled():  # shut down
            out.cancel()
        return out

    # Mastodon keeps a key for an hour; a post deleted meanwhile burns its key: sent
    # again (a redraft, the same words), it would answer with the deleted one, or 404
    KEY_HOURS = 1

    def _keys(self, name):
        now = time.time()
        return {k: v for k, v in (self.store.kv_get(name, {}) or {}).items()
                if now - float(v[-1] if isinstance(v, list) else v) < self.KEY_HOURS * 3600}

    def _send_key(self, *what):
        import hashlib
        key = send_key(self.me and self.me["id"], *what)
        burnt = self._keys("send_keys_burnt")
        while key in burnt:  # the same, made anew: a key of its own (the same each try)
            key = "fedtail-" + hashlib.sha256(key.encode()).hexdigest()[:40]
        return key

    def _note_send_key(self, sid, key):
        if sid:
            kept = self._keys("send_keys")
            kept[str(sid)] = [key, time.time()]
            self.store.kv_set("send_keys", kept)

    def _burn_send_key(self, sid):
        """My post `sid` deleted: the key it was sent with is spent."""
        kept = self._keys("send_keys")
        got = kept.pop(str(sid), None)
        if got:
            burnt = self._keys("send_keys_burnt")
            burnt[got[0]] = time.time()
            self.store.kv_set("send_keys_burnt", burnt)
            self.store.kv_set("send_keys", kept)

    def _find_sent(self, text, reply_to, since):
        """My post with this text (and this parent) made since then — or None, also when
        the server can't say right now either."""
        if not self.me:
            return None
        try:
            mine = self.api.account_statuses(self.me["id"], limit=10) or []
        except (requests.RequestException, ApiError) as e:
            log.warning("send: can't check whether the post got there: %s",
                        e.__class__.__name__)
            return None
        return next((st for st in mine if looks_sent(st, text, reply_to, since)), None)

    def edit(self, status, text, spoiler="", draft_key=None, media=None):
        """Change my post's text and warning; its pictures stay. media: {media id:
        (description, (x, y) focus or None)} — their words and focus point anew."""
        s = real(status)

        def job():
            ids = [m["id"] for m in s.get("media_attachments") or []]
            attrs = [dict({"id": mid, "description": desc or ""},
                          **({"focus": f"{float(focus[0]):.2f},{float(focus[1]):.2f}"}
                             if focus else {}))
                     for mid, (desc, focus) in (media or {}).items() if mid in ids]
            keep = {"sensitive": bool(s.get("sensitive"))}  # as it was: see edit_status
            if s.get("poll"):
                keep["poll"] = s["poll"]
            if attrs:
                keep["media_attributes"] = attrs
            st = self.api.edit_status(s["id"], text, spoiler, ids, self.markdown, **keep)
            self.store.put_statuses([st])
            if draft_key:
                self.delete_draft(draft_key)
            self.emit("status_updated", st)
            return st
        return self.submit(job)

    def source(self, status):
        """What I typed for this post; the shown text if the server can't say."""
        s = real(status)

        def job():
            try:
                return self.api.status_source(s["id"])
            except ApiError:
                from .model import html_to_text
                return {"text": html_to_text(s.get("content", "")),
                        "spoiler_text": s.get("spoiler_text", "")}
        return self.submit(job)

    def history(self, status):
        return self.call_api("status_history", real(status)["id"])

    def _update(self, st):
        self.store.put_statuses([st])
        self.emit("status_updated", st)
        return st

    @staticmethod
    def _on_server(s):
        """A post that lives only here (an RSS feed's item, core/rss.py): no server to
        like, boost or answer it on — said so, not asked."""
        from . import rss
        if rss.is_rss(s):
            from ..i18n import _
            raise ValueError(_("rss_local_only"))

    def redraft(self, status):
        """Delete my post and give back what it was made of, for a new draft: its text as
        I typed it (the source, not the server's HTML), CW, who sees it, language, what it
        answers. Pictures don't come back (servers drop them with the post)."""
        s = real(status)

        def job():
            src = {}
            try:
                src = self.api.status_source(s["id"]) or {}
            except ApiError as e:
                log.info("redraft %s: no source (%s), the text from the card", s["id"], e)
            self.api.delete_status(s["id"])
            self._burn_send_key(s["id"])
            self.store.delete_status(s["id"])
            self.emit("status_deleted", s["id"])
            from .model import html_to_text
            return {"text": src.get("text") or html_to_text(s.get("content") or ""),
                    "cw": src.get("spoiler_text", s.get("spoiler_text") or ""),
                    "visibility": s.get("visibility") or "private",
                    "language": s.get("language") or "",
                    "in_reply_to_id": s.get("in_reply_to_id"),
                    "media": len(s.get("media_attachments") or [])}
        return self.submit(job)

    @staticmethod
    def draft_key(reply_to_id=None, quote_id=None):
        if quote_id:
            return f"quote:{quote_id}"
        return f"reply:{reply_to_id}" if reply_to_id else "new"

    def get_draft(self, key):
        return self.store.get_draft(key)

    def save_draft(self, key, data, keep=False):
        """Keep a draft — with post.drafts_autosave, or always when `keep` (the editor
        gone while it sends in the background: a failure must not lose the text)."""
        if keep or self.cfg["post"]["drafts_autosave"]:
            self.store.save_draft(key, data)
            if self.sync:
                self.sync.record_draft(key)

    def drafts(self):
        """[(key, data, updated)] — every kept draft, the newest first (post.drafts_place)."""
        return self.store.list_drafts()

    def delete_draft(self, key):
        """A draft sent or emptied: gone here, and on my other devices (sync.drafts)."""
        self.store.delete_draft(key)
        if self.sync:
            self.sync.record_draft(key)

    @staticmethod
    def shelvable(key):
        """Can the editor of this draft set it aside for a clean one ("New draft")? Only a
        new post's: a reply's, a quote's, a correction's draft belongs to its post."""
        return key == "new"

    def drafts_waiting(self, key="new"):
        """How many kept drafts wait besides the one of this editor (key): the editor's
        "Drafts (N)" says it and opens them — set aside with "New draft", they were
        nowhere to be found but the ≡ menu (18.11). 0 with post.drafts_place off."""
        if not self.cfg["post"].get("drafts_place", True):
            return 0
        return sum(1 for k, data, _u in self.store.list_drafts()
                   if k != key and isinstance(data, dict) and
                   (str(data.get("text") or "").strip() or data.get("cw")
                    or data.get("media") or data.get("poll")))

    def shelve_draft(self, key="new"):
        """"New draft": the new post's draft set aside under a name of its own
        ("new:<time>", in Drafts), so the editor starts clean. → the new key, or None
        when there was nothing to keep."""
        data = self.store.get_draft(key) if self.shelvable(key) else None
        if not data or not (str(data.get("text") or "").strip() or data.get("cw")
                            or data.get("media") or data.get("poll")):
            return None
        new = f"new:{int(time.time() * 1000):x}"
        self.store.save_draft(new, data)
        if self.sync:
            self.sync.record_draft(new)
        self.delete_draft(key)
        return new

    def unshelve_draft(self, key):
        """A set-aside new post's draft (Drafts → Open) back into the editor: it becomes
        the new post's draft, and what that held is set aside in its place."""
        if key == "new" or not key.startswith("new:"):
            return key
        data = self.store.get_draft(key)
        if data is None:
            return None
        self.shelve_draft("new")
        self.store.save_draft("new", data)
        if self.sync:
            self.sync.record_draft("new")
        self.delete_draft(key)
        return "new"
