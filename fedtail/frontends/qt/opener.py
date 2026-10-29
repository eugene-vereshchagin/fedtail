"""Opening links and files with the desktop's own programs."""

import logging
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ... import sysenv
from ..richtext import openable

log = logging.getLogger(__name__)


def open_link(url):
    """A link in the browser (or mail, XMPP… client). Only the kinds a post may hold:
    a file: or smb: address from someone else's post or server is refused — on Windows
    opening file://host/share alone sends the login's NTLM hash to that host. The
    one-file build starts the opener itself, with the system's environment (see
    sysenv). True if handed over."""
    if not url:
        return False
    if not openable(url):
        log.warning("link not opened: %s: is not a web address",
                    urlsplit(str(url)).scheme or "no scheme")
        return False
    if sysenv.open_external(url):
        return True
    if QDesktopServices.openUrl(QUrl(url)):
        return True
    # Qt had no way (a platform without its services): the desktop's opener, by hand
    log.warning("link not opened by Qt: trying the desktop's opener")
    return sysenv.open_external(url, always=True)


def open_path(path):
    """A folder or file of our own (the config, the logs, the data) in its program."""
    url = QUrl.fromLocalFile(str(path))
    if not sysenv.open_external(url.toString()):
        QDesktopServices.openUrl(url)
