"""Writing: a post, a reply, a chain of them, an edit (and its history), a redraft; its
visibility, the accounts it may go from, what the editor completes (tags, people,
emoji, a link's quote); drafts; my profile."""

import logging
import re
import time

import requests

from .model import interaction_policy, looks_sent, narrower, real, send_key
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class MaybeSent(Exception):
    """The server didn't answer a send in time, and couldn't say whether the post was
    made: it may be out, or not. Retrying blindly may post it twice."""
    maybe_sent = True

    def __init__(self, cause):
        from ..i18n import _
        super().__init__(_("post_maybe_sent", err=cause.__class__.__name__))


class WritingMixin:
    """A part of Core (core/app.py): see the module's words."""

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

    def emoji_suggestions(self, prefix, limit=8):
        """The server's emoji whose shortcode has prefix (no ":"): starting with it
        first, then containing it. [(shortcode, emoji dict)]."""
        p = prefix.casefold()
        if not p:
            return []
        every = getattr(self, "_emoji", None) or []
        starts = [e for e in every if e["shortcode"].casefold().startswith(p)]
        within = [e for e in every if p in e["shortcode"].casefold() and e not in starts]
        best = sorted(starts, key=lambda e: e["shortcode"].casefold()) + \
            sorted(within, key=lambda e: e["shortcode"].casefold())
        return [(e["shortcode"], e) for e in best[:limit]]

    def mention_suggestions(self, prefix, limit=8):
        """People whose address or name starts with prefix (no "@"), the most seen
        first: [(acct, display name)]. Never yourself."""
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

    def post(self, text, visibility, reply_to=None, spoiler="", media=(), draft_key=None,
             language=None, sensitive=False, poll=None, quote=None, scheduled_at=None,
             account=None):
        """media: [(path, description)], [(path, description, (x, y) focus point)] or
        [(path, description, focus or None, cover picture's path)].
        language: ISO 639 code, None — post.language,
        "" — none (the server's default). The draft is dropped once the post is out,
        even if the window that sent it is gone by then."""
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
            try:
                st = self.api.post_status(
                    text, visibility, reply_to, spoiler, ids, self.markdown,
                    idempotency_key=send_key(self.me and self.me["id"], text, reply_to,
                                             visibility, spoiler),
                    timeout=(10, wait), **extra)
            except (requests.Timeout, requests.ConnectionError) as e:
                # the request may well have got there and the post been made, only the
                # answer was lost: look before saying "not sent" (a retry = a double)
                st = self._find_sent(text, reply_to, started)
                if st is None:
                    raise MaybeSent(e) from e
                log.info("send: no answer (%s), but the post is there: %s",
                         e.__class__.__name__, st.get("id"))
            log.debug("posted %s", st.get("id"))
            chain, prev = [st], st
            for i, part in enumerate(rest):  # the rest of a chain: each answering the last
                try:
                    prev = self.api.post_status(part, visibility, prev["id"], spoiler, [],
                                                self.markdown,
                                                **({"language": lang} if lang else {}))
                    chain.append(prev)
                except ApiError as e:
                    log.warning("chain: part %d of %d failed: %s", i + 2, len(rest) + 1, e)
                    self.emit("error", f"{len(chain)} / {len(rest) + 1}: {e}")
                    break
            if rest:
                log.info("chain: %d posts", len(chain))
            # the post is out; nothing below may turn that into a reported failure
            try:
                self.sound_moment("sent")
                if draft_key:
                    self.delete_draft(draft_key)
                self.store.put_statuses(chain)
                self.mark_read([x["id"] for x in chain] + ([reply_to] if reply_to else []))
                if self._carry_my_direct(chain):  # the dialogue: mine at once
                    self.emit("lanes_updated", {n: [] for n in self.private_lanes()})
                self._auto_subscribe([st])
                if reply_to:
                    # "you replied" under the post answered: the lanes it is in look again
                    # now (it changed no lane's list of posts, so nothing else tells them)
                    self.emit("parents")
            except Exception:
                log.exception("bookkeeping after post failed")
            self.poll_now()
            return dict(st, chain=len(chain)) if rest else st
        return self.submit(job)

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
            st = self.api.edit_status(s["id"], text, spoiler, ids, self.markdown,
                                      media_attributes=attrs) if attrs else \
                self.api.edit_status(s["id"], text, spoiler, ids, self.markdown)
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

    def save_draft(self, key, data):
        if self.cfg["post"]["drafts_autosave"]:
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
