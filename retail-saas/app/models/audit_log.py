from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    def __init__(self, **kwargs):
        if "resource" in kwargs and "entity_type" not in kwargs:
            kwargs["entity_type"] = kwargs.pop("resource")
        elif "resource" in kwargs:
            kwargs.pop("resource")

        if "resource_id" in kwargs and "entity_id" not in kwargs:
            r_id = kwargs.pop("resource_id")
            kwargs["entity_id"] = str(r_id) if r_id is not None else None
        elif "resource_id" in kwargs:
            kwargs.pop("resource_id")

        if "details" in kwargs and "new_values" not in kwargs:
            kwargs["new_values"] = kwargs.pop("details")
        elif "details" in kwargs:
            kwargs.pop("details")

        kwargs.pop("updated_at", None)
        super().__init__(**kwargs)

    @property
    def resource(self) -> str:
        return self.entity_type

    @resource.setter
    def resource(self, val: str) -> None:
        self.entity_type = val

    @property
    def resource_id(self) -> Optional[int]:
        try:
            return int(self.entity_id) if self.entity_id is not None else None
        except (ValueError, TypeError):
            return None

    @resource_id.setter
    def resource_id(self, val: Optional[int]) -> None:
        self.entity_id = str(val) if val is not None else None

    @property
    def details(self) -> Optional[dict]:
        return self.new_values

    @details.setter
    def details(self, val: Optional[dict]) -> None:
        self.new_values = val
