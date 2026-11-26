import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps
from pytesseract import Output

from backend.app.core.config import settings


SUPPORTED_IMAGE_FORMATS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff"
}

SUPPORTED_FORMATS = SUPPORTED_IMAGE_FORMATS | {".pdf"}

DEFAULT_MAX_PDF_PAGES = 20
PDF_RENDER_SCALE = 2.5


class OCRServiceError(Exception):
    """Base exception for invoice OCR processing."""


class UnsupportedFileError(OCRServiceError):
    """Raised when the input file format is unsupported."""


class InvalidInvoiceFileError(OCRServiceError):
    """Raised when the input file is missing or invalid."""


class OCRProcessingError(OCRServiceError):
    """Raised when OCR processing fails."""


@dataclass(frozen=True)
class OCRPageResult:
    page_number: int
    text: str
    confidence: float
    word_count: int


@dataclass(frozen=True)
class OCRResult:
    source_file: str
    text: str
    confidence: float
    word_count: int
    page_count: int
    pages: tuple[OCRPageResult, ...]


class InvoiceOCRService:
    """Extract text and recognition confidence from invoice files."""

    def __init__(self) -> None:
        pytesseract.pytesseract.tesseract_cmd = str(
            settings.tesseract_cmd
        )

        # Use the configured tessdata directory when provided.
        # An empty setting allows Tesseract to use its normal defaults.
        if settings.tessdata_prefix is not None:
            os.environ["TESSDATA_PREFIX"] = str(
                settings.tessdata_prefix
            )
        else:
            os.environ.pop("TESSDATA_PREFIX", None)

    @staticmethod
    def _validate_file(file_path: Path) -> Path:
        path = Path(file_path)

        if not path.exists() or not path.is_file():
            raise InvalidInvoiceFileError(
                f"Invoice file does not exist: {path}"
            )

        if path.suffix.lower() not in SUPPORTED_FORMATS:
            raise UnsupportedFileError(
                f"Unsupported invoice format: {path.suffix}"
            )

        if path.stat().st_size == 0:
            raise InvalidInvoiceFileError(
                "Invoice file is empty."
            )

        if path.stat().st_size > settings.max_upload_size_bytes:
            raise InvalidInvoiceFileError(
                "Invoice file exceeds the configured upload limit."
            )

        return path

    @staticmethod
    def _prepare_image(image: Image.Image) -> Image.Image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)

        return image

    @staticmethod
    def _recognize_image(
        image: Image.Image,
        page_number: int,
        language: str,
    ) -> OCRPageResult:

        try:
            prepared = InvoiceOCRService._prepare_image(image)

            text = pytesseract.image_to_string(
                prepared,
                lang=language,
                config="--oem 3 --psm 3",
            )

            data = pytesseract.image_to_data(
                prepared,
                lang=language,
                config="--oem 3 --psm 3",
                output_type=Output.DICT,
            )

            confidences = []

            for value in data["conf"]:
                try:
                    confidence = float(value)
                    if confidence >= 0:
                        confidences.append(confidence)
                except (TypeError, ValueError):
                    continue

            average_confidence = (
                sum(confidences) / len(confidences)
                if confidences else 0.0
            )

            word_count = sum(
                1 for word in data["text"] if word.strip()
            )

            return OCRPageResult(
                page_number=page_number,
                text=text.strip(),
                confidence=round(average_confidence, 2),
                word_count=word_count,
            )

        except Exception as exc:
            raise OCRProcessingError(
                f"OCR failed on page {page_number}: {exc}"
            ) from exc

    def process_image(
        self,
        file_path: str | Path,
        language: str | None = None,
    ) -> OCRResult:

        path = self._validate_file(Path(file_path))

        if path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
            raise UnsupportedFileError(
                "process_image accepts image files only."
            )

        selected_language = language or settings.ocr_language

        try:
            with Image.open(path) as image:
                result = self._recognize_image(
                    image.copy(),
                    page_number=1,
                    language=selected_language,
                )

        except OCRServiceError:
            raise
        except Exception as exc:
            raise InvalidInvoiceFileError(
                f"Unable to read invoice image: {exc}"
            ) from exc

        return OCRResult(
            source_file=path.name,
            text=result.text,
            confidence=result.confidence,
            word_count=result.word_count,
            page_count=1,
            pages=(result,),
        )

    def process_pdf(
        self,
        file_path: str | Path,
        language: str | None = None,
        max_pages: int = DEFAULT_MAX_PDF_PAGES,
    ) -> OCRResult:

        path = self._validate_file(Path(file_path))

        if path.suffix.lower() != ".pdf":
            raise UnsupportedFileError(
                "process_pdf accepts PDF files only."
            )

        if max_pages < 1:
            raise ValueError("max_pages must be at least 1.")

        selected_language = language or settings.ocr_language
        page_results = []

        try:
            with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as document:
                if document.is_encrypted:
                    raise InvalidInvoiceFileError(
                        "Encrypted PDFs are not supported."
                    )

                if len(document) == 0:
                    raise InvalidInvoiceFileError(
                        "PDF contains no pages."
                    )

                if len(document) > max_pages:
                    raise InvalidInvoiceFileError(
                        f"PDF has {len(document)} pages; "
                        f"maximum allowed is {max_pages}."
                    )

                matrix = pymupdf.Matrix(
                    PDF_RENDER_SCALE,
                    PDF_RENDER_SCALE,
                )

                for index, page in enumerate(document):
                    pixmap = page.get_pixmap(
                        matrix=matrix,
                        alpha=False,
                    )

                    image = Image.frombytes(
                        "RGB",
                        (pixmap.width, pixmap.height),
                        pixmap.samples,
                    )

                    result = self._recognize_image(
                        image,
                        page_number=index + 1,
                        language=selected_language,
                    )

                    page_results.append(result)

        except OCRServiceError:
            raise
        except Exception as exc:
            raise OCRProcessingError(
                f"Unable to process invoice PDF: {exc}"
            ) from exc

        combined_text = "\n\n".join(
            result.text for result in page_results
        )

        total_words = sum(
            result.word_count for result in page_results
        )

        total_confidence = sum(
            result.confidence * result.word_count
            for result in page_results
        )

        average_confidence = (
            total_confidence / total_words
            if total_words else 0.0
        )

        return OCRResult(
            source_file=path.name,
            text=combined_text,
            confidence=round(average_confidence, 2),
            word_count=total_words,
            page_count=len(page_results),
            pages=tuple(page_results),
        )

    def process_file(
        self,
        file_path: str | Path,
        language: str | None = None,
    ) -> OCRResult:

        path = Path(file_path)

        if path.suffix.lower() == ".pdf":
            return self.process_pdf(path, language=language)

        return self.process_image(path, language=language)
