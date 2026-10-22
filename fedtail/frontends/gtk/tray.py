"""The tray icon of the GTK window, as Qt's: GTK 4 has none of its own, so it speaks
the desktop's own protocol over D-Bus — StatusNotifierItem (KDE's, also the GNOME
AppIndicator extension's, XFCE's, LXQt's) with its menu (com.canonical.dbusmenu). A
click: the window away and back; the menu: Show, Write, Quit; the tooltip: how much is
new; "needs attention" while there is. No watcher on the bus (no tray there): None."""

from __future__ import annotations

import logging
import os

from ...i18n import _
from .gi_setup import Gio, GLib

log = logging.getLogger(__name__)

WATCHER = "org.kde.StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

ITEM_XML = """<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/>
<property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionIconName" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/>
<property name="Menu" type="o" access="read"/>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/>
</method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewToolTip"/>
<signal name="NewStatus"><arg type="s"/></signal>
</interface></node>"""

MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="TextDirection" type="s" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
<arg type="as" direction="in"/><arg type="u" direction="out"/>
<arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/>
<arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
</method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/>
<arg type="ai" direction="out"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>"""


def _pixmaps():
    """The opossum as the tray wants it: ARGB32, big-endian, at a few sizes."""
    from importlib import resources
    out = []
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        path = str(resources.files("fedtail").joinpath("data/icons/fedtail.png"))
        for side in (22, 32, 64):
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, side, side)
            if not pb.get_has_alpha():
                pb = pb.add_alpha(False, 0, 0, 0)
            w, h, stride = pb.get_width(), pb.get_height(), pb.get_rowstride()
            px = pb.get_pixels()
            argb = bytearray()
            for y in range(h):
                row = px[y * stride:y * stride + w * 4]
                for x in range(0, w * 4, 4):
                    r, g, b, a = row[x:x + 4]
                    argb += bytes((a, r, g, b))
            out.append((w, h, bytes(argb)))
    except (GLib.Error, OSError, ValueError) as e:
        log.info("tray: no picture (%s)", e)
    return out


class Tray:
    """One for the window. menu: [(label, fn)] — None for a separator."""

    def __init__(self, bus, activate, menu, title):
        self.bus, self.activate, self.menu = bus, activate, menu
        self.title, self.tip, self.attention = title, title, False
        self.revision = 1
        self.pixmaps = _pixmaps()
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        item = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.ids = [bus.register_object(ITEM_PATH, item, self._item_call, self._item_prop,
                                        None),
                    bus.register_object(MENU_PATH, menu_info, self._menu_call,
                                        self._menu_prop, None)]
        self.owner = Gio.bus_own_name_on_connection(bus, self.name,
                                                    Gio.BusNameOwnerFlags.NONE, None, None)
        def registered(conn, res):
            try:
                conn.call_finish(res)
                log.info("tray: %s", self.name)
            except GLib.Error as e:
                log.warning("tray: not taken (%s)", e.message)
        # (not waited for: the window never stands still for the panel)
        bus.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                 GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 5000,
                 None, registered)

    # ---- what the window changes -----------------------------------------------------
    def set_count(self, base, n):
        """The tooltip says how much is new; "needs attention" while there is."""
        self.tip = _("tray_new", title=base, n=n) if n else base
        self._signal(ITEM_PATH, "org.kde.StatusNotifierItem", "NewToolTip", None)
        if bool(n) != self.attention:
            self.attention = bool(n)
            self._signal(ITEM_PATH, "org.kde.StatusNotifierItem", "NewStatus",
                         GLib.Variant("(s)", (self._status(),)))

    def close(self):
        for i in self.ids:
            self.bus.unregister_object(i)
        Gio.bus_unown_name(self.owner)

    def _status(self):
        return "NeedsAttention" if self.attention else "Active"

    def _signal(self, path, iface, name, args):
        try:
            self.bus.emit_signal(None, path, iface, name, args)
        except GLib.Error as e:
            log.debug("tray: %s", e.message)

    # ---- org.kde.StatusNotifierItem ---------------------------------------------------
    def _item_prop(self, _conn, _sender, _path, _iface, prop):
        icon = "online.dmesg.fedtail"
        values = {
            "Category": GLib.Variant("s", "Communications"),
            "Id": GLib.Variant("s", "fedtail"),
            "Title": GLib.Variant("s", self.title),
            "Status": GLib.Variant("s", self._status()),
            "IconName": GLib.Variant("s", "" if self.pixmaps else icon),
            "IconPixmap": GLib.Variant("a(iiay)", self.pixmaps),
            "AttentionIconName": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", ("", [], self.tip, "")),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
        }
        return values.get(prop)

    def _item_call(self, _conn, _sender, _path, _iface, method, _params, inv):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(lambda: (self.activate(), GLib.SOURCE_REMOVE)[1])
        inv.return_value(None)

    # ---- com.canonical.dbusmenu --------------------------------------------------------
    def _menu_prop(self, _conn, _sender, _path, _iface, prop):
        return {"Version": GLib.Variant("u", 3), "Status": GLib.Variant("s", "normal"),
                "TextDirection": GLib.Variant("s", "ltr")}.get(prop)

    def _props(self, i):
        if i == 0:
            return {"children-display": GLib.Variant("s", "submenu")}
        entry = self.menu[i - 1]
        if entry is None:
            return {"type": GLib.Variant("s", "separator")}
        return {"label": GLib.Variant("s", entry[0]), "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True)}

    def _layout(self):
        kids = [GLib.Variant("(ia{sv}av)", (i, self._props(i), []))
                for i in range(1, len(self.menu) + 1)]
        return (0, self._props(0), kids)

    def _menu_call(self, _conn, _sender, _path, _iface, method, params, inv):
        if method == "GetLayout":
            inv.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout())))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0] or range(len(self.menu) + 1)
            inv.return_value(GLib.Variant("(a(ia{sv}))",
                                          ([(i, self._props(i)) for i in ids
                                            if 0 <= i <= len(self.menu)],)))
        elif method == "GetProperty":
            i, name = params.unpack()
            inv.return_value(GLib.Variant("(v)", (self._props(i).get(
                name, GLib.Variant("s", "")),)))
        elif method == "Event":
            i, event = params.unpack()[:2]
            if event == "clicked" and 1 <= i <= len(self.menu) and self.menu[i - 1]:
                fn = self.menu[i - 1][1]
                GLib.idle_add(lambda: (fn(), GLib.SOURCE_REMOVE)[1])
            inv.return_value(None)
        elif method == "EventGroup":
            for i, event, _data, _t in params.unpack()[0]:
                if event == "clicked" and 1 <= i <= len(self.menu) and self.menu[i - 1]:
                    fn = self.menu[i - 1][1]
                    GLib.idle_add(lambda f=fn: (f(), GLib.SOURCE_REMOVE)[1])
            inv.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            inv.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            inv.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            inv.return_value(None)


def make(win):
    """The tray for the window, or None: no session bus, no tray watcher on it."""
    app = win.get_application()
    bus = app.get_dbus_connection() if app is not None else None
    if bus is None:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return None
    try:
        bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                      "GetNameOwner", GLib.Variant("(s)", (WATCHER,)), None,
                      Gio.DBusCallFlags.NONE, 1000, None)
    except GLib.Error:
        log.info("tray: no StatusNotifierWatcher on the bus — no tray icon")
        return None
    menu = [(_("show"), win.show_from_tray), (_("write"), win.compose), None,
            (_("quit"), win.quit_app)]
    try:
        return Tray(bus, win.toggle_from_tray, menu, win.get_title() or "fedtail")
    except GLib.Error as e:
        log.warning("tray: %s", e.message)
        return None
