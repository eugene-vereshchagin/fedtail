"""PyGObject imports in one place: GTK 4 always, libadwaita when it's there and wanted
(ui.adwaita = auto | on | off). Everything else in the package imports from here."""

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango
except (ImportError, ValueError) as e:  # no PyGObject, or no GTK 4 typelib
    raise ImportError(f"GTK 4 for Python not found: {e}") from e

MIN_GTK = (4, 10)

Adw = None


def gtk_version():
    return (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())


def load_adwaita(mode):
    """libadwaita if ui.adwaita allows and it is installed; None otherwise. "on" without
    it is an error the caller reports; "auto" just goes without."""
    global Adw
    if mode == "off":
        return None
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw as _adw
    except (ImportError, ValueError):
        if mode == "on":
            raise
        return None
    Adw = _adw
    return Adw


__all__ = ["Adw", "Gdk", "Gio", "GLib", "GObject", "Gtk", "Pango", "MIN_GTK", "gtk_version",
           "load_adwaita"]
