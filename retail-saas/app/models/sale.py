from datetime import datetime
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

    store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=False,
        index=True
    )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=True,
        index=True
    )

    invoice_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    subtotal = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    discount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    tax = Column(
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
        String(30),
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="completed"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

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
        Numeric(12, 2),
        nullable=False
    )

    discount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    tax = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    total_price = Column(
        Numeric(12, 2),
        nullable=False
    )

    sale = relationship(
        "Sale",
        back_populates="items"
    )