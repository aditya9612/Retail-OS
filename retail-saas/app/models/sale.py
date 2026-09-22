from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )

    store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=False,
        index=True
    )

    sale_number = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    subtotal = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    tax_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    total_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    payment_method = Column(
        String(50),
        nullable=False
    )

    payment_status = Column(
        String(50),
        nullable=False,
        default="paid"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    @property
    def invoice_number(self) -> str:
        return self.sale_number

    @invoice_number.setter
    def invoice_number(self, val: str) -> None:
        self.sale_number = val

    @property
    def status(self) -> str:
        return self.payment_status

    @status.setter
    def status(self, val: str) -> None:
        self.payment_status = val

    @property
    def tax(self) -> Decimal:
        return Decimal(str(self.tax_amount or 0))

    @tax.setter
    def tax(self, val: Any) -> None:
        if val is not None:
            self.tax_amount = Decimal(str(val))

    @property
    def discount(self) -> Decimal:
        return Decimal("0.00")

    @discount.setter
    def discount(self, val: Any) -> None:
        pass

    @property
    def customer_id(self) -> int | None:
        return None

    @customer_id.setter
    def customer_id(self, val: Any) -> None:
        pass

    items = relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    sale_id = Column(
        Integer,
        ForeignKey("sales.id"),
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    quantity = Column(
        Integer,
        nullable=False
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    tax_rate = Column(
        Numeric(5, 2),
        nullable=False,
        default=0
    )

    tax_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0
    )

    total_price = Column(
        Numeric(12, 2),
        nullable=False
    )

    @property
    def discount(self) -> Decimal:
        return Decimal("0.00")

    @discount.setter
    def discount(self, val: Any) -> None:
        pass

    @property
    def tax(self) -> Decimal:
        return Decimal(str(self.tax_amount or 0))

    @tax.setter
    def tax(self, val: Any) -> None:
        if val is not None:
            self.tax_amount = Decimal(str(val))

    sale = relationship(
        "Sale",
        back_populates="items"
    )