"""Transactional SQLite checkpoints. One operating-system file lock owns the worker."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db(transaction=False) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript('''
                CREATE TABLE IF NOT EXISTS objects(kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL,
                    request_hash TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL);
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def db(self, transaction=True):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if transaction:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def objects(self, kind):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind=? ORDER BY rowid", (kind,))]

    def get(self, kind, ident):
        with self.db() as db:
            row = db.execute("SELECT data FROM objects WHERE kind=? AND id=?", (kind, ident)).fetchone()
            if not row:
                raise KeyError(ident)
            return json.loads(row[0])

    def put(self, kind, data, ident=None):
        data = {**data, "id": ident or uuid.uuid4().hex}
        with self.db() as db:
            db.execute("INSERT INTO objects VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, data["id"], json.dumps(data)))
        return data

    def delete(self, kind, ident):
        with self.db() as db:
            db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, ident))

    def create_run(self, data, key, request_hash):
        with self.db() as db:
            old = db.execute("SELECT request_hash,data FROM runs WHERE key=?", (key,)).fetchone()
            if old:
                if old[0] != request_hash:
                    raise Conflict("Idempotency key was already used for a different request")
                return json.loads(old[1])
            data = {**data, "id": uuid.uuid4().hex, "created_at": time.time(), "updated_at": time.time(),
                    "state": "queued", "stage": "Queued", "progress": 0, "revision": 1, "attempts": 0,
                    "next_retry": 0, "error": None, "artifact": None, "video_id": None, "metadata": None}
            db.execute("INSERT INTO runs VALUES(?,?,?,?)", (data["id"], key, request_hash, json.dumps(data)))
            return data

    def runs(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM runs ORDER BY rowid DESC")]

    def run(self, ident):
        with self.db() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (ident,)).fetchone()
            if not row:
                raise KeyError(ident)
            return json.loads(row[0])

    def change(self, ident, changes, states=None, revision=None):
        with self.db() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (ident,)).fetchone()
            if not row:
                raise KeyError(ident)
            data = json.loads(row[0])
            if (states is not None and data["state"] not in states) or (revision is not None and data["revision"] != revision):
                raise Conflict("Run changed; refresh and review the current revision")
            data.update(changes)
            data["updated_at"] = time.time()
            db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(data), ident))
            return data

    def save_state(self, state, data):
        with self.db() as db:
            expired = [json.loads(row[0]) for row in db.execute("SELECT data FROM oauth_states WHERE expires<?", (time.time(),))]
            db.execute("DELETE FROM oauth_states WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO oauth_states VALUES(?,?,?)", (state, json.dumps(data), time.time() + 600))
        return expired

    def consume_state(self, state):
        with self.db() as db:
            row = db.execute("SELECT data,expires FROM oauth_states WHERE state=?", (state,)).fetchone()
            db.execute("DELETE FROM oauth_states WHERE state=?", (state,))
        if not row or row[1] < time.time():
            raise ValueError("OAuth link expired or already used. Connect the channel again.")
        return json.loads(row[0])
