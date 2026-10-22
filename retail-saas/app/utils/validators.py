import re
from decimal import Decimal
from typing import Any, Optional


DISALLOWED_TEXT_PLACEHOLDERS = {
    "string", "null", "none", "undefined", "test", "dummy", "sample",
    "placeholder", "name", "description", "delivery", "unknown", "n/a", "na",
    "temp", "false", "true", "p0@#$", "ppppp", "123445"
}

DISALLOWED_CODE_PLACEHOLDERS = {
    "STRING", "NULL", "NONE", "UNDEFINED", "TEST", "DUMMY", "SAMPLE",
    "CODE", "DEFAULT", "TEMP", "NAME", "VALUE", "METHOD", "ZONE", "PARTNER"
}

FORBIDDEN_TEXT_SYMBOLS = set(r"\|[]{}<>?;:~^$%")


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
    numeric-only, special-character-only strings, repetitive spam ("ppppp"), and symbol spam.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    # Reject forbidden special symbols (\, |, [, ], {, }, <, >, ?, ;, :, ~, ^, $, %)
    if any(c in FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError(f"{field_name} contains invalid special characters")

    # Reject consecutive repeating symbols (e.g. ---, +++, //, ...)
    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive repeating symbols")

    # Must contain alphabetic letters
    alpha_chars = [c.lower() for c in v if c.isalpha()]
    alpha_count = len(alpha_chars)
    if alpha_count < 2:
        raise ValueError(f"{field_name} must contain at least 2 letters")

    # Must not be single character repeated (e.g. "ppppp", "aaaa")
    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repetitive characters '{value}'")

    # Digits must not dominate descriptive text (excluding addresses)
    digit_count = sum(1 for c in v if c.isdigit())
    if digit_count > alpha_count and not any(k in field_name.lower() for k in ["address", "tracking"]):
        raise ValueError(f"{field_name} cannot contain more digits than letters")

    return v


def validate_person_name(
    value: Any,
    field_name: str = "Delivery person name",
    required: bool = True,
) -> Optional[str]:
    """
    Validates a human person name.
    Rejects: numbers, placeholders ("string", "null"), special-only, empty/whitespace, repetitive spam.
    Allows: letters, spaces, hyphens, apostrophes, and periods (e.g. "Amit Shinde", "O'Connor").
    Requires at least 2 alphabetic characters and at least 2 distinct letters.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < 2 or len(v) > 100:
        raise ValueError(f"{field_name} must be between 2 and 100 characters")

    if any(c.isdigit() for c in v):
        raise ValueError(f"{field_name} cannot contain numbers")

    for c in v:
        if not (c.isalpha() or c in " '-."):
            raise ValueError(f"{field_name} contains invalid characters")

    if re.search(r"[-'.]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive repeating symbols")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(alpha_chars) < 2:
        raise ValueError(f"{field_name} must contain at least 2 letters")

    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repetitive characters '{value}'")

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
    Must start with a letter, contain at least two distinct letters, and reject
    numeric-only, single-character spam, zero-padding, and placeholders.
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

    clean_norm = re.sub(r"[^A-Z0-9]", "", v)
    if v in DISALLOWED_CODE_PLACEHOLDERS or clean_norm in DISALLOWED_CODE_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if not re.fullmatch(r"^[A-Z0-9_-]+$", v):
        raise ValueError(
            f"{field_name} can only contain uppercase letters, numbers, underscores, and hyphens"
        )

    if v.startswith(("-", "_")) or v.endswith(("-", "_")):
        raise ValueError(f"{field_name} cannot start or end with a hyphen or underscore")

    if "--" in v or "__" in v or "-_" in v or "_-" in v:
        raise ValueError(f"{field_name} cannot contain consecutive hyphens or underscores")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not v[0].isalpha():
        raise ValueError(f"{field_name} must start with an alphabetic letter")

    alpha_chars = [c for c in v if c.isalpha()]
    if len(alpha_chars) < 2:
        raise ValueError(f"{field_name} must contain at least 2 alphabetic letters")

    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repetitive characters '{value}'")

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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    clean = re.sub(r"[\s\-\(\)\.]", "", v)

    if not re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", clean):
        raise ValueError(
            f"{field_name} must be a 10-digit Indian mobile number starting with 6-9, "
            "or +91 followed by 10 digits starting with 6-9"
        )

    core_digits = clean[3:] if clean.startswith("+91") else clean

    # Reject full sequential / serial numbers (e.g. 9876543210, 6789012345, 8765432109)
    ascending_seq = "01234567890123456789"
    descending_seq = "98765432109876543210"
    if core_digits in descending_seq or core_digits in ascending_seq:
        raise ValueError(f"{field_name} cannot be a sequential serial number '{value}'")

    # Reject 7 or more consecutive ascending or descending sequential digits (e.g. 9123456789, 9876543200)
    for i in range(len(core_digits) - 6):
        sub = core_digits[i:i+7]
        if sub in "0123456789" or sub in "9876543210":
            raise ValueError(f"{field_name} cannot contain sequential serial digits '{value}'")

    # Reject identical digits (e.g. 9999999999, 8888888888, 7777777777, 6666666666)
    if len(set(core_digits)) == 1:
        raise ValueError(f"{field_name} cannot consist of identical repeated digits '{value}'")

    # Reject dummy repetitive sequence where remaining 9 digits are all identical (e.g. 6000000000, 7000000000, 8000000000, 9000000000, 6111111111)
    if len(set(core_digits[1:])) == 1:
        raise ValueError(f"{field_name} cannot consist of repetitive dummy digits '{value}'")

    # Reject 5 or more consecutive identical digits (e.g. 6000000000, 9800000123)
    if re.search(r"(\d)\1{4,}", core_digits):
        raise ValueError(f"{field_name} cannot contain 5 or more consecutive identical digits")

    # Reject ending with multiple dummy zeros (e.g. 6000000000, 9876500000)
    if core_digits.endswith("00000"):
        raise ValueError(f"{field_name} cannot end with multiple dummy zeros")

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
    numeric-only ("123", "123456"), special-only ("------", "###"), and repetitive characters.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < 3 or len(v) > 100:
        raise ValueError(f"{field_name} must be between 3 and 100 characters")

    for c in v:
        if not (c.isalnum() or c in "-_#/"):
            raise ValueError(f"{field_name} contains invalid characters")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    alnum_chars = [c for c in v if c.isalnum()]
    if not alnum_chars:
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    if len(set(alnum_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repetitive characters")

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
    Rejects: "string", placeholders, numeric-only, special-character-only values, and repetitive characters.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(alpha_chars) < 2:
        raise ValueError(
            f"{field_name} must contain meaningful address text with letters"
        )

    if len(set(alpha_chars)) < 2:
        raise ValueError(
            f"{field_name} cannot consist of repetitive characters"
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

    if len(set(p_str)) == 1:
        raise ValueError(
            f"Invalid pincode: '{p}'. Pincode cannot have all identical digits"
        )

    if p_str in {"123456", "654321"}:
        raise ValueError(
            f"Invalid pincode: '{p}'. Sequential dummy pincode not allowed"
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


INDIAN_STATES_AND_UTS: set[str] = {
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
}

NON_CITY_LOCATION_NAMES: set[str] = {
    "india", "japan", "china", "nepal", "bhutan", "bangladesh", "pakistan",
    "sri lanka", "afghanistan", "united states", "usa", "us", "united kingdom",
    "uk", "canada", "australia", "germany", "france", "italy", "spain",
    "russia", "singapore", "malaysia", "thailand", "unknown", "world",
    "global", "country", "state", "city", "none", "null", "string"
}

INDIAN_STATE_PINCODE_PREFIXES: dict[str, set[str]] = {
    "Andhra Pradesh": {"51", "52", "53"},
    "Arunachal Pradesh": {"79"},
    "Assam": {"78"},
    "Bihar": {"80", "81", "82", "83", "84", "85"},
    "Chhattisgarh": {"49"},
    "Goa": {"40"},  # 403xxx
    "Gujarat": {"36", "37", "38", "39"},
    "Haryana": {"12", "13"},
    "Himachal Pradesh": {"17"},
    "Jharkhand": {"81", "82", "83"},
    "Karnataka": {"56", "57", "58", "59"},
    "Kerala": {"67", "68", "69"},
    "Madhya Pradesh": {"45", "46", "47", "48"},
    "Maharashtra": {"40", "41", "42", "43", "44"},
    "Manipur": {"79"},
    "Meghalaya": {"79"},
    "Mizoram": {"79"},
    "Nagaland": {"79"},
    "Odisha": {"75", "76", "77"},
    "Punjab": {"14", "15", "16"},
    "Rajasthan": {"30", "31", "32", "33", "34"},
    "Sikkim": {"73"},
    "Tamil Nadu": {"60", "61", "62", "63", "64", "65", "66"},
    "Telangana": {"50"},
    "Tripura": {"79"},
    "Uttar Pradesh": {"20", "21", "22", "23", "24", "25", "26", "27", "28"},
    "Uttarakhand": {"24", "26"},
    "West Bengal": {"70", "71", "72", "73", "74"},
    "Andaman and Nicobar Islands": {"74"},
    "Chandigarh": {"16"},
    "Dadra and Nagar Haveli and Daman and Diu": {"39"},
    "Delhi": {"11"},
    "Jammu and Kashmir": {"18", "19"},
    "Ladakh": {"19"},
    "Lakshadweep": {"68"},
    "Puducherry": {"60"},  # 605xxx
}

MAJOR_INDIAN_CITIES_STATE_MAP: dict[str, str] = {
    "mumbai": "Maharashtra",
    "pune": "Maharashtra",
    "nagpur": "Maharashtra",
    "nashik": "Maharashtra",
    "thane": "Maharashtra",
    "aurangabad": "Maharashtra",
    "chhatrapati sambhajinagar": "Maharashtra",
    "solapur": "Maharashtra",
    "amravati": "Maharashtra",
    "kolhapur": "Maharashtra",
    "navi mumbai": "Maharashtra",
    "pimpri-chinchwad": "Maharashtra",
    "ahmedabad": "Gujarat",
    "surat": "Gujarat",
    "vadodara": "Gujarat",
    "rajkot": "Gujarat",
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "mysuru": "Karnataka",
    "mysore": "Karnataka",
    "hubli": "Karnataka",
    "mangalore": "Karnataka",
    "mangaluru": "Karnataka",
    "hyderabad": "Telangana",
    "warangal": "Telangana",
    "chennai": "Tamil Nadu",
    "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu",
    "tiruchirappalli": "Tamil Nadu",
    "salem": "Tamil Nadu",
    "kolkata": "West Bengal",
    "howrah": "West Bengal",
    "durgapur": "West Bengal",
    "asansol": "West Bengal",
    "jaipur": "Rajasthan",
    "jodhpur": "Rajasthan",
    "udaipur": "Rajasthan",
    "kota": "Rajasthan",
    "lucknow": "Uttar Pradesh",
    "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh",
    "varanasi": "Uttar Pradesh",
    "prayagraj": "Uttar Pradesh",
    "allahabad": "Uttar Pradesh",
    "noida": "Uttar Pradesh",
    "ghaziabad": "Uttar Pradesh",
    "meerut": "Uttar Pradesh",
    "patna": "Bihar",
    "gaya": "Bihar",
    "bhagalpur": "Bihar",
    "muzaffarpur": "Bihar",
    "bhopal": "Madhya Pradesh",
    "indore": "Madhya Pradesh",
    "jabalpur": "Madhya Pradesh",
    "gwalior": "Madhya Pradesh",
    "ranchi": "Jharkhand",
    "jamshedpur": "Jharkhand",
    "dhanbad": "Jharkhand",
    "bhubaneswar": "Odisha",
    "cuttack": "Odisha",
    "rourkela": "Odisha",
    "chandigarh": "Chandigarh",
    "ludhiana": "Punjab",
    "amritsar": "Punjab",
    "jalandhar": "Punjab",
    "dehradun": "Uttarakhand",
    "haridwar": "Uttarakhand",
    "shimla": "Himachal Pradesh",
    "srinagar": "Jammu and Kashmir",
    "jammu": "Jammu and Kashmir",
    "guwahati": "Assam",
    "visakhapatnam": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh",
    "guntur": "Andhra Pradesh",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "panaji": "Goa",
    "margao": "Goa",
    "raipur": "Chhattisgarh",
}

MAJOR_CITY_PINCODE_PREFIXES: dict[str, set[str]] = {
    "mumbai": {"400"},
    "navi mumbai": {"400", "410"},
    "thane": {"400", "401"},
    "pune": {"411", "412"},
    "pimpri-chinchwad": {"411"},
    "nashik": {"422"},
    "nagpur": {"440", "441"},
    "aurangabad": {"431"},
    "chhatrapati sambhajinagar": {"431"},
    "kolhapur": {"416"},
    "solapur": {"413"},
    "satara": {"415"},
    "amravati": {"444"},
    "ahmednagar": {"414"},
    "jalgaon": {"425"},
    "nanded": {"431"},
    "delhi": {"110"},
    "new delhi": {"110"},
    "bengaluru": {"560", "562"},
    "bangalore": {"560", "562"},
    "hyderabad": {"500"},
    "chennai": {"600"},
    "kolkata": {"700"},
    "ahmedabad": {"380", "382"},
    "surat": {"394", "395"},
    "vadodara": {"390", "391"},
    "rajkot": {"360"},
    "jaipur": {"302"},
    "jodhpur": {"342"},
    "lucknow": {"226"},
    "kanpur": {"208"},
    "agra": {"282"},
    "varanasi": {"221"},
    "noida": {"201"},
    "ghaziabad": {"201"},
    "patna": {"800"},
    "bhopal": {"462"},
    "indore": {"452"},
    "chandigarh": {"160"},
    "dehradun": {"248"},
    "shimla": {"171"},
    "srinagar": {"190"},
    "jammu": {"180"},
    "ranchi": {"834"},
    "bhubaneswar": {"751"},
    "guwahati": {"781"},
    "visakhapatnam": {"530"},
    "vijayawada": {"520"},
    "panaji": {"403"},
    "margao": {"403"},
    "raipur": {"492"},
}


def validate_indian_state(value: Any, required: bool = False) -> Optional[str]:
    """
    Validates that a state is an official Indian State or Union Territory.
    Accepts case-insensitive matching and returns the standard title-cased name.
    Rejects placeholders, numeric/symbol spam, and city names (e.g. 'Pune').
    """
    if value is None:
        if required:
            raise ValueError("State cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError("State must be a string")

    v = value.strip()
    if not v:
        raise ValueError("State cannot be empty or whitespace")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"State cannot be placeholder '{value}'")

    if v.isdigit():
        raise ValueError("State cannot be numeric-only")

    if any(c in FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError("State contains invalid special characters")

    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError("State cannot contain consecutive repeating symbols")

    # Reject city names supplied as states (e.g., state='Pune', 'Mumbai')
    if v.lower() in MAJOR_INDIAN_CITIES_STATE_MAP:
        correct_state = MAJOR_INDIAN_CITIES_STATE_MAP[v.lower()]
        raise ValueError(
            f"Invalid Indian state: '{value}'. '{value}' is a city in {correct_state}, not a state"
        )

    matched = next((s for s in INDIAN_STATES_AND_UTS if s.lower() == v.lower()), None)
    if not matched:
        raise ValueError(
            f"Invalid Indian state or union territory: '{value}'. Must be a valid Indian state or UT"
        )

    return matched


def validate_city_name(value: Any, required: bool = False) -> Optional[str]:
    """
    Validates an Indian city name.
    Rejects placeholders, numeric/symbol spam, countries, and Indian state/UT names (e.g. 'Maharashtra').
    Allows letters, spaces, hyphens, and apostrophes.
    """
    if value is None:
        if required:
            raise ValueError("City cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError("City must be a string")

    v = value.strip()
    if not v:
        raise ValueError("City cannot be empty or whitespace")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"City cannot be placeholder '{value}'")

    if len(v) < 2 or len(v) > 100:
        raise ValueError("City must be between 2 and 100 characters")

    if v.isdigit():
        raise ValueError("City cannot be numeric-only")

    if any(c in FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError("City contains invalid special characters")

    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError("City cannot contain consecutive repeating symbols")

    # Reject Indian State/UT names passed as city
    if v.lower() in {s.lower() for s in INDIAN_STATES_AND_UTS}:
        raise ValueError(
            f"City cannot be an Indian state or union territory name: '{value}'"
        )

    # Reject country or global names
    if v.lower() in NON_CITY_LOCATION_NAMES:
        raise ValueError(f"City cannot be a country or invalid location name: '{value}'")

    if not re.fullmatch(r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*", v):
        raise ValueError("City must contain only letters, spaces, hyphens and apostrophes")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(alpha_chars) < 2:
        raise ValueError("City must contain at least 2 letters")

    if len(set(alpha_chars)) < 2:
        raise ValueError(f"City cannot consist of repetitive characters '{value}'")

    return v.title() if len(v) > 3 else v


def validate_zone_pincodes_match_geo(
    pincodes: list[str],
    state: Optional[str] = None,
    city: Optional[str] = None,
) -> None:
    """
    Validates that each 6-digit Indian pincode matches the specified state and city based on
    official Indian Postal PIN code prefixes.
    """
    if not pincodes:
        return

    # 1. State-level prefix matching (first 2 digits)
    if state:
        canonical_state = next((s for s in INDIAN_STATES_AND_UTS if s.lower() == state.lower()), state)
        allowed_state_prefixes = INDIAN_STATE_PINCODE_PREFIXES.get(canonical_state)

        if allowed_state_prefixes:
            for p in pincodes:
                if not isinstance(p, str) or len(p) != 6 or not p.isdigit():
                    continue

                prefix2 = p[:2]

                # Specific check for Goa (403xxx) vs Maharashtra (400-402, 404-449)
                if canonical_state == "Goa" and not p.startswith("403"):
                    raise ValueError(
                        f"Pincode '{p}' does not belong to state 'Goa'. Goa pincodes start with '403'"
                    )
                if canonical_state == "Maharashtra" and p.startswith("403"):
                    raise ValueError(
                        f"Pincode '{p}' belongs to Goa (403xxx), not Maharashtra"
                    )

                if prefix2 not in allowed_state_prefixes:
                    sorted_prefixes = ", ".join(sorted(allowed_state_prefixes))
                    raise ValueError(
                        f"Pincode '{p}' does not belong to state '{canonical_state}'. "
                        f"Pincodes for '{canonical_state}' must start with [{sorted_prefixes}]"
                    )

    # 2. City-level prefix matching (first 3 digits)
    if city:
        city_lower = city.strip().lower()
        allowed_city_prefixes = MAJOR_CITY_PINCODE_PREFIXES.get(city_lower)

        if allowed_city_prefixes:
            for p in pincodes:
                if not isinstance(p, str) or len(p) != 6 or not p.isdigit():
                    continue

                prefix3 = p[:3]
                if prefix3 not in allowed_city_prefixes:
                    sorted_prefixes = ", ".join(sorted(allowed_city_prefixes))
                    raise ValueError(
                        f"Pincode '{p}' does not match city '{city}'. "
                        f"Pincodes for '{city}' must start with [{sorted_prefixes}]"
                    )


validate_zone_pincodes_match_state = validate_zone_pincodes_match_geo


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
            if not allow_zero:
                raise ValueError(f"{field_name} is required and must be greater than zero")
            return Decimal("0.00")
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
    max_value: Optional[int] = 60,
) -> Optional[int]:
    """
    Validates that a field is a strict positive integer (> 0).
    Rejects 0, negative integers, floats/decimals, booleans, strings, and values exceeding max_value.
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

    if max_value is not None and value > max_value:
        raise ValueError(f"{field_name} cannot exceed {max_value}")

    return value


def validate_carrier_credentials(
    value: Any,
    field_name: str = "Credential",
    required: bool = False,
) -> Optional[str]:
    """
    Validates API key / API secret credentials.
    Rejects placeholders ("string", "null", "none"), empty/whitespace, numeric-only,
    forbidden special characters (\\, |, [], {}, <>, ?, ;, :, ~, ^, $, %),
    consecutive repeating symbols, repetitive spam, and dummy values ("0-0", "@#e0").
    Requires between 6 and 255 characters with at least 4 alphanumeric characters.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) < 6 or len(v) > 255:
        raise ValueError(f"{field_name} must be between 6 and 255 characters")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot be numeric-only")

    # Reject forbidden symbols (\, |, [, ], {, }, <, >, ?, ;, :, ~, ^, $, %)
    if any(c in FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError(f"{field_name} contains invalid special characters")

    # Reject consecutive repeating symbols (e.g. ---, +++, ***)
    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive repeating symbols")

    alnum = [c for c in v if c.isalnum()]
    if len(alnum) < 4:
        raise ValueError(f"{field_name} must contain at least 4 alphanumeric characters")

    # Reject repetitive characters like pppppp, aaaaaa, 000000
    if len(set(v)) < 3:
        raise ValueError(f"{field_name} cannot consist of repetitive characters '{value}'")

    return v


def validate_tracking_url(
    value: Any,
    field_name: str = "Tracking URL template",
    required: bool = False,
) -> Optional[str]:
    """
    Validates tracking URL template.
    Must start with http:// or https:// and have valid URL structure with a valid domain.
    Allows template placeholder '{tracking_number}' or '{tracking_id}'.
    Rejects: numeric-only hosts (e.g. https://0000), special character spam,
    invalid domains, and placeholders.
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

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(f"{field_name} cannot be placeholder '{value}'")

    if len(v) > 255:
        raise ValueError(f"{field_name} cannot exceed 255 characters")

    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")

    # Check for forbidden raw symbols (allowing valid template braces e.g. {tracking_number})
    for c in r"\|<>?;~^$%":
        if c in v:
            raise ValueError(f"{field_name} contains invalid characters")

    scheme, rest = v.split("://", 1)
    if not rest or len(rest.strip()) < 3:
        raise ValueError(f"{field_name} is malformed")

    # Extract host
    host_part = rest.split("/")[0].split("?")[0].split("#")[0].strip()
    if not host_part:
        raise ValueError(f"{field_name} must contain a host")

    host = host_part.split(":")[0].strip()

    if host.isdigit():
        raise ValueError(f"{field_name} host cannot be numeric-only")

    if any(c in r"[]{}()\/!@#$^&*+=;:<>?" for c in host):
        raise ValueError(f"{field_name} host contains invalid characters")

    if re.search(r"[-_]{2,}", host):
        raise ValueError(f"{field_name} host cannot contain consecutive hyphens or underscores")

    if host.startswith(("-", ".")) or host.endswith(("-", ".")):
        raise ValueError(f"{field_name} host cannot start or end with a hyphen or dot")

    if host.lower() != "localhost":
        if "." not in host:
            raise ValueError(f"{field_name} must contain a valid domain name")
        labels = host.split(".")
        tld = labels[-1]
        is_ipv4 = len(labels) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in labels)
        if not is_ipv4:
            if not tld.isalpha() or len(tld) < 2:
                raise ValueError(f"{field_name} must have a valid domain extension")

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

    if len(local_part) < 2:
        raise ValueError("Email username must be at least 2 characters")

    if len(local_part) > 64:
        raise ValueError("Email username must not exceed 64 characters")

    if local_part.isdigit():
        raise ValueError("Email username cannot be purely numeric")

    if not any(c.isalpha() for c in local_part):
        raise ValueError("Email username must contain at least one letter")

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

