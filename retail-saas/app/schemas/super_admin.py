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
from app.utils.validators import validate_email_address, validate_single_pincode
from app.utils.phone import normalize_phone_number



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
        return validate_email_address(str(value), field_name="Super admin email", required=True)

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
    identifier: str = Field(
        ...,
        description="Super Admin registered email or mobile number",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_identifier(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ident = data.get("identifier") or data.get("email")
            if ident:
                data["identifier"] = str(ident).strip()
        return data


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
        return validate_email_address(str(value), field_name="Super admin email", required=False)

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


class SuperAdminProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Full name of Super Admin")
    phone: Optional[str] = Field(None, description="10-digit Indian phone number (e.g. 9876543210)")
    email: Optional[EmailStr] = Field(None, description="Email address")
    password: Optional[str] = Field(None, min_length=8, max_length=128, description="New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char)")
    pin: Optional[str] = Field(None, min_length=4, max_length=6, description="4 or 6 digit security PIN")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            clean = v.strip().replace(" ", "").replace("-", "")
            if clean.startswith("+91"):
                clean = clean[3:]
            if not re.fullmatch(r"[6-9]\d{9}", clean):
                raise ValueError("Phone must be a valid 10-digit Indian mobile number")
            return clean
        return v

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            clean = v.strip()
            if not clean.isdigit() or len(clean) not in {4, 6}:
                raise ValueError("PIN must be exactly 4 or 6 numeric digits")
            return clean
        return v


class SuperAdminPINLogin(BaseModel):
    identifier: str = Field(..., description="Super Admin email or registered phone number")
    pin: str = Field(..., min_length=4, max_length=6, description="4 or 6 digit security PIN")


class SuperAdminOTPSend(BaseModel):
    identifier: str = Field(..., description="Super Admin email or registered phone number")


class SuperAdminOTPSendResponse(BaseModel):
    message: str = Field(..., description="Status confirmation message")
    expires_in: int = Field(default=300, description="OTP validity in seconds")
    dev_otp: Optional[str] = Field(None, description="OTP for development/testing environment")


class SuperAdminOTPVerify(BaseModel):
    identifier: str = Field(..., description="Super Admin email or registered phone number")
    otp: str = Field(..., min_length=4, max_length=6, description="OTP code received on email or phone")


class SuperAdminPINSetup(BaseModel):
    identifier: Optional[str] = Field(
        None,
        description="Super Admin registered email or phone number",
    )
    pin: str = Field(
        ...,
        min_length=4,
        max_length=6,
        description="4 or 6 digit security PIN",
    )

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        clean = v.strip()
        if not clean.isdigit() or len(clean) not in {4, 6}:
            raise ValueError("PIN must be exactly 4 or 6 numeric digits")
        return clean


class SuperAdminResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SuperAdminProfileResponse(SuperAdminResponse):
    has_pin: bool = Field(default=True, examples=[True], description="Whether a security PIN is set")

    @model_validator(mode="before")
    @classmethod
    def check_has_pin(cls, data: Any) -> Any:
        if hasattr(data, "pin_hash"):
            return {
                "id": data.id,
                "email": data.email,
                "full_name": data.full_name,
                "phone": data.phone,
                "is_active": data.is_active,
                "has_pin": bool(data.pin_hash),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        elif isinstance(data, dict):
            if "has_pin" not in data and "pin_hash" in data:
                data["has_pin"] = bool(data["pin_hash"])
        return data


class SuperAdminPINSetupResponse(SuperAdminProfileResponse):
    success: bool = Field(default=True, description="Indicates if the PIN operation succeeded")
    message: str = Field(default="Security PIN configured successfully", description="Status message")


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
    business_name: Optional[str] = None
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

    @model_validator(mode="before")
    @classmethod
    def populate_business_name(cls, data: Any) -> Any:
        if hasattr(data, "name"):
            if not getattr(data, "business_name", None):
                setattr(data, "business_name", data.name)
        elif isinstance(data, dict):
            if "business_name" not in data and "name" in data:
                data["business_name"] = data["name"]
            elif "name" not in data and "business_name" in data:
                data["name"] = data["business_name"]
        return data


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


class SuperAdminTenantDeleteResponse(BaseModel):
    success: bool
    message: str


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
    total_stores: int = 0
    active_stores: int = 0
    active_plans: int = 0
    pending_upi_transactions: int = 0
    verified_upi_transactions: int = 0
    rejected_upi_transactions: int = 0
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
        examples=[Decimal("24999.00")],
        description="Cumulative paid SaaS invoice revenue (SUM of total_amount where status = 'paid')",
    )


# ==========================================
# P2 TASK 10: SAAS SUBSCRIPTION & BILLING SCHEMAS
# ==========================================

class SuperAdminPlanSummary(BaseModel):
    id: int
    code: str
    name: str
    price: Decimal = Field(default=Decimal("0.00"), examples=[Decimal("999.00")])
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
    unit_price: Decimal = Field(default=Decimal("0.00"), examples=[Decimal("999.00")])
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
    Schema for Super Admin creating a new Business / Store Owner (Tenant) and initial branch.
    """
    business_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Name of the retail business / company / brand (Tenant entity)",
    )
    store_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="Name of the initial branch / outlet (defaults to main store if omitted)",
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
        description="Unique business subdomain/slug (auto-generated from business_name if omitted)",
    )
    plan_code: Optional[str] = Field(
        default="basic",
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

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Resolve business_name from aliases if modern business_name is absent
            if not data.get("business_name"):
                data["business_name"] = (
                    data.get("company_name")
                    or data.get("tenant_name")
                    or data.get("store_name")
                )
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

    @field_validator("owner_email")
    @classmethod
    def validate_owner_email(cls, value: EmailStr) -> str:
        return validate_email_address(str(value), field_name="Owner email", required=True)

    @field_validator("owner_phone")
    @classmethod
    def validate_owner_phone(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return normalize_phone_number(str(value).strip())

    @field_validator("pincode")
    @classmethod
    def validate_owner_pincode(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return validate_single_pincode(value)


class SuperAdminStoreOwnerUpdate(BaseModel):
    """
    Schema for Super Admin updating Store Owner (Tenant) information.
    """
    business_name: Optional[str] = Field(default=None, min_length=2, max_length=255, description="Business / Company name")
    store_name: Optional[str] = Field(default=None, min_length=2, max_length=255, description="Main store name")
    owner_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    owner_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("business_name"):
                data["business_name"] = (
                    data.get("company_name")
                    or data.get("tenant_name")
                    or data.get("store_name")
                )
            if not data.get("store_name") and data.get("tenant_name"):
                data["store_name"] = data["tenant_name"]
            if not data.get("owner_name") and data.get("admin_name"):
                data["owner_name"] = data["admin_name"]
            if not data.get("owner_phone") and data.get("phone"):
                data["owner_phone"] = data["phone"]
        return data

    @field_validator("owner_phone")
    @classmethod
    def validate_owner_phone(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return normalize_phone_number(str(value).strip())

    @field_validator("pincode")
    @classmethod
    def validate_owner_pincode(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return validate_single_pincode(value)


# ==========================================
# ENTERPRISE EXTENSIONS: IMPERSONATION, AUDIT, HEALTH, OVERRIDE, BROADCAST
# ==========================================

class TenantImpersonationResponse(BaseModel):
    access_token: str = Field(..., description="Scoped JWT access token for tenant admin access")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(default=3600, description="Token expiration window in seconds")
    tenant_id: int = Field(..., description="Target tenant ID")
    tenant_name: str = Field(..., description="Target tenant / company name")
    impersonated_user_id: int = Field(..., description="Target tenant user ID")
    impersonated_email: str = Field(..., description="Target tenant admin email")
    impersonated_by_super_admin_id: int = Field(..., description="Super Admin ID who initiated impersonation")


class SuperAdminAuditLogItem(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuperAdminAuditLogListResponse(BaseModel):
    items: list[SuperAdminAuditLogItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class SuperAdminExtendTrialRequest(BaseModel):
    extension_days: int = Field(default=14, ge=1, le=365, description="Number of additional trial days to grant")
    reason: Optional[str] = Field(None, max_length=255, description="Reason for trial extension")


class SuperAdminOverridePlanRequest(BaseModel):
    plan_code: str = Field(..., min_length=1, max_length=50, description="Target SaaS plan code (e.g. pro, enterprise)")
    billing_reason: str = Field(default="offline_payment", description="Billing reason (offline_payment, promotional, enterprise_deal)")
    duration_months: int = Field(default=1, ge=1, le=36, description="Duration in months")
    notes: Optional[str] = Field(None, max_length=500, description="Internal notes / payment reference")


class SystemHealthComponent(BaseModel):
    status: str = Field(default="healthy", description="Status of the component (healthy, degraded, down)")
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    message: Optional[str] = Field(None, description="Diagnostic message")


class SystemHealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Overall platform status")
    timestamp: datetime = Field(..., description="Timestamp of health check")
    environment: str = Field(default="production", description="Environment identifier")
    version: str = Field(default="1.0.0", description="Application version")
    database: SystemHealthComponent
    redis: SystemHealthComponent


class BroadcastAnnouncementRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150, description="Announcement title / banner headline")
    message: str = Field(..., min_length=2, max_length=1000, description="Announcement body message")
    level: str = Field(default="info", description="Severity level: info, warning, critical")
    is_active: bool = Field(default=True, description="Whether the banner is actively broadcasted")
    expires_at: Optional[datetime] = Field(None, description="Optional automatic expiration timestamp")


class BroadcastAnnouncementResponse(BaseModel):
    title: str
    message: str
    level: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    created_by_super_admin_id: Optional[int] = None
