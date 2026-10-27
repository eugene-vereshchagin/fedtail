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


# ---- accounts: switch, add, make main, log in anew, log out --------------------------
# (the windows' Accounts menu and login window, for the web page and the terminal)

# a login under way, between "open the login page" and "log in": profile name ->
# (the Core it goes into, the page's address, (server, acct) when it's the same
# account again or None). Places come and go per request; this outlives them.
_LOGINS = {}


def _plain(html):
    """The windows' words have <br> and <b> in them: as text."""
    import html as html_mod
    import re
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    return html_mod.unescape(re.sub(r"<[^>]+>", "", text))


class AccountPlaces:
    """The places "accounts" and "login" (mixed into Places)."""

    def _cores(self):
        """(the core this place runs on — the primary one of an all-in-one window —,
        whether other accounts are merged into it)."""
        core = getattr(self.view, "_core", self.view)
        return getattr(core, "primary", core), bool(getattr(core, "others", None))

    @staticmethod
    def _handle(core):
        """The handle this core's profile logged in as ("" — not known)."""
        from ...core.view import View
        return View(core).auth_handle

    def _p_accounts(self, _arg, _tab, _cur):
        from ...core import profiles
        from .places import Btn, Page, Row
        core, merged = self._cores()
        me = core.paths.profile
        page = Page("accounts", _("accounts"))
        for p in profiles.listing():
            line = "" if p["logged_in"] else _("not_logged_in")
            title = profiles.label(p) + (" ★" if p["main"] else "")
            if p["name"] == me:
                buttons = []
                if not p["main"]:
                    buttons.append(self._btn(_("make_main").rstrip(" ★"), "accounts", "main",
                                             tip=_("make_main_tip")))
                if not merged and core.auth:  # all-in-one: they'd mix the accounts up
                    buttons += [self._btn(_("relogin"), "accounts", "relogin"),
                                self._btn(_("logout"), "accounts", "logout")]
                page.rows.append(Row("item", "● " + title, line, key=p["name"],
                                     buttons=tuple(buttons)))
            else:
                act = "switch" if p["logged_in"] else "login"
                page.rows.append(Row("item", title, line, key=p["name"], buttons=(
                    self._btn(_("open_action"), "accounts", act, p["name"]),)))
        page.more = Btn(_("account_add"), ("accounts", "add", ""))
        return page

    def _a_accounts_switch(self, name, _v, _c, _ans):
        from .places import Out
        return Out(open={"profile": name})

    def _a_accounts_login(self, name, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "login", "arg": name})

    def _a_accounts_main(self, _d, _v, _c, _ans):
        from ...core import paths
        from .places import Out
        core, _merged = self._cores()
        paths.set_main(core.paths.profile)
        log.info("main profile: %s (from the accounts place)", core.paths.profile)
        return Out(message=_("made_main", profile=core.paths.profile), refresh=True)

    def _a_accounts_add(self, _d, _v, _c, answer):
        from ...core import paths, profiles
        from .places import Out
        if answer is None:
            return Out(ask=(_("account_add").rstrip("…"), _("account_add_q"), ""))
        name = str(answer).strip()
        taken = {p["name"] for p in profiles.listing()}
        if not name or name in taken or name in profiles.NOT_PROFILES or \
                not paths._PROFILE_RE.match(name):
            return Out(error=_("account_bad_name", name=name))
        return Out(open={"page": "login", "arg": name})

    def _a_accounts_relogin(self, _d, _v, confirmed, _ans):
        from .places import Out
        core, _merged = self._cores()
        acct = "@" + (self._handle(core) or core.paths.profile)
        if not confirmed:
            return Out(confirm=_plain(_("relogin_q", acct=acct)))
        return Out(open={"page": "login", "arg": core.paths.profile})

    def _a_accounts_logout(self, _d, _v, confirmed, _ans):
        """As the windows: the token gone (here and on the server), ★ handed on; then
        the next account logged in — or the login, none left."""
        from ...core import paths, profiles
        from .places import Out
        core, _merged = self._cores()
        me = core.paths.profile
        acct = "@" + (self._handle(core) or me)
        others = [p for p in profiles.listing() if p["logged_in"] and p["name"] != me]
        main = paths.main_profile()
        target = next((p for p in others if p["name"] == main), others[0]) if others else None
        if not confirmed:
            text = [_("logout_q", acct=acct)]
            if target is not None:
                if me == main:
                    text.append(_("logout_main_moves", to=profiles.label(target)))
                text.append(_("logout_switch", to=profiles.label(target)))
            else:
                text.append(_("logout_last"))
            return Out(confirm=_plain("<br><br>".join(text)))
        log.info("logout: profile %s", me)
        core.logout()
        profiles.hand_over_main(me)
        if target is not None:
            return Out(open={"profile": target["name"]})
        return Out(open={"page": "login", "arg": me})

    # ---- logging in: the server, its page in the browser, the code pasted --------------
    def _login_core(self, name):
        """The Core a login goes into: this one (the same account again), or one made
        for the other profile (its folders and config made as a first start makes them)."""
        from ...core import config, paths
        from ...core.app import Core
        core, _merged = self._cores()
        if name == core.paths.profile:
            return core, True
        where = paths.resolve(name)
        where.ensure()
        cfg, _warn = config.load(where.config_file)
        return Core(cfg, where, api_class=core.api_class), False

    def _p_login(self, name, _tab, _cur):
        from .places import Btn, Field, Page, Row
        core, _merged = self._cores()
        page = Page("login", _("login_title", profile=name), arg=name)
        got = _LOGINS.get(name)
        if got is None:
            server = ""
            if name == core.paths.profile and core.auth:
                server = core.auth["server"].split("://")[-1].rstrip("/")
            page.form = (Field("server", _("login_server").rstrip(":"), server,
                               tip="example.social"),)
            if core.cfg["net"].get("proxy_at_login"):  # before the first request
                page.form += (Field("proxy", _("login_proxy").rstrip(":"),
                                    str(core.cfg["net"].get("proxy") or ""),
                                    tip=_("login_proxy_tip")),)
            page.submit = Btn(_("login_step1"), ("login", "begin", name), primary=True)
            return page
        _core, url, _expect = got
        page.rows.append(Row("text", _plain(_("login_browser_opened", url=url)), key="url",
                             buttons=(self._btn(_("open_browser"), "login", "open", name),)))
        page.hint = _("login_hint")
        page.form = (Field("code", _("login_step2").lstrip("2. "), ""),)
        page.submit = Btn(_("login_step2"), ("login", "finish", name), primary=True)
        page.more = Btn(_("login_step1"), ("login", "again", name))
        return page

    def _a_login_begin(self, name, values, _c, _ans):
        from .places import Out, _wait
        server = str(values.get("server") or "").strip()
        if not server:
            return Out(error=_("login_server"))
        core, same = self._login_core(name)
        expect = None
        if same and core.auth:
            expect = (core.auth["server"], self._handle(core))
        try:
            more = {"proxy": str(values["proxy"])} if "proxy" in values else {}
            url = _wait(core.begin_login(server, **more))
        except Exception as e:  # noqa: BLE001 — the server's own words
            if not same:
                core.shutdown()
            return Out(error=_("error", err=e))
        old = _LOGINS.pop(name, None)
        if old and old[0] is not core:
            own, _merged = self._cores()
            if old[0] is not own:
                old[0].shutdown()
        _LOGINS[name] = (core, url, expect)
        return Out(refresh=True, open={"url": url})

    def _a_login_open(self, name, _v, _c, _ans):
        from .places import Out
        got = _LOGINS.get(name)
        return Out(open={"url": got[1]}) if got else Out(refresh=True)

    def _a_login_again(self, name, _v, _c, _ans):
        from .places import Out
        got = _LOGINS.pop(name, None)
        own, _merged = self._cores()
        if got and got[0] is not own:
            got[0].shutdown()
        return Out(refresh=True)

    def _a_login_finish(self, name, values, _c, _ans):
        from ...core import profiles
        from ...core.app import OtherAccount
        from .places import Out, _wait
        got = _LOGINS.get(name)
        if got is None:
            return Out(refresh=True)
        core, _url, expect = got
        code = str(values.get("code") or "").strip()
        if not code:
            return Out(error=_("login_hint"))
        try:
            me = _wait(core.finish_login(code, expect=expect))
        except OtherAccount as e:
            got_acct = str(e)[len(OtherAccount.PREFIX):]
            return Out(error=_plain(_("login_other_account", got=got_acct,
                                      want="@" + (expect[1] if expect else ""))))
        except Exception as e:  # noqa: BLE001
            return Out(error=_("error", err=e))
        _LOGINS.pop(name, None)
        profiles.remember(core.paths, me, core.auth["server"])
        own, _merged = self._cores()
        from ...core.view import View
        handle = View(core).acc(me).handle
        done = _("login_done", acct=handle)
        if core is own:  # the same account again: on with the new token
            try:
                _wait(core.connect())
            except Exception as e:  # noqa: BLE001
                return Out(error=_("error", err=e))
            return Out(message=done, open={"page": "accounts"})
        core.shutdown()
        log.info("login: profile %s is @%s", name, handle)
        return Out(message=done, open={"profile": name})


__all__ = ["AccountPlaces", "MorePlaces", "QUICK"]
