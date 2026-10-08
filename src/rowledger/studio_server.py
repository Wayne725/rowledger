import base64
import binascii
import csv
import hmac
import json
import secrets
import sqlite3
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from .readers import MAX_BYTES
from .studio_store import ConflictError, StudioStore

MAX_REQUEST = 2 * 4 * ((MAX_BYTES + 2) // 3) + 2 * 1024 * 1024


def _object(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Unexpected request fields.")
    return value


def _file(value):
    _object(value, ("name", "content"))
    if not isinstance(value["content"], str):
        raise ValueError("File content must be base64 text.")
    try:
        content = base64.b64decode(value["content"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid file encoding.") from error
    if not 0 < len(content) <= MAX_BYTES:
        raise ValueError("Each input must contain 1 byte to 10 MiB.")
    return value["name"], content


def make_server(workspace, port=8765):
    store, token = StudioStore(workspace), secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *args):
            pass

        def _send(self, status, content, content_type="application/json; charset=utf-8", filename=None):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.send_header("Connection", "close")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.close_connection = True
            self.wfile.write(content)

        def _trusted(self, api=False):
            authority = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != authority:
                self._send(403, {"error": "Use the printed 127.0.0.1 address."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{authority}":
                self._send(403, {"error": "Cross-origin requests are not allowed."})
                return False
            supplied_token = self.headers.get("X-RowLedger-Token", "")
            if api and (not supplied_token.isascii() or not hmac.compare_digest(supplied_token, token)):
                self._send(403, {"error": "Reload Studio to obtain a current local session."})
                return False
            return True

        def _body(self):
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Use a JSON request with Content-Length.")
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not 0 < int(length) <= MAX_REQUEST:
                raise ValueError("Request exceeds the upload limit or has no valid length.")
            payload = self.rfile.read(int(length))
            if len(payload) != int(length):
                raise ValueError("Incomplete request body.")
            return json.loads(payload)

        def _handle(self, operation):
            try:
                operation()
            except ConflictError as error:
                self._send(409, {"error": str(error)})
            except KeyError:
                self._send(404, {"error": "Batch not found."})
            except (ValueError, UnicodeError, csv.Error, zipfile.BadZipFile, ParseError, DefusedXmlException) as error:
                self._send(400, {"error": str(error)})
            except (OSError, sqlite3.Error):
                self._send(500, {"error": "Workspace storage failed. Check local disk access and retry."})

        def do_GET(self):
            self._handle(self._get)

        def _get(self):
            url = urlsplit(self.path)
            api = url.path.startswith("/api/")
            if not self._trusted(api):
                return
            assets = {"/": ("studio.html", "text/html; charset=utf-8"),
                      "/studio.css": ("studio.css", "text/css; charset=utf-8"),
                      "/studio.js": ("studio.js", "text/javascript; charset=utf-8")}
            if url.path in assets:
                name, content_type = assets[url.path]
                content = files("rowledger").joinpath("studio_assets", name).read_text().replace("__SESSION_TOKEN__", token)
                self._send(200, content.encode(), content_type)
            elif url.path == "/api/batches":
                self._send(200, {"batches": store.list_batches()})
            else:
                parts = url.path.strip("/").split("/")
                if len(parts) not in (3, 4) or parts[:2] != ["api", "batches"]:
                    self._send(404, {"error": "Not found."})
                    return
                query = parse_qs(url.query, keep_blank_values=True)
                value = lambda key, default="": query.get(key, [default])[0]
                if len(parts) == 4 and parts[3] == "export":
                    data = store.export(parts[2], int(value("revision", "-1")))
                    self._send(200, data, "application/zip", f"rowledger-{parts[2]}.zip")
                elif len(parts) == 3:
                    self._send(200, store.get(parts[2], page=int(value("page", "1")),
                                             query=value("q"), status=value("status"), side=value("side")))
                else:
                    self._send(404, {"error": "Not found."})

        def do_POST(self):
            self._handle(self._post)

        def _post(self):
            if not self._trusted(True):
                return
            path = urlsplit(self.path).path
            payload = self._body()
            if path == "/api/demo":
                _object(payload, ())
                examples = files("rowledger").joinpath("examples")
                result = store.create("合成範例 / 訂單與收款", "orders.csv", examples.joinpath("orders.csv").read_bytes(),
                                      "payments.csv", examples.joinpath("payments.csv").read_bytes())
                self._send(200 if result["reused"] else 201, result)
                return
            if path == "/api/batches":
                _object(payload, ("title", "orders", "payments", "rules"))
                orders_name, orders = _file(payload["orders"])
                payments_name, payments = _file(payload["payments"])
                result = store.create(payload["title"], orders_name, orders, payments_name, payments, payload["rules"])
                self._send(200 if result["reused"] else 201, result)
                return
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "batches"]:
                self._send(404, {"error": "Not found."})
            elif parts[3] == "review":
                _object(payload, ("revision", "document", "actor", "note"))
                self._send(200, store.save_review(parts[2], **payload))
            elif parts[3] == "state":
                _object(payload, ("revision", "state", "actor", "note", "acknowledge_attention"))
                self._send(200, store.set_state(parts[2], **payload))
            else:
                self._send(404, {"error": "Not found."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.studio_store, server.session_token = store, token
    return server


def serve(workspace, port):
    server = make_server(workspace, port)
    print(f"RowLedger Studio: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Private workspace: {server.studio_store.directory}; Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
