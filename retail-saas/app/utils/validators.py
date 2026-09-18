import re
from decimal import Decimal
from typing import Any, Optional


def validate_meaningful_text(
    value: Any,
    field_name: str = "Field",
    min_length: int = 2,
    max_length: int = 2000,
    required: bool = True,
) -> Optional[str]:
    """
    Validates that a string field contains meaningful textual content.
    Rejects: None (if required), empty/whitespace, placeholders ("string", "null", "none", "undefined"),
    numeric-only, and special-character-only strings.
    Allows legitimate punctuation and spaces.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} cannot consist only of special characters")

    return v


def validate_person_name(
    value: Any,
    field_name: str = "Delivery person name",
    required: bool = True,
) -> Optional[str]:
    """
    Validates a human person name.
    Rejects: numbers, placeholders ("string", "null"), special-only, empty/whitespace.
    Allows: letters, spaces, hyphens, apostrophes, and periods (e.g. "Amit Shinde", "O'Connor").
    Requires at least 2 alphabetic characters.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < 2 or len(v) > 100:
        raise ValueError(f"{field_name} must be between 2 and 100 characters")

    if any(c.isdigit() for c in v):
        raise ValueError(f"{field_name} cannot contain numbers")

    for c in v:
        if not (c.isalpha() or c in " '-."):
            raise ValueError(f"{field_name} contains invalid characters")

    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count < 2:
        raise ValueError(f"{field_name} must contain at least 2 letters")

    return v


def validate_code(
    value: Any,
    field_name: str = "Code",
    min_length: int = 2,
    max_length: int = 50,
    required: bool = True,
) -> Optional[str]:
    """
    Validates uppercase identifier codes across Delivery Method, Zone, and Partner.
    Format: Alphanumeric uppercase with hyphens and underscores (^[A-Z0-9_-]+$).
    Must contain at least one letter. Rejects numeric-only, special-only, and placeholders.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip().upper()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v in ("STRING", "NULL", "NONE", "UNDEFINED"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if not re.fullmatch(r"^[A-Z0-9_-]+$", v):
        raise ValueError(
            f"{field_name} can only contain uppercase letters, numbers, underscores, and hyphens"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not any(c.isalpha() for c in v):
        raise ValueError(f"{field_name} must contain at least one letter")

    return v


def validate_indian_phone(
    value: Any,
    field_name: str = "Contact phone",
    required: bool = False,
) -> Optional[str]:
    """
    Validates Indian mobile phone numbers.
    Accepted: 10 digits starting with 6, 7, 8, 9 OR +91 followed by 10 digits starting with 6, 7, 8, 9.
    Rejects: special characters (including hyphens), letters, wrong lengths, wrong initial digit.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if not re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", v):
        raise ValueError(
            f"{field_name} must be a 10-digit Indian mobile number starting with 6-9, "
            "or +91 followed by 10 digits starting with 6-9"
        )

    return v


def validate_tracking_number(
    value: Any,
    field_name: str = "Tracking number",
    required: bool = False,
) -> Optional[str]:
    """
    Validates tracking numbers based on existing project conventions.
    Length: 3 to 100 characters.
    Allowed chars: alphanumeric and -_#/
    Rejects: null/empty (if required), placeholders ("string", "null"),
    numeric-only ("123", "123456"), and special-only ("------", "###").
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < 3 or len(v) > 100:
        raise ValueError(f"{field_name} must be between 3 and 100 characters")

    for c in v:
        if not (c.isalnum() or c in "-_#/"):
            raise ValueError(f"{field_name} contains invalid characters")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    return v


def validate_real_address(
    value: Any,
    field_name: str = "Delivery address",
    min_length: int = 3,
    max_length: int = 500,
    required: bool = True,
) -> Optional[str]:
    """
    Validates real-world addresses.
    Allows: numbers, letters, spaces, commas, hyphens, slashes, building/flat numbers, PIN codes.
    Rejects: "string", placeholders, numeric-only, and special-character-only values.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count < 2:
        raise ValueError(
            f"{field_name} must contain meaningful address text with letters"
        )

    return v


def validate_single_pincode(p: Any) -> str:
    """
    Validates an Indian postal PIN code.
    Exactly 6 digits, first digit 1-9 (100000 - 999999).
    Rejects booleans, decimals, negatives, alphabetic/special chars.
    """
    if p is None:
        raise ValueError("Pincode cannot be null")
    if isinstance(p, bool):
        raise ValueError("Pincode cannot be a boolean")
    if isinstance(p, float):
        raise ValueError("Pincode cannot be a decimal number")

    if isinstance(p, int):
        p_str = str(p)
    elif isinstance(p, str):
        p_str = p.strip()
    else:
        raise ValueError("Pincode must be a 6-digit string or integer")

    if not p_str.isdigit() or len(p_str) != 6:
        raise ValueError(
            f"Invalid pincode: '{p}'. Pincode must contain exactly 6 digits"
        )

    if p_str.startswith("0"):
        raise ValueError(
            f"Invalid pincode: '{p}'. First digit of Indian pincode cannot be 0"
        )

    return p_str


def validate_pincodes_list(value: Any, required: bool = True) -> list[str]:
    """
    Validates a list of 6-digit postal PIN codes.
    De-duplicates entries while preserving order.
    """
    if value is None:
        if required:
            raise ValueError("Pincodes list cannot be null")
        return []

    if not isinstance(value, (list, tuple, set)):
        raise ValueError("Pincodes must be a list of 6-digit pincode strings")

    if required and len(value) == 0:
        raise ValueError("Pincodes list cannot be empty")

    validated: list[str] = []
    seen: set[str] = set()
    for item in value:
        p = validate_single_pincode(item)
        if p not in seen:
            seen.add(p)
            validated.append(p)

    return validated


def validate_strict_bool(
    value: Any,
    field_name: str = "is_active",
    required: bool = True,
) -> Optional[bool]:
    """
    Validates strict boolean. Accepts only True or False.
    Rejects 'true', 'false', '1', '0', 1, 0, and null (if required).
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if isinstance(value, bool):
        return value

    raise ValueError(f"{field_name} must be a boolean (true or false)")


def validate_positive_money(
    value: Any,
    field_name: str = "Cost",
    required: bool = True,
    allow_zero: bool = True,
) -> Optional[Decimal]:
    """
    Validates a monetary amount.
    Accepts Decimal, float, int.
    If allow_zero is True, >= 0.00 is accepted.
    Rejects booleans, negative values, and non-numeric strings.
    """
    if value is None:
        if required:
            return Decimal("0.00") if allow_zero else None
        return None

    if isinstance(value, bool):
        raise ValueError(f"{field_name} cannot be a boolean")

    if isinstance(value, str):
        v_str = value.strip()
        if not v_str or v_str.lower() in ("string", "null", "none"):
            raise ValueError(f"{field_name} must be a valid numeric monetary value")
        try:
            d = Decimal(v_str)
        except Exception:
            raise ValueError(f"{field_name} must be a valid decimal number")
    elif isinstance(value, (int, float, Decimal)):
        try:
            d = Decimal(str(value))
        except Exception:
            raise ValueError(f"{field_name} must be a valid decimal number")
    else:
        raise ValueError(f"{field_name} must be a valid numeric monetary value")

    if allow_zero:
        if d < Decimal("0.00"):
            raise ValueError(f"{field_name} cannot be negative")
    else:
        if d <= Decimal("0.00"):
            raise ValueError(f"{field_name} must be greater than zero")

    return d


def validate_positive_int(
    value: Any,
    field_name: str = "Estimated days",
    required: bool = False,
) -> Optional[int]:
    """
    Validates that a field is a strict positive integer (> 0).
    Rejects 0, negative integers, floats/decimals, booleans, and strings.
    Does not enforce any arbitrary upper limit.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if isinstance(value, bool):
        raise ValueError(f"{field_name} cannot be a boolean")

    if isinstance(value, float):
        raise ValueError(f"{field_name} must be an integer, not decimal")

    if isinstance(value, str):
        raise ValueError(f"{field_name} must be an integer, not string")

    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")

    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer (> 0)")

    return value


def validate_carrier_credentials(
    value: Any,
    field_name: str = "Credential",
    required: bool = False,
) -> Optional[str]:
    """
    Validates API key / API secret credentials.
    Rejects placeholders ("string", "null", "none"), empty/whitespace, and special-only strings.
    Preserves actual carrier credentials up to 255 characters.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > 255:
        raise ValueError(f"{field_name} cannot exceed 255 characters")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} cannot consist only of special characters")

    return v


def validate_tracking_url(
    value: Any,
    field_name: str = "Tracking URL template",
    required: bool = False,
) -> Optional[str]:
    """
    Validates tracking URL template.
    Must start with http:// or https:// and have valid URL structure.
    Allows template placeholder '{tracking_number}'.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > 255:
        raise ValueError(f"{field_name} cannot exceed 255 characters")

    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")

    if len(v.split("://", 1)[1].strip()) < 3:
        raise ValueError(f"{field_name} is malformed")

    return v


def validate_email_format(
    value: Any,
    field_name: str = "Contact email",
    required: bool = False,
) -> Optional[str]:
    """
    Validates contact email address.
    Rejects placeholders, empty/whitespace, and invalid email formats.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > 100:
        raise ValueError(f"{field_name} must be at most 100 characters")

    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
        raise ValueError(f"Invalid {field_name.lower()} format")

    return v
