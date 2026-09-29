"""Local learning server; use only synthetic data when exposing it through a tunnel."""

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .domain import LabError, classify, normalize
from .store import Store

MAX_BODY = 64 * 1024


def make_server(host, port, db_path, key):
    if not isinstance(key, str) or len(key) < 24 or not key.isascii():
        raise ValueError("LAB_API_KEY must be at least 24 ASCII characters; run python3 -m redhawk init")
    store = Store(db_path)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            pass  # Do not print headers, webhook URLs, or request bodies.

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if status == 503:
                self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            supplied = self.headers.get("X-Lab-Key", "")
            if not hmac.compare_digest(supplied.encode(), key.encode()):
                self.reply(401, {"error": "Set the X-Lab-Key header to LAB_API_KEY"})
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                self.reply(200, {"status": "ok", "service": "redhawk-lab"})
            elif self.authorized():
                if path.startswith("/events/"):
                    self.reply(200, store.inspect(unquote(path.removeprefix("/events/"))))
                else:
                    self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            data = {}
            try:
                if path not in {"/normalize", "/classify", "/tickets"}:
                    raise LabError(404, "Not found")
                if self.headers.get_content_type() != "application/json":
                    raise LabError(415, "Send Content-Type: application/json")
                if self.headers.get("Transfer-Encoding"):
                    raise LabError(400, "Use Content-Length; chunked request bodies are not supported")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise LabError(400, "Invalid Content-Length") from None
                if not 0 < length <= MAX_BODY:
                    raise LabError(413, "Body must contain 1–65536 bytes")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise LabError(400, "Incomplete request body")
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise LabError(400, "Body must be valid JSON") from None
                if not isinstance(data, dict):
                    data = {}
                    raise LabError(422, "Body must be a JSON object")
                if path == "/tickets":
                    status, result = store.create_ticket(data)
                else:
                    result = normalize(data) if path == "/normalize" else classify(data)
                    status = 200
                    store.log(result["event_id"], path[1:], status, "ok")
                self.reply(status, result)
            except LabError as error:
                event_id = data.get("event_id")
                if isinstance(event_id, str) and len(event_id) <= 100:
                    store.log(event_id, path[1:], error.status, str(error))
                self.reply(error.status, {"error": str(error)})
            except (TimeoutError, ConnectionError):
                self.close_connection = True

    return ThreadingHTTPServer((host, port), Handler)
