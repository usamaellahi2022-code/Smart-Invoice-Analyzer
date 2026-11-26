from backend.app.services.invoice_extraction_service import (
    InvoiceExtractionService,
)


SAMPLE_OCR = """INVOICE

SAMPLE DOCUMENT — FOR SOFTWARE TESTING ONLY

ACME Technologies Ltd Invoice Number: INV-2026-TEST-001
125 Market Street Invoice Date: 15 November 2026
Peshawar, Pakistan Due Date: 15 December 2026

Email: billing@example.com

Bill To

Example Customer
42 Sample Avenue
Peshawar, Pakistan

Currency: USD

Software development services $800.00 $800.00
Technical support and maintenance 1 $200.00 $200.00
Subtotal $1,000.00
Tax (15%) $150.00
Total Due $1,150.00
Payment Terms

Payment is due by 15 December 2026. This sample invoice is fictional and intended only for testing document

extraction and validation software.
"""


def test_real_invoice_all_eight_fields_are_extracted():
    result = InvoiceExtractionService().extract(SAMPLE_OCR)
    fields = result["fields"]

    assert fields["invoice_number"]["value"] == "INV-2026-TEST-001"
    assert fields["invoice_date"]["value"] == "2026-11-15"
    assert fields["due_date"]["value"] == "2026-12-15"
    assert fields["supplier"]["value"] == "ACME Technologies Ltd"
    assert fields["subtotal"]["value"] == 1000.0
    assert fields["tax"]["value"] == 150.0
    assert fields["total"]["value"] == 1150.0
    assert fields["currency"]["value"] == "USD"


def test_supplier_detection_rejects_sample_disclaimer():
    result = InvoiceExtractionService().extract(SAMPLE_OCR)
    supplier = result["fields"]["supplier"]["value"]

    assert supplier == "ACME Technologies Ltd"
    assert "SAMPLE DOCUMENT" not in supplier


def test_real_invoice_validation_passes():
    result = InvoiceExtractionService().extract(SAMPLE_OCR)

    assert result["validation"]["is_valid"] is True
    assert result["validation"]["errors"] == []
    assert result["validation"]["warnings"] == []


def test_extracted_field_confidence_values_are_percentage_scores():
    result = InvoiceExtractionService().extract(SAMPLE_OCR)

    for field in result["fields"].values():
        assert 0.0 <= field["confidence"] <= 100.0
