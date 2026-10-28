"""A small WebDAV server over a folder, for the tests of sync's WebDAV backend: what
Nextcloud, Apache's mod_dav and rclone answer to PROPFIND, GET, PUT, DELETE and MKCOL —
a base path in front (as /remote.php/dav/files/<user>/), hrefs percent-encoded, Basic
auth, 405 for a folder that is there, 409 for one whose parent isn't."""

import base64
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

BASE = "/remote.php/dav/files/me/"


class Dav:
    def __init__(self, root, user="me", password="secret"):
        self.root = Path(root)
        self.login = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.calls = []
        dav = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _path(self):
                path = unquote(urlsplit(self.path).path)
                if not path.startswith(BASE.rstrip("/")):
                    return None
                return dav.root / path[len(BASE):].strip("/")

            def _answer(self, code, body=b"", kind="text/plain"):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _go(self):
                dav.calls.append((self.command, self.path))
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                if self.headers.get("Authorization") != dav.login:
                    return self._answer(401)
                p = self._path()
                if p is None:
                    return self._answer(404)
                return getattr(self, "_" + self.command.lower())(p, body)

            def _propfind(self, p, _body):
                if not p.exists():
                    return self._answer(404)
                items = [p] + (sorted(p.iterdir()) if p.is_dir() and
                               self.headers.get("Depth") != "0" else [])
                parts = []
                for it in items:
                    rel = it.relative_to(dav.root).as_posix()
                    href = quote(BASE + ("" if rel == "." else rel)) + ("/" if it.is_dir()
                                                                       and rel != "." else "")
                    kind = "<d:collection/>" if it.is_dir() else ""
                    parts.append(f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>"
                                 f"<d:resourcetype>{kind}</d:resourcetype></d:prop>"
                                 f"<d:status>HTTP/1.1 200 OK</d:status></d:propstat>"
                                 f"</d:response>")
                xml = ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                       + "".join(parts) + "</d:multistatus>")
                return self._answer(207, xml.encode(), "application/xml; charset=utf-8")

            def _get(self, p, _body):
                if not p.is_file():
                    return self._answer(404)
                return self._answer(200, p.read_bytes(), "application/octet-stream")

            def _put(self, p, body):
                if not p.parent.is_dir():
                    return self._answer(409)
                p.write_bytes(body)
                return self._answer(201)

            def _delete(self, p, _body):
                if not p.exists():
                    return self._answer(404)
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                return self._answer(204)

            def _mkcol(self, p, _body):
                if p.exists():
                    return self._answer(405)
                if not p.parent.is_dir():
                    return self._answer(409)
                p.mkdir()
                return self._answer(201)

            do_PROPFIND = do_GET = do_PUT = do_DELETE = do_MKCOL = _go  # noqa: N815

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}{BASE}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
