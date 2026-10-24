"""More places for the web page and the terminal — what the windows have in dialogs and
headers of their own: "What the server can do" (the probe), the server's
announcements, and a profile's details (the head of the windows' profile tab: counts,
since when, people I follow who follow them, what they feature, a move, the pinned
posts, and their older posts from their own server).

A mixin of common/places.py's Places: the same Page, Row, Btn, Out, the same rules.
"""

from __future__ import annotations

import logging

from ...i18n import _

log = logging.getLogger(__name__)

QUICK = ("👍", "❤️", "😂", "🎉")  # reactions offered under every announcement (as Qt's)


def _host(url):
    from urllib.parse import urlsplit
    return (urlsplit(url or "").hostname or "").lower()


class MorePlaces:
    """Places beyond the first ones (mixed into Places)."""

    # ---- what my server can do --------------------------------------------------------
    def _domain(self):
        return _host((self.view.auth or {}).get("server") or "") or "server"

    def _probe_rows(self):
        from . import server
        return server.probe_rows(self.view.last_probe(), self.date)

    def _p_probe(self, _arg, _tab, _cur):
        """The answers of the last check (kept), the worst first, and the buttons: check
        (again), copy as a Markdown table, save it to a file."""
        from .places import Page, Row
        note, rows = self._probe_rows()
        page = Page("probe", _("probe_tab"), hint=_("probe_tip"))
        again = _("probe_again") if rows else _("probe_run")
        buttons = [self._btn(again, "probe", "run", primary=True)]
        if rows:
            buttons += [self._btn(_("probe_copy"), "probe", "copy", tip=_("probe_copy_tip")),
                        self._btn(_("probe_save"), "probe", "save", tip=_("probe_save_tip"))]
        page.rows.append(Row("text", note, key="note", buttons=tuple(buttons)))
        for what, answer, known in rows:
            page.rows.append(Row("item", what, answer + (" *" if known else ""), key=what))
        if any(known for *_x, known in rows):
            page.rows.append(Row("text", "* " + _("probe_known_tip"), key="known"))
        return page

    def _a_probe_run(self, _d, _v, _c, _ans):
        from .places import Out, _wait
        try:
            _wait(self.view.probe_server())
        except Exception as e:  # noqa: BLE001 — said, the last answers stay
            return Out(error=_("probe_failed", err=e))
        return Out(refresh=True)

    def _probe_text(self):
        from . import server
        note, rows = self._probe_rows()
        return server.probe_markdown(self._domain(), note, [(w, a) for w, a, _k in rows])

    def _a_probe_copy(self, _d, _v, _c, _ans):
        from .places import Out
        return Out(copy=self._probe_text(), message=_("probe_copied"))

    def _a_probe_save(self, _d, _v, _c, _ans):
        """Into the folder pictures are saved to (ui.save_dir, else Downloads)."""
        from ...core import saving
        from .places import Out
        folder = saving.save_dir(self.view.cfg)
        folder.mkdir(parents=True, exist_ok=True)
        path = saving.free_path(folder, f"fedtail-{self._domain()}-features.md")
        path.write_text(self._probe_text(), "utf-8")
        return Out(message=_("saved_to", path=str(path)))

    # ---- the server's announcements ------------------------------------------------------
    def _p_announcements(self, _arg, _tab, _cur):
        from ..richtext import clean
        from .places import Page, Row, _wait
        items = _wait(self.view.announcements()) or []
        page = Page("announcements", _("announce_title"), empty="—")
        if len(items) > 1:
            page.hint = _("announce_more", n=len(items) - 1)
        reacts = self.view.supports("announcement_reactions")
        for a in items:
            when = self.date(a.published) if a.published else ""
            page.rows.append(Row("heading", f"📢 {_('announce_title')} {when}".strip()))
            buttons = [self._btn(_("announce_ok"), "announcements", "dismiss", a.id,
                                 primary=True, tip=_("tip_announce_ok"))]
            if reacts:
                have = {r.name: r for r in a.reactions}
                for name in list(have) + [e for e in QUICK if e not in have]:
                    r = have.get(name)
                    if len(name) > 4 and not (r and r.count):
                        continue  # a custom emoji nobody used: not offered
                    on = not (r and r.me)
                    label = f"{name} {r.count}" if r and r.count else name
                    buttons.append(self._btn(label, "announcements", "react",
                                             f"{a.id} {int(on)} {name}",
                                             tip=_("announce_react_tip")))
            page.rows.append(Row("html", clean(a.html), key=a.id, buttons=tuple(buttons)))
        return page

    def _a_announcements_dismiss(self, aid, _v, _c, _ans):
        from .places import Out, _wait
        _wait(self.view.dismiss_announcement(aid))
        return Out(refresh=True)

    def _a_announcements_react(self, data, _v, _c, _ans):
        from .places import Out, _wait
        aid, on, name = data.split(" ", 2)
        _wait(self.view.react_announcement(aid, name, on == "1"))
        return Out(refresh=True)

    # ---- a profile's details ----------------------------------------------------------------
    def _p_profile_info(self, acc_id, _tab, cursor):
        """What the head of the windows' profile tab says beyond the line under the
        name: the counts, since when, a move, who of mine follows them, what they put
        forward, the pinned posts — and, past what my server knows, their older posts
        from their own server (cursor: where those go on)."""
        from .places import Page, Row, _wait, acc_line
        v = self.view
        acc = _wait(v.account(acc_id))
        page = Page("profile_info", f"{_('profile_title')}: @{acc.handle}", arg=acc_id,
                    hint=acc_line(acc))
        if cursor:  # the next page of their older posts, from their server
            return self._origin_page(page, acc, cursor)
        page.rows.append(Row("text", _("card_counts", posts=acc.posts,
                                       followers=acc.followers, following=acc.following),
                             key="counts"))
        if acc.created:
            page.rows.append(Row("text", _("card_since", when=self.date(acc.created)),
                                 key="since"))
        me = v.me
        if me is None or acc.id != me.id:
            try:
                rel = _wait(v.relationship(acc.id))
                if rel is not None and rel.following:
                    page.rows.append(Row("text", "✓ " + _("following_them"), key="rel"))
            except Exception as e:  # noqa: BLE001 — the rest still shows
                log.info("profile info: relationship: %s", e.__class__.__name__)
        if acc.moved is not None:
            m = acc.moved
            page.rows.append(Row("html", _("moved_to", acct="@" + m.handle), key="moved",
                                 buttons=(self._btn(_("moved_open"), "person", "open", m.id),
                                          self._btn(_("moved_follow"), "person", "follow",
                                                    m.id, primary=True))))
        if (me is None or acc.id != me.id) and v.supports("familiar"):
            try:
                known = _wait(v.familiar(acc.id)) or []
                if known:
                    page.rows.append(Row("text", _("familiar", who=", ".join(
                        "@" + a.handle for a in known[:5]) + (
                        f" {_('and_more', n=len(known) - 5)}" if len(known) > 5 else "")),
                        key="familiar"))
            except Exception as e:  # noqa: BLE001
                log.info("profile info: familiar: %s", e.__class__.__name__)
        try:
            feat = _wait(v.featured(acc.id)) or {}
        except Exception as e:  # noqa: BLE001
            log.info("profile info: featured: %s", e.__class__.__name__)
            feat = {}
        tags = [t.name if hasattr(t, "name") else str((t or {}).get("name", ""))
                for t in feat.get("tags") or ()]
        if tags:
            page.rows.append(Row("text", _("featured_tags") + " " +
                                 " ".join("#" + t for t in tags if t), key="ftags"))
        people = feat.get("people") or ()
        if people:
            page.rows.append(Row("heading", _("featured_people")))
            for a in people:
                page.rows.append(Row("account", acc_line(a), data=a, key="f:" + a.id))
        try:
            pins = _wait(v.pinned(acc.id)) or []
        except Exception as e:  # noqa: BLE001
            log.info("profile info: pinned: %s", e.__class__.__name__)
            pins = []
        if pins:
            page.rows.append(Row("heading", "📌 " + _("pinned")))
            page.rows += [Row("post", data=p, key="pin:" + p.id) for p in pins]
        host = _host(acc.url or acc.uri)
        if "@" in acc.handle and host:
            page.rows.append(Row("heading", _("profile_posts")))
            page.more = self._btn(_("older_from_origin", host=host), "profile_info",
                                  "origin", acc.id, tip=_("older_from_origin_tip",
                                                          host=host))
        return page

    def _origin_page(self, page, acc, cursor):
        from .places import Row, _wait
        host = _host(acc.url or acc.uri)
        start = None if cursor == "start" else cursor
        posts, nxt = _wait(self.view.older_from_origin(acc, start))
        page.hint = _("origin_got", n=len(posts), host=host) + " · " + \
            _("older_from_origin_note")
        page.rows += [Row("post", data=p, key=p.id) for p in posts or ()]
        page.empty = _("no_older")
        if nxt:
            page.more = self._btn(_("older_down"), "profile_info", "origin",
                                  f"{acc.id} {nxt}", tip=_("origin_asking", host=host))
        return page

    def _a_profile_info_origin(self, data, _v, _c, _ans):
        from .places import Out
        acc_id, _s, cursor = data.partition(" ")
        return Out(open={"page": "profile_info", "arg": acc_id, "cursor": cursor or "start"})


__all__ = ["MorePlaces", "QUICK"]
