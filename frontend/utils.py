from io import BytesIO, StringIO

import pandas as pd


def extract_field_rows(payload: dict) -> list[dict]:
    """Convert the backend extraction fields into display-ready rows."""

    extraction = payload.get("extraction", {})
    fields = extraction.get("fields", {})

    rows = []

    for field_name, details in fields.items():
        details = details or {}

        rows.append(
            {
                "Field": field_name.replace("_", " ").title(),
                "Value": details.get("value"),
                "Confidence": details.get("confidence"),
                "Source": details.get("source"),
            }
        )

    return rows


def flatten_invoice(payload: dict, processed_at: str = "") -> dict:
    """Flatten one API result into a spreadsheet-friendly record."""

    extraction = payload.get("extraction", {})
    validation = extraction.get("validation", {})
    ocr = payload.get("ocr", {})

    record = {
        "processed_at": processed_at,
        "source_file": payload.get("source_file", ""),
        "validation_status": (
            "Valid" if validation.get("is_valid") else "Needs review"
        ),
        "validation_errors": "; ".join(validation.get("errors", [])),
        "validation_warnings": "; ".join(validation.get("warnings", [])),
        "ocr_confidence": ocr.get("confidence"),
        "ocr_word_count": ocr.get("word_count"),
        "ocr_page_count": ocr.get("page_count"),
    }

    for field_name, details in extraction.get("fields", {}).items():
        details = details or {}
        record[field_name] = details.get("value")
        record[f"{field_name}_confidence"] = details.get("confidence")

    return record


def history_to_csv(history: list[dict]) -> bytes:
    """Export processing history as UTF-8 CSV."""

    dataframe = pd.DataFrame(history)
    buffer = StringIO()
    dataframe.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")


def history_to_excel(history: list[dict]) -> bytes:
    """Export processing history as an Excel workbook."""

    dataframe = pd.DataFrame(history)
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(
            writer,
            index=False,
            sheet_name="Invoice History",
        )

    return buffer.getvalue()
