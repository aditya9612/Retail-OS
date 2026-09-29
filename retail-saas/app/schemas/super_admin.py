from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from app.schemas.saas_invoice import SaaSInvoiceResponse
from app.schemas.saas_upi import UPITransactionResponse



class SuperAdminRefreshToken(BaseModel):
    refresh_token: str = Field(..., min_length=1, description="Super Admin refresh token")


class SuperAdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Full name cannot be empty"
            )

        if len(value) < 2:
            raise ValueError(
                "Full name must contain at least 2 characters"
            )

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]*",
            value,
        ):
            raise ValueError(
                "Full name can contain only letters, spaces, dots, apostrophes and hyphens"
            )

        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "Password cannot start or end with whitespace"
            )

        if any(char.isspace() for char in value):
            raise ValueError(
                "Password cannot contain whitespace"
            )

        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not re.search(r"\d", value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not re.search(
            r"[^A-Za-z0-9]",
            value,
        ):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not re.fullmatch(
            r"[6-9]\d{9}",
            value,
        ):
            raise ValueError(
                "Phone must be a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9"
            )

        return value


class SuperAdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value


class SuperAdminUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )
    phone: str | None = None
    email: EmailStr | None = None

    @field_validator("email")
    @classmethod
    def validate_email(
        cls,
        value: EmailStr | None,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Full name cannot be empty"
            )

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]*",
            value,
        ):
            raise ValueError(
                "Full name can contain only letters, spaces, dots, apostrophes and hyphens"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not re.fullmatch(
            r"[6-9]\d{9}",
            value,
        ):
            raise ValueError(
                "Phone must be a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9"
            )

        return value


class SuperAdminStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminChangePassword(BaseModel):
    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(
        cls,
        value: str,
    ) -> str:
        if value != value.strip():
            raise ValueError(
                "Password cannot start or end with whitespace"
            )

        if any(char.isspace() for char in value):
            raise ValueError(
                "Password cannot contain whitespace"
            )

        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not re.search(r"\d", value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not re.search(
            r"[^A-Za-z0-9]",
            value,
        ):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value


class SuperAdminResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SuperAdminListResponse(BaseModel):
    items: list[SuperAdminResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class SuperAdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SuperAdminTenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    plan: str | None = None
    subscription_status: str | None = None
    subscription_end_date: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


class SuperAdminTenantListResponse(BaseModel):
    items: list[SuperAdminTenantResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class SuperAdminTenantOwnerResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: str | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class SuperAdminStoreSummaryResponse(BaseModel):
    id: int
    name: str
    code: str | None = None
    city: str | None = None
    state: str | None = None
    is_main: bool
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class SuperAdminStoreResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    email: str | None = None
    is_main: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class SuperAdminStoreListResponse(BaseModel):
    items: list[SuperAdminStoreResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class SuperAdminTenantDetailResponse(SuperAdminTenantResponse):
    owner: SuperAdminTenantOwnerResponse | None = None
    total_stores: int = 0
    active_stores: int = 0
    total_users: int = 0
    active_users: int = 0
    stores: list[SuperAdminStoreSummaryResponse] = []


class TenantStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminTenantUserResponse(BaseModel):
    id: int
    tenant_id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: str | None = None
    is_active: bool
    created_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True
    )

    @field_validator("role", mode="before")
    @classmethod
    def extract_role_name(cls, value: Any) -> str | None:
        if hasattr(value, "name"):
            return value.name
        if isinstance(value, str):
            return value
        return None


class SuperAdminTenantUserListResponse(BaseModel):
    items: list[SuperAdminTenantUserResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class SuperAdminDashboardResponse(BaseModel):
    total_super_admins: int
    active_super_admins: int
    inactive_super_admins: int
    total_tenants: int
    active_tenants: int
    inactive_tenants: int
    total_users: int
    # P2 Task 10: SaaS Subscription & Revenue Oversight Metrics
    subscriptions_by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Counts for all subscription statuses: trialing, active, past_due, expired, cancelled",
    )
    expired_subscriptions_count: int = Field(
        default=0,
        description="Count of subscriptions with status 'expired'",
    )
    pending_upgrades_count: int = Field(
        default=0,
        description="Count of subscriptions with pending_plan_id IS NOT NULL",
    )
    scheduled_downgrades_count: int = Field(
        default=0,
        description="Count of subscriptions with scheduled_plan_id IS NOT NULL",
    )
    total_saas_revenue: Decimal = Field(
        default=Decimal("0.00"),
        description="Cumulative paid SaaS invoice revenue (SUM of total_amount where status = 'paid')",
    )


# ==========================================
# P2 TASK 10: SAAS SUBSCRIPTION & BILLING SCHEMAS
# ==========================================

class SuperAdminPlanSummary(BaseModel):
    id: int
    code: str
    name: str
    price: Decimal
    currency: str
    billing_interval: str

    model_config = ConfigDict(from_attributes=True)


class SuperAdminSubscriptionListItem(BaseModel):
    subscription_id: int
    tenant_id: int
    tenant_name: str
    tenant_domain: Optional[str] = None
    status: str
    current_plan: Optional[SuperAdminPlanSummary] = None
    pending_plan: Optional[SuperAdminPlanSummary] = None
    scheduled_plan: Optional[SuperAdminPlanSummary] = None
    unit_price: Decimal
    currency: str
    billing_interval: str
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    trial_end_date: Optional[datetime] = None
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SuperAdminSubscriptionListResponse(BaseModel):
    items: list[SuperAdminSubscriptionListItem]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class SuperAdminEntitlementUsage(BaseModel):
    dimension: str
    current_usage: int
    limit: Optional[int] = None
    is_unlimited: bool


class SuperAdminSubscriptionDetailInfo(BaseModel):
    id: int
    status: str
    billing_interval: str
    unit_price: Decimal
    currency: str
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    trial_end_date: Optional[datetime] = None
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuperAdminTenantSubscriptionDetailResponse(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_domain: Optional[str] = None
    has_subscription: bool
    subscription: Optional[SuperAdminSubscriptionDetailInfo] = None
    current_plan: Optional[SuperAdminPlanSummary] = None
    pending_plan: Optional[SuperAdminPlanSummary] = None
    scheduled_plan: Optional[SuperAdminPlanSummary] = None
    usage_summary: list[SuperAdminEntitlementUsage] = []
    recent_invoices: list[SaaSInvoiceResponse] = []
    latest_unpaid_invoice: Optional[SaaSInvoiceResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SuperAdminInvoiceListItem(BaseModel):
    invoice_id: int
    invoice_number: str
    tenant_id: int
    tenant_name: str
    subscription_id: int
    billing_reason: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    status: str
    due_date: datetime
    paid_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuperAdminInvoiceListResponse(BaseModel):
    items: list[SuperAdminInvoiceListItem]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class SuperAdminTenantSummary(BaseModel):
    id: int
    name: str
    domain: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SuperAdminInvoiceDetailResponse(BaseModel):
    invoice: SaaSInvoiceResponse
    tenant: SuperAdminTenantSummary
    subscription: Optional[SuperAdminSubscriptionDetailInfo] = None
    current_plan: Optional[SuperAdminPlanSummary] = None
    upi_transactions: list[UPITransactionResponse] = []
    latest_upi_transaction: Optional[UPITransactionResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SuperAdminStoreOwnerCreate(BaseModel):
    """
    Schema for Super Admin creating a new Store Owner (Tenant).
    Supports Store Owner terminology with fallback to legacy tenant fields.
    """
    store_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Name of the retail business / main store",
    )
    owner_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of the Store Owner",
    )
    owner_email: EmailStr = Field(
        ...,
        description="Email address for Store Owner login",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Initial password for Store Owner",
    )
    owner_phone: Optional[str] = Field(
        default=None,
        description="Phone number of the Store Owner",
    )
    domain: Optional[str] = Field(
        default=None,
        description="Unique subdomain/slug for the store (auto-generated if omitted)",
    )
    plan_id: Optional[int] = Field(
        default=None,
        description="SaaS plan ID to assign",
    )
    plan_code: Optional[str] = Field(
        default=None,
        description="SaaS plan code (e.g. basic, pro, enterprise)",
    )
    address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Address of the main store",
    )
    city: Optional[str] = Field(
        default=None,
        max_length=100,
        description="City",
    )
    state: Optional[str] = Field(
        default=None,
        max_length=100,
        description="State",
    )
    pincode: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Pincode",
    )

    # Backwards-compatible aliases
    tenant_name: Optional[str] = None
    admin_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    slug: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("store_name") and data.get("tenant_name"):
                data["store_name"] = data["tenant_name"]
            if not data.get("owner_name") and data.get("admin_name"):
                data["owner_name"] = data["admin_name"]
            if not data.get("owner_email") and data.get("email"):
                data["owner_email"] = data["email"]
            if not data.get("owner_phone") and data.get("phone"):
                data["owner_phone"] = data["phone"]
            if not data.get("domain") and data.get("slug"):
                data["domain"] = data["slug"]
        return data

    @field_validator("owner_phone")
    @classmethod
    def validate_owner_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value


class SuperAdminStoreOwnerUpdate(BaseModel):
    """
    Schema for Super Admin updating Store Owner (Tenant) information.
    """
    store_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    owner_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    owner_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    is_active: Optional[bool] = None

    # Aliases
    tenant_name: Optional[str] = None
    admin_name: Optional[str] = None
    phone: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("store_name") and data.get("tenant_name"):
                data["store_name"] = data["tenant_name"]
            if not data.get("owner_name") and data.get("admin_name"):
                data["owner_name"] = data["admin_name"]
            if not data.get("owner_phone") and data.get("phone"):
                data["owner_phone"] = data["phone"]
        return data
