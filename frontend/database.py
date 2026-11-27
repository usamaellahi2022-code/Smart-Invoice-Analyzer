import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from frontend.utils import flatten_invoice


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "invoice_history.sqlite3"


def resolve_database_path(db_path=None) -> Path:
    """Resolve the SQLite database path."""

    if db_path is not None:
        path = Path(db_path)
    else:
        configured_path = os.getenv("SMART_INVOICE_DB_PATH", "").strip()

        path = (
            Path(configured_path)
            if configured_path
            else DEFAULT_DATABASE_PATH
        )

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def initialize_database(db_path=None) -> Path:
    """Create the database and its schema when necessary."""

    path = resolve_database_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processed_at TEXT NOT NULL,
                source_file TEXT NOT NULL DEFAULT '',
                invoice_number TEXT,
                invoice_date TEXT,
                due_date TEXT,
                supplier TEXT,
                subtotal REAL,
                tax REAL,
                total REAL,
                currency TEXT,
                validation_status TEXT NOT NULL DEFAULT 'Needs review',
                ocr_confidence REAL,
                record_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_invoices_processed_at
            ON invoices(processed_at DESC);

            CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number
            ON invoices(invoice_number);
            """
        )

        connection.execute("PRAGMA user_version = 1")

    return path


def save_invoice_result(payload: dict, processed_at: str = "", db_path=None) -> dict:
    """Persist an invoice API response and its flattened history record."""

    if not isinstance(payload, dict):
        raise TypeError("Invoice payload must be a dictionary.")

    timestamp = processed_at or datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    record = flatten_invoice(payload, timestamp)

    path = initialize_database(db_path)

    record_json = json.dumps(record, ensure_ascii=False, default=str)
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    columns = (
        "processed_at",
        "source_file",
        "invoice_number",
        "invoice_date",
        "due_date",
        "supplier",
        "subtotal",
        "tax",
        "total",
        "currency",
        "validation_status",
        "ocr_confidence",
        "record_json",
        "payload_json",
    )

    values = (
        timestamp,
        str(record.get("source_file") or ""),
        record.get("invoice_number"),
        record.get("invoice_date"),
        record.get("due_date"),
        record.get("supplier"),
        record.get("subtotal"),
        record.get("tax"),
        record.get("total"),
        record.get("currency"),
        record.get("validation_status", "Needs review"),
        record.get("ocr_confidence"),
        record_json,
        payload_json,
    )

    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(columns)

    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")

        cursor = connection.execute(
            f"""
            INSERT INTO invoices ({column_names})
            VALUES ({placeholders})
            """,
            values,
        )

        record["id"] = cursor.lastrowid

    return record


def get_invoice_history(limit=None, db_path=None) -> list[dict]:
    """Return saved invoice records, newest first, including database IDs."""

    path = initialize_database(db_path)

    query = """
        SELECT id, record_json
        FROM invoices
        ORDER BY id DESC
    """

    parameters = ()

    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("History limit must be a positive integer.")

        query += " LIMIT ?"
        parameters = (limit,)

    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        rows = connection.execute(query, parameters).fetchall()

    history = []

    for database_id, record_json in rows:
        record = json.loads(record_json)
        record["id"] = database_id
        history.append(record)

    return history

def get_invoice_payloads(db_path=None) -> list[dict]:
    """Return original saved API responses, newest first."""

    path = initialize_database(db_path)

    with sqlite3.connect(path, timeout=10) as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM invoices
            ORDER BY id DESC
            """
        ).fetchall()

    return [json.loads(row[0]) for row in rows]


def clear_invoice_history(db_path=None) -> int:
    """Delete all saved invoice history records."""

    path = initialize_database(db_path)

    with sqlite3.connect(path, timeout=10) as connection:
        cursor = connection.execute("DELETE FROM invoices")
        deleted_count = cursor.rowcount

    return deleted_count


def get_invoice_count(db_path=None) -> int:
    """Return the number of saved invoice records."""

    path = initialize_database(db_path)

    with sqlite3.connect(path, timeout=10) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM invoices"
        ).fetchone()

    return int(row[0])
