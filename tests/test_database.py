import json
import sqlite3

import pytest

from frontend.database import (
    clear_invoice_history,
    get_invoice_count,
    get_invoice_history,
    get_invoice_payloads,
    initialize_database,
    save_invoice_result,
)


def sample_payload(invoice_number="INV-100", total=1150.0):
    return {
        "success": True,
        "source_file": "sample.pdf",
        "ocr": {
            "confidence": 91.5,
            "word_count": 40,
            "page_count": 1,
            "text": "Sample invoice text",
        },
        "extraction": {
            "fields": {
                "invoice_number": {
                    "value": invoice_number,
                    "confidence": 0.95,
                    "source": "regex",
                },
                "invoice_date": {
                    "value": "2026-11-20",
                    "confidence": 0.90,
                    "source": "regex",
                },
                "supplier": {
                    "value": "Example Supplier",
                    "confidence": 0.92,
                    "source": "regex",
                },
                "subtotal": {
                    "value": 1000.0,
                    "confidence": 0.95,
                    "source": "regex",
                },
                "tax": {
                    "value": 150.0,
                    "confidence": 0.95,
                    "source": "regex",
                },
                "total": {
                    "value": total,
                    "confidence": 0.98,
                    "source": "regex",
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.90,
                    "source": "regex",
                },
            },
            "validation": {
                "is_valid": True,
                "errors": [],
                "warnings": [],
            },
        },
    }


def test_database_initialization_creates_schema(tmp_path):
    database_path = tmp_path / "nested" / "invoice_history.sqlite3"

    result = initialize_database(database_path)

    assert result == database_path.resolve()
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(invoices)")
        }

    assert "record_json" in columns
    assert "payload_json" in columns
    assert "invoice_number" in columns


def test_save_and_retrieve_invoice(tmp_path):
    database_path = tmp_path / "invoices.sqlite3"

    saved = save_invoice_result(
        sample_payload(),
        "2026-11-20T12:00:00",
        database_path,
    )

    history = get_invoice_history(db_path=database_path)

    assert len(history) == 1
    assert history[0]["invoice_number"] == "INV-100"
    assert history[0]["total"] == 1150.0
    assert history[0]["source_file"] == "sample.pdf"
    assert saved["id"] == history[0]["id"]


def test_history_survives_database_reopening(tmp_path):
    database_path = tmp_path / "persistent.sqlite3"

    save_invoice_result(
        sample_payload("INV-PERSIST"),
        "2026-11-20T12:00:00",
        database_path,
    )

    # A separate read operation opens a new SQLite connection.
    history = get_invoice_history(db_path=database_path)

    assert history[0]["invoice_number"] == "INV-PERSIST"


def test_history_is_returned_newest_first(tmp_path):
    database_path = tmp_path / "ordered.sqlite3"

    save_invoice_result(
        sample_payload("INV-OLD"),
        "2026-11-20T10:00:00",
        database_path,
    )
    save_invoice_result(
        sample_payload("INV-NEW"),
        "2026-11-20T11:00:00",
        database_path,
    )

    history = get_invoice_history(db_path=database_path)

    assert [item["invoice_number"] for item in history] == [
        "INV-NEW",
        "INV-OLD",
    ]


def test_history_limit_returns_requested_number(tmp_path):
    database_path = tmp_path / "limited.sqlite3"

    for number in range(3):
        save_invoice_result(
            sample_payload(f"INV-{number}"),
            f"2026-11-20T1{number}:00:00",
            database_path,
        )

    assert len(get_invoice_history(limit=2, db_path=database_path)) == 2


def test_invalid_history_limit_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        get_invoice_history(limit=0, db_path=tmp_path / "invalid.sqlite3")


def test_original_api_payload_is_preserved(tmp_path):
    database_path = tmp_path / "payload.sqlite3"
    payload = sample_payload("INV-ORIGINAL")

    save_invoice_result(payload, db_path=database_path)

    saved_payloads = get_invoice_payloads(db_path=database_path)

    assert saved_payloads[0]["source_file"] == "sample.pdf"
    assert saved_payloads[0]["ocr"]["text"] == "Sample invoice text"
    assert (
        saved_payloads[0]["extraction"]["fields"]["invoice_number"]["value"]
        == "INV-ORIGINAL"
    )


def test_clear_history_removes_saved_records(tmp_path):
    database_path = tmp_path / "clear.sqlite3"

    save_invoice_result(sample_payload(), db_path=database_path)
    assert get_invoice_count(db_path=database_path) == 1

    deleted = clear_invoice_history(db_path=database_path)

    assert deleted == 1
    assert get_invoice_count(db_path=database_path) == 0
    assert get_invoice_history(db_path=database_path) == []


def test_database_rejects_non_dictionary_payload(tmp_path):
    with pytest.raises(TypeError):
        save_invoice_result(
            ["not", "a", "dictionary"],
            db_path=tmp_path / "bad.sqlite3",
        )
