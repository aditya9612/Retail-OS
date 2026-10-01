import re
from typing import Optional


INDIAN_PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")


def normalize_phone_number(raw_phone: Optional[str]) -> str:
    """
    Normalizes and validates an Indian mobile phone number into canonical 10-digit format.

    Rules:
    1. Strip leading and trailing whitespace.
    2. Strip spaces, hyphens, parentheses, and dots.
    3. If +91 followed by valid 10 digits starting with [6-9], remove +91.
    4. If 91 followed by valid 10 digits starting with [6-9], remove 91.
    5. If 0 followed by valid 10 digits starting with [6-9], remove leading 0.
    6. Canonical format: exactly 10 digits starting with [6-9].
    7. Raises ValueError if input is empty, None, or does not match canonical format.
    """
    if raw_phone is None:
        raise ValueError("Phone number is required")

    cleaned = str(raw_phone).strip()
    if not cleaned:
        raise ValueError("Phone number cannot be empty")

    # Remove formatting characters: spaces, hyphens, parentheses, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", cleaned)

    # Check for + prefix
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("+"):
        raise ValueError("Only Indian mobile numbers (+91) are supported")
    elif cleaned.startswith("0") and len(cleaned) == 11 and cleaned[1] in "6789":
        # Leading 0 (e.g. domestic mobile prefix: 09876543210)
        cleaned = cleaned[1:]
    elif cleaned.startswith("91") and len(cleaned) == 12 and cleaned[2] in "6789":
        # 91 prefix without plus (e.g. 919876543210)
        cleaned = cleaned[2:]

    if not INDIAN_PHONE_REGEX.fullmatch(cleaned):
        raise ValueError(
            "Invalid Indian mobile number. Must be a valid 10-digit mobile number starting with 6, 7, 8, or 9"
        )

    return cleaned


def mask_phone_number(raw_phone: Optional[str]) -> str:
    """
    Masks a phone number for privacy in logs, audit records, and UI displays.
    Keeps only the last 4 digits visible and masks all preceding characters with asterisks.

    Examples:
        '9876543210'    -> '******3210'
        '+919876543210' -> '*********3210'
        '09876543210'   -> '*******3210'
        '3210'          -> '3210'
        '210'           -> '***'
        ''              -> ''
        None            -> ''
    """
    if raw_phone is None:
        return ""

    raw_str = str(raw_phone).strip()
    if not raw_str:
        return ""

    # Mask all but the last 4 characters
    if len(raw_str) >= 4:
        return "*" * (len(raw_str) - 4) + raw_str[-4:]
    return "*" * len(raw_str)
