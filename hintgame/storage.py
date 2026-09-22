"""Durable storage with revision checks; retries never overwrite another vote."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import random
import sqlite3
import time
import urllib.error
import urllib.request

from .content import initial_state


class StorageError(RuntimeError):
    pass


class Repository:
    def read(self):
        raise NotImplementedError

    def compare_swap(self, revision, state):
        raise NotImplementedError

    def mutate(self, action):
        for attempt in range(40):
            revision, state = self.read()
            working = deepcopy(state)
            result = action(working)
            if working == state:
                return result
            if self.compare_swap(revision, working):
                return result
            time.sleep(random.uniform(0.005, min(0.2, 0.015 * (attempt + 1))))
        raise StorageError("The game is busy saving other answers. Please try again; existing answers are safe.")

    def snapshot(self):
        return self.read()[1]


class SQLiteRepository(Repository):
    def __init__(self, path, event_id="main", factory=initial_state):
        self.path, self.event_id = str(path), event_id
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL)")
            conn.execute("INSERT OR IGNORE INTO events VALUES (?, 0, ?)", (event_id, json.dumps(factory())))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def read(self):
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT revision, document FROM events WHERE id=?", (self.event_id,)).fetchone()
            if row is None:
                raise StorageError("The event could not be found.")
            return row[0], json.loads(row[1])
        except (sqlite3.Error, ValueError) as exc:
            raise StorageError("Local storage could not be read. Please retry or check the host’s storage setup.") from exc

    def compare_swap(self, revision, state):
        try:
            with self.connect() as conn:
                cur = conn.execute("UPDATE events SET document=?, revision=revision+1 WHERE id=? AND revision=?", (json.dumps(state), self.event_id, revision))
                return cur.rowcount == 1
        except sqlite3.Error as exc:
            raise StorageError("The answer could not be saved. Please retry.") from exc


class SupabaseRepository(Repository):
    def __init__(self, url, service_key, event_id="main", factory=initial_state):
        if not url.startswith("https://") or not service_key:
            raise StorageError("Set a valid HTTPS SUPABASE_URL and SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) in Streamlit secrets.")
        self.url, self.key, self.event_id = url.rstrip("/"), service_key, event_id
        self.rpc("hint_initialize", {"p_id": event_id, "p_document": factory()})

    def rpc(self, name, payload):
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        # Current sb_secret_ keys are not JWTs; only legacy keys use Bearer auth.
        if not self.key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}", data=json.dumps(payload).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # Never surface response bodies, service keys, or connection credentials.
            raise StorageError("Shared storage is unavailable. Your previous answers are safe. Retry, or ask the host to check Supabase configuration.") from exc

    def read(self):
        row = self.rpc("hint_read", {"p_id": self.event_id})
        if not row:
            raise StorageError("This event has not been initialized.")
        return row["revision"], row["document"]

    def compare_swap(self, revision, state):
        return bool(self.rpc("hint_compare_swap", {"p_id": self.event_id, "p_revision": revision, "p_document": state}))
