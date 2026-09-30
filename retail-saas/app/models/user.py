from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_tenant_entitlement", "tenant_id", "is_deleted", "is_active"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    @property
    def hashed_password(self) -> str:
        return self.password_hash

    @hashed_password.setter
    def hashed_password(self, val: str) -> None:
        self.password_hash = val

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    pancard: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    addhar_card: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    profile_photo: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    pan_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    addhar_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    @property
    def aadhar_card(self) -> str | None:
        return self.addhar_card

    @aadhar_card.setter
    def aadhar_card(self, val: str | None) -> None:
        self.addhar_card = val

    @property
    def aadhar_number(self) -> str | None:
        return self.addhar_number

    @aadhar_number.setter
    def aadhar_number(self, val: str | None) -> None:
        self.addhar_number = val

    @property
    def pancard_number(self) -> str | None:
        return self.pan_number

    @pancard_number.setter
    def pancard_number(self, val: str | None) -> None:
        self.pan_number = val



    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        back_populates="users",
    )

    store: Mapped["Store | None"] = relationship(
        "Store",
        back_populates="users",
    )

    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="users",
    )