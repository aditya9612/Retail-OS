from datetime import date
from datetime import datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String , Text,DECIMAL, DateTime, Enum ,Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__= "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(500))
    birthday: Mapped[date | None] = mapped_column(Date)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(20), default="active")
    segment: Mapped[str] = mapped_column(String(20), default="new")
    total_spend: Mapped[int] = mapped_column(Integer, default=0)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="customer")
    feedbacks: Mapped[list["CustomerFeedback"]] = relationship("CustomerFeedback", back_populates="customer")
    loyalty: Mapped[list["LoyaltyPoint"]] = relationship(
        "LoyaltyPoint",
        back_populates="customer",
        cascade="all, delete-orphan"
    )
    wallet: Mapped["CustomerWallet | None"] = relationship(
        "CustomerWallet",
        back_populates="customer",
        uselist=False,
        cascade="all, delete-orphan",
    )
    referrals: Mapped[list["CustomerReferral"]] = relationship(
        "CustomerReferral",
        foreign_keys="CustomerReferral.customer_id"
    )

class CustomerFeedback(Base, TimestampMixin):
    __tablename__ = "customer_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False
    )

    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=True
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    comments: Mapped[str | None] = mapped_column(Text)

    suggestions: Mapped[str | None] = mapped_column(Text)

    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="feedbacks"
    )

class LoyaltyPoint(Base, TimestampMixin):
    __tablename__ = "loyalty_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False
    )

    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=True
    )

    points_earned: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    points_redeemed: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    balance_points: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="loyalty"
    )    

class CustomerWallet(Base, TimestampMixin):
    __tablename__ = "customer_wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        unique=True
    )

    current_balance: Mapped[float] = mapped_column(
        DECIMAL(12, 2),
        default=0.00
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="wallet"
    )

    transactions: Mapped[list["WalletTransaction"]] = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan"
    )
    
class WalletTransaction(Base, TimestampMixin):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("customer_wallets.id"),
        nullable=False
    )

    transaction_type: Mapped[str] = mapped_column(
        Enum("CREDIT", "DEBIT", name="wallet_transaction_type")
    )

    amount: Mapped[float] = mapped_column(
        DECIMAL(12, 2)
    )

    reference_no: Mapped[str | None] = mapped_column(
        String(100)
    )

    remarks: Mapped[str | None] = mapped_column(
        String(255)
    )

    wallet: Mapped["CustomerWallet"] = relationship(
        "CustomerWallet",
        back_populates="transactions"
    )

class CustomerReferral(Base, TimestampMixin):
    __tablename__ = "customer_referrals"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False
    )

    referral_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )

    referred_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True
    )

    reward_amount: Mapped[float] = mapped_column(
        DECIMAL(12, 2),
        default=0.00
    )

class CustomerNote(Base):
    __tablename__ = "customer_notes"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )

    note = Column(Text, nullable=False)

    created_by = Column(Integer, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    customer = relationship("Customer")        

class CustomerCommunication(Base):
    __tablename__ = "customer_communications"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)

    communication_type = Column(
        Enum("SMS", "WHATSAPP", "EMAIL"),
        nullable=False
    )

    message = Column(Text, nullable=False)

    delivery_status = Column(
        Enum("PENDING", "SENT", "FAILED"),
        default="SENT"
    )

    sent_at = Column(DateTime, server_default=func.now())

