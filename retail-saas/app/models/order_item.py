from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped[Optional["Product"]] = relationship("Product")

    def __init__(self, **kwargs):
        if "discount" in kwargs and "discount_amount" not in kwargs:
            kwargs["discount_amount"] = kwargs.pop("discount")
        elif "discount" in kwargs:
            kwargs.pop("discount")

        if "total" in kwargs and "total_amount" not in kwargs:
            kwargs["total_amount"] = kwargs.pop("total")
        elif "total" in kwargs:
            kwargs.pop("total")

        self._product_name = kwargs.pop("product_name", None)
        self._sku = kwargs.pop("sku", None)
        self._variant = kwargs.pop("variant", None)
        self._tax_rate = kwargs.pop("tax_rate", None)
        super().__init__(**kwargs)

    @property
    def discount(self) -> Decimal:
        return self.discount_amount

    @discount.setter
    def discount(self, val: Decimal) -> None:
        self.discount_amount = val

    @property
    def total(self) -> Decimal:
        return self.total_amount

    @total.setter
    def total(self, val: Decimal) -> None:
        self.total_amount = val

    @property
    def product_name(self) -> str:
        if getattr(self, "_product_name", None):
            return self._product_name
        if self.product:
            return self.product.name
        return ""

    @product_name.setter
    def product_name(self, val: str) -> None:
        self._product_name = val

    @property
    def sku(self) -> str:
        if getattr(self, "_sku", None):
            return self._sku
        if self.product:
            return self.product.sku
        return ""

    @sku.setter
    def sku(self, val: str) -> None:
        self._sku = val

    @property
    def variant(self) -> Optional[str]:
        return getattr(self, "_variant", None)

    @variant.setter
    def variant(self, val: Optional[str]) -> None:
        self._variant = val

    @property
    def tax_rate(self) -> Decimal:
        if getattr(self, "_tax_rate", None) is not None:
            return self._tax_rate
        if self.product:
            return self.product.tax_rate
        return Decimal("0.00")

    @tax_rate.setter
    def tax_rate(self, val: Decimal) -> None:
        self._tax_rate = val
