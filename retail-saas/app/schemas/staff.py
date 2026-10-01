import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class StaffCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )

    email: str

    phone: str

    role: str

    is_active: bool = True

@field_validator("name")
@classmethod
def validate_name(cls, value: str) -> str:
    # Do not silently accept leading/trailing spaces
    if value != value.strip():
        raise ValueError(
            "Name must not have leading or trailing spaces"
        )

    if not value:
        raise ValueError("Name is required")

    if len(value) < 2:
        raise ValueError("Name must contain at least 2 characters")

    if len(value) > 100:
        raise ValueError("Name must not exceed 100 characters")

    # Only English letters and exactly one space between words.
    # Rejects numbers and all special characters.
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Name can contain only letters with a single space "
            "between words. Numbers and special characters are not allowed."
        )

    return value

@field_validator("role")
@classmethod
def validate_role(cls, value: str) -> str:
    # Do not silently accept leading/trailing spaces
    if value != value.strip():
        raise ValueError(
            "Role must not have leading or trailing spaces"
        )

    if not value:
        raise ValueError("Role is required")

    if len(value) < 2:
        raise ValueError("Role must contain at least 2 characters")

    if len(value) > 50:
        raise ValueError("Role must not exceed 50 characters")

    # Only English letters and exactly one space between words.    # Rejects numbers and all special characters.
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Role can contain only letters with a single space "
            "between words. Numbers and special characters are not allowed."
        )

    return value

@field_validator("phone")
@classmethod
def validate_phone(cls, v: str) -> str:
    clean_phone = v.strip()

    # Only 10 digits, starting with 6, 7, 8, or 9
    if not re.fullmatch(r"[6-9][0-9]{9}", clean_phone):
        raise ValueError(
            "Mobile number must contain exactly 10 digits "
            "and must start with 6, 7, 8, or 9. "
            "Letters, spaces, and special characters are not allowed."
        )

    return clean_phone

@field_validator("email")
@classmethod
def validate_email(cls, value: str) -> str:
    email = value.strip().lower()

    if not email:
        raise ValueError("Email is required")

    # Maximum email length according to common email standards
    if len(email) > 254:
        raise ValueError("Email must not exceed 254 characters")

    # No spaces allowed
    if re.search(r"\s", email):
        raise ValueError("Email must not contain spaces")

    # Exactly one @ symbol
    if email.count("@") != 1:
        raise ValueError("Email must contain exactly one @ symbol")

    local_part, domain = email.split("@")

    # Local part validation
    if not local_part:
        raise ValueError("Email username is required")

    if len(local_part) > 64:
        raise ValueError("Email username must not exceed 64 characters")

    # Cannot start or end with a dot
    if local_part.startswith(".") or local_part.endswith("."):
        raise ValueError("Email username cannot start or end with a dot")

    # No consecutive dots
    if ".." in email:
        raise ValueError("Email must not contain consecutive dots")

    # Allowed characters before @
    if not re.fullmatch(
        r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+",
        local_part,
    ):
        raise ValueError("Email username contains invalid characters")

    # Domain validation
    if not domain:
        raise ValueError("Email domain is required")

    if len(domain) > 253:
        raise ValueError("Email domain is too long")

    # Domain must contain only valid characters
    if not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+",
        domain,
    ):
        raise ValueError("Invalid email domain")

    # Domain extension must contain at least 2 letters
    extension = domain.rsplit(".", 1)[-1]

    if not re.fullmatch(r"[A-Za-z]{2,63}", extension):
        raise ValueError("Invalid email domain extension")

    return email

class StaffResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    role: str
    store_id: int
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class StaffUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100
    )

    email: Optional[str] = None

    phone: Optional[str] = None

    role: Optional[str] = None

    store_id: Optional[int] = Field(
        None,
        gt=0
    )

    is_active: Optional[bool] = None


@field_validator("name")
@classmethod
def validate_name(cls, value: str) -> str:
    # Do not silently accept leading/trailing spaces
    if value != value.strip():
        raise ValueError(
            "Name must not have leading or trailing spaces"
        )

    if not value:
        raise ValueError("Name is required")

    if len(value) < 2:
        raise ValueError("Name must contain at least 2 characters")

    if len(value) > 100:
        raise ValueError("Name must not exceed 100 characters")

    # Only English letters and exactly one space between words.
    # Rejects numbers and all special characters.
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Name can contain only letters with a single space "
            "between words. Numbers and special characters are not allowed."
        )

    return value

@field_validator("role")
@classmethod
def validate_role(cls, value: str) -> str:
    # Do not silently accept leading/trailing spaces
    if value != value.strip():
        raise ValueError(
            "Role must not have leading or trailing spaces"
        )

    if not value:
        raise ValueError("Role is required")

    if len(value) < 2:
        raise ValueError("Role must contain at least 2 characters")

    if len(value) > 50:
        raise ValueError("Role must not exceed 50 characters")

    # Only English letters and exactly one space between words.    # Rejects numbers and all special characters.
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Role can contain only letters with a single space "
            "between words. Numbers and special characters are not allowed."
        )

    return value

@field_validator("phone")
@classmethod
def validate_phone(cls, v: str) -> str:
    clean_phone = v.strip()

    # Only 10 digits, starting with 6, 7, 8, or 9
    if not re.fullmatch(r"[6-9][0-9]{9}", clean_phone):
        raise ValueError(
            "Mobile number must contain exactly 10 digits "
            "and must start with 6, 7, 8, or 9. "
            "Letters, spaces, and special characters are not allowed."
        )

    return clean_phone

@field_validator("email")
@classmethod
def validate_email(cls, value: str) -> str:
    email = value.strip().lower()

    if not email:
        raise ValueError("Email is required")

    # Maximum email length according to common email standards
    if len(email) > 254:
        raise ValueError("Email must not exceed 254 characters")

    # No spaces allowed
    if re.search(r"\s", email):
        raise ValueError("Email must not contain spaces")

    # Exactly one @ symbol
    if email.count("@") != 1:
        raise ValueError("Email must contain exactly one @ symbol")

    local_part, domain = email.split("@")

    # Local part validation
    if not local_part:
        raise ValueError("Email username is required")

    if len(local_part) > 64:
        raise ValueError("Email username must not exceed 64 characters")

    # Cannot start or end with a dot
    if local_part.startswith(".") or local_part.endswith("."):
        raise ValueError("Email username cannot start or end with a dot")

    # No consecutive dots
    if ".." in email:
        raise ValueError("Email must not contain consecutive dots")

    # Allowed characters before @
    if not re.fullmatch(
        r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+",
        local_part,
    ):
        raise ValueError("Email username contains invalid characters")

    # Domain validation
    if not domain:
        raise ValueError("Email domain is required")

    if len(domain) > 253:
        raise ValueError("Email domain is too long")

    # Domain must contain only valid characters
    if not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+",
        domain,
    ):
        raise ValueError("Invalid email domain")

    # Domain extension must contain at least 2 letters
    extension = domain.rsplit(".", 1)[-1]

    if not re.fullmatch(r"[A-Za-z]{2,63}", extension):
        raise ValueError("Invalid email domain extension")

    return email



class StaffAssign(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0
    )

    store_id: int = Field(
        ...,
        gt=0
    )


class StaffTransfer(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0
    )

    source_store_id: int = Field(
        ...,
        gt=0
    )

    destination_store_id: int = Field(
        ...,
        gt=0
    )
