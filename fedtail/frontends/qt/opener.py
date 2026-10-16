"""Opening links and files with the desktop's own programs."""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ... import sysenv


def open_link(url):
    """A link in the browser, a file or folder in its program. The one-file build
    starts the opener itself, with the system's environment (see sysenv)."""
    if url and not sysenv.open_external(url):
        QDesktopServices.openUrl(QUrl(url))
