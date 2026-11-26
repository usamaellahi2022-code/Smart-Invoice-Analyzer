from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from backend.app.services.ocr_service import (
    InvoiceOCRService,
    InvalidInvoiceFileError,
    UnsupportedFileError,
)


@pytest.fixture
def service():
    return InvoiceOCRService()


@pytest.fixture
def invoice_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "test_invoice.png"

    image = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(image)

    draw.text(
        (50, 60),
        "INVOICE NUMBER: INV-2026-001",
        fill="black",
    )
    draw.text(
        (50, 150),
        "TOTAL AMOUNT: 1250.00",
        fill="black",
    )
    draw.text(
        (50, 240),
        "CURRENCY: USD",
        fill="black",
    )

    image.save(image_path)
    return image_path


def test_image_ocr_extracts_invoice_text(service, invoice_image):
    result = service.process_image(invoice_image)

    normalized = result.text.replace(" ", "").replace("\n", "")

    assert "INV-2026-001" in normalized
    assert "1250.00" in normalized
    assert "USD" in normalized


def test_image_ocr_returns_metadata(service, invoice_image):
    result = service.process_image(invoice_image)

    assert result.source_file == "test_invoice.png"
    assert result.page_count == 1
    assert result.word_count > 0
    assert 0 <= result.confidence <= 100
    assert len(result.pages) == 1


def test_unsupported_file_is_rejected(service, tmp_path):
    file_path = tmp_path / "invoice.docx"
    file_path.write_text("not an invoice")

    with pytest.raises(UnsupportedFileError):
        service.process_file(file_path)


def test_missing_file_is_rejected(service, tmp_path):
    file_path = tmp_path / "missing.png"

    with pytest.raises(InvalidInvoiceFileError):
        service.process_image(file_path)


def test_empty_file_is_rejected(service, tmp_path):
    file_path = tmp_path / "empty.png"
    file_path.write_bytes(b"")

    with pytest.raises(InvalidInvoiceFileError):
        service.process_image(file_path)


def test_pdf_page_limit_validation(service, tmp_path):
    file_path = tmp_path / "sample.pdf"

    import pymupdf

    document = pymupdf.open()
    document.new_page()
    document.new_page()
    document.save(file_path)
    document.close()

    with pytest.raises(InvalidInvoiceFileError):
        service.process_pdf(file_path, max_pages=1)
