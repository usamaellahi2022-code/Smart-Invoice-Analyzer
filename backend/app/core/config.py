import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=False)


def resolve_project_path(value: str) -> Path:
    """Resolve a path relative to the project root when not absolute."""
    path = Path(value)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def resolve_tesseract_command(value: str) -> Path:
    """Resolve an explicit path or find Tesseract through system PATH."""
    command = value.strip()

    if not command:
        raise ValueError("TESSERACT_CMD cannot be empty.")

    candidate = Path(command)

    # Explicit absolute or relative paths take precedence.
    if candidate.is_absolute() or "/" in command or "\\" in command:
        return resolve_project_path(command)

    # Standard installations can be discovered through PATH.
    located = shutil.which(command)

    if located:
        return Path(located).resolve()

    # Keep a bare executable name so subprocess can resolve it through PATH.
    return candidate


def resolve_optional_directory(value: str) -> Path | None:
    """An empty directory setting means use the application's default."""
    if not value.strip():
        return None

    return resolve_project_path(value)


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str

    tesseract_cmd: Path
    tessdata_prefix: Path | None
    ocr_language: str

    upload_dir: Path
    processed_dir: Path
    output_dir: Path
    log_dir: Path

    max_upload_size_mb: int

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def get_settings() -> Settings:
    max_upload_size = int(
        os.getenv("MAX_UPLOAD_SIZE_MB", "20")
    )

    if max_upload_size <= 0:
        raise ValueError("MAX_UPLOAD_SIZE_MB must be positive.")

    tesseract_value = os.getenv(
        "TESSERACT_CMD",
        r"D:\Tools\Tesseract-OCR\tesseract.exe"
    )

    tessdata_value = os.getenv(
        "TESSDATA_PREFIX",
        r"D:\Tools\Tesseract-OCR\tessdata"
    )

    settings = Settings(
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),

        tesseract_cmd=resolve_tesseract_command(tesseract_value),
        tessdata_prefix=resolve_optional_directory(tessdata_value),
        ocr_language=os.getenv("OCR_LANGUAGE", "eng"),

        upload_dir=resolve_project_path(
            os.getenv("UPLOAD_DIR", "data/incoming")
        ),

        processed_dir=resolve_project_path(
            os.getenv("PROCESSED_DIR", "data/processed")
        ),

        output_dir=resolve_project_path(
            os.getenv("OUTPUT_DIR", "outputs")
        ),

        log_dir=resolve_project_path("logs"),

        max_upload_size_mb=max_upload_size,
    )

    if not settings.ocr_language.strip():
        raise ValueError("OCR_LANGUAGE cannot be empty.")

    return settings


settings = get_settings()
