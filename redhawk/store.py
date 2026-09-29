"""SQLite persistence makes retries observable and duplicate writes safe."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .domain import LabError, ticket_payload


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tickets (
                    event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS failures (event_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, event_id TEXT NOT NULL,
                    operation TEXT NOT NULL, status INTEGER NOT NULL, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS events_by_id ON events(event_id);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def record(db, event_id, operation, status, detail):
        db.execute(
            "INSERT INTO events(event_id, operation, status, detail) VALUES (?, ?, ?, ?)",
            (event_id, operation, status, detail),
        )

    def log(self, event_id, operation, status, detail):
        with self.connection() as db:
            self.record(db, event_id, operation, status, detail)

    def create_ticket(self, data):
        payload = ticket_payload(data)
        event_id = payload["event_id"]
        encoded = json.dumps(payload, sort_keys=True)
        with self.connection() as db:
            # Check, fault injection, and write share one transaction, including concurrent callers.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM tickets WHERE event_id = ?", (event_id,)).fetchone()
            if existing:
                if existing["payload"] != encoded:
                    raise LabError(409, "event_id already exists with different ticket fields")
                self.record(db, event_id, "tickets", 200, "duplicate: returned existing ticket")
                return 200, {"duplicate": True, "ticket": json.loads(existing["payload"])}
            if payload["fail_once"]:
                first = db.execute("INSERT OR IGNORE INTO failures VALUES (?)", (event_id,)).rowcount
                if first:
                    self.record(db, event_id, "tickets", 503, "intentional one-time failure before write")
                    # Return rather than raise: commit the fault marker so the next attempt succeeds.
                    return 503, {"error": "Simulated temporary outage. Retry the SAME event_id."}
            db.execute("INSERT INTO tickets(event_id, payload) VALUES (?, ?)", (event_id, encoded))
            self.record(db, event_id, "tickets", 201, "created")
            return 201, {"duplicate": False, "ticket": payload}

    def inspect(self, event_id):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM tickets WHERE event_id = ?", (event_id,)).fetchone()
            events = db.execute("SELECT * FROM events WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()
        return {"ticket": json.loads(row["payload"]) if row else None,
                "events": [dict(event) for event in events]}
