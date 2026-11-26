import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from frontend.utils import (
    extract_field_rows,
    flatten_invoice,
    history_to_csv,
    history_to_excel,
)


DEFAULT_API_URL = os.getenv(
    "SMART_INVOICE_API_URL",
    "http://127.0.0.1:8000/api/v1/invoices/analyze",
)

st.set_page_config(
    page_title="Smart Invoice Analyzer",
    page_icon="??",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("?? Smart Invoice Analyzer")
st.caption(
    "Upload an invoice to extract key information, "
    "review confidence scores, and validate its data."
)

if "invoice_history" not in st.session_state:
    st.session_state.invoice_history = []

if "current_result" not in st.session_state:
    st.session_state.current_result = None

with st.sidebar:
    st.header("Connection")
    api_url = st.text_input(
        "Backend API endpoint",
        value=DEFAULT_API_URL,
        help="The FastAPI invoice analysis endpoint.",
    )

    st.divider()
    st.subheader("Supported formats")
    st.write("PDF, PNG, JPG, JPEG, TIFF")
    st.caption("Maximum upload size is controlled by the backend.")

    st.divider()
    st.subheader("Processing history")
    st.metric("Invoices processed", len(st.session_state.invoice_history))

    if st.button("Clear session history", use_container_width=True):
        st.session_state.invoice_history = []
        st.session_state.current_result = None
        st.rerun()

upload_col, action_col = st.columns([3, 1])

with upload_col:
    uploaded_file = st.file_uploader(
        "Choose an invoice",
        type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"],
        help="Select a PDF or image invoice for analysis.",
    )

with action_col:
    st.write("")
    st.write("")
    analyze_clicked = st.button(
        "Analyze invoice",
        type="primary",
        use_container_width=True,
        disabled=uploaded_file is None,
    )

if analyze_clicked and uploaded_file is not None:
    if not api_url.strip():
        st.error("Enter a valid backend API endpoint.")
    else:
        try:
            with st.spinner("Uploading invoice and running OCR analysis..."):
                response = requests.post(
                    api_url.strip(),
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type or "application/octet-stream",
                        )
                    },
                    timeout=(10, 180),
                )

            try:
                response_payload = response.json()
            except ValueError:
                response_payload = {}

            if response.ok:
                timestamp = datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )

                st.session_state.current_result = response_payload
                record = flatten_invoice(response_payload, timestamp)
                st.session_state.invoice_history.insert(0, record)

                st.success("Invoice processed successfully.")
                st.rerun()

            else:
                detail = response_payload.get(
                    "detail",
                    f"Backend returned HTTP {response.status_code}.",
                )
                st.error(f"Invoice analysis failed: {detail}")

        except requests.exceptions.Timeout:
            st.error(
                "The backend took too long to respond. "
                "Check that the API is running and try again."
            )

        except requests.exceptions.ConnectionError:
            st.error(
                "Could not connect to the backend. "
                "Start the FastAPI server and verify the API endpoint."
            )

        except requests.exceptions.RequestException as exc:
            st.error(f"Request failed: {exc}")

result = st.session_state.current_result

if result:
    st.divider()
    st.header("Invoice analysis results")

    extraction = result.get("extraction", {})
    validation = extraction.get("validation", {})
    ocr = result.get("ocr", {})

    metric_a, metric_b, metric_c, metric_d = st.columns(4)

    metric_a.metric(
        "OCR confidence",
        (
            f"{ocr['confidence']:.2f}%"
            if isinstance(ocr.get("confidence"), (int, float))
            else "N/A"
        ),
    )
    metric_b.metric("Pages", ocr.get("page_count", "N/A"))
    metric_c.metric("Words detected", ocr.get("word_count", "N/A"))
    metric_d.metric(
        "Validation",
        "Valid" if validation.get("is_valid") else "Needs review",
    )

    st.subheader("Extracted invoice fields")

    field_rows = extract_field_rows(result)

    if field_rows:
        field_dataframe = pd.DataFrame(field_rows)
        st.dataframe(
            field_dataframe,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("The backend did not return any extracted fields.")

    if validation.get("is_valid"):
        st.success("The extracted invoice passed validation.")
    else:
        st.warning("The invoice needs a manual review.")

    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])

    if errors:
        with st.expander("Validation errors", expanded=True):
            for error in errors:
                st.error(error)

    if warnings:
        with st.expander("Validation warnings", expanded=True):
            for warning in warnings:
                st.warning(warning)

    with st.expander("Recognized OCR text"):
        st.text(ocr.get("text", "No OCR text returned."))

    st.caption(f"Source file: {result.get('source_file', 'Unknown')}")

st.divider()
st.header("Processing history")

history = st.session_state.invoice_history

if history:
    history_dataframe = pd.DataFrame(history)

    preferred_columns = [
        "processed_at",
        "source_file",
        "validation_status",
        "invoice_number",
        "invoice_date",
        "due_date",
        "supplier",
        "subtotal",
        "tax",
        "total",
        "currency",
        "ocr_confidence",
    ]

    visible_columns = [
        column
        for column in preferred_columns
        if column in history_dataframe.columns
    ]

    st.dataframe(
        history_dataframe[visible_columns],
        use_container_width=True,
        hide_index=True,
    )

    csv_data = history_to_csv(history)
    excel_data = history_to_excel(history)

    export_csv_col, export_excel_col = st.columns(2)

    with export_csv_col:
        st.download_button(
            "Download history as CSV",
            data=csv_data,
            file_name="invoice_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with export_excel_col:
        st.download_button(
            "Download history as Excel",
            data=excel_data,
            file_name="invoice_history.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )
else:
    st.info(
        "No invoices processed in this session yet. "
        "Upload an invoice to start your history."
    )

st.caption("Smart Invoice Analyzer | Local development version")
