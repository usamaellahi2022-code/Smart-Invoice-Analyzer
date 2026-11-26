from frontend.utils import (
    extract_field_rows,
    flatten_invoice,
    history_to_csv,
    history_to_excel,
)


def sample_payload():
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
                    "value": "INV-100",
                    "confidence": 0.95,
                    "source": "regex",
                },
                "total": {
                    "value": 1150.0,
                    "confidence": 0.90,
                    "source": "regex",
                },
            },
            "validation": {
                "is_valid": True,
                "errors": [],
                "warnings": ["Due date was not detected."],
            },
        },
    }


def test_extract_field_rows_formats_backend_fields():
    rows = extract_field_rows(sample_payload())

    assert len(rows) == 2
    assert rows[0]["Field"] == "Invoice Number"
    assert rows[0]["Value"] == "INV-100"
    assert rows[0]["Confidence"] == 0.95


def test_flatten_invoice_includes_fields_and_validation():
    record = flatten_invoice(sample_payload(), "2026-11-20T12:00:00")

    assert record["source_file"] == "sample.pdf"
    assert record["validation_status"] == "Valid"
    assert record["invoice_number"] == "INV-100"
    assert record["total"] == 1150.0
    assert "Due date was not detected." in record["validation_warnings"]


def test_csv_export_contains_invoice_data():
    record = flatten_invoice(sample_payload())
    csv_data = history_to_csv([record])

    assert b"sample.pdf" in csv_data
    assert b"INV-100" in csv_data


def test_excel_export_creates_valid_workbook():
    from io import BytesIO
    from openpyxl import load_workbook

    record = flatten_invoice(sample_payload())
    excel_data = history_to_excel([record])

    workbook = load_workbook(BytesIO(excel_data), read_only=True)

    assert "Invoice History" in workbook.sheetnames

    worksheet = workbook["Invoice History"]
    headers = list(next(worksheet.iter_rows(values_only=True)))

    assert "source_file" in headers
    assert "invoice_number" in headers

    workbook.close()
