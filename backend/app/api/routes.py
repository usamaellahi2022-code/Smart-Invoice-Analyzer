import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.core.config import settings
from backend.app.services.invoice_extraction_service import (
    InvoiceExtractionService,
)
from backend.app.services.ocr_service import (
    InvoiceOCRService,
    InvalidInvoiceFileError,
    OCRProcessingError,
    UnsupportedFileError,
)


logger = logging.getLogger("smart_invoice_analyzer.api")

router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])

ocr_service = InvoiceOCRService()
extraction_service = InvoiceExtractionService()

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@router.post("/analyze")
async def analyze_invoice(file: UploadFile = File(...)):
    """Upload an invoice and return OCR, extracted fields and validation."""

    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported invoice file. Use PDF, PNG, JPG or TIFF.",
        )

    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    temporary_path = upload_dir / f"{uuid4().hex}{extension}"

    try:
        content = await file.read(settings.max_upload_size_bytes + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded invoice is empty.",
            )

        if len(content) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=413,
                detail="Invoice exceeds the configured upload limit.",
            )

        temporary_path.write_bytes(content)

        ocr_result = ocr_service.process_file(temporary_path)

        if not ocr_result.text.strip():
            raise HTTPException(
                status_code=422,
                detail="No readable text was detected in the invoice.",
            )

        extracted = extraction_service.extract(ocr_result.text)

        logger.info(
            "Invoice processed successfully: format=%s pages=%d words=%d",
            extension,
            ocr_result.page_count,
            ocr_result.word_count,
        )

        return {
            "success": True,
            "source_file": original_name,
            "ocr": {
                "confidence": ocr_result.confidence,
                "word_count": ocr_result.word_count,
                "page_count": ocr_result.page_count,
                "text": ocr_result.text,
            },
            "extraction": extracted,
        }

    except HTTPException:
        raise

    except UnsupportedFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except InvalidInvoiceFileError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid or unreadable invoice file.",
        ) from exc

    except OCRProcessingError as exc:
        logger.exception(
            "Invoice OCR processing failed: format=%s",
            extension,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Unable to process the invoice. "
                "Check that the file is valid and readable."
            ),
        ) from exc

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected invoice processing failure: format=%s",
            extension,
        )
        raise HTTPException(
            status_code=500,
            detail="Unexpected invoice processing error.",
        ) from exc

    finally:
        try:
            await file.close()
        except Exception:
            logger.exception("Unable to close uploaded invoice stream.")

        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                logger.exception("Unable to remove temporary invoice upload.")
