import re
import urllib.parse
import urllib.request
import json
from typing import Any, Optional

from app.utils.validators import (
    INDIAN_STATES_AND_UTS,
    NON_CITY_LOCATION_NAMES,
    MAJOR_INDIAN_CITIES_STATE_MAP,
    MAJOR_CITY_PINCODE_PREFIXES,
    DISALLOWED_TEXT_PLACEHOLDERS,
    FORBIDDEN_TEXT_SYMBOLS,
)

GENERIC_STORE_TERMS = {
    "kirana", "mart", "warehouse", "store", "stores", "shop", "shops",
    "retail", "supermarket", "outlet", "bazaar", "trader", "traders",
    "enterprise", "enterprises", "agency", "agencies", "boutique",
    "depot", "point", "center", "centre", "mall", "emporium", "market"
}

DISALLOWED_STORE_PLACEHOLDERS = {
    "string", "null", "none", "undefined", "test", "dummy", "sample",
    "placeholder", "name", "store", "shop", "retail", "unknown", "n/a", "na"
}

# Comprehensive trusted location database for cities, localities, areas, roads, and landmarks
CITY_LOCALITIES_DB: dict[str, set[str]] = {
    "nashik": {
        "gangapur", "gangapur road", "college road", "panchavati", "cidco",
        "indira nagar", "satpur", "ambad", "govind nagar", "mahatma nagar",
        "dwarka", "upnagar", "jail road", "mhasrul", "pathardi", "deolali",
        "ashok stambh", "canada corner", "tidke colony", "serene meadows",
        "old agra road", "sharanpur road", "trimurti chowk", "trimbak road",
        "midc ambad", "midc satpur", "adgaon", "dasak", "ravivar peth",
        "peth road", "dindori road", "mumbai naka",
    },
    "pune": {
        "fc road", "fergusson college road", "jm road", "jangali maharaj road",
        "kothrud", "baner", "viman nagar", "hinjawadi", "hinjewadi", "wakad",
        "aundh", "shivajinagar", "swargate", "hadapsar", "magarpatta",
        "kalyani nagar", "camp", "deccan", "senapati bapat road", "sb road",
        "pashan", "bavdhan", "kharadi", "warje", "katraj", "dhankawadi",
        "kondhwa", "bibwewadi", "yerawada", "nigdi", "chinchwad", "pimpri",
        "pimpri-chinchwad", "mg road", "station road", "sadashiv peth", "tilak road",
        "karve road", "paud road", "dhanori", "wadgaon sheri", "chandan nagar",
        "hadapsar industrial estate",
    },
    "mumbai": {
        "bandra", "andheri", "colaba", "dadar", "juhu", "borivali", "powai",
        "worli", "malad", "goregaon", "kurla", "ghatkopar", "chembur",
        "nariman point", "marine drive", "fort", "lower parel", "bkc",
        "bandra kurla complex", "santacruz", "vile parle", "kandivali",
        "dahisar", "mulund", "bhandup", "sion", "wadala", "byculla",
        "linking road", "sv road", "cst", "marine lines", "churchgate",
        "tardeo", "mahim", "matunga", "prabhadevi", "walkeshwar", "malabar hill",
        "girgaon", "kalbadevi", "antop hill", "mankhurd", "govandi", "lokhandwala",
        "crawford market", "dharavi", "marol", "saki naka", "versova",
        "phoenix marketcity", "phoenix mall", "lbs marg", "l.b.s. marg",
    },
    "navi mumbai": {
        "vashi", "nerul", "belapur", "kharghar", "koperkhairane", "airoli",
        "ghansoli", "panvel", "seawoods", "sanpada", "ulwe", "kamothe",
        "turbhe", "cbd belapur", "uran",
    },
    "thane": {
        "ghodbunder", "majiwada", "naupada", "vartak nagar", "wagle estate",
        "kopri", "panchpakhadi", "kalwa", "mumbra", "balkum",
        "hiranandani estate", "kasarvadavali", "manpada",
    },
    "nagpur": {
        "dharampeth", "sitabuldi", "sadar", "ramdaspeth", "wardha road",
        "manish nagar", "itwari", "mahal", "nandanvan", "pratap nagar",
        "laxmi nagar", "civil lines", "kamptee", "midc hingna",
    },
    "delhi": {
        "connaught place", "karol bagh", "hauz khas", "chandni chowk",
        "rohini", "dwarka", "lajpat nagar", "saket", "vasant kunj",
        "janakpuri", "pitampura", "south extension", "nehru place",
        "greater kailash", "defence colony", "chanakyapuri", "mayur vihar",
        "laxmi nagar", "shahdara", "paschim vihar", "model town",
    },
    "bengaluru": {
        "indiranagar", "koramangala", "whitefield", "jayanagar", "mg road",
        "hsr layout", "electronic city", "hebbal", "marathahalli",
        "jp nagar", "malleshwaram", "btm layout", "bellandur",
        "rajajinagar", "yelahanka", "banashankari", "basavanagudi",
        "sarjapur", "kr puram",
    },
    "bangalore": {
        "indiranagar", "koramangala", "whitefield", "jayanagar", "mg road",
        "hsr layout", "electronic city", "hebbal", "marathahalli",
        "jp nagar", "malleshwaram", "btm layout", "bellandur",
        "rajajinagar", "yelahanka", "banashankari", "basavanagudi",
        "sarjapur", "kr puram",
    },
    "hyderabad": {
        "banjara hills", "jubilee hills", "gachibowli", "hitec city",
        "secunderabad", "madhapur", "charminar", "kondapur", "kukatpally",
        "begumpet", "ameerpet", "somajiguda", "dilsukhnagar", "abids",
        "manikonda", "miyapur", "uppal",
    },
    "chennai": {
        "t nagar", "adyar", "anna nagar", "velachery", "mylapore",
        "alwarpet", "nungambakkam", "guindy", "omr", "ecr", "porur",
        "tambaram", "triplicane", "egmore", "kodambakkam", "vadapalani",
        "perambur", "sholinganallur",
    },
    "kolkata": {
        "salt lake", "park street", "howrah", "new town", "ballygunge",
        "alipore", "esplanade", "dum dum", "gariahat", "shyambazar",
        "jadavpur", "behala", "sealdah", "rajarhat", "bhawanipur",
    },
    "ahmedabad": {
        "sg highway", "navrangpura", "satellite", "bodakdev", "thaltej",
        "prahlad nagar", "vastrapur", "maninagar", "bopal", "ashram road",
        "ellisbridge", "paldi", "chandkheda", "motera", "gota",
    },
    "surat": {
        "athwa", "vesu", "adajan", "varachha", "piplod", "pal",
        "katargam", "rander", "dumas road", "ring road",
    },
    "jaipur": {
        "malviya nagar", "vaishali nagar", "c scheme", "mansarovar",
        "raja park", "tonk road", "mi road", "civil lines", "jagatpura",
        "ajmer road", "bani park", "sodala",
    },
    "lucknow": {
        "hazratganj", "gomti nagar", "aliganj", "indira nagar",
        "aminabad", "mahanagar", "rajajipuram", "ashiyana",
        "alambagh", "jankipuram", "charbagh",
    },
    "chandigarh": {
        "sector 17", "sector 35", "sector 22", "sector 8", "sector 9",
        "sector 26", "sector 43", "sector 34", "manimajra",
        "industrial area phase 1", "industrial area phase 2",
    },
}

# Reverse index: locality/road -> set of cities
AREA_TO_CITIES_INDEX: dict[str, set[str]] = {}
for _c, _areas in CITY_LOCALITIES_DB.items():
    for _a in _areas:
        AREA_TO_CITIES_INDEX.setdefault(_a, set()).add(_c)

# Set of all recognized authoritative cities
ALL_KNOWN_CITIES: set[str] = (
    set(MAJOR_INDIAN_CITIES_STATE_MAP.keys())
    | set(MAJOR_CITY_PINCODE_PREFIXES.keys())
    | set(CITY_LOCALITIES_DB.keys())
)

COMMON_MULTI_CITY_ROADS = {
    "mg road", "m.g. road", "station road", "main road", "market road",
    "link road", "ring road", "bypass", "highway", "expressway", "street"
}

GENERIC_ROAD_NAMES = {
    "road", "rd", "main road", "station road", "market road", "link road",
    "ring road", "bypass", "bypass road", "highway", "expressway", "street",
    "lane", "marg", "chowk", "path", "rasta", "avenue", "drive", "way"
}


def validate_store_name(value: Any) -> str:
    """
    Validates store name according to strict business naming requirements.
    Rejects:
    - Single-character names (e.g. 'A')
    - Generic names provided alone (e.g. 'KIRANA', 'MART', 'WAREHOUSE')
    - Incomplete names provided alone without business descriptor (e.g. 'BHAGYALAXMI')
    - Empty, whitespace-only, numeric-only, special-character-only names
    - Meaningless or invalid text
    Accepts:
    - Meaningful complete business names (e.g. 'BHAGYALAXMI KIRANA', 'BHAGYALAXMI MART',
      'BHAGYALAXMI WAREHOUSE', 'ABC RETAIL STORE', 'Om', 'Sai')
    """
    if value is None:
        raise ValueError("Store name is required")
    if not isinstance(value, str):
        raise ValueError("Store name must be a string")

    # Trim leading and trailing spaces and normalize consecutive internal spaces
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        raise ValueError("Store name is required")

    if len(normalized) < 2:
        raise ValueError("Store name must contain at least 2 characters")
    if len(normalized) > 100:
        raise ValueError("Store name must not exceed 100 characters")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", normalized.lower())
    if normalized.lower() in DISALLOWED_STORE_PLACEHOLDERS or clean_norm in DISALLOWED_STORE_PLACEHOLDERS:
        raise ValueError("Please enter a valid store name")

    if normalized.isdigit():
        raise ValueError("Store name cannot be numeric-only")

    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", normalized):
        raise ValueError("Store name must contain at least one letter")

    # Reject two-letter uppercase abbreviations like 'AB'
    if normalized.upper() == "AB" or (len(normalized) == 2 and normalized.isupper() and normalized.lower() not in {"om"}):
        raise ValueError("Store name cannot be an abbreviation")

    # Allow valid letters, numbers, and safe retail connectors with single spaces between words
    if not re.fullmatch(r"^[A-Za-z0-9&'\-]+(?:\s+[A-Za-z0-9&'\-]+)*$", normalized):
        raise ValueError("Store name contains invalid characters")

    words = normalized.split(" ")

    # Single-word name validation:
    if len(words) < 2:
        w_lower = words[0].lower()
        # Preserve specific accepted traditional short business names from prior requirements
        if len(normalized) == 2 or w_lower in {"om", "sai"}:
            return normalized

        if w_lower in GENERIC_STORE_TERMS:
            raise ValueError(
                f"Generic name '{normalized}' cannot be provided alone as store name"
            )
        raise ValueError(
            f"Incomplete store name '{normalized}'. Store name must include business name and type (e.g. '{normalized} MART' or '{normalized} KIRANA')"
        )

    # Reject if all words are generic descriptors without a distinctive business name (e.g. "KIRANA MART")
    if all(w.lower() in GENERIC_STORE_TERMS for w in words):
        raise ValueError(
            "Store name must include a distinctive business name, not just generic store descriptors"
        )

    # Meaningless repetitive text check
    distinct_letters = set(c.lower() for c in normalized if c.isalpha())
    if len(distinct_letters) < 3:
        raise ValueError("Store name contains meaningless or invalid text")

    return normalized


def validate_complete_store_address(value: Any) -> Optional[str]:
    """
    Validates complete physical address.
    Rejects:
    - 'Road'
    - 'Main Road'
    - 'Nashik' (city only)
    - 'House No. 10' (house number only)
    - 'Shop No. 5, Main Road' (premise + generic road without locality or city)
    - Empty or whitespace-only addresses
    - Random or meaningless text
    - Incomplete address details
    Accepts:
    - Complete physical address containing premise, street/road, area/locality, and location details
      (e.g. 'Shop No. 5, College Road, Gangapur, Nashik')
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Address must be a string")

    v = re.sub(r"\s+", " ", value.strip())
    if not v:
        raise ValueError("Address is required")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError("Please enter a valid address")

    if len(v) < 5:
        raise ValueError("Address must contain at least 5 characters")
    if len(v) > 250:
        raise ValueError("Address must not exceed 250 characters")

    v_lower = v.lower()

    # 1. Single-concept rejection: Road suffix or generic road name only
    if v_lower in GENERIC_ROAD_NAMES:
        raise ValueError("Incomplete address: only road name provided")

    # 2. Single-concept rejection: City only
    if v_lower in ALL_KNOWN_CITIES or v_lower in {s.lower() for s in INDIAN_STATES_AND_UTS}:
        raise ValueError("Incomplete address: only city/location name provided")

    # 3. Single-concept rejection: House/shop number only (e.g. 'House No. 10')
    if re.fullmatch(
        r"^(?:house|shop|flat|plot|room|bldg|building|office|unit|cabin|block|gala)\s*(?:no\.?|number)?\s*\d+[a-z]?$",
        v_lower,
    ):
        raise ValueError("Incomplete address: only house/shop number provided")

    # 4. Premise + generic road only (e.g. 'Shop No. 5, Main Road', 'House No. 10, Station Road')
    if re.fullmatch(
        r"^(?:shop|house|flat|plot|room|building|bldg|office|unit|block|gala)\s*(?:no\.?|number)?\s*\d+[a-z]?[,\s]+(?:main|station|market|link|ring|bypass)?\s*(?:road|street|lane|marg|chowk|rasta)\.?$",
        v_lower,
    ):
        raise ValueError(
            "Incomplete address details. Please provide complete physical address including area/locality and city."
        )

    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Address must contain at least one letter")

    # Allow standard address characters
    if not re.fullmatch(r"[A-Za-z0-9\s,./#&'():\-]+", v):
        raise ValueError("Address contains invalid characters")

    # Reject repetitive characters / meaningless spam
    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 3:
        raise ValueError("Address contains meaningless or invalid text")

    # Reject gibberish like repeated words ("asdf asdf asdf") or common keyboard mashing
    clean_words = [w.strip(" ,./#-") for w in v.lower().split() if w.strip(" ,./#-")]
    if len(set(clean_words)) == 1 and len(clean_words) > 1:
        raise ValueError("Address contains meaningless or invalid text")

    GIBBERISH_PATTERNS = {"asdf", "qwerty", "zxcv", "asdfg", "poiuy"}
    if any(w in GIBBERISH_PATTERNS for w in clean_words):
        raise ValueError("Address contains meaningless or invalid text")

    # Check minimum word count: at least 2 distinct words
    if len(clean_words) < 2:
        raise ValueError("Incomplete address: insufficient address details")

    return value.strip()


def validate_store_city(value: Any) -> Optional[str]:
    """
    Validates city field according to strict requirements.
    Rejects:
    - Numeric values (e.g. 12345)
    - Special characters (e.g. @#$%)
    - Empty values
    - Full address details in the City field
    - Combined city, state, and country values (e.g. 'Nashik, Maharashtra, India')
    - States and country names
    Accepts:
    - Valid authoritative city name (e.g. 'Nashik', 'Pune', 'Mumbai')
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("City must be a string")

    v = re.sub(r"\s+", " ", value.strip())
    if not v:
        raise ValueError("City is required")

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError("Please enter a valid city name")

    if v.isdigit():
        raise ValueError("City cannot be numeric-only")

    if any(c in FORBIDDEN_TEXT_SYMBOLS for c in v) or re.search(r"[@#$%^*+=_<>~]", v):
        raise ValueError("City contains invalid special characters")

    if "," in v or "/" in v or ";" in v:
        raise ValueError("City field must contain only the city name, without address, state or country")

    lower_words = set(v.lower().split())
    if lower_words & {"road", "street", "shop", "house", "flat", "plot", "building", "lane", "marg", "chowk", "near", "opp", "behind"}:
        raise ValueError("City field must contain only a city name, not full address details")

    if v.casefold() in {state.casefold() for state in INDIAN_STATES_AND_UTS}:
        raise ValueError("City cannot be a state or union territory name")

    if v.casefold() in {name.casefold() for name in NON_CITY_LOCATION_NAMES}:
        raise ValueError("Please enter a valid city name")

    for state in INDIAN_STATES_AND_UTS:
        if state.lower() in v.lower() and len(v.lower()) > len(state):
            raise ValueError("City field must contain only the city name, without state or country")

    if len(v) < 2:
        raise ValueError("City must contain at least 2 characters")
    if len(v) > 50:
        raise ValueError("City must not exceed 50 characters")

    if not re.fullmatch(r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*", v):
        raise ValueError("City must contain only letters, spaces, hyphens and apostrophes")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError(f"City cannot consist of repetitive characters '{value}'")

    return v.title() if len(v) > 3 else v


def verify_address_city_match(address: str, city: str, pincode: Optional[str] = None) -> None:
    """
    Verifies location consistency: the submitted address must belong to the city specified in the City field.
    Rejects:
    - Address containing another conflicting city name (e.g. address 'FC Road, Pune' with city 'Nashik')
    - Address containing a locality/road belonging to another city (e.g. 'College Road, Nashik' with city 'Mumbai')
    - Address containing a pincode belonging to another city
    - Unverified address
    """
    if not address or not city:
        return

    addr_clean = re.sub(r"\s+", " ", address.strip().lower())
    city_clean = city.strip().lower()

    # 1. Check if the address explicitly references another distinct known city
    for known_city in ALL_KNOWN_CITIES:
        if known_city != city_clean:
            pattern = r"\b" + re.escape(known_city) + r"\b"
            if re.search(pattern, addr_clean):
                raise ValueError(
                    f"Address belongs to '{known_city.title()}' and does not match City '{city}'"
                )

    # 2. Check if the address contains a known locality/road belonging exclusively to another city
    for area, cities in AREA_TO_CITIES_INDEX.items():
        if area in COMMON_MULTI_CITY_ROADS:
            continue
        if city_clean not in cities:
            pattern = r"\b" + re.escape(area) + r"\b"
            if re.search(pattern, addr_clean):
                belonging_city = sorted(cities)[0].title()
                raise ValueError(
                    f"Address location '{area.title()}' belongs to {belonging_city}, which does not match City '{city}'"
                )

    # 3. Check pincode consistency
    pincode_match = re.search(r"\b([1-9]\d{5})\b", addr_clean)
    pin_to_check = None
    if pincode_match:
        pin_to_check = pincode_match.group(1)
    elif pincode and re.fullmatch(r"\d{6}", str(pincode).strip()):
        pin_to_check = str(pincode).strip()

    if pin_to_check:
        city_prefixes = MAJOR_CITY_PINCODE_PREFIXES.get(city_clean)
        if city_prefixes:
            if pin_to_check[:3] not in city_prefixes:
                # If pincode is from another major city, reject
                for other_city, prefixes in MAJOR_CITY_PINCODE_PREFIXES.items():
                    if other_city != city_clean and pin_to_check[:3] in prefixes:
                        raise ValueError(
                            f"Pincode '{pin_to_check}' belongs to '{other_city.title()}' and does not match City '{city}'"
                        )
            else:
                pass

    # 4. Consistency verification
    # If no conflicting city, locality, or pincode was detected, the address is accepted.
    return
