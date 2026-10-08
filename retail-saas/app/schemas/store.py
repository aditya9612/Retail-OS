import re
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, EmailStr
from app.utils.validators import validate_email_address, validate_gstin_number

INDIAN_STATES_AND_UTS = {
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
NON_CITY_LOCATION_NAMES = {
    "india",
    "japan",
    "china",
    "nepal",
    "bhutan",
    "bangladesh",
    "pakistan",
    "sri lanka",
    "afghanistan",
    "united states",
    "united kingdom",
    "canada",
    "australia",
    "germany",
    "france",
    "italy",
    "spain",
    "russia",
    "singapore",
    "malaysia",
    "thailand",
}

NON_CITY_LOCATION_NAMES.update(
    {state.lower() for state in INDIAN_STATES_AND_UTS}
)

class StoreCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=50)
    state: Optional[str] = Field(default=None, max_length=50)
    pincode: Optional[str] = Field(default=None, max_length=10)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = None
    is_main: bool = False
    gstin: Optional[str] = Field(default=None, max_length=15)
    is_warehouse: Optional[bool] = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        if value.lower() in {
            "string",
            "test",
            "name",
            "store",
            "example",
            "null",
            "none",
            "n/a",
            "na",
        }:
            raise ValueError("Please enter a valid store name")

        if not value:
            raise ValueError("Store name is required")

        if len(value) < 2:
             raise ValueError("Store name must contain at least 2 characters")

        if len(value) > 100:
             raise ValueError("Store name must not exceed 100 characters")

             # Must contain at least one alphabetic character
        if not re.search(r"[A-Za-z]", value):
             raise ValueError(
                 "Store name must contain at least one letter"
        )

    # Allow letters, numbers, spaces and common name characters
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9\s.&'()_-]*",
            value
        ):
             raise ValueError(
                 "Store name contains invalid characters"
        )

        return value


    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if value is None:
         return None

        value = value.strip().upper()

        if not value:
            raise ValueError("Store code is required")

        if len(value) < 2:
            raise ValueError("Store code must contain at least 2 characters")

        if len(value) > 20:
            raise ValueError("Store code must not exceed 20 characters")

        # Must start with a letter
        if not re.fullmatch(r"[A-Z][A-Z0-9_-]*", value):
            raise ValueError(
                "Store code must start with a letter and contain only "
                "letters, numbers, hyphens and underscores"
            )

        return value

    @field_validator("address")
    @classmethod
    def validate_address(cls, value):
        if value is None:
         return None

        value = value.strip()

        if not value:
            raise ValueError("Address is required")

        if len(value) < 5:
            raise ValueError("Address must contain at least 5 characters")

        if len(value) > 250:
            raise ValueError("Address must not exceed 250 characters")

        # Address must contain at least one letter
        if not re.search(r"[A-Za-z]", value):
            raise ValueError("Address must contain at least one letter")

        # Reject an address containing only special characters/numbers
        if not re.search(r"[A-Za-z0-9]", value):
            raise ValueError("Invalid address")

        # Allow normal address characters
        if not re.fullmatch(
            r"[A-Za-z0-9\s,./#&'()\-]+",
            value
        ):
            raise ValueError("Address contains invalid characters")

        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value):
        if value is None:
            return None

        value = value.strip()
        if value.lower() in {
          "string",
          "test",
          "city",
          "example",
          "null",
          "none",
          "n/a",
          "na",
            }:
          raise ValueError("Please enter a valid city name")
        if not value:
            raise ValueError("City is required")

        if len(value) < 2:
            raise ValueError("City must contain at least 2 characters")

        if len(value) > 100:
            raise ValueError("City must not exceed 100 characters")

        if not re.search(r"[A-Za-z]", value):
            raise ValueError("City must contain at least one letter")

        if not re.fullmatch(r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*", value):
            raise ValueError(
            "City must contain only letters, spaces, hyphens and apostrophes"
        )

        if value.lower() in NON_CITY_LOCATION_NAMES:
            raise ValueError("Please enter a valid city name")

        return value

    @field_validator("state")
    @classmethod
    def validate_state(cls, value):
        if value is None:
         return None

        value = value.strip()

        if not value:
            raise ValueError("State is required")

        # Case-insensitive matching
        matched_state = next(
            (
                state
                for state in INDIAN_STATES_AND_UTS
                if state.lower() == value.lower()
            ),
            None,
        )

        if not matched_state:
            raise ValueError(
                "Invalid Indian state or union territory"
            )

        # Return standard name
        return matched_state

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value):
        if value is None:
         return None
        value = value.strip()                                           # Exactly 6 digits
        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must be exactly 6 digits")        # Reject all same digits
        if len(set(value)) == 1:
            raise ValueError("Invalid pincode")                    # Reject obvious sequential test values
        if value in {"123456", "654321"}:
            raise ValueError("Invalid pincode")

        # Indian PIN cannot start with 0
        if value.startswith("0"):
            raise ValueError("Invalid Indian pincode")

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if v is None:
          return None

        clean_phone = v.strip()

        if not clean_phone.isdigit() or len(clean_phone) != 10:
            raise ValueError("Phone number must be exactly 10 digits")

        if clean_phone[0] not in "6789":
            raise ValueError("Phone number must start with 6, 7, 8, or 9")

        if len(set(clean_phone)) == 1:
            raise ValueError("Please enter a valid phone number")

        return clean_phone

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is None:
            return None
        return validate_email_address(value, field_name="Store email", required=False)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_main: Optional[bool] = None
    gstin: Optional[str] = None
    is_active: Optional[bool] = None
    is_warehouse: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        if value.lower() in {
            "string",
            "test",
            "name",
            "store",
            "example",
            "null",
            "none",
            "n/a",
            "na",
        }:
            raise ValueError("Please enter a valid store name")
        if not value:
            raise ValueError("Store name is required")

        if len(value) < 2:
            raise ValueError("Store name must contain at least 2 characters")

        if len(value) > 100:
            raise ValueError("Store name must not exceed 100 characters")

        if not re.search(r"[A-Za-z]", value):
            raise ValueError("Store name must contain at least one letter")

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&'()_-]*", value):
            raise ValueError(
                "Store name contains invalid characters"
            )

        return value

    @field_validator("address")
    @classmethod
    def validate_address(cls, value):
        if value is None:
            return None
        value = value.strip()

        if not value:
            raise ValueError("Address is required")

        if len(value) < 5:
            raise ValueError("Address must contain at least 5 characters")

        if len(value) > 250:
            raise ValueError("Address must not exceed 250 characters")

        # Address must contain at least one letter
        if not re.search(r"[A-Za-z]", value):
            raise ValueError("Address must contain at least one letter")

        # Reject an address containing only special characters/numbers
        if not re.search(r"[A-Za-z0-9]", value):
            raise ValueError("Invalid address")

        # Allow normal address characters
        if not re.fullmatch(
            r"[A-Za-z0-9\s,./#&'()\-]+",
            value
        ):
            raise ValueError("Address contains invalid characters")

        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value):
        if value is None:
            return None

        value = value.strip()

        if value.lower() in {
            "string",
            "test",
            "city",
            "example",
            "null",
            "none",
            "n/a",
        "na",
        }:
            raise ValueError("Please enter a valid city name")
        if not value:
            raise ValueError("City is required")

        if len(value) < 2:
            raise ValueError("City must contain at least 2 characters")

        if len(value) > 100:
            raise ValueError("City must not exceed 100 characters")

        if not re.search(r"[A-Za-z]", value):
            raise ValueError("City must contain at least one letter")

        if not re.fullmatch(r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*", value):
            raise ValueError(
            "City must contain only letters, spaces, hyphens and apostrophes"
        )

        if value.lower() in NON_CITY_LOCATION_NAMES:
            raise ValueError("Please enter a valid city name")

        return value

    @field_validator("state")
    @classmethod
    def validate_state(cls, value):
        if value is None:
            return None
        value = value.strip()

        if not value:
            raise ValueError("State is required")

        # Case-insensitive matching
        matched_state = next(
            (
                state
                for state in INDIAN_STATES_AND_UTS
                if state.lower() == value.lower()
            ),
            None,
        )

        if not matched_state:
            raise ValueError(
                "Invalid Indian state or union territory"
            )

        # Return standard name
        return matched_state

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value):
        if value is None:
            return None
        value = value.strip()

        # Exactly 6 digits
        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must be exactly 6 digits")

        # Reject all same digits
        if len(set(value)) == 1:
            raise ValueError("Invalid pincode")

        # Reject obvious sequential test values
        if value in {"123456", "654321"}:
            raise ValueError("Invalid pincode")

        # Indian PIN cannot start with 0
        if value.startswith("0"):
            raise ValueError("Invalid Indian pincode")

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if v is None:
            return None
        clean_phone = v.strip()

        clean_phone = v.strip()

        if not clean_phone.isdigit() or len(clean_phone) != 10:
            raise ValueError("Phone number must be exactly 10 digits")

        if clean_phone[0] not in "6789":
            raise ValueError("Phone number must start with 6, 7, 8, or 9")

        if len(set(clean_phone)) == 1:
            raise ValueError("Please enter a valid phone number")

        return clean_phone
    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is None:
            return None
        return validate_email_address(value, field_name="Store email", required=False)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)



from pydantic import BaseModel, ConfigDict, EmailStr


class StoreResponse(BaseModel):
    id: int
    tenant_id: int

    name: str
    code: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None

    pincode: int | None = None
    phone: int | None = None
    email: EmailStr | None = None

    is_main: bool = False
    gstin: str | None = None
    is_active: bool = True
    is_warehouse: bool = False

    model_config = ConfigDict(from_attributes=True)