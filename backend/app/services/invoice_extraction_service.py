import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as date_parser


class InvoiceExtractionService:
    """Extract and validate common invoice fields from OCR text."""

    CURRENCY_SYMBOLS = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "₹": "INR",
        "¥": "JPY",
    }

    CURRENCY_CODES = {
        "USD", "EUR", "GBP", "INR", "JPY",
        "CAD", "AUD", "CHF", "CNY", "AED",
        "SAR", "PKR", "BDT", "SGD", "NZD",
    }

    AMOUNT_PATTERN = re.compile(
        r"(?<![A-Za-z0-9])"
        r"(?:[$€£₹¥]\s*)?"
        r"-?\d[\d,]*(?:\.\d{1,2})?"
        r"(?!\d)"
    )

    def extract(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("OCR text cannot be empty.")

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        fields = {
            "invoice_number": self._field_result(
                self._extract_invoice_number(lines)
            ),
            "invoice_date": self._field_result(
                self._extract_date(
                    lines,
                    r"invoice\s*date|date\s*of\s*invoice|billing\s*date"
                )
            ),
            "due_date": self._field_result(
                self._extract_date(
                    lines,
                    r"due\s*date|payment\s*due|pay\s*by"
                )
            ),
            "supplier": self._field_result(
                self._extract_supplier(lines)
            ),
            "subtotal": self._field_result(
                self._extract_amount(
                    lines,
                    r"sub\s*total|subtotal|net\s*amount"
                )
            ),
            "tax": self._field_result(
                self._extract_amount(
                    lines,
                    r"tax|vat|gst|sales\s*tax"
                )
            ),
            "total": self._field_result(
                self._extract_total(lines)
            ),
            "currency": self._field_result(
                self._extract_currency(text)
            ),
        }

        for name, field in fields.items():
            field["confidence"] = self._confidence(
                name,
                field["value"],
                field["source"],
            )

        validation = self._validate(fields)

        return {
            "fields": fields,
            "validation": validation,
        }

    @staticmethod
    def _field_result(result):
        """Convert an extractor's (value, source) pair into a field."""
        if not isinstance(result, tuple) or len(result) != 2:
            raise TypeError(
                "An extraction method must return (value, source)."
            )

        value, source = result

        return {
            "value": value,
            "confidence": 0.0,
            "source": source,
        }

    @staticmethod
    def _field(value: Any, confidence: float, source=None):
        return {
            "value": value,
            "confidence": confidence,
            "source": source,
        }

    @staticmethod
    def _label_value(lines, pattern):
        """Find a labelled value even when the label is mid-line."""

        regex = re.compile(
            rf"(?<![A-Za-z0-9])(?:{pattern})\s*[:#\-]?\s*(.*?)\s*$",
            re.IGNORECASE,
        )

        for line in lines:
            match = regex.search(line)

            if match and match.group(1).strip():
                return match.group(1).strip(), line

        return None, None
    def _extract_invoice_number(self, lines):
        patterns = (
            r"invoice\s*(?:number|no\.?|#|id)",
            r"bill\s*(?:number|no\.?|#)",
            r"document\s*(?:number|no\.?|#)",
        )

        for pattern in patterns:
            value, source = self._label_value(lines, pattern)

            if value:
                value = re.split(
                    r"\s{2,}|(?=\s+(?:date|due date)\s*:)",
                    value,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()

                if value:
                    return value, source

        return None, None

    def _extract_date(self, lines, pattern):
        value, source = self._label_value(lines, pattern)

        if not value:
            return None, None

        match = re.search(
            r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"
            r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
            r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}",
            value,
        )

        if not match:
            return None, None

        try:
            parsed = date_parser.parse(
                match.group(0),
                fuzzy=False,
                dayfirst=False,
            ).date()

            return parsed.isoformat(), source

        except (ValueError, OverflowError):
            return None, source

    def _extract_supplier(self, lines):
        """Extract supplier while rejecting invoice disclaimers."""

        patterns = (
            r"supplier",
            r"vendor",
            r"billed\s*from",
            r"seller",
            r"company",
        )

        for pattern in patterns:
            value, source = self._label_value(lines, pattern)

            if value and len(value) >= 2:
                return value, source

        ignored = re.compile(
            r"sample|document|testing|fictional|intended|extraction|"
            r"software|invoice|bill\s+to|ship\s+to|date|total|"
            r"tax|subtotal|amount|payment|phone|email|www\.|http",
            re.IGNORECASE,
        )

        # Some invoices put the supplier and invoice number on one line.
        # Extract the text before the invoice-number label.
        for line in lines:
            match = re.search(
                r"invoice\s*(?:number|no\.?|#|id)\s*[:#\-]",
                line,
                re.IGNORECASE,
            )

            if match:
                candidate = line[:match.start()].strip(" :#-")

                if len(candidate) >= 3 and not ignored.search(candidate):
                    return candidate, line

        # Fallback: look for a plausible company name near the top.
        for line in lines[:10]:
            candidate = line.strip()

            if (
                len(candidate) >= 3
                and not ignored.search(candidate)
                and not self.AMOUNT_PATTERN.fullmatch(candidate)
            ):
                return candidate, line

        return None, None
    def _extract_amount(self, lines, pattern):
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE):
                if re.search(
                    r"tax\s*(?:id|number|no\.?)",
                    line,
                    re.IGNORECASE,
                ):
                    continue

                matches = self.AMOUNT_PATTERN.findall(line)

                if matches:
                    value = self._parse_amount(matches[-1])

                    if value is not None:
                        return value, line

        return None, None

    def _extract_total(self, lines):
        priority_patterns = (
            r"grand\s*total",
            r"total\s*due",
            r"amount\s*due",
            r"invoice\s*total",
            r"balance\s*due",
            r"total",
        )

        for pattern in priority_patterns:
            result = self._extract_amount(lines, pattern)

            if result[0] is not None:
                return result

        return None, None

    @staticmethod
    def _parse_amount(value):
        cleaned = (
            value.replace(",", "")
            .replace("$", "")
            .replace("€", "")
            .replace("£", "")
            .replace("₹", "")
            .replace("¥", "")
            .strip()
        )

        try:
            amount = Decimal(cleaned)

            if not amount.is_finite():
                return None

            return float(amount)

        except InvalidOperation:
            return None

    def _extract_currency(self, text):
        code_pattern = re.compile(
            r"\b(" + "|".join(sorted(self.CURRENCY_CODES)) + r")\b",
            re.IGNORECASE,
        )

        match = code_pattern.search(text)

        if match:
            return match.group(1).upper(), match.group(0)

        for symbol, code in self.CURRENCY_SYMBOLS.items():
            if symbol in text:
                return code, symbol

        return None, None

    @staticmethod
    def _confidence(name, value, source):
        if value is None:
            return 0.0

        scores = {
            "invoice_number": 96,
            "invoice_date": 94,
            "due_date": 94,
            "supplier": 92,
            "subtotal": 95,
            "tax": 95,
            "total": 97,
            "currency": 96,
        }

        score = scores.get(name, 80)

        if name == "supplier" and source == value:
            score = 60

        if name == "currency" and source in ("$", "¥"):
            score = 65

        return float(score)

    def _validate(self, fields):
        errors = []
        warnings = []

        required = (
            "invoice_number",
            "invoice_date",
            "supplier",
            "total",
            "currency",
        )

        for name in required:
            if fields[name]["value"] is None:
                errors.append(f"Missing required field: {name}")

        for name in ("subtotal", "tax", "total"):
            value = fields[name]["value"]

            if value is not None and value < 0:
                errors.append(f"{name} cannot be negative.")

        invoice_date = fields["invoice_date"]["value"]
        due_date = fields["due_date"]["value"]

        if invoice_date and due_date:
            if due_date < invoice_date:
                errors.append(
                    "Due date cannot be earlier than invoice date."
                )

        subtotal = fields["subtotal"]["value"]
        tax = fields["tax"]["value"]
        total = fields["total"]["value"]

        if subtotal is not None and tax is not None and total is not None:
            expected = Decimal(str(subtotal)) + Decimal(str(tax))
            actual = Decimal(str(total))

            if abs(expected - actual) > Decimal("0.02"):
                errors.append(
                    "Subtotal plus tax does not match the invoice total."
                )

        if subtotal is None:
            warnings.append("Subtotal was not detected.")

        if tax is None:
            warnings.append("Tax was not detected.")

        if due_date is None:
            warnings.append("Due date was not detected.")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }