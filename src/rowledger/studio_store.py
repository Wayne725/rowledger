import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .engine import SCHEMA_VERSION, apply_review, canonical_json, reconcile
from .export import export_bundle
from .readers import MAX_BYTES
from .rules import Rules


class ConflictError(ValueError):
    pass


def _text(value, label, limit):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= limit
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", value)):
        raise ValueError(f"{label} must contain 1–{limit} characters.")
    return value.strip()


def _filename(name):
    name = _text(name, "Filename", 200)
    if (any(character in name for character in "/\\:") or re.search(r"[\x00-\x1f]", name)
            or Path(name).suffix.lower() not in (".csv", ".xlsx")):
        raise ValueError("Use a CSV/XLSX filename without directory components.")
    return name


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StudioStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / "studio.sqlite3"
        if self.database.is_symlink():
            raise ValueError("The workspace database cannot be a symbolic link.")
        if not self.database.exists():
            descriptor = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported Studio database version.")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, snapshot TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL, revision INTEGER NOT NULL,
                    state TEXT NOT NULL, base TEXT NOT NULL, decisions TEXT NOT NULL,
                    orders_name TEXT NOT NULL, orders BLOB NOT NULL,
                    payments_name TEXT NOT NULL, payments BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    batch_id TEXT NOT NULL REFERENCES batches(id), revision INTEGER NOT NULL,
                    at TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL,
                    action TEXT NOT NULL, detail TEXT NOT NULL,
                    PRIMARY KEY (batch_id, revision)
                );
                PRAGMA user_version = 1;
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _row(self, connection, batch_id):
        row = connection.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if row is None:
            raise KeyError("Batch not found.")
        return row

    def _result(self, row):
        base = json.loads(row["base"])
        return apply_review(base, {"schema_version": SCHEMA_VERSION, "run_id": row["snapshot"],
                                   "decisions": json.loads(row["decisions"])})

    def _metadata(self, row, result):
        return {key: row[key] for key in ("id", "title", "created", "updated", "revision", "state")} | {
            "snapshot": row["snapshot"], "summary": result["summary"], "rules": result["rules"],
            "sources": result["sources"], "decisions": result["decisions"]}

    def create(self, title, orders_name, orders, payments_name, payments, rules=None):
        title = _text(title, "Batch name", 100)
        orders_name, payments_name = _filename(orders_name), _filename(payments_name)
        if any(not isinstance(value, bytes) or not 0 < len(value) <= MAX_BYTES for value in (orders, payments)):
            raise ValueError("Each input must contain 1 byte to 10 MiB.")
        rules = Rules.from_dict({} if rules is None else rules)
        with tempfile.TemporaryDirectory(prefix="rowledger-import-") as directory:
            paths = {}
            for side, name, content in (("orders", orders_name, orders), ("payments", payments_name, payments)):
                folder = Path(directory) / side
                folder.mkdir()
                paths[side] = folder / name
                paths[side].write_bytes(content)
            result = reconcile(paths["orders"], paths["payments"], rules)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM batches WHERE snapshot = ?", (result["run_id"],)).fetchone()
            if existing:
                return {"batch": self._metadata(existing, self._result(existing)), "reused": True}
            batch_id, now = uuid.uuid4().hex, _now()
            connection.execute("INSERT INTO batches VALUES (?, ?, ?, ?, ?, 0, 'open', ?, '[]', ?, ?, ?, ?)",
                               (batch_id, result["run_id"], title, now, now, canonical_json(result),
                                orders_name, orders, payments_name, payments))
            self._event(connection, batch_id, 0, "Local import", "Created from immutable source files.",
                        "created", {"snapshot": result["run_id"], "sources": result["sources"]})
            return {"batch": self._metadata(self._row(connection, batch_id), result), "reused": False}

    def _event(self, connection, batch_id, revision, actor, note, action, detail):
        connection.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (batch_id, revision, _now(), actor, note, action, canonical_json(detail)))

    def list_batches(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT id, title, created, updated, revision, state, snapshot, base, decisions "
                                      "FROM batches ORDER BY updated DESC, id DESC")
            batches = []
            for row in rows:
                base, decisions = json.loads(row["base"]), json.loads(row["decisions"])
                batches.append({key: row[key] for key in ("id", "title", "created", "updated", "revision", "state", "snapshot")} | {
                    "summary": {"rows": base["summary"]["rows"],
                                "matched_pairs": base["summary"]["matched_pairs"] + len(decisions),
                                "needs_attention": base["summary"]["needs_attention"] - 2 * len(decisions)}})
            return batches

    def get(self, batch_id, *, page=1, query="", status="", side=""):
        if type(page) is not int or page < 1 or not isinstance(query, str) or len(query) > 200:
            raise ValueError("Invalid page or search query.")
        if side not in ("", "orders", "payments"):
            raise ValueError("Invalid source side.")
        statuses = {"", "attention", "matched", "manual_matched", "unmatched", "invalid", "duplicate_key",
                    "blocked_invalid", "currency_mismatch", "amount_mismatch"}
        if status not in statuses:
            raise ValueError("Invalid row status.")
        with self._connect() as connection:
            connection.execute("BEGIN")
            row = self._row(connection, batch_id)
            result = self._result(row)
            needle = query.casefold()
            matches = [item for item in result["rows"]
                       if (not side or item["side"] == side)
                       and (not status or (status == "attention" and item["status"] not in ("matched", "manual_matched"))
                            or status == item["status"])
                       and (not needle or needle in canonical_json(item).casefold())]
            events = connection.execute("SELECT * FROM events WHERE batch_id = ? ORDER BY revision DESC LIMIT 100",
                                        (batch_id,)).fetchall()
            return self._metadata(row, result) | {"rows": matches[(page - 1) * 50:page * 50],
                "page": page, "total": len(matches), "pages": max(1, (len(matches) + 49) // 50),
                "events": [{key: event[key] for key in ("revision", "at", "actor", "note", "action")}
                           for event in events]}

    def _check_revision(self, row, revision):
        if type(revision) is not int or revision < 0:
            raise ValueError("A nonnegative revision is required.")
        if row["revision"] != revision:
            raise ConflictError("This batch changed. Reload it before saving.")

    def save_review(self, batch_id, revision, document, actor, note):
        actor, note = _text(actor, "Reviewer", 100), _text(note, "Change reason", 1000)
        if len(canonical_json(document).encode()) > 1024 * 1024:
            raise ValueError("Review exceeds 1 MiB.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, batch_id)
            self._check_revision(row, revision)
            if row["state"] != "open":
                raise ConflictError("Reopen the batch before changing decisions.")
            result = apply_review(json.loads(row["base"]), document)
            old = json.loads(row["decisions"])
            if old == result["decisions"]:
                raise ValueError("The review contains no changes.")
            connection.execute("UPDATE batches SET decisions = ?, revision = revision + 1, updated = ? WHERE id = ?",
                               (canonical_json(result["decisions"]), _now(), batch_id))
            self._event(connection, batch_id, revision + 1, actor, note, "review_saved",
                        {"snapshot": row["snapshot"], "before": old, "after": result["decisions"]})
            return self._metadata(self._row(connection, batch_id), result)

    def set_state(self, batch_id, revision, state, actor, note, acknowledge_attention=False):
        actor, note = _text(actor, "Reviewer", 100), _text(note, "Change reason", 1000)
        if state not in ("open", "closed") or type(acknowledge_attention) is not bool:
            raise ValueError("Invalid batch state or acknowledgement.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, batch_id)
            self._check_revision(row, revision)
            if row["state"] == state:
                raise ValueError("The batch is already in this state.")
            result = self._result(row)
            if state == "closed" and result["summary"]["needs_attention"] and not acknowledge_attention:
                raise ValueError("Explicitly acknowledge unresolved rows before closing this batch.")
            connection.execute("UPDATE batches SET state = ?, revision = revision + 1, updated = ? WHERE id = ?",
                               (state, _now(), batch_id))
            self._event(connection, batch_id, revision + 1, actor, note,
                        "closed" if state == "closed" else "reopened",
                        {"snapshot": row["snapshot"], "summary": result["summary"],
                         "unresolved_rows": [item["row_id"] for item in result["rows"]
                                             if item["status"] not in ("matched", "manual_matched")]})
            return self._metadata(self._row(connection, batch_id), result)

    def export(self, batch_id, revision):
        with self._connect() as connection:
            connection.execute("BEGIN")
            row = self._row(connection, batch_id)
            self._check_revision(row, revision)
            result = self._result(row)
            events = connection.execute("SELECT * FROM events WHERE batch_id = ? ORDER BY revision", (batch_id,)).fetchall()
            metadata = self._metadata(row, result) | {
                "events": [{key: event[key] for key in ("revision", "at", "actor", "note", "action")}
                           | {"detail": json.loads(event["detail"])} for event in events]}
            inputs = {side: (row[f"{side}_name"], bytes(row[side])) for side in ("orders", "payments")}
        with tempfile.TemporaryDirectory(prefix="rowledger-export-") as directory:
            output = export_bundle(result, Path(directory) / "bundle")
            (output / "workspace.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            for side, (name, content) in inputs.items():
                target = output / "inputs" / side
                target.mkdir(parents=True)
                (target / name).write_bytes(content)
            manifest = {"run_id": result["run_id"], "batch_id": batch_id, "revision": revision,
                        "state": row["state"], "sha256": {path.relative_to(output).as_posix():
                            hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}}
            (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(output.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(output).as_posix())
            return stream.getvalue()
