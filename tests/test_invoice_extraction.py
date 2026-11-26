import pytest

from backend.app.services.invoice_extraction_service import (
    InvoiceExtractionService,
)


@pytest.fixture
def service():
    return InvoiceExtractionService()


@pytest.fixture
def invoice_text():
    return """
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


def test_extracts_invoice_fields(service, invoice_text):
    result = service.extract(invoice_text)
    fields = result["fields"]

    assert fields["invoice_number"]["value"] == "INV-2026-001"
    assert fields["invoice_date"]["value"] == "2026-11-15"
    assert fields["due_date"]["value"] == "2026-12-15"
    assert fields["supplier"]["value"] == "ACME Technologies Ltd"
    assert fields["subtotal"]["value"] == 1000.0
    assert fields["tax"]["value"] == 150.0
    assert fields["total"]["value"] == 1150.0
    assert fields["currency"]["value"] == "USD"


def test_confidence_scores_are_valid(service, invoice_text):
    result = service.extract(invoice_text)

    for field in result["fields"].values():
        assert 0 <= field["confidence"] <= 100


def test_valid_invoice_passes_validation(service, invoice_text):
    result = service.extract(invoice_text)

    assert result["validation"]["is_valid"] is True
    assert result["validation"]["errors"] == []


def test_total_mismatch_is_detected(service):
    text = """
INVOICE NUMBER: INV-100
INVOICE DATE: 2026-11-15
SUPPLIER: Example Ltd
SUBTOTAL: 1000.00
TAX: 150.00
TOTAL: 1200.00
CURRENCY: USD
"""

    result = service.extract(text)

    assert result["validation"]["is_valid"] is False
    assert any(
        "does not match" in error
        for error in result["validation"]["errors"]
    )


def test_missing_required_fields_are_reported(service):
    result = service.extract("This is an invoice without readable fields.")

    assert result["validation"]["is_valid"] is False
    assert len(result["validation"]["errors"]) > 0


def test_empty_ocr_text_is_rejected(service):
    with pytest.raises(ValueError):
        service.extract("   ")


def test_currency_symbol_detection(service):
    result = service.extract(
        """
INVOICE NUMBER: INV-200
INVOICE DATE: 2026-11-15
SUPPLIER: Example Ltd
TOTAL: €250.00
"""
    )

    assert result["fields"]["currency"]["value"] == "EUR"


def test_due_date_before_invoice_date_is_rejected(service):
    result = service.extract(
        """
INVOICE NUMBER: INV-201
INVOICE DATE: 2026-11-20
DUE DATE: 2026-11-10
SUPPLIER: Example Ltd
TOTAL: 100.00
CURRENCY: USD
"""
    )

    assert result["validation"]["is_valid"] is False
    assert any(
        "earlier" in error
        for error in result["validation"]["errors"]
    )


def test_extracts_spaced_subtotal_label():
    from backend.app.services.invoice_extraction_service import (
        InvoiceExtractionService,
    )

    result = InvoiceExtractionService().extract(
        "Invoice Number: INV-1001\n"
        "Invoice Date: 2026-11-15\n"
        "Supplier: Example Ltd\n"
        "Sub Total: 100.00\n"
        "Tax: 10.00\n"
        "Grand Total: 110.00\n"
        "Currency: USD"
    )

    assert result["fields"]["subtotal"]["value"] == 100.0
    assert result["fields"]["tax"]["value"] == 10.0
    assert result["fields"]["total"]["value"] == 110.0


def test_extracts_net_amount_label():
    from backend.app.services.invoice_extraction_service import (
        InvoiceExtractionService,
    )

    result = InvoiceExtractionService().extract(
        "Invoice Number: INV-1002\n"
        "Invoice Date: 2026-11-15\n"
        "Supplier: Example Ltd\n"
        "Net Amount: 250.00\n"
        "Tax: 25.00\n"
        "Grand Total: 275.00\n"
        "Currency: USD"
    )

    assert result["fields"]["subtotal"]["value"] == 250.0
    assert result["fields"]["tax"]["value"] == 25.0
    assert result["fields"]["total"]["value"] == 275.0
