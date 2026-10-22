"""The GTK window's tray icon (gtk/tray.py) on a real session bus: a fake
StatusNotifierWatcher takes the registration; the item's tooltip, its menu (dbusmenu)
and its click are asked as the desktop's panel asks them. Needs dbus-run-session."""

import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

SCRIPT = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib
from fedtail import i18n
i18n.setup("ru")
from fedtail.frontends.gtk import tray

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
registered = []
WXML = """<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
</interface></node>"""
info = Gio.DBusNodeInfo.new_for_xml(WXML).interfaces[0]
def call(conn, sender, path, iface, method, params, inv):
    registered.append(params.unpack()[0])
    inv.return_value(None)
bus.register_object("/StatusNotifierWatcher", info, call, None, None)
Gio.bus_own_name_on_connection(bus, tray.WATCHER, Gio.BusNameOwnerFlags.NONE, None, None)
ctx = GLib.MainContext.default()
def pump(sec=0.3):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        ctx.iteration(False)
pump()
done = []
t = tray.Tray(bus, lambda: done.append("activate"),
              [("Показать", lambda: done.append("show")), None,
               ("Выйти", lambda: done.append("quit"))], "fedtail")
pump()
assert registered == [t.name], registered
def ask(path, iface, method, args, out):
    r = bus.call_sync(t.name, path, iface, method, args, GLib.VariantType.new(out),
                      Gio.DBusCallFlags.NONE, 2000, None)
    return r.unpack()
def prop(name):
    return ask(tray.ITEM_PATH, "org.freedesktop.DBus.Properties", "Get",
               GLib.Variant("(ss)", ("org.kde.StatusNotifierItem", name)), "(v)")[0]
res = {}
import threading
def client():
    res["tip"] = prop("ToolTip")[2]
    res["status"] = prop("Status")
    rev, layout = ask(tray.MENU_PATH, "com.canonical.dbusmenu", "GetLayout",
                      GLib.Variant("(iias)", (0, -1, [])), "(u(ia{sv}av))")
    res["labels"] = [k[1].get("label") for k in layout[2]]
    ask(tray.MENU_PATH, "com.canonical.dbusmenu", "Event",
        GLib.Variant("(isvu)", (3, "clicked", GLib.Variant("s", ""), 0)), "()")
    ask(tray.ITEM_PATH, "org.kde.StatusNotifierItem", "Activate",
        GLib.Variant("(ii)", (0, 0)), "()")
th = threading.Thread(target=client); th.start()
while th.is_alive():
    pump(0.05)
pump()
t.set_count("fedtail", 5)
res["status_after"] = None
th2 = threading.Thread(target=lambda: res.update(status_after=prop("Status"),
                                                 tip_after=prop("ToolTip")[2]))
th2.start()
while th2.is_alive():
    pump(0.05)
print(res, done)
assert res["tip"] == "fedtail"
assert res["status"] == "Active"
assert res["labels"] == ["Показать", None, "Выйти"], res["labels"]
assert done == ["quit", "activate"], done
assert res["status_after"] == "NeedsAttention"
assert "5" in res["tip_after"]
t.close()
print("OK")
'''


@unittest.skipUnless(shutil.which("dbus-run-session"), "no dbus-run-session")
class TrayTest(unittest.TestCase):
    def test_the_tray_on_a_session_bus(self):
        try:
            import gi
            gi.require_version("Gtk", "4.0")
        except (ImportError, ValueError):
            self.skipTest("no GTK 4")
        r = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", SCRIPT,
                            os.path.dirname(HERE)], capture_output=True, text=True,
                           timeout=60)
        self.assertIn("OK", r.stdout, r.stdout + r.stderr[-2000:])
