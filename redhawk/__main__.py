"""Run from the repository root: python3 -m redhawk --help."""

import argparse
import json
import os
import secrets
import signal
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .cases import CASES, assess
from .server import make_server


def load_env():
    path = Path(".env")
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # Never forward credentials or webhook payloads to a different URL.


def request(url, payload=None, key=None):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Use an HTTP(S) URL without embedded credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use HTTPS for remote endpoints")
    headers = {"Accept": "application/json"}
    if key:
        headers["X-Lab-Key"] = key
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    req = Request(url, data=body, headers=headers)
    try:
        response = build_opener(NoRedirect).open(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(1024 * 1024).decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except ValueError:
            value = {"response": raw[:500]}
        return response.code, value


def api(args, path, payload=None):
    key = os.environ.get("LAB_API_KEY")
    if not key:
        raise ValueError("Run python3 -m redhawk init first, or set LAB_API_KEY")
    return request(args.base_url.rstrip("/") + path, payload, key)


def reference(args, payload):
    """Reference solution uses the same HTTP API as the three platforms."""
    for path in ("/normalize", "/classify"):
        status, payload = api(args, path, payload)
        if status != 200:
            return status
    payload.update(source="reference", queue="review" if payload["needs_review"] else "standard")
    for attempt in range(3):
        status, _ = api(args, "/tickets", payload)
        if status not in (429, 503):
            return status
        time.sleep(0.1 * 2**attempt)
    return status


def check(args):
    deadline = time.monotonic() + args.wait
    while True:
        status, snapshot = api(args, "/events/" + quote(args.event_id, safe=""))
        if status != 200:
            raise ValueError(f"Lab API returned HTTP {status}; check the URL and key")
        failures = assess(snapshot, args.case, args.platform)
        if not failures:
            print(f"PASS {args.case}: {args.event_id}")
            return 0
        if time.monotonic() >= deadline:
            print(f"NOT PASSED {args.case}: {args.event_id}")
            for failure in failures:
                print(f"  - {failure}")
            print("Inspect: python3 -m redhawk inspect " + args.event_id)
            return 1
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Learn n8n, Zapier, and Make against one practice API")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a private .env with a random API key; never overwrite")
    serve = commands.add_parser("serve", help="Start the lab API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--db", default=".lab/lab.sqlite3")
    sample = commands.add_parser("sample", help="Print a synthetic webhook payload")
    sample.add_argument("case", choices=CASES)
    sample.add_argument("--event-id", default="sample-001")
    for name in ("demo", "send", "check", "inspect"):
        cmd = commands.add_parser(name, help={"demo": "Run the reference solution (no platforms needed)", "send": "Send a case to a platform webhook", "check": "Verify the recorded outcome", "inspect": "Show the ticket and event trace"}[name])
        cmd.add_argument("--base-url", default=os.environ.get("LAB_BASE_URL", "http://127.0.0.1:8787"))
        if name == "inspect":
            cmd.add_argument("event_id")
            continue
        if name != "demo":
            cmd.add_argument("case", choices=CASES)
            cmd.add_argument("--platform", required=True, choices=["n8n", "zapier", "make", "reference"] if name == "check" else ["n8n", "zapier", "make"])
            cmd.add_argument("--event-id", required=name == "check")
        if name == "check":
            cmd.add_argument("--wait", type=float, default=0, help="Seconds to wait for asynchronous processing")
    args = parser.parse_args()
    try:
        if args.command == "init":
            content = ("# Generated locally; do not commit or share. No shell expansion.\n"
                       f"LAB_API_KEY={secrets.token_urlsafe(32)}\n"
                       "LAB_BASE_URL=http://127.0.0.1:8787\n"
                       "N8N_WEBHOOK_URL=\nZAPIER_WEBHOOK_URL=\nMAKE_WEBHOOK_URL=\n"
                       "# Optional inbound n8n header-auth credential (different from LAB_API_KEY).\n"
                       "N8N_WEBHOOK_KEY=\n")
            fd = os.open(".env", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(content)
            print("Created .env. API key stays in that file. Next: python3 -m redhawk serve")
        elif args.command == "serve":
            server = make_server(args.host, args.port, args.db, os.environ.get("LAB_API_KEY", ""))
            print(f"Lab API: http://{args.host}:{server.server_port} (Ctrl-C to stop)", flush=True)
            # Docker sends SIGTERM to PID 1. Handle it explicitly instead of waiting for SIGKILL.
            def stop_server(_signum, _frame):
                raise KeyboardInterrupt

            previous_handler = signal.signal(signal.SIGTERM, stop_server)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
                signal.signal(signal.SIGTERM, previous_handler)
        elif args.command == "sample":
            print(json.dumps({"event_id": args.event_id, **CASES[args.case]["input"]}, indent=2))
        elif args.command == "inspect":
            status, result = api(args, "/events/" + quote(args.event_id, safe=""))
            print(json.dumps(result, indent=2))
            return 0 if status == 200 else 1
        elif args.command == "demo":
            for case in CASES:
                args.case, args.platform = case, "reference"
                args.event_id, args.wait = f"reference-{case}-{uuid.uuid4().hex[:12]}", 0
                payload = {"event_id": args.event_id, **CASES[case]["input"]}
                for _ in range(2 if case == "duplicate" else 1):
                    reference(args, payload)
                if check(args):
                    return 1
            print("All reference cases passed. Now reproduce them in your platform.")
        elif args.command == "send":
            url = os.environ.get(f"{args.platform.upper()}_WEBHOOK_URL")
            if not url:
                raise ValueError(f"Set {args.platform.upper()}_WEBHOOK_URL in .env")
            event_id = args.event_id or f"{args.platform}-{args.case}-{uuid.uuid4().hex[:12]}"
            payload = {"event_id": event_id, **CASES[args.case]["input"]}
            # Only an explicitly configured n8n ingress key goes to the webhook, never the API key.
            key = os.environ.get("N8N_WEBHOOK_KEY") if args.platform == "n8n" else None
            for _ in range(2 if args.case == "duplicate" else 1):
                status, _ = request(url, payload, key)
                print(f"Webhook HTTP {status}; event_id={event_id}")
                if not 200 <= status < 300:
                    print("Delivery was not acknowledged. Check the webhook URL and listener.")
                    return 1
            print("Acknowledged does not mean finished. Verify with:")
            print(f"python3 -m redhawk check {args.case} --platform {args.platform} --event-id {event_id} --wait 30")
        elif args.command == "check":
            if not 0 <= args.wait <= 600:
                raise ValueError("--wait must be between 0 and 600 seconds")
            return check(args)
    except FileExistsError:
        print(".env already exists; kept unchanged.", file=sys.stderr)
        return 1
    except (ValueError, OSError, URLError) as error:
        # Network exception strings can contain secret webhook URLs; do not echo them.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__ + ": check local files, server, and network connection"
        print(message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
