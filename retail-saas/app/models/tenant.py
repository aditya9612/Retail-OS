from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.saas_billing import SaaSSubscription
    from app.models.store import Store
    from app.models.user import User


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="basic", nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(50), default="trial", nullable=False)
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("saas_subscriptions.id", use_alter=True),
        nullable=True,
        index=True,
    )
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    stores: Mapped[list["Store"]] = relationship("Store", back_populates="tenant")
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    current_subscription: Mapped[Optional["SaaSSubscription"]] = relationship(
        "SaaSSubscription",
        foreign_keys=[current_subscription_id],
    )

    @property
    def slug(self) -> str:
        return self.domain

    @slug.setter
    def slug(self, val: str) -> None:
        self.domain = val

    @property
    def business_name(self) -> str:
        return self.name

    @business_name.setter
    def business_name(self, val: str) -> None:
        self.name = val

    @property
    def gstin(self) -> Optional[str]:
        if self.settings and isinstance(self.settings, dict):
            return self.settings.get("gstin")
        return getattr(self, "_gstin", None)

    @gstin.setter
    def gstin(self, val: Optional[str]) -> None:
        self._gstin = val

    @property
    def email(self) -> Optional[str]:
        if self.settings and isinstance(self.settings, dict):
            val = self.settings.get("email")
            if val:
                return val
        if getattr(self, "_email", None):
            return self._email
        try:
            if hasattr(self, "users") and self.users:
                for u in self.users:
                    if getattr(u, "email", None) and not getattr(u, "is_deleted", False):
                        return u.email
        except Exception:
            pass
        return None

    @email.setter
    def email(self, val: Optional[str]) -> None:
        self._email = val

    @property
    def phone(self) -> Optional[str]:
        if self.settings and isinstance(self.settings, dict):
            val = self.settings.get("phone")
            if val:
                return val
        if getattr(self, "_phone", None):
            return self._phone
        try:
            if hasattr(self, "users") and self.users:
                for u in self.users:
                    if getattr(u, "phone", None) and not getattr(u, "is_deleted", False):
                        return u.phone
        except Exception:
            pass
        return None

    @phone.setter
    def phone(self, val: Optional[str]) -> None:
        self._phone = val

    @property
    def address(self) -> Optional[str]:
        if self.settings and isinstance(self.settings, dict):
            return self.settings.get("address")
        return getattr(self, "_address", None)

    @address.setter
    def address(self, val: Optional[str]) -> None:
        self._address = val
