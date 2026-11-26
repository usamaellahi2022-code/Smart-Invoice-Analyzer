from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api import routes
from backend.app.services.ocr_service import OCRResult, OCRPageResult


client = TestClient(app)


def fake_ocr_result():
    text = """
ACME TECHNOLOGIES
INVOICE NUMBER: INV-2026-001
INVOICE DATE: 2026-11-15
DUE DATE: 2026-12-15
SUPPLIER: ACME Technologies Ltd
SUBTOTAL: 1000.00
TAX: 150.00
GRAND TOTAL: 1150.00
CURRENCY: USD
"""

    page = OCRPageResult(
        page_number=1,
        text=text,
        confidence=95.0,
        word_count=25,
    )

    return OCRResult(
        source_file="test.png",
        text=text,
        confidence=95.0,
        word_count=25,
        page_count=1,
        pages=(page,),
    )


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["documentation"] == "/docs"


def test_invoice_analysis_endpoint(monkeypatch):
    monkeypatch.setattr(
        routes.ocr_service,
        "process_file",
        lambda path: fake_ocr_result(),
    )

    response = client.post(
        "/api/v1/invoices/analyze",
        files={
            "file": (
                "invoice.png",
                b"fake-image-content",
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["source_file"] == "invoice.png"
    assert body["ocr"]["page_count"] == 1

    fields = body["extraction"]["fields"]

    assert fields["invoice_number"]["value"] == "INV-2026-001"
    assert fields["total"]["value"] == 1150.0
    assert body["extraction"]["validation"]["is_valid"] is True


def test_unsupported_upload_is_rejected():
    response = client.post(
        "/api/v1/invoices/analyze",
        files={
            "file": (
                "invoice.docx",
                b"test",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400


def test_empty_upload_is_rejected(monkeypatch):
    monkeypatch.setattr(
        routes.ocr_service,
        "process_file",
        lambda path: fake_ocr_result(),
    )

    response = client.post(
        "/api/v1/invoices/analyze",
        files={
            "file": (
                "empty.png",
                b"",
                "image/png",
            )
        },
    )

    assert response.status_code == 400