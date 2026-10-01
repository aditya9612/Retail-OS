from email_validator import validate_email
from email_validator import validate_email
from email_validator import validate_email
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic import  ConfigDict, EmailStr

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
    def validate_role(cls, v: str) -> str:
        value = v.strip()

        if not value:
            raise ValueError("Role cannot be empty")

        if value.lower() in {
        "string",
        "test",
        "role",
        "example",
        "null",
        "none",
        "n/a",
        "na",
        }:
            raise ValueError("Please enter a valid role")

        if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
            raise ValueError(
            "Role can contain only letters with a single space between words. "
            "Numbers and special characters are not allowed."
        )

        if len(value) < 2 or len(value) > 50:
                raise ValueError("Role must be between 2 and 50 characters")

        return value
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()

        if not email:
            raise ValueError("Email is required")

        if len(email) > 254:
                raise ValueError("Email must not exceed 254 characters")

    # No spaces allowed
        if " " in email:
            raise ValueError("Email must not contain spaces")

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


    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        value = v.strip()

        if not value:
            raise ValueError("Role cannot be empty")

        if value.lower() in {
        "string",
        "test",
        "role",
        "example",
        "null",
        "none",
        "n/a",
        "na",
        }:
                raise ValueError("Please enter a valid role")

        if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
            raise ValueError(
                "Role can contain only letters with a single space between words. "
                "Numbers and special characters are not allowed."
        )

        if len(value) < 2 or len(value) > 50:
            raise ValueError("Role must be between 2 and 50 characters")

        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()

        if not email:
            raise ValueError("Email is required")

        if len(email) > 254:
            raise ValueError("Email must not exceed 254 characters")

        # No spaces allowed
        if " " in email:
            raise ValueError("Email must not contain spaces")

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

        # Local part validati   on
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
class StaffResponse(BaseModel):
    id: int

    name: str
    email: EmailStr
    phone: str
    role: str

    store_id: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)