"""≡ → Sync: setting up sync between the account's devices without a terminal — the
same steps as `fedtail sync …`, in every interface (the windows, GTK, the terminal's
places, the web page, the phone's place list).

Three tabs:
  where — the sync server's address or a shared folder (written into config.toml and
          used at once), how it stands, "Sync now";
  login — the sync server's own narrow token: the browser's page, then its code;
  key   — the account's key: shown to copy to another device, taken from another
          device, kept in the journal under a password (and taken from there with the
          password alone), or made anew when the old one isn't at hand.
"""

from __future__ import annotations

import logging

from ...i18n import _

log = logging.getLogger(__name__)

_LOGIN = {}  # profile → the sync login under way (core.sync_login_begin's pending)


class SyncPlaces:
    def _p_sync(self, _arg, tab, _cur):
        from .places import Btn, Field, Page, Row
        v = self.view
        tab = tab if tab in ("where", "login", "key") else "where"
        page = Page("sync", _("sync_title"), tab=tab, tabs=(
            ("where", _("sync_tab_where")), ("login", _("sync_tab_login")),
            ("key", _("sync_tab_key"))))
        st = v.sync_status()
        s = v.cfg["sync"]
        if tab == "where":
            page.hint = _("sync_where_hint")
            if st is None:
                page.rows.append(Row("text", _("sync_off_title"), _("sync_off_line")))
            else:
                last = st.get("last") or {}
                nothing = _("sync_nothing")
                page.rows += [
                    Row("text", _("sync_f_where"), f"{st['backend']}: {st['where']}"),
                    Row("text", _("sync_f_login"), st.get("login") or nothing),
                    Row("text", _("sync_f_key"), st.get("key") or nothing),
                    Row("text", _("sync_f_pending"), str(st.get("pending", 0))),
                    Row("text", _("sync_f_last"), " ".join(
                        x for x in (last.get("at", ""), last.get("error", "")) if x)
                        or nothing, buttons=(self._btn(_("sync_now_btn"), "sync", "now"),)),
                ]
            page.form = (Field("url", _("sync_f_url"), str(s.get("url") or ""),
                               tip=_("sync_f_url_tip")),
                         Field("folder", _("sync_f_folder"), str(s.get("folder") or ""),
                               tip=_("sync_f_folder_tip")))
            page.submit = Btn(_("sync_save_where"), ("sync", "where", ""), True)
            page.more = Btn(_("sync_what_btn"), ("sync", "what", ""))
            return page
        if tab == "login":
            page.hint = _("sync_login_hint")
            if st is not None and st.get("backend") == "folder":
                page.rows.append(Row("text", _("sync_login_folder")))
                return page
            if st is not None and st.get("login"):
                page.rows.append(Row("text", _("sync_f_login"), st["login"]))
            got = _LOGIN.get(v.paths.profile)
            if got is None:
                page.submit = Btn(_("sync_login_go") if not (st or {}).get("login")
                                  else _("sync_login_again"), ("sync", "login", ""), True)
                return page
            page.rows.append(Row("text", _("login_browser_opened", url=got["url"]), key="url",
                                 buttons=(self._btn(_("open_browser"), "sync", "open"),)))
            page.form = (Field("code", _("sync_login_code_f"), ""),)
            page.submit = Btn(_("login_step2"), ("sync", "code", ""), True)
            return page
        # the key
        page.hint = _("sync_key_hint")
        has_key = bool((st or {}).get("key")) or bool(v.sync_key())
        if has_key:
            page.rows.append(Row("text", _("sync_f_key"), (st or {}).get("key") or "✓",
                                 buttons=(self._btn(_("sync_key_show_btn"), "sync", "show"),)))
            if st is not None:
                page.rows.append(Row("text", _("sync_escrow_title"), _("sync_escrow_line")))
                page.form = (Field("password", _("sync_password"), "", "secret"),
                             Field("password2", _("sync_password_again"), "", "secret"))
                page.submit = Btn(_("sync_escrow_put"), ("sync", "escrow", ""))
            return page
        page.rows.append(Row("text", _("sync_no_key_title"), _("sync_no_key_line")))
        escrow = st is not None and v.sync_has_escrow()
        fields = [Field("key", _("sync_key_paste_f"), "", tip=_("sync_key_paste_tip"))]
        if escrow:
            fields.append(Field("password", _("sync_password_take"), "", "secret",
                                tip=_("sync_password_take_tip")))
        page.form = tuple(fields)
        page.submit = Btn(_("sync_take_btn"), ("sync", "take", ""), True)
        if st is not None:
            page.more = Btn(_("sync_fresh_btn"), ("sync", "fresh", ""))
        return page

    # ---- the buttons ---------------------------------------------------------------
    def _a_sync_where(self, _d, values, _c, _ans):
        from .places import Out
        v = self.view
        url = str(values.get("url") or "").strip()
        folder = str(values.get("folder") or "").strip()
        if url and not url.startswith(("https://", "http://")):
            url = "https://" + url
        on = v.sync_setup(url=url, folder=folder)
        return Out(message=_("sync_saved_on") if on else _("sync_saved_off"), refresh=True)

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

    def _a_sync_login(self, _d, _v, _c, _ans):
        from .places import Out
        v = self.view
        if not v.logged_in:
            return Out(error=_("cli_login_first"))
        pending = v.sync_login_begin()
        _LOGIN[v.paths.profile] = pending
        return Out(refresh=True, open={"url": pending["url"]})

    def _a_sync_open(self, _d, _v, _c, _ans):
        from .places import Out
        got = _LOGIN.get(self.view.paths.profile)
        return Out(open={"url": got["url"]}) if got else Out(refresh=True)

    def _a_sync_code(self, _d, values, _c, _ans):
        from .places import Out
        v = self.view
        got = _LOGIN.get(v.paths.profile)
        code = str(values.get("code") or "").strip()
        if got is None:
            return Out(refresh=True)
        if not code:
            return Out(error=_("sync_login_code_f"))
        v.sync_login_end(got, code)
        _LOGIN.pop(v.paths.profile, None)
        v.sync_setup()  # the token there now: the engine anew, with it
        return Out(message=_("sync_login_ok", instance=got["instance"]),
                   open={"page": "sync", "tab": "key"})

    def _a_sync_show(self, _d, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_key_show_sure"))
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
        return Out(message=_("sync_escrow_done"), refresh=True)

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
        return Out(message=_("sync_join_ok", kid=kid), open={"page": "sync", "tab": "where"})

    def _a_sync_fresh(self, _d, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("sync_fresh_sure"))
        kid = self.view.sync_fresh_key()
        self.view.sync_setup()
        return Out(message=_("sync_fresh_done", kid=kid), refresh=True)
