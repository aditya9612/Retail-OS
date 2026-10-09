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

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    clean = re.sub(r"[\s\-\(\)\.]", "", v)

    if not re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", clean):
        raise ValueError(
            f"{field_name} must be a 10-digit Indian mobile number starting with 6-9, "
            "or +91 followed by 10 digits starting with 6-9"
        )

    return clean


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


COMMON_TLD_TYPOS: dict[str, str] = {
    "comm": "com",
    "coom": "com",
    "con": "com",
    "cpm": "com",
    "cmo": "com",
    "ocm": "com",
    "xom": "com",
    "som": "com",
    "fom": "com",
    "vom": "com",
    "bom": "com",
    "comn": "com",
    "inn": "in",
    "ikn": "in",
    "orgg": "org",
    "ogr": "org",
    "nett": "net",
    "nte": "net",
    "eduu": "edu",
    "eud": "edu",
    "govv": "gov",
}

COMMON_DOMAIN_TYPOS: dict[str, str] = {
    "gmail.comm": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.coom": "gmail.com",
    "gmail.cm": "gmail.com",
    "gmail.cpm": "gmail.com",
    "gmail.om": "gmail.com",
    "gmail.ocm": "gmail.com",
    "gmail.cmo": "gmail.com",
    "gmai.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "yahoo.comm": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "yahoo.coom": "yahoo.com",
    "yahoo.cm": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "hotmail.comm": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "hotmail.coom": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "outlook.comm": "outlook.com",
    "outlook.con": "outlook.com",
    "outlook.coom": "outlook.com",
    "outlok.com": "outlook.com",
    "icloud.comm": "icloud.com",
    "icloud.con": "icloud.com",
    "icloud.coom": "icloud.com",
    "rediffmail.comm": "rediffmail.com",
    "rediffmail.con": "rediffmail.com",
}


def validate_email_address(
    value: Any,
    field_name: str = "Email",
    required: bool = True,
    max_length: int = 254,
) -> Optional[str]:
    """
    Validates email address syntax, domain structure, and protects against common domain/TLD typos.
    Rejects placeholders, empty/whitespace, invalid RFC formats, and misspelled domains (e.g. .comm).
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty")
        return None

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > max_length:
        raise ValueError(f"{field_name} cannot exceed {max_length} characters")

    if v.count("@") != 1:
        raise ValueError("Invalid email address")

    local_part, domain = v.rsplit("@", 1)
    local_part = local_part.strip().lower()
    domain = domain.strip().lower()

    if not local_part:
        raise ValueError("Email must contain a username before @")

    if len(local_part) > 64:
        raise ValueError("Email username must not exceed 64 characters")

    if local_part.startswith(".") or local_part.endswith("."):
        raise ValueError("Email username cannot start or end with a dot")

    if ".." in local_part:
        raise ValueError("Email username cannot contain consecutive dots")

    if not re.fullmatch(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$", local_part):
        raise ValueError("Email username contains invalid characters")

    if not domain:
        raise ValueError("Email must contain a valid domain")

    if len(domain) > 253:
        raise ValueError("Email domain is too long")

    if "." not in domain:
        raise ValueError("Email domain must contain a valid domain extension")

    if domain.startswith(".") or domain.endswith("."):
        raise ValueError("Email domain cannot start or end with a dot")

    if ".." in domain:
        raise ValueError("Email domain cannot contain consecutive dots")

    labels = domain.split(".")
    for label in labels:
        if not label:
            raise ValueError("Invalid email domain format")
        if label.startswith("-") or label.endswith("-"):
            raise ValueError(f"Invalid email domain label '{label}'")
        if not re.fullmatch(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", label):
            raise ValueError(f"Email domain contains invalid characters: '{label}'")

    tld = labels[-1]
    if not tld.isalpha():
        raise ValueError(f"Email domain extension '.{tld}' must contain only letters")

    if len(tld) < 2:
        raise ValueError(f"Email domain extension '.{tld}' is too short")

    if len(tld) > 24:
        raise ValueError(f"Email domain extension '.{tld}' is too long")

    if domain in COMMON_DOMAIN_TYPOS:
        suggested = COMMON_DOMAIN_TYPOS[domain]
        raise ValueError(f"Invalid email domain '{domain}'. Did you mean '@{suggested}'?")

    if tld in COMMON_TLD_TYPOS:
        suggested_tld = COMMON_TLD_TYPOS[tld]
        raise ValueError(f"Invalid email domain extension '.{tld}'. Did you mean '.{suggested_tld}'?")

    return f"{local_part}@{domain}"


def validate_email_format(
    value: Any,
    field_name: str = "Contact email",
    required: bool = False,
) -> Optional[str]:
    """
    Validates contact email address.
    Rejects placeholders, empty/whitespace, and invalid email formats.
    """
    return validate_email_address(value, field_name=field_name, required=required, max_length=100)


PAN_CARD_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
AADHAAR_CARD_PATTERN = re.compile(r"^[2-9][0-9]{11}$")


def validate_pan_number(
    value: Any,
    field_name: str = "PAN card number",
    required: bool = False,
) -> Optional[str]:
    """
    Validates Indian Permanent Account Number (PAN).
    Format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).
    Automatically strips whitespace and converts to uppercase.
    Rejects: wrong length, wrong characters, placeholders.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip().upper()
    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty or whitespace")
        return None

    if v in ("STRING", "NULL", "NONE", "UNDEFINED"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) != 10:
        raise ValueError(
            f"Invalid {field_name}. It must be exactly 10 characters long (e.g. ABCDE1234F)"
        )

    if not PAN_CARD_PATTERN.fullmatch(v):
        raise ValueError(
            f"Invalid {field_name} format '{v}'. It must contain 5 letters followed by 4 digits and 1 letter (e.g. ABCDE1234F)"
        )

    return v


def validate_aadhaar_number(
    value: Any,
    field_name: str = "Aadhaar number",
    required: bool = False,
) -> Optional[str]:
    """
    Validates Indian Aadhaar card number.
    Format: exactly 12 numeric digits, cannot start with 0 or 1.
    Automatically strips spaces and hyphens (e.g. '1234 5678 9012' -> '123456789012').
    Rejects: non-digits, length != 12, starting with 0/1, repeated dummy digits.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if isinstance(value, int):
        v = str(value)
    elif isinstance(value, str):
        v = value.strip()
    else:
        raise ValueError(f"{field_name} must be a string or integer")

    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty or whitespace")
        return None

    if v.lower() in ("string", "null", "none", "undefined"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    clean_v = re.sub(r"[\s\-]", "", v)

    if not clean_v.isdigit():
        raise ValueError(f"{field_name} must contain only numeric digits")

    if len(clean_v) != 12:
        raise ValueError(
            f"Invalid {field_name}. It must be exactly 12 digits (found {len(clean_v)} digits)"
        )

    if clean_v.startswith("0") or clean_v.startswith("1"):
        raise ValueError(
            f"Invalid {field_name}. Aadhaar number cannot start with 0 or 1"
        )

    if len(set(clean_v)) == 1:
        raise ValueError(
            f"Invalid {field_name}. Aadhaar number cannot contain 12 identical digits"
        )

    return clean_v


GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)


def validate_gstin_number(
    value: Any,
    field_name: str = "GSTIN",
    required: bool = False,
) -> Optional[str]:
    """
    Validates Indian 15-character Goods and Services Tax Identification Number (GSTIN).
    Format: 2 digits (state code 01-38, 97, 99), 10 chars (PAN), 1 entity digit, 'Z', 1 checksum digit.
    Automatically strips whitespace and converts to uppercase.
    Rejects placeholders, whitespace, invalid lengths, and invalid formats.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip().upper()
    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty")
        return None

    if v.lower() in ("string", "null", "none", "undefined", "-----", "@#$%%"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) != 15:
        raise ValueError(f"{field_name} must be exactly 15 characters")

    if not GSTIN_PATTERN.fullmatch(v):
        raise ValueError(f"Invalid {field_name} format")

    state_code = int(v[:2])
    if not (1 <= state_code <= 38 or state_code in (97, 99)):
        raise ValueError(f"Invalid state code '{v[:2]}' in {field_name}")

    return v


WEBSITE_PATTERN = re.compile(
    r"^(?:https?://)?(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?:/.*)?$"
)


def validate_website_url(
    value: Any,
    field_name: str = "Website",
    required: bool = False,
) -> Optional[str]:
    """
    Validates a website URL or domain name.
    Accepts: 'https://example.com', 'http://store.co.in', 'www.mystore.com', 'retailos.in'
    Rejects placeholders, whitespace, invalid domains, and dangerous script content.
    """
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty")
        return None

    if v.lower() in ("string", "null", "none", "undefined", "-----", "@#$%%"):
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > 255:
        raise ValueError(f"{field_name} cannot exceed 255 characters")

    if not WEBSITE_PATTERN.fullmatch(v):
        raise ValueError(f"Invalid {field_name.lower()} format")

    return v

