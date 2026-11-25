"""A server's emoji its post names without a picture, found on the author's server.

A server passes on another one's post with its custom emoji listed, but for some it has
no picture (GoToSocial, 25.11: `:acceptable:` with an empty url beside one it had): every
interface left `:acceptable:` as text, in the post and its warning. Here the author's
server is asked for its emoji once (its public list of emoji — no token goes
there; `feed.emoji_from_origin`), kept for a week, and the post comes out of
`emoji_filled` with the pictures in place, in every interface (view.entry asks it, as it
asks auto_translation). A server that doesn't answer is asked again only after a day.
"""

import logging
import time

from . import proto
from .proto import raw

log = logging.getLogger(__name__)

KEEP_S = 7 * 86400   # a server's list of emoji kept this long
RETRY_S = 86400      # a server that gave none: asked again after this


def _host(acc):
    """The host of an account from another server ("user@host"), or "" (mine)."""
    acct = str(raw.handle(acc)) if isinstance(acc, dict) else ""
    return acct.rsplit("@", 1)[1].lower() if "@" in acct else ""


def _bare(emojis):
    """The shortcodes listed without a picture."""
    return {str(e.get("shortcode")) for e in emojis or () if isinstance(e, dict)
            and e.get("shortcode") and not (e.get("url") or e.get("static_url"))}


class OriginEmojiMixin:
    def emoji_filled(self, st):
        """The post with the pictures of its bare emoji (and its author's, its booster's)
        from the authors' servers, when known; None — nothing to fill (then the servers
        not asked yet are asked, and the lanes are drawn anew when they answer)."""
        if not isinstance(st, dict) or not self.cfg["feed"].get("emoji_from_origin", True):
            return None
        changed = False

        def fill(obj, host):
            nonlocal changed
            if not isinstance(obj, dict) or not host:
                return obj
            bare = _bare(obj.get("emojis"))
            if not bare:
                return obj
            known = self._origin_emoji_list(host)
            if not known:
                return obj
            out = []
            for e in obj.get("emojis") or ():
                code = e.get("shortcode") if isinstance(e, dict) else None
                if code in bare and code in known:
                    e = dict(e, url=known[code], static_url=known[code])
                    changed = True
                out.append(e)
            return dict(obj, emojis=out)

        def post(p):
            if not isinstance(p, dict):
                return p
            host = _host(p.get("account"))
            p = fill(p, host)
            acc = p.get("account")
            filled = fill(acc, host)
            return dict(p, account=filled) if filled is not acc else p

        inner = raw.boosted(st)
        out = post(st)
        if isinstance(inner, dict):
            out = raw.with_boosted(out, post(inner))
        return out if changed else None

    def _origin_emoji_list(self, host):
        """{shortcode: picture} of a server, or {} (not known yet: asked in the
        background once, the lanes drawn anew when it answers)."""
        state = self._origin_emoji
        if host in self._own_hosts():
            return {}
        got = state["lists"].get(host)
        if got is None:
            got = (self.store.kv_get(f"origin_emoji:{host}") or {}) if self.store else {}
            state["lists"][host] = got
        fresh = time.time() - float(got.get("at") or 0) < (KEEP_S if got.get("emojis")
                                                           else RETRY_S)
        if not fresh:
            with state["lock"]:
                ask = host not in state["asked"]
                state["asked"].add(host)
            if ask:  # out of the lock: the job takes it too
                self.bg.submit(self._ask_origin_emoji, host)
            got = state["lists"].get(host) or got  # a job done at once (a test) is seen
        return got.get("emojis") or {}

    def _ask_origin_emoji(self, host):
        from . import remote
        state = self._origin_emoji
        try:
            data = remote.get_json(proto.urls.emojis(host),
                                   own_hosts=self._own_hosts())
        except Exception as e:  # noqa: BLE001 — a server that can't be reached: no pictures
            log.info("origin emoji %s: %s", host, e.__class__.__name__)
            data = None
        emojis = {str(e["shortcode"]): str(e.get("static_url") or e.get("url"))
                  for e in data if isinstance(e, dict) and e.get("shortcode")
                  and str(e.get("static_url") or e.get("url") or "").startswith("https://")} \
            if isinstance(data, list) else {}
        got = {"at": time.time(), "emojis": emojis}
        state["lists"][host] = got
        if self.store:
            self.store.kv_set(f"origin_emoji:{host}", got)
        with state["lock"]:
            state["asked"].discard(host)
        log.info("origin emoji %s: %d", host, len(emojis))
        if emojis:
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
