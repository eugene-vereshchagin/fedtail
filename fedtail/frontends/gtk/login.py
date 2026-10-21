"""Login: register the app, open the browser, paste the code (as qt/login.py)."""

from ...i18n import _
from .gi_setup import Gtk


class LoginDialog(Gtk.Window):
    def __init__(self, win, done, expect=None):
        super().__init__(transient_for=win, modal=True,
                         title=_("login_title", profile=win.core.paths.profile))
        self.win, self.core, self.done, self.expect = win, win.core, done, expect
        self.url = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(16)
        box.append(Gtk.Label(label=_("login_server"), xalign=0))
        self.server = Gtk.Entry(placeholder_text="example.social")
        if expect:
            self.server.set_text(expect[0].split("://")[-1].rstrip("/"))
        self.server.connect("activate", lambda _e: self.step1())
        box.append(self.server)
        self.b1 = Gtk.Button(label=_("login_step1"))
        self.b1.connect("clicked", lambda _b: self.step1())
        box.append(self.b1)
        hint = Gtk.Label(label=_("login_hint"), xalign=0, wrap=True)
        box.append(hint)
        self.code = Gtk.Entry(sensitive=False)
        self.code.connect("activate", lambda _e: self.step2())
        box.append(self.code)
        self.b2 = Gtk.Button(label=_("login_step2"), sensitive=False)
        self.b2.add_css_class("suggested-action")
        self.b2.connect("clicked", lambda _b: self.step2())
        box.append(self.b2)
        self.msg = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.msg.add_css_class("ft-muted")
        box.append(self.msg)
        self.set_child(box)
        self.set_default_size(480, -1)

    def step1(self):
        if not self.server.get_text().strip():
            return
        self.b1.set_sensitive(False)
        self.msg.set_text(_("loading"))
        self.win.bridge.call(self.core.begin_login(self.server.get_text()), self._opened,
                             self._fail)

    def _opened(self, url):
        self.url = url
        self.win.open_url(url)
        self.code.set_sensitive(True)
        self.b2.set_sensitive(True)
        self.b1.set_sensitive(True)
        self.code.grab_focus()
        self.msg.set_text(_("login_browser_opened", url=url))

    def step2(self):
        if not self.code.get_text().strip():
            return
        self.b2.set_sensitive(False)
        self.win.bridge.call(self.core.finish_login(self.code.get_text(), expect=self.expect),
                             self._ok, self._fail)

    def _ok(self, _me):
        self.close()
        self.done()

    def _fail(self, err):
        from ...core.app import OtherAccount
        if err.startswith(OtherAccount.PREFIX) and self.expect:
            self.msg.set_text(_("login_other_account", got=err[len(OtherAccount.PREFIX):],
                                want="@" + self.expect[1]))
        else:
            self.msg.set_text(_("error", err=err))
        self.b1.set_sensitive(True)
        self.b2.set_sensitive(self.url is not None)
