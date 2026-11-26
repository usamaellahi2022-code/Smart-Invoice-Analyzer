import logging
from logging.handlers import RotatingFileHandler

from backend.app.core.config import settings


def configure_logging() -> logging.Logger:
    """Configure rotating file and console logging for the application."""

    settings.log_dir.mkdir(parents=True, exist_ok=True)

    configured_level = getattr(
        logging,
        settings.log_level.upper(),
        logging.INFO,
    )

    logger = logging.getLogger("smart_invoice_analyzer")
    logger.setLevel(configured_level)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
