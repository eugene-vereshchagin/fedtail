"""≡ → Sync: setting up sync between the account's devices step by step, without a
terminal — the same in every interface (the windows, GTK, the terminal's places, the
web page, the phone).

The place shows where the setup stands and the one next step:

  1. where   — the sync server's address, a shared folder or a WebDAV folder
               (config.toml, used at once) — or, with another device syncing already,
               its key's QR code scanned: the server's address comes with it;
  2. login   — a WebDAV folder's user and password; the step is there for WebDAV only
               (a sync server's journal is the key's, made with the invite code given at
               step 1; a folder needs none): a "✓ none needed" read as "logged in" (02.11);
  3. key     — the fork: "this is my first device" (the key is made here) or "I'm adding
               this device to those already syncing" (the key pasted from another
               device, or taken out of the journal with its password);
  done       — how it goes, "Sync now", the key shown for the next device, the key put
               into the journal under a password, what to sync, where, turning it off.

`tab` picks a step by hand ("where" to change the server, "join" / "first" for the
two ways at step 3); none — the step it stands at.
"""

from __future__ import annotations

import logging

from ...i18n import _
from .syncline import last_line

log = logging.getLogger(__name__)

STEPS = ("where", "login", "key")


def crypto_min():
    from ...core.sync import crypto
    return crypto.MIN_PASSWORD


class SyncPlaces:
    def _sync_state(self):
        """(status or None, the step it stands at: "where" | "login" | "key" | "done")."""
        v = self.view
        st = v.sync_status()
        if st is None:
            return None, "where"
        if st.get("backend") == "webdav" and not st.get("login"):
            return st, "login"
        if self._invite_wanted(st):  # the server won't make the journal: step 1 again
            return st, "where"
        if not st.get("key") and not v.sync_key():
            return st, "key"
        return st, "done"

    @staticmethod
    def _invite_wanted(st):
        """The last round met a server that wants an invite code for the journal."""
        return (st or {}).get("backend") == "server" and \
            ((st or {}).get("last") or {}).get("error_kind") == "invite"

    def _sync_steps(self, page, st, at):
        """The steps on top: ✓ done, ▶ now, · later — each with what it holds; the login
        one for a WebDAV folder only."""
        from .places import Row
        s = self.view.cfg["sync"]
        webdav = (st or {}).get("backend") == "webdav" or (st is None and s.get("webdav"))
        order = [x for x in STEPS if x != "login" or webdav]
        now = order.index(at) if at in order else len(order)
        said = {"where": s.get("folder") or s.get("webdav") or s.get("url") or "",
                "login": (st or {}).get("login") or "",
                "key": (st or {}).get("key") or ""}
        for i, step in enumerate(order):
            mark = "✓" if i < now else ("▶" if i == now else "·")
            line = said[step] if i < now else _("sync_step_" + step + "_what")
            page.rows.append(Row("text", f"{mark} {i + 1}. {_('sync_step_' + step)}", line,
                                 key="step:" + step))

    def _p_sync(self, _arg, tab, _cur):
        from .places import Btn, Field, Page, Row
        v = self.view
        st, at = self._sync_state()
        step = tab if tab in ("where", "join", "first") else at
        if tab == "escrow" and at == "done":
            step = "escrow"
        page = Page("sync", _("sync_title"), tab=step)
        self._sync_steps(page, st, "key" if step in ("join", "first") else
                         ("where" if step == "where" else
                          ("done" if step == "escrow" else at)))
        s = v.cfg["sync"]

        if step != "done" and st is not None and at != "done":
            # set up partly: said plainly that nothing syncs yet (a ✓ read as "on", 02.11)
            page.rows.append(Row("text", _("sync_not_yet_title"), _("sync_not_yet_line"),
                                 key="not_yet"))

        if step == "where":
            page.hint = _("sync_where_hint")
            if self._invite_wanted(st):  # why the page stands here: said on top of it
                page.rows.append(Row("text", _("sync_invite_needed_title"),
                                     _("sync_invite_needed_line"), key="invite"))
            if not self._invite_wanted(st):  # another device syncs: its QR says where too
                page.rows.append(Row("item", _("sync_scan_title"), _("sync_scan_line"),
                                     key="scan", buttons=(self._btn(
                                         _("sync_join_btn"), "sync", "goto", "join"),)))
            page.form = (Field("url", _("sync_f_url"), str(s.get("url") or ""),
                               tip=_("sync_f_url_tip")),
                         Field("invite", _("sync_f_invite"), "", tip=_("sync_f_invite_tip")),
                         Field("folder", _("sync_f_folder"), str(s.get("folder") or ""),
                               tip=_("sync_f_folder_tip"), folder=True),
                         Field("webdav", _("sync_f_webdav"), str(s.get("webdav") or ""),
                               tip=_("sync_f_webdav_tip")))
            page.submit = Btn(_("sync_next"), ("sync", "where", ""), True)
            if st is not None:
                page.more = Btn(_("sync_turn_off"), ("sync", "off", ""))
            return page

        if step == "login" and (st or {}).get("backend") == "webdav":
            page.hint = _("sync_webdav_hint", where=s.get("webdav") or "")
            page.form = (Field("user", _("sync_webdav_user"), str(s.get("webdav_user") or "")),
                         Field("password", _("sync_webdav_password"), "", "secret",
                               tip=_("sync_webdav_password_tip")))
            page.submit = Btn(_("sync_next"), ("sync", "dav", ""), True)
            page.more = Btn(_("sync_back_where"), ("sync", "goto", "where"))
            return page

        if step == "key":  # the fork: the first device, or one more
            page.hint = _("sync_fork_hint")
            there = v.sync_journal_there()
            first = Row("item", _("sync_first_title"), _("sync_first_line"),
                        key="first", buttons=(self._btn(_("sync_first_btn"), "sync", "goto",
                                                        "first", primary=not there),))
            join = Row("item", _("sync_join_title"), _("sync_join_line"), key="join",
                       buttons=(self._btn(_("sync_join_btn"), "sync", "goto", "join",
                                          primary=bool(there)),))
            page.rows += [join, first] if there else [first, join]
            if there:
                page.rows.append(Row("text", _("sync_journal_there")))
            return page

        if step == "first":
            page.hint = _("sync_first_hint")
            page.submit = Btn(_("sync_first_go"), ("sync", "first", ""), True)
            page.more = Btn(_("sync_back_fork"), ("sync", "goto", "key"))
            return page

        if step == "join":
            escrow = st is not None and v.sync_has_escrow() is not False  # None: maybe
            page.hint = _("sync_join_hint")
            fields = [Field("key", _("sync_key_paste_f"), "", tip=_("sync_key_paste_tip"),
                            scan=True)]
            if escrow:
                fields.append(Field("password", _("sync_password_take"), "", "secret",
                                    tip=_("sync_password_take_tip")))
            page.form = tuple(fields)
            page.submit = Btn(_("sync_take_btn"), ("sync", "take", ""), True)
            page.more = Btn(_("sync_back_fork"), ("sync", "goto", "key"))
            if st is not None:
                page.rows.append(Row("text", _("sync_lost_title"), _("sync_lost_line"),
                                     key="lost", buttons=(self._btn(
                                         _("sync_fresh_btn"), "sync", "fresh"),)))
            return page

        if step == "escrow":  # the password for new devices, on a page of its own
            page.hint = _("sync_escrow_hint", n=crypto_min())
            page.form = (Field("password", _("sync_password"), "", "secret"),
                         Field("password2", _("sync_password_again"), "", "secret"))
            page.submit = Btn(_("sync_escrow_put"), ("sync", "escrow", ""), True)
            page.more = Btn(_("sync_back_done"), ("sync", "goto", "done"))
            return page

        # done: how it goes, and what one does with it from here
        last = (st or {}).get("last") or {}
        nothing = _("sync_nothing")
        page.hint = _("sync_done_hint")
        page.rows += [
            Row("text", _("sync_f_pending"), str((st or {}).get("pending", 0))),
            Row("text", _("sync_f_last"), last_line(last) or nothing,
                buttons=(self._btn(_("sync_now_btn"), "sync", "now", primary=True),)),
            Row("item", _("sync_next_device_title"), _("sync_next_device_line"),
                key="show", buttons=(self._btn(_("sync_key_show_btn"), "sync", "show"),)),
            Row("item", _("sync_escrow_title"),
                _("sync_escrow_set") if v.sync_has_escrow() else _("sync_escrow_line"),
                key="escrow", buttons=(self._btn(
                    _("sync_escrow_change") if v.sync_has_escrow() else _("sync_escrow_btn"),
                    "sync", "goto", "escrow"),)),
            Row("item", _("sync_what_title"), _("sync_what_line"), key="what",
                buttons=(self._btn(_("sync_what_btn"), "sync", "what"),
                         self._btn(_("sync_change_where"), "sync", "goto", "where"))),
        ]
        page.rows += self._lane_rows()
        return page

    def _lane_rows(self):
        """The lanes between the devices (sync.lane_rules): on here or not, "send my
        lanes" — and each other device, whether it takes them. The same lanes everywhere
        is the same counts everywhere (08.11)."""
        from .places import Row
        v = self.view
        on = bool(v.cfg["sync"].get("lane_rules", False))
        if on:
            row = Row("item", _("sync_lanes_title"), _("sync_lanes_on_line"), key="lanes",
                      buttons=(self._btn(_("sync_lanes_push"), "sync", "pushlanes",
                                         tip=_("sync_lanes_push_tip")),))
        else:
            row = Row("item", _("sync_lanes_title"), _("sync_lanes_off_line"), key="lanes",
                      buttons=(self._btn(_("sync_lanes_turn_on"), "sync", "laneson"),))
        rows = [row]
        for d in v.sync_devices() or ():
            name = d["name"] or _("sync_device_unnamed")
            said = {True: _("sync_device_lanes_yes"), False: _("sync_device_lanes_no"),
                    None: _("sync_device_lanes_unknown")}[d["lane_rules"]]
            rows.append(Row("text", "· " + name, said, key="dev:" + d["id"]))
        return rows

    def _a_sync_laneson(self, _d, _v, _c, _ans):
        from .places import Out
        self.view.sync_lane_rules_on()
        return Out(message=_("sync_lanes_now_on"), open={"page": "sync"})

    def _a_sync_pushlanes(self, _d, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_lanes_push_sure"))
        if not self.view.push_lane_rules():
            return Out(error=_("sync_lanes_off_line"))
        done = self.view.sync_now()
        return Out(message=_("sync_lanes_sent") if done else _("sync_lanes_queued"),
                   refresh=True)

    # ---- the buttons ---------------------------------------------------------------
    def _a_sync_goto(self, step, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "sync", "tab": step})

    def _a_sync_where(self, _d, values, _c, _ans):
        from .places import Out
        v = self.view
        url = str(values.get("url") or "").strip()
        folder = str(values.get("folder") or "").strip()
        dav = str(values.get("webdav") or "").strip()
        if not url and not folder and not dav:
            return Out(error=_("sync_where_none"))
        if url and not url.startswith(("https://", "http://")):
            url = "https://" + url
        if dav and not dav.startswith(("https://", "http://")):
            dav = "https://" + dav
        invite = str(values.get("invite") or "").strip() or None
        try:
            v.sync_setup(url=url, folder=folder, webdav=dav, invite=invite)
        except ValueError as e:  # http:// to someone's server: refused, nothing kept
            return Out(error=str(e))
        if invite and v.sync_key():  # the code for a journal that waits for it: tried now
            done = v.sync_now()
            if done:
                return Out(message=_("sync_round", sent=done[0], got=done[1]),
                           open={"page": "sync"})
        # "Sync is on" said with no key yet read as done (02.11): on only once it can run
        _st, at = self._sync_state()
        return Out(message=_("sync_saved_on") if at == "done" else _("sync_saved_where"),
                   open={"page": "sync"})

    def _a_sync_dav(self, _d, values, _c, _ans):
        from .places import Out
        why = self.view.sync_webdav_login(values.get("user"), str(values.get("password") or ""))
        if why:
            return Out(error=why)
        return Out(message=_("sync_webdav_ok"), open={"page": "sync"})

    def _a_sync_off(self, _d, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_off_sure"))
        self.view.sync_setup(url="", folder="", webdav="")
        return Out(message=_("sync_saved_off"), open={"page": "sync"})

    def _a_sync_what(self, _d, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "settings", "tab": "sync"})

    def _a_sync_now(self, _d, _v, _c, _ans):
        from .places import Out, _wait
        v = self.view
        if v.logged_in:
            try:
                _wait(v.connect())  # a thread's state from elsewhere asks the server
            except Exception as e:  # noqa: BLE001 — the round says what's wrong
                log.info("sync now: connect: %s", e)
        done = v.sync_now()
        if not done:
            last = (v.sync_status() or {}).get("last") or {}
            return Out(error=last.get("error") or _("sync_round_failed"), refresh=True)
        return Out(message=_("sync_round", sent=done[0], got=done[1]), refresh=True)

    def _a_sync_first(self, _d, _v, _c, _ans):
        from .places import Out
        v = self.view
        try:
            kid = v.sync_first_key()
        except ValueError:
            return Out(error=_("sync_first_but_journal"), open={"page": "sync", "tab": "join"})
        v.sync_setup()
        done = v.sync_now()
        return Out(message=_("sync_first_done", kid=kid) +
                   (" · " + _("sync_round", sent=done[0], got=done[1]) if done else ""),
                   open={"page": "sync"})

    def _a_sync_show(self, _d, _v, confirmed, _ans):
        """The key for the next device — after a "sure?": its QR code to scan, and the
        text to copy (place sync_key)."""
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_key_show_sure"))
        if not self.view.sync_key():
            return Out(error=_("sync_key_none"))
        return Out(open={"page": "sync_key"})

    def _p_sync_key(self, _arg, _tab, _cur):
        from . import qr
        from .places import Btn, Page, Row
        key = self.view.sync_key()
        page = Page("sync_key", _("sync_key_title"), hint=_("sync_key_hint"),
                    empty=_("sync_key_none"))
        if key:
            link = self.view.sync_key_link() or key
            try:  # the key and the server's address: the new device types nothing
                code = qr.matrix(link)
            except qr.TooLong:  # an address too long for it: the key alone
                link, code = key, qr.matrix(key)
            page.rows.append(Row("qr", line=_("sync_key_scan_server") if link != key
                                 else _("sync_key_scan_line"), key="qr", data=qr.rows(code)))
            page.rows.append(Row("pre", key, key="text", buttons=(
                self._btn(_("sync_key_copy"), "sync", "copykey"),)))
        page.more = Btn(_("sync_back_done"), ("sync", "goto", "done"))
        return page

    def _a_sync_copykey(self, _d, _v, _c, _ans):
        from .places import Out
        key = self.view.sync_key()
        return Out(message=_("sync_key_copied"), copy=key) if key else \
            Out(error=_("sync_key_none"))

    def _a_sync_escrow(self, _d, values, _c, _ans):
        from ...core.sync import crypto
        from .places import Out
        one, two = str(values.get("password") or ""), str(values.get("password2") or "")
        if len(one) < crypto.MIN_PASSWORD:
            return Out(error=_("sync_password_short", n=crypto.MIN_PASSWORD))
        if one != two:
            return Out(error=_("sync_password_differ"))
        self.view.sync_put_escrow(one)
        return Out(message=_("sync_escrow_done"), open={"page": "sync"})

    def _a_sync_take(self, _d, values, _c, _ans):
        from ...core.sync import crypto
        from .places import Out
        v = self.view
        key = str(values.get("key") or "").strip()
        password = str(values.get("password") or "")
        try:
            if key:
                kid = v.sync_join(key)
            elif password:
                kid = v.sync_take_escrow(password)
            else:
                return Out(error=_("sync_take_what"))
        except crypto.BadBlob:
            return Out(error=_("sync_password_wrong"))
        except ValueError:
            return Out(error=_("sync_join_bad"))
        v.sync_setup()
        done = v.sync_now()
        return Out(message=_("sync_join_ok", kid=kid) +
                   (" · " + _("sync_round", sent=done[0], got=done[1]) if done else ""),
                   open={"page": "sync"})

    def _a_sync_fresh(self, _d, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_fresh_sure"))
        kid = self.view.sync_fresh_key()
        self.view.sync_setup()
        return Out(message=_("sync_fresh_done", kid=kid), open={"page": "sync"})
