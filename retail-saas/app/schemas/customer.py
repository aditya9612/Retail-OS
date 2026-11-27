from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Literal, Any
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from app.schemas.order import OrderResponse
from app.utils.validators import validate_email_address, validate_gstin_number


class CustomerExportStatus(str, Enum):
    all = "all"
    active = "active"
    inactive = "inactive"


class CustomerExportFormat(str, Enum):
    excel = "excel"
    pdf = "pdf"


def validate_phone_number(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Phone number must be a string")

    v = v.strip()

    if not v:
        raise ValueError("Phone number cannot be empty or whitespace")

    if not re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", v):
        raise ValueError(
            "Phone number must be 10 digits starting with 6-9, "
            "or +91 followed by 10 digits starting with 6-9"
        )

    core_digits = v[3:] if v.startswith("+91") else v

    # Reject full sequential / serial numbers (e.g. 9876543210, 6789012345, 8765432109)
    ascending_seq = "01234567890123456789"
    descending_seq = "98765432109876543210"
    if core_digits in descending_seq or core_digits in ascending_seq:
        raise ValueError("Phone number cannot be a sequential serial number")

    # Reject 7 or more consecutive ascending or descending sequential digits (e.g. 9123456789, 9876543200)
    for i in range(len(core_digits) - 6):
        sub = core_digits[i:i+7]
        if sub in "0123456789" or sub in "9876543210":
            raise ValueError("Phone number cannot contain sequential serial digits")

    # Reject identical repeated digits (e.g. 9999999999, 8888888888, 7777777777, 6666666666)
    if len(set(core_digits)) == 1:
        raise ValueError("Phone number cannot consist of identical repeated digits")

    # Reject repetitive dummy digits where remaining 9 digits are identical (e.g. 9000000000, 8000000000, 7000000000, 6000000000, 9111111111)
    if len(set(core_digits[1:])) == 1:
        raise ValueError("Phone number cannot consist of repetitive dummy digits")

    # Reject 5 or more consecutive identical digits (e.g. 9800000123, 9999912345)
    if re.search(r"(\d)\1{4,}", core_digits):
        raise ValueError("Phone number cannot contain 5 or more consecutive identical digits")

    # Reject ending with multiple dummy zeros (e.g. 9876500000, 9123400000)
    if core_digits.endswith("00000"):
        raise ValueError("Phone number cannot end with multiple dummy zeros")

    return v


def validate_customer_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Name must be a string")

    v = v.strip()

    if len(v) < 2 or len(v) > 255:
        raise ValueError("Name must be between 2 and 255 characters")

    if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
        raise ValueError(f"Name cannot be placeholder '{v}'")

    if not any(c.isalpha() for c in v):
        raise ValueError(
            "Name must contain at least one alphabetic character"
        )

    if v.isdigit():
        raise ValueError("Name cannot consist only of digits")

    alpha_count = sum(1 for c in v if c.isalpha())

    if alpha_count < 2:
        raise ValueError(
            "Name must contain at least two alphabetic characters"
        )

    for c in v:
        if not (c.isalpha() or c in " '-."):
            raise ValueError(
                "Name contains invalid characters. Only letters, spaces, "
                "apostrophes, hyphens, and periods are allowed"
            )

    return v


CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS = {
    "string", "null", "none", "undefined", "test", "dummy", "sample",
    "placeholder", "name", "description", "unknown", "n/a", "na",
    "temp", "false", "true", "p0@#$", "ppppp", "123445"
}

CUSTOMER_FORBIDDEN_TEXT_SYMBOLS = set(r"\|[]{}<>~^")


def validate_meaningful_text(
    v: Optional[str],
    field_name: str = "Field",
    min_length: int = 1,
    max_length: int = 2000,
    required: bool = True,
) -> Optional[str]:

    if v is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(v, str):
        raise ValueError(f"{field_name} must be a string")

    v = v.strip()

    if not v:
        if required:
            raise ValueError(
                f"{field_name} cannot be empty or whitespace"
            )
        return None

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between "
            f"{min_length} and {max_length} characters"
        )

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(
            f"{field_name} cannot be placeholder '{v}'"
        )

    if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError(f"{field_name} contains invalid special characters")

    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive repeating symbols")

    dangerous_patterns = [
        r"<\s*script",
        r"<\s*/\s*script",
        r"<\s*iframe",
        r"<\s*style",
        r"javascript\s*:",
        r"onload\s*=",
        r"onerror\s*=",
        r"<\s*img",
        r"<\s*a\s+",
        r"alert\s*\(",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, v, re.IGNORECASE):
            raise ValueError(
                f"{field_name} contains invalid or dangerous "
                "HTML/script content"
            )

    if "<" in v and ">" in v:
        raise ValueError(
            f"HTML tags are not allowed in {field_name.lower()}"
        )

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    alpha_count = len(alpha_chars)

    if alpha_count == 0:
        if v.isdigit():
            raise ValueError(
                f"{field_name} cannot be numeric-only"
            )

        raise ValueError(
            f"{field_name} must contain meaningful text with letters, "
            "not only numbers or symbols"
        )

    if len(alpha_chars) >= 2 and len(set(alpha_chars)) < 2:
        raise ValueError(
            f"{field_name} cannot consist of repetitive characters '{v}'"
        )

    return v


FORBIDDEN_ADDRESS_SYMBOLS = {'!', ';', '$', '%', '^', '*', '~', '<', '>', '{', '}', '[', ']', '|', '`', '?'}


def validate_address(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    v = v.strip()

    if not v:
        raise ValueError(
            "Address cannot be empty or whitespace"
        )

    if len(v) < 3:
        raise ValueError("Address must be at least 3 characters long")

    if any(c in FORBIDDEN_ADDRESS_SYMBOLS for c in v):
        raise ValueError("Address contains invalid special characters")

    if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
        raise ValueError(f"Address cannot be placeholder '{v}'")

    if v.isdigit():
        raise ValueError("Address cannot consist only of numbers")

    letters = re.findall(r"[a-zA-Z]", v)
    if len(letters) < 3:
        raise ValueError("Address must contain at least 3 alphabetic characters")

    if re.search(r"[-_.,/#]{3,}", v):
        raise ValueError("Address cannot contain consecutive repeating symbols")

    clean_chars = v.replace(" ", "").lower()
    if len(set(clean_chars)) == 1 and len(clean_chars) >= 2:
        raise ValueError("Address cannot consist of repeating characters")

    validate_address_geo_consistency(v)

    return v


# Indian states and Union Territories mapping for address geolocation consistency
INDIAN_STATES_MAP: dict[str, str] = {
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "uttaranchal": "Uttarakhand",
    "west bengal": "West Bengal",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "chandigarh": "Chandigarh",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "jammu and kashmir": "Jammu and Kashmir",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
}

GSTIN_STATE_CODE_MAP: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

# Major districts and cities across Indian states and Union Territories
INDIAN_DISTRICT_TO_STATES: dict[str, set[str]] = {
    # Maharashtra
    "mumbai": {"Maharashtra"},
    "pune": {"Maharashtra"},
    "nagpur": {"Maharashtra"},
    "nashik": {"Maharashtra"},
    "thane": {"Maharashtra"},
    "aurangabad": {"Maharashtra", "Bihar"},
    "chhatrapati sambhajinagar": {"Maharashtra"},
    "solapur": {"Maharashtra"},
    "amravati": {"Maharashtra"},
    "kolhapur": {"Maharashtra"},
    "navi mumbai": {"Maharashtra"},
    "pimpri-chinchwad": {"Maharashtra"},
    "pimpri chinchwad": {"Maharashtra"},
    "satara": {"Maharashtra"},
    "sangli": {"Maharashtra"},
    "jalgaon": {"Maharashtra"},
    "ahmednagar": {"Maharashtra"},
    "ahilyanagar": {"Maharashtra"},
    "dhule": {"Maharashtra"},
    "nandurbar": {"Maharashtra"},
    "jalna": {"Maharashtra"},
    "parbhani": {"Maharashtra"},
    "hingoli": {"Maharashtra"},
    "beed": {"Maharashtra"},
    "nanded": {"Maharashtra"},
    "dharashiv": {"Maharashtra"},
    "osmanabad": {"Maharashtra"},
    "latur": {"Maharashtra"},
    "buldhana": {"Maharashtra"},
    "akola": {"Maharashtra"},
    "washim": {"Maharashtra"},
    "yavatmal": {"Maharashtra"},
    "wardha": {"Maharashtra"},
    "chandrapur": {"Maharashtra"},
    "bhandara": {"Maharashtra"},
    "gondia": {"Maharashtra"},
    "gadchiroli": {"Maharashtra"},
    "ratnagiri": {"Maharashtra"},
    "sindhudurg": {"Maharashtra"},
    "raigad": {"Maharashtra"},
    "palghar": {"Maharashtra"},
    "panvel": {"Maharashtra"},
    "kalyan": {"Maharashtra"},
    "dombivli": {"Maharashtra"},
    "vasai": {"Maharashtra"},
    "virar": {"Maharashtra"},
    "ulhasnagar": {"Maharashtra"},
    "malegaon": {"Maharashtra"},
    "ichalkaranji": {"Maharashtra"},
    "baramati": {"Maharashtra"},
    # Rajasthan
    "jaisalmer": {"Rajasthan"},
    "jaipur": {"Rajasthan"},
    "jodhpur": {"Rajasthan"},
    "udaipur": {"Rajasthan"},
    "kota": {"Rajasthan"},
    "bikaner": {"Rajasthan"},
    "ajmer": {"Rajasthan"},
    "bhilwara": {"Rajasthan"},
    "alwar": {"Rajasthan"},
    "bharatpur": {"Rajasthan"},
    "sikar": {"Rajasthan"},
    "pali": {"Rajasthan"},
    "sri ganganagar": {"Rajasthan"},
    "ganganagar": {"Rajasthan"},
    "barmer": {"Rajasthan"},
    "chittorgarh": {"Rajasthan"},
    "jhunjhunu": {"Rajasthan"},
    "churu": {"Rajasthan"},
    "nagaur": {"Rajasthan"},
    "dholpur": {"Rajasthan"},
    "sawai madhopur": {"Rajasthan"},
    "tonk": {"Rajasthan"},
    "bundi": {"Rajasthan"},
    "jhalawar": {"Rajasthan"},
    "hanumangarh": {"Rajasthan"},
    "banswara": {"Rajasthan"},
    "dungarpur": {"Rajasthan"},
    "pratapgarh": {"Rajasthan", "Uttar Pradesh"},
    "rajsamand": {"Rajasthan"},
    "sirohi": {"Rajasthan"},
    "jalore": {"Rajasthan"},
    "dausa": {"Rajasthan"},
    "karauli": {"Rajasthan"},
    "beawar": {"Rajasthan"},
    "balotra": {"Rajasthan"},
    "didwana": {"Rajasthan"},
    "phalodi": {"Rajasthan"},
    # Gujarat
    "ahmedabad": {"Gujarat"},
    "surat": {"Gujarat"},
    "vadodara": {"Gujarat"},
    "baroda": {"Gujarat"},
    "rajkot": {"Gujarat"},
    "bhavnagar": {"Gujarat"},
    "jamnagar": {"Gujarat"},
    "junagadh": {"Gujarat"},
    "gandhinagar": {"Gujarat"},
    "anand": {"Gujarat"},
    "navsari": {"Gujarat"},
    "morbi": {"Gujarat"},
    "nadiad": {"Gujarat"},
    "surendranagar": {"Gujarat"},
    "bharuch": {"Gujarat"},
    "mehsana": {"Gujarat"},
    "bhuj": {"Gujarat"},
    "porbandar": {"Gujarat"},
    "valsad": {"Gujarat"},
    "vapi": {"Gujarat"},
    "godhra": {"Gujarat"},
    "patan": {"Gujarat"},
    "palanpur": {"Gujarat"},
    "botad": {"Gujarat"},
    "amreli": {"Gujarat"},
    "deesa": {"Gujarat"},
    "himatnagar": {"Gujarat"},
    "ankleshwar": {"Gujarat"},
    # Karnataka
    "bengaluru": {"Karnataka"},
    "bangalore": {"Karnataka"},
    "mysuru": {"Karnataka"},
    "mysore": {"Karnataka"},
    "hubli": {"Karnataka"},
    "dharwad": {"Karnataka"},
    "mangaluru": {"Karnataka"},
    "mangalore": {"Karnataka"},
    "belagavi": {"Karnataka"},
    "belgaum": {"Karnataka"},
    "gulbarga": {"Karnataka"},
    "kalaburagi": {"Karnataka"},
    "davanagere": {"Karnataka"},
    "ballari": {"Karnataka"},
    "bellary": {"Karnataka"},
    "vijayapura": {"Karnataka"},
    "bijapur": {"Karnataka", "Chhattisgarh"},
    "shimoga": {"Karnataka"},
    "shivamogga": {"Karnataka"},
    "tumakuru": {"Karnataka"},
    "tumkur": {"Karnataka"},
    "raichur": {"Karnataka"},
    "bidar": {"Karnataka"},
    "hosapete": {"Karnataka"},
    "gadag": {"Karnataka"},
    "hassan": {"Karnataka"},
    "udupi": {"Karnataka"},
    "bagalkot": {"Karnataka"},
    "kolar": {"Karnataka"},
    "mandya": {"Karnataka"},
    "chikmagalur": {"Karnataka"},
    "chikkamagaluru": {"Karnataka"},
    "chitradurga": {"Karnataka"},
    "haveri": {"Karnataka"},
    "yadgir": {"Karnataka"},
    "karwar": {"Karnataka"},
    # Telangana
    "hyderabad": {"Telangana"},
    "secunderabad": {"Telangana"},
    "warangal": {"Telangana"},
    "nizamabad": {"Telangana"},
    "karimnagar": {"Telangana"},
    "ramagundam": {"Telangana"},
    "khammam": {"Telangana"},
    "mahbubnagar": {"Telangana"},
    "nalgonda": {"Telangana"},
    "adilabad": {"Telangana"},
    "suryapet": {"Telangana"},
    "siddipet": {"Telangana"},
    # Tamil Nadu
    "chennai": {"Tamil Nadu"},
    "coimbatore": {"Tamil Nadu"},
    "madurai": {"Tamil Nadu"},
    "tiruchirappalli": {"Tamil Nadu"},
    "trichy": {"Tamil Nadu"},
    "salem": {"Tamil Nadu"},
    "tirunelveli": {"Tamil Nadu"},
    "tiruppur": {"Tamil Nadu"},
    "erode": {"Tamil Nadu"},
    "vellore": {"Tamil Nadu"},
    "thoothukudi": {"Tamil Nadu"},
    "tuticorin": {"Tamil Nadu"},
    "dindigul": {"Tamil Nadu"},
    "thanjavur": {"Tamil Nadu"},
    "ranipet": {"Tamil Nadu"},
    "sivakasi": {"Tamil Nadu"},
    "karur": {"Tamil Nadu"},
    "ooty": {"Tamil Nadu"},
    "udhagamandalam": {"Tamil Nadu"},
    "hosur": {"Tamil Nadu"},
    "nagercoil": {"Tamil Nadu"},
    "kanchipuram": {"Tamil Nadu"},
    "kumbakonam": {"Tamil Nadu"},
    "cuddalore": {"Tamil Nadu"},
    "tiruvannamalai": {"Tamil Nadu"},
    # Uttar Pradesh
    "lucknow": {"Uttar Pradesh"},
    "kanpur": {"Uttar Pradesh"},
    "agra": {"Uttar Pradesh"},
    "varanasi": {"Uttar Pradesh"},
    "prayagraj": {"Uttar Pradesh"},
    "allahabad": {"Uttar Pradesh"},
    "noida": {"Uttar Pradesh"},
    "greater noida": {"Uttar Pradesh"},
    "ghaziabad": {"Uttar Pradesh"},
    "meerut": {"Uttar Pradesh"},
    "bareilly": {"Uttar Pradesh"},
    "aligarh": {"Uttar Pradesh"},
    "moradabad": {"Uttar Pradesh"},
    "saharanpur": {"Uttar Pradesh"},
    "gorakhpur": {"Uttar Pradesh"},
    "faizabad": {"Uttar Pradesh"},
    "ayodhya": {"Uttar Pradesh"},
    "jhansi": {"Uttar Pradesh"},
    "muzaffarnagar": {"Uttar Pradesh"},
    "mathura": {"Uttar Pradesh"},
    "firozabad": {"Uttar Pradesh"},
    "mirzapur": {"Uttar Pradesh"},
    "sambhal": {"Uttar Pradesh"},
    "amroha": {"Uttar Pradesh"},
    "hardoi": {"Uttar Pradesh"},
    "fatehpur": {"Uttar Pradesh"},
    "raebareli": {"Uttar Pradesh"},
    "sitapur": {"Uttar Pradesh"},
    "bahraich": {"Uttar Pradesh"},
    "shahjahanpur": {"Uttar Pradesh"},
    "rampur": {"Uttar Pradesh"},
    "jaunpur": {"Uttar Pradesh"},
    "unnao": {"Uttar Pradesh"},
    # Madhya Pradesh
    "bhopal": {"Madhya Pradesh"},
    "indore": {"Madhya Pradesh"},
    "jabalpur": {"Madhya Pradesh"},
    "gwalior": {"Madhya Pradesh"},
    "ujjain": {"Madhya Pradesh"},
    "sagar": {"Madhya Pradesh"},
    "dewas": {"Madhya Pradesh"},
    "satna": {"Madhya Pradesh"},
    "ratlam": {"Madhya Pradesh"},
    "rewa": {"Madhya Pradesh"},
    "katni": {"Madhya Pradesh"},
    "singrauli": {"Madhya Pradesh"},
    "burhanpur": {"Madhya Pradesh"},
    "khandwa": {"Madhya Pradesh"},
    "chhindwara": {"Madhya Pradesh"},
    "guna": {"Madhya Pradesh"},
    "shivpuri": {"Madhya Pradesh"},
    "vidisha": {"Madhya Pradesh"},
    "chhatarpur": {"Madhya Pradesh"},
    "damoh": {"Madhya Pradesh"},
    "mandsaur": {"Madhya Pradesh"},
    "khargone": {"Madhya Pradesh"},
    "neemuch": {"Madhya Pradesh"},
    "hoshangabad": {"Madhya Pradesh"},
    "narmadapuram": {"Madhya Pradesh"},
    # Bihar
    "patna": {"Bihar"},
    "gaya": {"Bihar"},
    "bhagalpur": {"Bihar"},
    "muzaffarpur": {"Bihar"},
    "purnia": {"Bihar"},
    "darbhanga": {"Bihar"},
    "bihar sharif": {"Bihar"},
    "arrah": {"Bihar"},
    "begusarai": {"Bihar"},
    "katihar": {"Bihar"},
    "munger": {"Bihar"},
    "chhapra": {"Bihar"},
    "danapur": {"Bihar"},
    "bettiah": {"Bihar"},
    "saharsa": {"Bihar"},
    "sasaram": {"Bihar"},
    "hajipur": {"Bihar"},
    "dehri": {"Bihar"},
    "siwan": {"Bihar"},
    "motihari": {"Bihar"},
    "nawada": {"Bihar"},
    # West Bengal
    "kolkata": {"West Bengal"},
    "howrah": {"West Bengal"},
    "durgapur": {"West Bengal"},
    "asansol": {"West Bengal"},
    "siliguri": {"West Bengal"},
    "bardhaman": {"West Bengal"},
    "burdwan": {"West Bengal"},
    "malda": {"West Bengal"},
    "baharampur": {"West Bengal"},
    "habra": {"West Bengal"},
    "kharagpur": {"West Bengal"},
    "shantipur": {"West Bengal"},
    "dankuni": {"West Bengal"},
    "haldia": {"West Bengal"},
    "raiganj": {"West Bengal"},
    "krishnanagar": {"West Bengal"},
    "medinipur": {"West Bengal"},
    "midnapore": {"West Bengal"},
    "jalpaiguri": {"West Bengal"},
    "darjeeling": {"West Bengal"},
    "kalimpong": {"West Bengal"},
    # Punjab
    "ludhiana": {"Punjab"},
    "amritsar": {"Punjab"},
    "jalandhar": {"Punjab"},
    "patiala": {"Punjab"},
    "bathinda": {"Punjab"},
    "mohali": {"Punjab"},
    "sas nagar": {"Punjab"},
    "hoshiarpur": {"Punjab"},
    "batala": {"Punjab"},
    "pathankot": {"Punjab"},
    "moga": {"Punjab"},
    "abohar": {"Punjab"},
    "malerkotla": {"Punjab"},
    "khanna": {"Punjab"},
    "phagwara": {"Punjab"},
    "muktsar": {"Punjab"},
    "barnala": {"Punjab"},
    "rajpura": {"Punjab"},
    "firozpur": {"Punjab"},
    "kapurthala": {"Punjab"},
    # Haryana
    "gurugram": {"Haryana"},
    "gurgaon": {"Haryana"},
    "faridabad": {"Haryana"},
    "panipat": {"Haryana"},
    "ambala": {"Haryana"},
    "yamunanagar": {"Haryana"},
    "rohtak": {"Haryana"},
    "hisar": {"Haryana"},
    "karnal": {"Haryana"},
    "sonipat": {"Haryana"},
    "panchkula": {"Haryana"},
    "bhiwani": {"Haryana"},
    "sirsa": {"Haryana"},
    "bahadurgarh": {"Haryana"},
    "jind": {"Haryana"},
    "rewari": {"Haryana"},
    "palwal": {"Haryana"},
    "kurukshetra": {"Haryana"},
    # Kerala
    "thiruvananthapuram": {"Kerala"},
    "trivandrum": {"Kerala"},
    "kochi": {"Kerala"},
    "cochin": {"Kerala"},
    "kozhikode": {"Kerala"},
    "calicut": {"Kerala"},
    "thrissur": {"Kerala"},
    "trichur": {"Kerala"},
    "kollam": {"Kerala"},
    "quilon": {"Kerala"},
    "kannur": {"Kerala"},
    "alappuzha": {"Kerala"},
    "alleppey": {"Kerala"},
    "kottayam": {"Kerala"},
    "palakkad": {"Kerala"},
    "palghat": {"Kerala"},
    "manjeri": {"Kerala"},
    "thalassery": {"Kerala"},
    "kasaragod": {"Kerala"},
    "ernakulam": {"Kerala"},
    # Odisha
    "bhubaneswar": {"Odisha"},
    "cuttack": {"Odisha"},
    "rourkela": {"Odisha"},
    "berhampur": {"Odisha"},
    "brahmapur": {"Odisha"},
    "sambalpur": {"Odisha"},
    "puri": {"Odisha"},
    "balasore": {"Odisha"},
    "baleshwar": {"Odisha"},
    "bhadrak": {"Odisha"},
    "baripada": {"Odisha"},
    "jharsuguda": {"Odisha"},
    # Andhra Pradesh
    "visakhapatnam": {"Andhra Pradesh"},
    "vizag": {"Andhra Pradesh"},
    "vijayawada": {"Andhra Pradesh"},
    "guntur": {"Andhra Pradesh"},
    "nellore": {"Andhra Pradesh"},
    "kurnool": {"Andhra Pradesh"},
    "kakinada": {"Andhra Pradesh"},
    "rajahmundry": {"Andhra Pradesh"},
    "tirupati": {"Andhra Pradesh"},
    "kadapa": {"Andhra Pradesh"},
    "anantapur": {"Andhra Pradesh"},
    "vizianagaram": {"Andhra Pradesh"},
    "eluru": {"Andhra Pradesh"},
    "ongole": {"Andhra Pradesh"},
    "nandyal": {"Andhra Pradesh"},
    # Jharkhand
    "ranchi": {"Jharkhand"},
    "jamshedpur": {"Jharkhand"},
    "dhanbad": {"Jharkhand"},
    "bokaro": {"Jharkhand"},
    "deoghar": {"Jharkhand"},
    "hazaribagh": {"Jharkhand"},
    "giridih": {"Jharkhand"},
    "ramgarh": {"Jharkhand"},
    # Assam
    "guwahati": {"Assam"},
    "silchar": {"Assam"},
    "dibrugarh": {"Assam"},
    "jorhat": {"Assam"},
    "nagaon": {"Assam"},
    "tinsukia": {"Assam"},
    "tezpur": {"Assam"},
    # Chhattisgarh
    "raipur": {"Chhattisgarh"},
    "bhilai": {"Chhattisgarh"},
    "bilaspur": {"Chhattisgarh", "Himachal Pradesh"},
    "korba": {"Chhattisgarh"},
    "durg": {"Chhattisgarh"},
    "rajnandgaon": {"Chhattisgarh"},
    "raigarh": {"Chhattisgarh"},
    "jagdalpur": {"Chhattisgarh"},
    # Uttarakhand
    "dehradun": {"Uttarakhand"},
    "haridwar": {"Uttarakhand"},
    "roorkee": {"Uttarakhand"},
    "haldwani": {"Uttarakhand"},
    "rudrapur": {"Uttarakhand"},
    "kashipur": {"Uttarakhand"},
    "rishikesh": {"Uttarakhand"},
    "nainital": {"Uttarakhand"},
    "mussoorie": {"Uttarakhand"},
    # Himachal Pradesh
    "shimla": {"Himachal Pradesh"},
    "dharamshala": {"Himachal Pradesh"},
    "mandi": {"Himachal Pradesh"},
    "solan": {"Himachal Pradesh"},
    "kullu": {"Himachal Pradesh"},
    "manali": {"Himachal Pradesh"},
    "una": {"Himachal Pradesh"},
    # Goa
    "panaji": {"Goa"},
    "margao": {"Goa"},
    "vasco da gama": {"Goa"},
    "mapusa": {"Goa"},
    "ponda": {"Goa"},
    # Jammu and Kashmir
    "srinagar": {"Jammu and Kashmir"},
    "jammu": {"Jammu and Kashmir"},
    "anantnag": {"Jammu and Kashmir"},
    "baramulla": {"Jammu and Kashmir"},
    "udhampur": {"Jammu and Kashmir"},
    # Ladakh
    "leh": {"Ladakh"},
    "kargil": {"Ladakh"},
    # UTs
    "chandigarh": {"Chandigarh"},
    "delhi": {"Delhi"},
    "new delhi": {"Delhi"},
    "puducherry": {"Puducherry"},
}

CUSTOMER_ROAD_SUFFIXES = {
    "road", "rd", "street", "st", "lane", "ln", "marg", "path", "avenue", "ave",
    "highway", "expressway", "bypass", "circle", "chowk", "gate", "bridge",
    "colony", "nagar", "bhavan", "bhawan", "complex", "tower", "towers",
    "apartment", "apartments", "society", "park", "estate", "naka", "plaza"
}


def extract_geo_from_address(addr: str) -> tuple[list[tuple[str, set[str]]], list[str]]:
    """
    Extracts recognized districts/cities and states from an Indian address string.
    Returns:
    (found_districts: list of (district_name, possible_states), found_states: list of state_names)
    """
    clean_addr = addr.lower()
    norm = re.sub(r"[^\w\s-]", " ", clean_addr)

    found_states: list[str] = []
    sorted_states = sorted(INDIAN_STATES_MAP.keys(), key=lambda x: len(x), reverse=True)
    for st_key in sorted_states:
        pattern = r"\b" + re.escape(st_key) + r"\b"
        if re.search(pattern, norm):
            st_canonical = INDIAN_STATES_MAP[st_key]
            if st_canonical not in found_states:
                found_states.append(st_canonical)

    found_districts: list[tuple[str, set[str]]] = []
    sorted_districts = sorted(INDIAN_DISTRICT_TO_STATES.keys(), key=lambda x: len(x), reverse=True)
    for dist_key in sorted_districts:
        pattern = r"\b" + re.escape(dist_key) + r"(?:\s+(\w+))?\b"
        matches = list(re.finditer(pattern, norm))
        for m in matches:
            next_word = m.group(1)
            if next_word and next_word in CUSTOMER_ROAD_SUFFIXES:
                continue
            if dist_key in {"delhi", "new delhi", "chandigarh", "goa", "puducherry"} and dist_key.title() in found_states:
                continue
            dist_canonical = dist_key.title()
            possible_states = INDIAN_DISTRICT_TO_STATES[dist_key]
            found_districts.append((dist_canonical, possible_states))
            break

    return found_districts, found_states


def validate_address_geo_consistency(addr: Optional[str], gstin: Optional[str] = None) -> None:
    """
    Validates geographical consistency of Indian addresses:
    1. Rejects addresses where the specified district/city belongs to a different state
       than the state explicitly written in the address (e.g. 'Kurandvad, jaisalmer, Maharashtra').
    2. Rejects addresses mentioning multiple conflicting Indian states.
    3. Rejects addresses where district or state contradicts the state code of the GSTIN (if provided).
    """
    if not addr:
        return

    found_districts, found_states = extract_geo_from_address(addr)

    # 1. State vs District consistency within the address
    if found_districts and found_states:
        for dist_name, valid_states in found_districts:
            for st in found_states:
                if st not in valid_states:
                    expected_str = "/".join(sorted(valid_states))
                    raise ValueError(
                        f"Address mismatch: District/City '{dist_name}' belongs to {expected_str}, but state is specified as '{st}'"
                    )

    # 2. Conflicting multiple states in address
    if len(set(found_states)) > 1:
        states_str = ", ".join(sorted(set(found_states)))
        raise ValueError(f"Address contains multiple conflicting states: {states_str}")

    # 3. GSTIN state correlation (if GSTIN is provided)
    if gstin and isinstance(gstin, str) and len(gstin.strip()) >= 2:
        gstin_code = gstin.strip()[:2]
        expected_gstin_state = GSTIN_STATE_CODE_MAP.get(gstin_code)
        if expected_gstin_state:
            for st in found_states:
                if st != expected_gstin_state:
                    raise ValueError(
                        f"Address state '{st}' does not match GSTIN state '{expected_gstin_state}' (State code {gstin_code})"
                    )
            for dist_name, valid_states in found_districts:
                if expected_gstin_state not in valid_states:
                    expected_str = "/".join(sorted(valid_states))
                    raise ValueError(
                        f"Address district/city '{dist_name}' ({expected_str}) does not match GSTIN state '{expected_gstin_state}' (State code {gstin_code})"
                    )


MAX_CUSTOMER_AGE_YEARS: int = 120


def validate_birthday(v: Optional[date]) -> Optional[date]:
    if v is None:
        return None

    today = date.today()
    if v > today:
        raise ValueError(
            "Birthday cannot be in the future"
        )

    try:
        min_allowed_date = today.replace(year=today.year - MAX_CUSTOMER_AGE_YEARS)
    except ValueError:
        # Handles leap year Feb 29
        min_allowed_date = today.replace(year=today.year - MAX_CUSTOMER_AGE_YEARS, day=28)

    if v < min_allowed_date:
        raise ValueError(
            f"Birthday cannot be more than {MAX_CUSTOMER_AGE_YEARS} years in the past"
        )

    return v

class SubResourceNoDataResponse(BaseModel):
    success: bool = True
    message: str
    data: list = Field(default_factory=list)

class CustomerOrdersResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int
    orders: list[OrderResponse] = Field(default_factory=list)
    data: list[OrderResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class CustomerBase(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=255,
        description="Name must be 2 to 255 characters",
    )

    email: Optional[EmailStr] = None

    phone: str = Field(
        pattern=r"^(?:\+91)?[6-9]\d{9}$",
        description="Phone must be 10 digits or +91 followed by 10 digits"
    )

    address: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Address must be at least 3 characters if provided",
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
    )

    birthday: Optional[date] = None

    whatsapp_opt_in: StrictBool = True
    sms_opt_in: StrictBool = True

    @field_validator("whatsapp_opt_in", "sms_opt_in", mode="before")
    @classmethod
    def validate_opt_in_bool(cls, v: Any, info) -> Any:
        if v is None or not isinstance(v, bool):
            raise ValueError(f"Invalid value for {info.field_name}. Expected a boolean: true or false.")
        return v

    status: Literal[
        "active",
        "inactive",
        "blocked"
    ] = "active"

    segment: Literal[
        "new",
        "regular",
        "vip",
        "inactive"
    ] = "new"

    credit_limit: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("9999999.99"),
        description="Customer credit limit is required (0.00 for no credit limit)",
    )
    outstanding_balance: Optional[Decimal] = Field(
        default=Decimal("0.00"),
        description="Read-only field. System directly records 0.00 for new customers.",
        json_schema_extra={"readOnly": True},
    )

    @field_validator("email", mode="before")
    @classmethod
    def validate_customer_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Customer email must be a string")
        v_str = v.strip()
        if not v_str:
            return None
        if v_str.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or v_str.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(f"Customer email cannot be placeholder '{v}'")
        if any(c.isupper() for c in v_str):
            raise ValueError("Customer email must contain lowercase letters only")
        return validate_email_address(v_str, field_name="Customer email", required=False)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return validate_phone_number(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return validate_customer_name(v)

    @field_validator("address")
    @classmethod
    def check_address(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        return validate_address(v)

    @field_validator("birthday")
    @classmethod
    def check_birthday(
        cls,
        v: Optional[date]
    ) -> Optional[date]:
        return validate_birthday(v)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)

    @model_validator(mode="after")
    def validate_customer_address_and_gstin(self) -> "CustomerBase":
        if self.address and self.gstin:
            validate_address_geo_consistency(self.address, self.gstin)
        return self


class CustomerCreate(CustomerBase):

    credit_limit: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("9999999.99"),
        description="Customer credit limit is required (0.00 for no credit limit)",
    )

    address: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Address is required, cannot be erased from JSON, and must be at least 3 characters",
    )

    birthday: Optional[date] = Field(
        default=None,
        description=(
            "Customer birthday is optional, cannot be in the future, "
            "and cannot be more than 120 years in the past"
        ),
    )

    @field_validator("address", mode="before")
    @classmethod
    def check_create_address_before(cls, v):

        if v is None:
            raise ValueError("Address cannot be null or omitted")

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                raise ValueError(
                    "Address cannot be empty or whitespace"
                )
            if len(v_strip) < 3:
                raise ValueError(
                    "Address must be at least 3 characters long"
                )
            if v_strip.isdigit():
                raise ValueError(
                    "Address cannot consist only of numbers"
                )
            if any(c in FORBIDDEN_ADDRESS_SYMBOLS for c in v_strip):
                raise ValueError(
                    "Address contains invalid special characters"
                )
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Address cannot be placeholder '{v}'"
                )
            letters = re.findall(r"[a-zA-Z]", v_strip)
            if len(letters) < 3:
                raise ValueError(
                    "Address must contain at least 3 alphabetic characters"
                )
            return v_strip

        return v

    @field_validator("birthday", mode="before")
    @classmethod
    def check_create_birthday_before(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Birthday cannot be placeholder '{v}'"
                )
            return v_strip

        return v

    @field_validator("birthday")
    @classmethod
    def validate_create_birthday(
        cls,
        value: Optional[date],
    ) -> Optional[date]:
        return validate_birthday(value)

    @field_validator("email", mode="before")
    @classmethod
    def check_create_email_before(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Customer email must be a string")
        v_str = v.strip()
        if not v_str:
            return None
        if v_str.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or v_str.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(f"Customer email cannot be placeholder '{v}'")
        if any(c.isupper() for c in v_str):
            raise ValueError("Customer email must contain lowercase letters only")
        return validate_email_address(v_str, field_name="Customer email", required=False)

    @field_validator("credit_limit", mode="before")
    @classmethod
    def validate_create_credit_limit(cls, v: Any) -> Decimal:
        if v is None:
            raise ValueError("Credit limit is required and cannot be null")

        if isinstance(v, bool):
            raise ValueError("Credit limit must be a valid numeric amount, not a boolean")

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                raise ValueError("Credit limit cannot be empty or whitespace")
            clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v_strip.lower())
            if v_strip.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
                raise ValueError(f"Credit limit cannot be placeholder '{v}'")
            if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v_strip):
                raise ValueError("Credit limit contains invalid characters")
            if re.search(r"[-+@#*/=_.,:;?!&$%]{2,}", v_strip):
                raise ValueError("Credit limit contains consecutive invalid symbols")
            if re.search(r"[a-zA-Z]", v_strip):
                raise ValueError("Credit limit cannot contain alphabetic characters")
            try:
                dec = Decimal(v_strip)
            except Exception:
                raise ValueError("Credit limit must be a valid numeric amount")
        elif isinstance(v, (int, float, Decimal)):
            dec = Decimal(str(v))
        else:
            raise ValueError("Credit limit must be a valid numeric amount")

        if dec < Decimal("0.00"):
            raise ValueError("Credit limit cannot be negative")

        if dec > Decimal("9999999.99"):
            raise ValueError("Credit limit cannot exceed 9999999.99")

        return dec.quantize(Decimal("0.01"))

    @field_validator("outstanding_balance", mode="before")
    @classmethod
    def validate_create_outstanding_balance(cls, v: Any) -> Decimal:
        if v is None:
            return Decimal("0.00")

        if isinstance(v, bool):
            raise ValueError("Outstanding balance must be a valid numeric amount, not a boolean")

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                raise ValueError("Outstanding balance cannot be empty or whitespace")
            clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v_strip.lower())
            if v_strip.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
                raise ValueError(f"Outstanding balance cannot be placeholder '{v}'")
            if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v_strip):
                raise ValueError("Outstanding balance contains invalid characters")
            if re.search(r"[-+@#*/=_.,:;?!&$%]{2,}", v_strip):
                raise ValueError("Outstanding balance contains consecutive invalid symbols")
            if re.search(r"[a-zA-Z]", v_strip):
                raise ValueError("Outstanding balance cannot contain alphabetic characters")
            try:
                dec = Decimal(v_strip)
            except Exception:
                raise ValueError("Outstanding balance must be a valid numeric amount")
        elif isinstance(v, (int, float, Decimal)):
            dec = Decimal(str(v))
        else:
            raise ValueError("Outstanding balance must be a valid numeric amount")

        if dec < Decimal("0.00"):
            raise ValueError("Outstanding balance cannot be negative")

        if dec > Decimal("9999999.99"):
            raise ValueError("Outstanding balance cannot exceed 9999999.99")

        return dec.quantize(Decimal("0.01"))


class CustomerUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    email: Optional[EmailStr] = None

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=13,
        pattern=r"^(?:\+91)?[6-9]\d{9}$",
        description=(
            "Phone must be 10 digits or "
            "+91 followed by 10 digits"
        ),
    )

    address: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Address must be at least 3 characters if provided",
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
    )

    birthday: Optional[date] = None

    whatsapp_opt_in: Optional[StrictBool] = None
    sms_opt_in: Optional[StrictBool] = None

    @field_validator("whatsapp_opt_in", "sms_opt_in", mode="before")
    @classmethod
    def validate_update_opt_in_bool(cls, v: Any, info) -> Any:
        if v is None or not isinstance(v, bool):
            raise ValueError(f"Invalid value for {info.field_name}. Expected a boolean: true or false.")
        return v
    credit_limit: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))

    @field_validator("name", mode="before")
    @classmethod
    def check_update_name_before(cls, v):

        if v is None:
            raise ValueError(
                "Name cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Name must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Name cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Name cannot be placeholder '{v}'"
            )

        return v

    @field_validator("name")
    @classmethod
    def check_name(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_customer_name(v)

    @field_validator("phone", mode="before")
    @classmethod
    def check_update_phone_before(cls, v):

        if v is None:
            raise ValueError(
                "Phone cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Phone must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Phone cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Phone cannot be placeholder '{v}'"
            )

        return v

    @field_validator("phone")
    @classmethod
    def check_phone(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_phone_number(v)

    @field_validator("address", mode="before")
    @classmethod
    def check_update_address_before(cls, v):

        if v is None:
            raise ValueError(
                "Address cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Address must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Address cannot be empty or whitespace"
            )

        if len(v) < 3:
            raise ValueError(
                "Address must be at least 3 characters long"
            )

        if any(c in FORBIDDEN_ADDRESS_SYMBOLS for c in v):
            raise ValueError(
                "Address contains invalid special characters"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Address cannot be placeholder '{v}'"
            )

        return v

    @field_validator("address")
    @classmethod
    def check_address(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_address(v)

    @field_validator("birthday", mode="before")
    @classmethod
    def check_update_birthday_before(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Birthday cannot be placeholder '{v}'"
                )
            return v_strip

        return v

    @field_validator("birthday")
    @classmethod
    def check_birthday(
        cls,
        v: Optional[date]
    ) -> Optional[date]:

        if v is None:
            return None

        return validate_birthday(v)

    @field_validator("email", mode="before")
    @classmethod
    def check_update_email_before(cls, v):

        if v is None:
            raise ValueError(
                "Email cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Email must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Email cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Email cannot be placeholder '{v}'"
            )

        if any(c.isupper() for c in v):
            raise ValueError(
                "Customer email must contain lowercase letters only"
            )

        return validate_email_address(v, field_name="Customer email", required=True)

    @field_validator("gstin", mode="before")
    @classmethod
    def check_update_gstin_before(cls, v):

        if v is None:
            raise ValueError(
                "GSTIN cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "GSTIN must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "GSTIN cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"GSTIN cannot be placeholder '{v}'"
            )

        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)

    @model_validator(mode="after")
    def validate_update_customer_address_and_gstin(self) -> "CustomerUpdate":
        if self.address and self.gstin:
            validate_address_geo_consistency(self.address, self.gstin)
        return self

    @field_validator("credit_limit", mode="before")
    @classmethod
    def validate_update_credit_limit(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError("Credit limit must be a valid numeric amount, not a boolean")
        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                raise ValueError("Credit limit cannot be empty or whitespace")
            clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v_strip.lower())
            if v_strip.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
                raise ValueError(f"Credit limit cannot be placeholder '{v}'")
            if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v_strip):
                raise ValueError("Credit limit contains invalid characters")
            if re.search(r"[-+@#*/=_.,:;?!&$%]{2,}", v_strip):
                raise ValueError("Credit limit contains consecutive invalid symbols")
            if re.search(r"[a-zA-Z]", v_strip):
                raise ValueError("Credit limit cannot contain alphabetic characters")
            try:
                dec = Decimal(v_strip)
            except Exception:
                raise ValueError("Credit limit must be a valid numeric amount")
        elif isinstance(v, (int, float, Decimal)):
            dec = Decimal(str(v))
        else:
            raise ValueError("Credit limit must be a valid numeric amount")

        if dec < Decimal("0.00"):
            raise ValueError("Credit limit cannot be negative")
        if dec > Decimal("9999999.99"):
            raise ValueError("Credit limit cannot exceed 9999999.99")

        return dec.quantize(Decimal("0.01"))


class CustomerResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    tenant_id: int
    name: str
    email: Optional[str] = None
    phone: str
    address: Optional[str] = None
    gstin: Optional[str] = None
    birthday: Optional[date] = None
    whatsapp_opt_in: bool = True
    sms_opt_in: bool = True
    status: str = "active"
    segment: str = "new"
    credit_limit: Optional[Decimal] = Decimal("0.00")
    outstanding_balance: Optional[Decimal] = Decimal("0.00")
    loyalty_points: Optional[int] = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v):
        if v is None:
            return "Customer"
        s = str(v).strip()
        return s if s else "Customer"

    @field_validator("status", mode="before")
    @classmethod
    def sanitize_status(cls, v):
        if v is None or not str(v).strip():
            return "active"

        s = str(v).strip().lower()
        if s in ("active", "inactive", "blocked"):
            return s

        return "active"

    @field_validator("segment", mode="before")
    @classmethod
    def sanitize_segment(cls, v):
        if v is None or not str(v).strip():
            return "new"

        s = str(v).strip().lower()
        if s in ("new", "regular", "vip", "inactive"):
            return s

        return "new"

    @field_validator("email", mode="before")
    @classmethod
    def sanitize_email(cls, v):
        if v is None or not str(v).strip():
            return None

        s = str(v).strip().lower()
        return s if ("@" in s and "." in s) else None

    @field_validator("gstin", mode="before")
    @classmethod
    def sanitize_gstin(cls, v):
        if v is None or not str(v).strip():
            return None

        return str(v).strip().upper()

    @field_validator("phone", mode="before")
    @classmethod
    def sanitize_phone(cls, v):
        if v is None:
            return ""

        return str(v).strip()

    @field_validator("whatsapp_opt_in", "sms_opt_in", mode="before")
    @classmethod
    def sanitize_opt_in(cls, v):
        if v is None:
            return True
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.lower() in ("true", "1", "t", "yes", "y")
        return bool(v)

    @field_validator("credit_limit", "outstanding_balance", mode="before")
    @classmethod
    def sanitize_decimal(cls, v):
        if v is None:
            return Decimal("0.00")
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0.00")

    @field_validator("loyalty_points", mode="before")
    @classmethod
    def sanitize_loyalty(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except Exception:
            return 0


class MessageResponse(BaseModel):
    message: str


class CustomerStatsResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: Optional[int] = 0
    blocked_customers: Optional[int] = 0
    new_customers: Optional[int] = 0
    regular_customers: Optional[int] = 0
    vip_customers: Optional[int] = 0
    total_revenue: Optional[int] = 0
    new_this_month: Optional[int] = 0

class CustomerFeedbackCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    invoice_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    rating: int = Field(
        ge=1,
        le=5
    )

    comments: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    suggestions: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    feedback: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    @field_validator("comments", "suggestions", "feedback", mode="before")
    @classmethod
    def clean_feedback_strings_before(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            return v_strip
        return v

    @field_validator("comments")
    @classmethod
    def validate_comments(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Comments",
            1,
            2000,
            required=False,
        )

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Suggestions",
            1,
            2000,
            required=False,
        )

    @field_validator("feedback")
    @classmethod
    def validate_feedback(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Feedback",
            1,
            2000,
            required=False,
        )


class CustomerFeedbackResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    invoice_id: Optional[int] = None
    rating: int
    comments: Optional[str] = None
    suggestions: Optional[str] = None
    feedback: Optional[str] = None
    created_at: datetime

class WalletOperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(
        gt=0,
        description="Customer ID must be a positive integer"
    )

    amount: Decimal = Field(
        gt=0,
        decimal_places=2,
        max_digits=12,
        description="Amount must be greater than zero"
    )

    reference_no: str = Field(
        min_length=3,
        max_length=30,
        description="Reference number (3 to 30 characters)"
    )

    remarks: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Remarks must be meaningful text without numbers (3 to 100 characters)"
    )

    @field_validator("reference_no", mode="before")
    @classmethod
    def validate_reference(cls, v: Any) -> str:
        if v is None:
            raise ValueError("Reference number is required and cannot be null")

        if not isinstance(v, str):
            raise ValueError("Reference number must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Reference number cannot be empty or whitespace")

        if len(v) < 3 or len(v) > 30:
            raise ValueError("Reference number must be between 3 and 30 characters")

        if v.lower() in {"string", "null", "none", "undefined", "test", "dummy", "sample"}:
            raise ValueError(f"Reference number cannot be placeholder '{v}'")

        if not re.fullmatch(r"^[A-Za-z0-9_-]{3,30}$", v):
            raise ValueError("Reference number contains invalid characters (only alphanumeric, hyphens, and underscores allowed)")

        if not any(c.isdigit() for c in v):
            raise ValueError("Reference number cannot be alphabetic-only")

        # Reject all zeros, all same character repeated, or sequential dummy strings
        digits_only = "".join(c for c in v if c.isdigit())
        if digits_only and len(set(digits_only)) == 1 and len(digits_only) >= 5:
            raise ValueError("Reference number cannot be repeated identical digits")

        if re.fullmatch(r"^0+$", v) or (re.fullmatch(r"^[0_-]+$", v) and not any(c.isalpha() or c in '123456789' for c in v)):
            raise ValueError("Reference number cannot be zero or all zeros")

        return v

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Remarks must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Remarks cannot be empty or whitespace")

        if len(v) < 3 or len(v) > 100:
            raise ValueError("Remarks must be between 3 and 100 characters")

        # Reject numeric digits strictly in remarks per requirement
        if any(c.isdigit() for c in v):
            raise ValueError("Remarks cannot contain numeric digits")

        # Reject placeholders
        clean_norm = re.sub(r"[^a-zA-Z]", "", v.lower())
        if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
            raise ValueError(f"Remarks cannot be placeholder '{v}'")

        if v.lower() in {"na", "n/a", "nil", "none", "null", "test", "dummy", "sample"}:
            raise ValueError(f"Remarks cannot be placeholder '{v}'")

        # Reject forbidden special symbols
        if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v):
            raise ValueError("Remarks contains invalid special characters")

        # Reject consecutive repeating symbols
        if re.search(r"[-+*/=_]{2,}", v):
            raise ValueError("Remarks cannot contain consecutive repeating symbols")

        # Require meaningful alphabetic words
        alpha_chars = [c.lower() for c in v if c.isalpha()]
        if len(alpha_chars) < 3:
            raise ValueError("Remarks must contain at least 3 letters")

        # Reject single character repeated (e.g. "aaaaa", "ppppp")
        if len(set(alpha_chars)) < 2:
            raise ValueError(f"Remarks cannot consist of repetitive characters '{v}'")

        # Reject keyboard smash / gibberish: any unbroken word longer than 25 characters
        words = v.split()
        for word in words:
            if len(word) > 25:
                raise ValueError("Remarks cannot contain excessively long unbroken words or random gibberish")

        return v


class WalletCreditRequest(WalletOperationBase):
    pass


class WalletDebitRequest(WalletOperationBase):
    pass


class WalletResponse(BaseModel):

    id: Optional[int] = None
    customer_id: int
    current_balance: Optional[float] = None
    balance: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )

    @model_validator(mode="after")
    def sync_balance(self):

        if (
            self.balance is None
            and self.current_balance is not None
        ):
            self.balance = Decimal(
                str(self.current_balance)
            )

        elif (
            self.current_balance is None
            and self.balance is not None
        ):
            self.current_balance = float(
                self.balance
            )

        return self


class WalletTransactionResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    wallet_id: Optional[int] = None
    customer_id: Optional[int] = None
    transaction_type: str
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    balance_after: Optional[Decimal] = None
    reason: Optional[str] = None
    created_at: datetime


class WalletOperationResponse(BaseModel):

    id: int
    customer_id: int
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    balance: float
    current_balance: Optional[float] = None

    model_config = ConfigDict(
        from_attributes=True
    )

class LoyaltyAddPointsRequest(BaseModel):
    points: int = Field(..., gt=0, le=10000, description="Loyalty points to add")


class LoyaltyEarnRequest(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    points: int = Field(
        gt=0
    )

    invoice_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    reason: str = Field(
        min_length=1,
        max_length=500
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str):

        return validate_meaningful_text(
            v,
            "Reason",
            1,
            500,
            required=True,
        )


class LoyaltyRedeemRequest(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    points: int = Field(
        gt=0
    )

    reason: Optional[str] = Field(
        default=None,
        max_length=500
    )


class LoyaltyResponse(BaseModel):

    id: Optional[int] = None
    customer_id: int
    invoice_id: Optional[int] = None
    points_earned: Optional[int] = None
    points_redeemed: Optional[int] = None
    balance_points: Optional[int] = None
    points: Optional[int] = None
    reason: Optional[str] = None
    expiry_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )

    @model_validator(mode="after")
    def sync_points(self):

        if (
            self.points is None
            and self.balance_points is not None
        ):
            self.points = self.balance_points

        elif (
            self.balance_points is None
            and self.points is not None
        ):
            self.balance_points = self.points

        return self


DISALLOWED_LOYALTY_REASON_PLACEHOLDERS = {
    "string", "null", "none", "undefined", "test", "dummy", "sample",
    "placeholder", "name", "reason", "na", "n/a", "temp", "p0@#$", "ppppp", "12233", "123445"
}

FORBIDDEN_LOYALTY_SYMBOLS = set(r"\|[]{}<>~^$%;:?")


def validate_loyalty_reason(v: Any) -> str:
    """
    Validates reason field for loyalty point updates/adjustments:
    - Rejects null, non-string, empty, whitespace.
    - Requires 3 to 500 characters.
    - Rejects placeholders ('string', 'null', 'none', 'undefined', 'test', etc.).
    - Rejects forbidden symbols (|, [, ], {, }, <, >, ~, ^, $, %, ;, :, ?).
    - Rejects consecutive repeating symbols (--, ++, @@, ##, **, //, ==, __, ..).
    - Rejects HTML/script injection (<script>, javascript:, onload=).
    - Must contain at least 2 distinct alphabetic letters.
    - Rejects numeric-only (e.g. 12233).
    - Rejects repetitive character spam (e.g. ppppp, aaaa).
    - Digits cannot exceed letters.
    - Rejects consonant mash without vowels (e.g. HTDFFGHGKGKHK) or 5+ consecutive consonants.
    """
    if v is None:
        raise ValueError("Reason cannot be null")

    if not isinstance(v, str):
        raise ValueError("Reason must be a string")

    val = v.strip()
    if not val:
        raise ValueError("Reason cannot be empty or whitespace")

    if len(val) < 3 or len(val) > 500:
        raise ValueError("Reason must be between 3 and 500 characters")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", val.lower())
    if val.lower() in DISALLOWED_LOYALTY_REASON_PLACEHOLDERS or clean_norm in DISALLOWED_LOYALTY_REASON_PLACEHOLDERS:
        raise ValueError(f"Reason cannot be placeholder '{val}'")

    if any(c in FORBIDDEN_LOYALTY_SYMBOLS for c in val):
        raise ValueError("Reason contains invalid special characters")

    if re.search(r"[-+@#*/=_.,]{2,}", val):
        raise ValueError("Reason cannot contain consecutive repeating symbols")

    if re.search(r"<\s*script|javascript\s*:|onload\s*=", val, re.IGNORECASE):
        raise ValueError("Reason contains invalid script content")

    alpha_chars = [c.lower() for c in val if c.isalpha()]
    if len(alpha_chars) < 2:
        if val.isdigit():
            raise ValueError("Reason cannot be numeric-only")
        raise ValueError("Reason must contain at least 2 alphabetic letters")

    if len(set(alpha_chars)) < 2:
        raise ValueError(f"Reason cannot consist of repetitive characters '{val}'")

    digit_count = sum(1 for c in val if c.isdigit())
    if digit_count > len(alpha_chars):
        raise ValueError("Reason cannot contain more digits than letters")

    # Consonant cluster check (5 or more consecutive consonants)
    if re.search(r"[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}", val):
        raise ValueError(f"Reason contains meaningless consonant cluster in '{val}'")

    # Vowel check in words of length >= 3
    vowels = set("aeiouAEIOU")
    words = re.findall(r"[a-zA-Z]+", val)
    for word in words:
        if len(word) >= 3 and not any(c in vowels for c in word):
            raise ValueError(f"Reason contains meaningless word '{word}' without vowels")

    return val


class LoyaltyUpdateRequest(BaseModel):
    points: int = Field(..., ge=0, le=1000000, description="New loyalty points balance (must be non-negative integer)")
    reason: str = Field(..., description="Meaningful reason for loyalty points adjustment")

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason_field(cls, v: Any) -> str:
        return validate_loyalty_reason(v)


class LoyaltyDeleteData(BaseModel):
    customer_id: int
    loyalty_points: int = 0


class LoyaltyDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Customer loyalty balance reset successfully"
    data: LoyaltyDeleteData


class LoyaltyStatsData(BaseModel):
    active_members: int = 0
    new_members_this_week: int = 0
    points_in_circulation: int = 0
    points_liability_amount: Decimal = Decimal("0.00")
    points_redeemed_this_month: int = 0
    amount_saved_this_month: Decimal = Decimal("0.00")
    avg_spend_per_member_bill: Decimal = Decimal("0.00")
    member_spend_multiplier: Decimal = Decimal("1.0")


class LoyaltyStatsResponse(BaseModel):
    success: bool = True
    message: str = "Loyalty statistics retrieved successfully"
    data: LoyaltyStatsData


class LoyaltyCustomerItem(BaseModel):
    customer_id: int
    customer_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    loyalty_points: int = 0
    tier: str = "Silver Tier"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LoyaltyCustomerListResponse(BaseModel):
    success: bool = True
    message: str = "Loyalty customers retrieved successfully"
    data: list[LoyaltyCustomerItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class CommunicationCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    channel: Optional[
        Literal["whatsapp", "sms", "email"]
    ] = None

    communication_type: Optional[
        Literal["SMS", "WHATSAPP", "EMAIL"]
    ] = None

    message: str = Field(
        min_length=1,
        max_length=5000
    )

    @field_validator(
        "communication_type",
        mode="before"
    )
    @classmethod
    def normalize_comm_type(cls, v):

        if isinstance(v, str):
            v = v.strip().upper()

        return v

    @field_validator(
        "channel",
        mode="before"
    )
    @classmethod
    def normalize_channel(cls, v):

        if isinstance(v, str):
            v = v.strip().lower()

        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str):

        return validate_meaningful_text(
            v,
            "Message",
            1,
            5000,
            required=True,
        )

    @model_validator(mode="after")
    def sync_communication_type(self):

        if (
            self.communication_type is None
            and self.channel is not None
        ):
            self.communication_type = (
                self.channel.upper()
            )

        if (
            self.channel is None
            and self.communication_type is not None
        ):
            self.channel = (
                self.communication_type.lower()
            )

        return self


class CommunicationResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    channel: Optional[str] = None
    communication_type: Optional[str] = None
    message: str
    status: Optional[str] = None
    delivery_status: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @model_validator(mode="after")
    def sync_channel_and_status(self):

        if (
            not self.channel
            and self.communication_type
        ):
            self.channel = self.communication_type

        if (
            not self.communication_type
            and self.channel
        ):
            self.communication_type = self.channel

        if (
            not self.status
            and self.delivery_status
        ):
            self.status = self.delivery_status

        if (
            not self.delivery_status
            and self.status
        ):
            self.delivery_status = self.status

        if (
            not self.sent_at
            and self.created_at
        ):
            self.sent_at = self.created_at

        return self

class ReferralCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    referred_customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    referral_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional custom referral code. If not provided, one is automatically generated."
    )

    @model_validator(mode="after")
    def validate_referral(self):

        if (
            self.customer_id is not None
            and self.referred_customer_id is not None
            and self.customer_id
            == self.referred_customer_id
        ):
            raise ValueError(
                "Customer cannot refer themselves"
            )

        return self


class ReferralResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    referral_code: Optional[str] = None
    referred_customer_id: Optional[int] = None
    reward_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CustomerNoteCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    note: str = Field(
        min_length=5,
        max_length=5000,
        description="Meaningful note text (letters must exceed digits, no repeating ??)",
    )

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str):
        if v is None:
            raise ValueError("Note is required and cannot be null")

        if not isinstance(v, str):
            raise ValueError("Note must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Note cannot be empty or whitespace")

        if len(v) < 5 or len(v) > 5000:
            raise ValueError("Note must be between 5 and 5000 characters")

        # Reject HTML or dangerous script injections
        dangerous_patterns = [
            r"<\s*script",
            r"<\s*/\s*script",
            r"<\s*iframe",
            r"<\s*style",
            r"javascript\s*:",
            r"onload\s*=",
            r"onerror\s*=",
            r"<\s*img",
            r"<\s*a\s+",
            r"alert\s*\(",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Note contains invalid or dangerous HTML/script content")

        if "<" in v and ">" in v:
            raise ValueError("HTML tags are not allowed in note")

        # Reject consecutive repeating question marks or punctuation (e.g. ????? from Image 2)
        if re.search(r"\?{2,}", v):
            raise ValueError("Note cannot contain consecutive repeating question marks")

        if re.search(r"!{3,}", v):
            raise ValueError("Note cannot contain consecutive repeating exclamation marks")

        if re.search(r"[-+*/=_]{3,}", v):
            raise ValueError("Note cannot contain consecutive repeating symbols")

        # Reject placeholder phrases or meta dummy text
        clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
        if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
            raise ValueError(f"Note cannot be placeholder '{v}'")

        clean_phrase = re.sub(r"[^a-zA-Z\s]", "", v.lower()).strip()
        clean_phrase = re.sub(r"\s+", " ", clean_phrase)
        disallowed_note_phrases = {
            "note is not required",
            "not required",
            "no note",
            "nothing",
            "test note",
            "dummy note",
            "sample note",
            "ordinary note",
        }
        if clean_phrase in disallowed_note_phrases:
            raise ValueError(f"Note cannot be placeholder or test phrase '{v}'")

        # Letter and digit checks (Image 1 fix)
        alpha_chars = [c.lower() for c in v if c.isalpha()]
        alpha_count = len(alpha_chars)
        digit_count = sum(1 for c in v if c.isdigit())

        if alpha_count < 3:
            raise ValueError("Note must contain meaningful text with at least 3 letters")

        # Digits must not dominate descriptive text (rejects 99% numerical/decimal spam)
        if digit_count >= alpha_count:
            raise ValueError("Note cannot contain more digits than letters or be dominated by numbers/decimals")

        # Reject long consecutive numeric sequences
        if re.search(r"\d{15,}", v):
            raise ValueError("Note cannot contain excessively long continuous number sequences")

        # Reject repetitive single character spam (e.g. "aaaaa", "ppppp")
        if len(set(alpha_chars)) < 2:
            raise ValueError(f"Note cannot consist of repetitive characters '{v}'")

        # Reject excessively long unbroken words, numbers, or gibberish (e.g. Image 1 token)
        words = v.split()
        if len(words) < 2 and len(v) > 20:
            raise ValueError("Note must contain at least 2 words")

        for word in words:
            if len(word) > 35:
                raise ValueError("Note cannot contain excessively long unbroken words, numbers, or random gibberish")

        return v


class CustomerNoteResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    note: str
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class CampaignSendRequest(BaseModel):

    campaign_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    channel: Optional[
        Literal["whatsapp", "sms", "email"]
    ] = None

    customer_ids: Optional[list[int]] = Field(
        default=None,
        min_length=1
    )

    communication_type: Optional[str] = None

    message: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=5000,
    )

    @field_validator("customer_ids")
    @classmethod
    def validate_customer_ids(
        cls,
        v: Optional[list[int]]
    ):

        if v is None:
            return None

        if not v:
            raise ValueError(
                "customer_ids cannot be empty"
            )

        for cid in v:
            if cid <= 0:
                raise ValueError(
                    "Customer IDs must be positive integers"
                )

        return v

    @field_validator(
        "communication_type",
        mode="before"
    )
    @classmethod
    def validate_comm_type(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v = v.strip().upper()

        if v not in (
            "SMS",
            "WHATSAPP",
            "EMAIL"
        ):
            raise ValueError(
                "Invalid communication type. "
                "Allowed values: SMS, WHATSAPP, EMAIL"
            )

        return v

    @field_validator(
        "channel",
        mode="before"
    )
    @classmethod
    def normalize_channel(cls, v):

        if isinstance(v, str):
            v = v.strip().lower()

        return v

    @field_validator("message")
    @classmethod
    def validate_message(
        cls,
        v: Optional[str]
    ):

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Message",
            1,
            5000,
            required=True,
        )

    @model_validator(mode="after")
    def sync_campaign_channel_and_type(self):

        if (
            self.communication_type is None
            and self.channel is not None
        ):
            self.communication_type = (
                self.channel.upper()
            )

        if (
            self.channel is None
            and self.communication_type is not None
        ):
            self.channel = (
                self.communication_type.lower()
            )

        return self


class CampaignSendResponse(BaseModel):

    campaign_id: Optional[int] = None
    sent_count: int
    failed_count: int
    message: str
    total_customers: Optional[int] = None


class TopCustomerResponse(BaseModel):

    id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total_spend: Optional[float] = None
    loyalty_points: Optional[int] = None
    status: Optional[str] = None
    order_count: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class RetentionResponse(BaseModel):

    total_customers: int
    active_customers: Optional[int] = None
    inactive_customers: Optional[int] = None
    retained_customers: Optional[int] = None
    retention_rate: float


class LifetimeValueResponse(BaseModel):

    customer_id: int
    customer_name: str
    total_spend: Optional[float] = None
    loyalty_points: Optional[int] = None
    lifetime_value: Optional[Decimal] = None
    total_orders: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class LoyaltyReportResponse(BaseModel):

    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    points_earned: Optional[int] = None
    points_redeemed: Optional[int] = None
    balance_points: Optional[int] = None
    total_customers: Optional[int] = None
    total_points_earned: Optional[int] = None
    total_points_redeemed: Optional[int] = None
    total_points_balance: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class CustomerStatusUpdate(BaseModel):

    status: Literal[
        "active",
        "inactive",
        "blocked"
    ]


class CustomerCounts(BaseModel):
    """Customer summary counts for list view display."""

    total: int = 0
    active: int = 0
    inactive: int = 0
    blocked: int = 0
    new: int = 0
    regular: int = 0
    vip: int = 0


class CustomerListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CustomerResponse] = Field(default_factory=list)


class CustomerReferralListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[ReferralResponse] = Field(default_factory=list)


class CustomerCommunicationListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CommunicationResponse] = Field(default_factory=list)


class TopCustomerListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[TopCustomerResponse] = Field(default_factory=list)


class LifetimeValueListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[LifetimeValueResponse] = Field(default_factory=list)


class LoyaltyReportListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[LoyaltyReportResponse] = Field(default_factory=list)


class CreditLimitUpdateRequest(BaseModel):
    credit_limit: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("99999999.99"),
        description="Customer credit limit (must be non-negative)",
    )


class CustomerPaymentRequest(BaseModel):
    amount: Decimal = Field(
        ...,
        gt=Decimal("0.00"),
        le=Decimal("99999999.99"),
        description="Payment amount to credit against dues",
    )
    payment_method: str = Field(
        default="cash",
        description="Payment method: cash, upi, card, bank_transfer",
    )
    reference_no: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Transaction or payment reference number",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Payment remarks or invoice reference",
    )


class CustomerLedgerEntryResponse(BaseModel):
    id: int
    customer_id: int
    entry_type: str
    amount: Decimal
    balance_after: Decimal
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerLedgerStatementResponse(BaseModel):
    success: bool = True
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    outstanding_balance: Decimal
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")
    entries: list[CustomerLedgerEntryResponse] = Field(default_factory=list)


class FeedbackAnalyticsResponse(BaseModel):
    success: bool = True
    total_feedbacks: int
    average_rating: float
    rating_breakdown: dict[str, int]
    nps_score: float


class CustomerDeleteResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int


class SendLedgerPdfResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int
    customer_name: str
    phone: Optional[str] = None
    outstanding_balance: Decimal
    communication_id: int


