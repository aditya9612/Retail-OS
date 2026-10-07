import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.services.excel_export_service import ExcelExportService

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.store import Store
from app.models.store_expense import StoreExpense
from app.models.user import User
from app.schemas.report import (
    CurrentStockItem,
    CurrentStockResponse,
    CustomerLifetimeValueItem,
    CustomerLifetimeValueResponse,
    CustomerOverviewResponse,
    CustomerRetentionResponse,
    CustomerSegmentsResponse,
    DailySalesResponse,
    GSTSalesResponse,
    GSTSummaryResponse,
    InventoryValuationResponse,
    LowStockItem,
    LowStockResponse,
    MonthlySalesResponse,
    MonthlySalesTopProduct,
    ProductProfitabilityItem,
    ProductProfitabilityResponse,
    ProductVelocityItem,
    ProfitLossResponse,
    ReportExportRequest,
    SlowMovingProductsResponse,
    TopSellingProductsResponse,
    YearlySalesMonthItem,
    YearlySalesResponse,
)
from app.utils.constants import OrderStatus, PaymentStatus, RefundStatus


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # TENANT & STORE RESOLUTION HELPERS
    # =========================================================================

    def _resolve_tenant_and_store(
        self,
        user_or_tenant: Union[User, int],
        requested_store_id: Optional[int] = None,
    ) -> tuple[int, Optional[int]]:
        """
        Derives tenant_id and resolves store_id based on role and assignment:
        - Store Manager / Staff (user.store_id is set):
            - omitted store_id => force user.store_id
            - requested foreign store_id => 403 Forbidden
        - Tenant Owner / Tenant Admin (user.store_id is None):
            - omitted store_id => tenant-wide (None)
            - requested store_id => verify Store.tenant_id == current_user.tenant_id; foreign/invalid => 404 Not Found
        """
        if isinstance(user_or_tenant, int):
            return user_or_tenant, requested_store_id

        user: User = user_or_tenant
        if not user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no tenant assigned",
            )
        tenant_id = user.tenant_id

        if user.store_id is not None:
            if requested_store_id is not None and requested_store_id != user.store_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to requested store",
                )
            return tenant_id, user.store_id

        if requested_store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == requested_store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if not store:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Store not found",
                )
            return tenant_id, requested_store_id

        return tenant_id, None

    def _validate_date_range(self, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before or equal to end_date",
            )

    # =========================================================================
    # A. SALES REPORTS
    # =========================================================================

    def daily_sales(
        self,
        user_or_tenant: Union[User, int],
        target_date: Optional[date] = None,
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        target_date = target_date or date.today()
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        # Orders aggregation
        order_query = self.db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.subtotal), Decimal("0.00")),
            func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.tax_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.total_amount), Decimal("0.00")),
        ).filter(
            Order.tenant_id == tenant_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
        )
        if resolved_store_id is not None:
            order_query = order_query.filter(Order.store_id == resolved_store_id)

        res = order_query.first()
        order_count = int(res[0] or 0)
        gross_sales = Decimal(str(res[1] or "0.00"))
        discount_amount = Decimal(str(res[2] or "0.00"))
        tax_amount = Decimal(str(res[3] or "0.00"))
        total_sales = Decimal(str(res[4] or "0.00"))

        # Refunds aggregation
        refund_query = self.db.query(
            func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00"))
        ).filter(
            Refund.tenant_id == tenant_id,
            Refund.status == RefundStatus.APPROVED.value,
            Refund.created_at >= start,
            Refund.created_at <= end,
        )
        if resolved_store_id is not None:
            refund_query = (
                refund_query.join(Invoice, Refund.invoice_id == Invoice.id)
                .join(Order, Invoice.order_id == Order.id)
                .filter(Order.store_id == resolved_store_id)
            )
        refund_amount = Decimal(str(refund_query.scalar() or "0.00"))

        net_sales = total_sales - refund_amount
        average_order_value = (
            (total_sales / order_count).quantize(Decimal("0.01"))
            if order_count > 0
            else Decimal("0.00")
        )

        # Payment breakdown
        payment_query = (
            self.db.query(
                Payment.payment_method,
                func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
            )
            .join(Order, Payment.order_id == Order.id)
            .filter(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= start,
                Payment.created_at <= end,
            )
        )
        if resolved_store_id is not None:
            payment_query = payment_query.filter(Order.store_id == resolved_store_id)

        payment_rows = payment_query.group_by(Payment.payment_method).all()
        payment_methods = {r[0]: Decimal(str(r[1])) for r in payment_rows}

        return {
            "date": str(target_date),
            "order_count": order_count,
            "gross_sales": gross_sales,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "total_sales": total_sales,
            "refund_amount": refund_amount,
            "net_sales": net_sales,
            "average_order_value": average_order_value,
            "payment_methods": payment_methods,
            "store_id": resolved_store_id,
        }

    def monthly_sales(
        self,
        user_or_tenant: Union[User, int],
        year: int,
        month: int,
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        start = datetime(year, month, 1)
        next_month = (
            datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        )
        end = next_month - timedelta(microseconds=1)

        # Orders aggregation
        order_query = self.db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.subtotal), Decimal("0.00")),
            func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.tax_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.total_amount), Decimal("0.00")),
        ).filter(
            Order.tenant_id == tenant_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
        )
        if resolved_store_id is not None:
            order_query = order_query.filter(Order.store_id == resolved_store_id)

        res = order_query.first()
        order_count = int(res[0] or 0)
        gross_sales = Decimal(str(res[1] or "0.00"))
        discount_amount = Decimal(str(res[2] or "0.00"))
        tax_amount = Decimal(str(res[3] or "0.00"))
        total_sales = Decimal(str(res[4] or "0.00"))

        # Refunds aggregation
        refund_query = self.db.query(
            func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00"))
        ).filter(
            Refund.tenant_id == tenant_id,
            Refund.status == RefundStatus.APPROVED.value,
            Refund.created_at >= start,
            Refund.created_at <= end,
        )
        if resolved_store_id is not None:
            refund_query = (
                refund_query.join(Invoice, Refund.invoice_id == Invoice.id)
                .join(Order, Invoice.order_id == Order.id)
                .filter(Order.store_id == resolved_store_id)
            )
        refund_amount = Decimal(str(refund_query.scalar() or "0.00"))
        net_sales = total_sales - refund_amount

        # Previous month sales for growth rate
        if month == 1:
            prev_start = datetime(year - 1, 12, 1)
            prev_end = datetime(year, 1, 1) - timedelta(microseconds=1)
        else:
            prev_start = datetime(year, month - 1, 1)
            prev_end = datetime(year, month, 1) - timedelta(microseconds=1)

        prev_sales_q = self.db.query(
            func.coalesce(func.sum(Order.total_amount), Decimal("0.00"))
        ).filter(
            Order.tenant_id == tenant_id,
            Order.created_at >= prev_start,
            Order.created_at <= prev_end,
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
        )
        if resolved_store_id is not None:
            prev_sales_q = prev_sales_q.filter(Order.store_id == resolved_store_id)
        prev_total = Decimal(str(prev_sales_q.scalar() or "0.00"))

        growth_rate_pct: Optional[float] = None
        if prev_total > Decimal("0.00"):
            growth_rate_pct = round(
                float((total_sales - prev_total) / prev_total * 100), 2
            )

        # Top products
        top_products_q = (
            self.db.query(
                OrderItem.product_id,
                Product.name,
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(func.sum(OrderItem.total_amount), Decimal("0.00")),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(Product, OrderItem.product_id == Product.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start,
                Order.created_at <= end,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if resolved_store_id is not None:
            top_products_q = top_products_q.filter(Order.store_id == resolved_store_id)

        top_rows = (
            top_products_q.group_by(OrderItem.product_id, Product.name)
            .order_by(func.sum(OrderItem.total_amount).desc())
            .limit(5)
            .all()
        )
        top_products = [
            {
                "product_id": r[0],
                "product_name": r[1],
                "quantity_sold": int(r[2]),
                "revenue": Decimal(str(r[3])),
            }
            for r in top_rows
        ]

        return {
            "year": year,
            "month": month,
            "order_count": order_count,
            "gross_sales": gross_sales,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "total_sales": total_sales,
            "refund_amount": refund_amount,
            "net_sales": net_sales,
            "growth_rate_pct": growth_rate_pct,
            "top_products": top_products,
            "store_id": resolved_store_id,
        }

    def yearly_sales(
        self,
        user_or_tenant: Union[User, int],
        year: int,
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]

        monthly_breakdown: List[dict] = []
        total_year_orders = 0
        total_year_gross = Decimal("0.00")
        total_year_sales = Decimal("0.00")
        total_year_net = Decimal("0.00")

        for m in range(1, 13):
            m_start = datetime(year, m, 1)
            m_next = datetime(year + 1, 1, 1) if m == 12 else datetime(year, m + 1, 1)
            m_end = m_next - timedelta(microseconds=1)

            order_q = self.db.query(
                func.count(Order.id),
                func.coalesce(func.sum(Order.subtotal), Decimal("0.00")),
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")),
            ).filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= m_start,
                Order.created_at <= m_end,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            if resolved_store_id is not None:
                order_q = order_q.filter(Order.store_id == resolved_store_id)
            res = order_q.first()
            m_orders = int(res[0] or 0)
            m_gross = Decimal(str(res[1] or "0.00"))
            m_total = Decimal(str(res[2] or "0.00"))

            ref_q = self.db.query(
                func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00"))
            ).filter(
                Refund.tenant_id == tenant_id,
                Refund.status == RefundStatus.APPROVED.value,
                Refund.created_at >= m_start,
                Refund.created_at <= m_end,
            )
            if resolved_store_id is not None:
                ref_q = (
                    ref_q.join(Invoice, Refund.invoice_id == Invoice.id)
                    .join(Order, Invoice.order_id == Order.id)
                    .filter(Order.store_id == resolved_store_id)
                )
            m_refund = Decimal(str(ref_q.scalar() or "0.00"))
            m_net = m_total - m_refund

            monthly_breakdown.append({
                "month": m,
                "month_name": month_names[m],
                "order_count": m_orders,
                "gross_sales": m_gross,
                "total_sales": m_total,
                "net_sales": m_net,
            })

            total_year_orders += m_orders
            total_year_gross += m_gross
            total_year_sales += m_total
            total_year_net += m_net

        return {
            "year": year,
            "total_orders": total_year_orders,
            "gross_sales": total_year_gross,
            "total_sales": total_year_sales,
            "net_sales": total_year_net,
            "monthly_breakdown": monthly_breakdown,
            "store_id": resolved_store_id,
        }

    # =========================================================================
    # B. GST REPORTS
    # =========================================================================

    def gst_sales(
        self,
        user_or_tenant: Union[User, int],
        start_date: date,
        end_date: date,
        store_id: Optional[int] = None,
    ) -> dict:
        self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        start = datetime.combine(start_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())

        inv_query = self.db.query(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.subtotal - Invoice.discount_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.cgst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.sgst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.igst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.tax_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.total_amount), Decimal("0.00")),
        ).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.created_at >= start,
            Invoice.created_at <= end,
        )
        if resolved_store_id is not None:
            inv_query = inv_query.join(Order, Invoice.order_id == Order.id).filter(
                Order.store_id == resolved_store_id
            )

        res = inv_query.first()
        invoice_count = int(res[0] or 0)
        taxable_amount = Decimal(str(res[1] or "0.00"))
        cgst_amount = Decimal(str(res[2] or "0.00"))
        sgst_amount = Decimal(str(res[3] or "0.00"))
        igst_amount = Decimal(str(res[4] or "0.00"))
        total_tax = Decimal(str(res[5] or "0.00"))
        total_amount = Decimal(str(res[6] or "0.00"))

        # Rate breakdown by joining InvoiceItem
        item_q = (
            self.db.query(
                InvoiceItem.gst_rate,
                func.coalesce(
                    func.sum(InvoiceItem.unit_price * InvoiceItem.quantity - InvoiceItem.discount_amount),
                    Decimal("0.00"),
                ),
                func.coalesce(func.sum(InvoiceItem.gst_amount), Decimal("0.00")),
            )
            .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
            .filter(
                Invoice.tenant_id == tenant_id,
                Invoice.created_at >= start,
                Invoice.created_at <= end,
            )
        )
        if resolved_store_id is not None:
            item_q = item_q.join(Order, Invoice.order_id == Order.id).filter(
                Order.store_id == resolved_store_id
            )

        rate_rows = item_q.group_by(InvoiceItem.gst_rate).all()
        rate_breakdown = {
            f"{r[0]}%": {
                "taxable_amount": Decimal(str(r[1])),
                "tax_amount": Decimal(str(r[2])),
            }
            for r in rate_rows
        }

        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "invoice_count": invoice_count,
            "taxable_amount": taxable_amount,
            "cgst_amount": cgst_amount,
            "sgst_amount": sgst_amount,
            "igst_amount": igst_amount,
            "total_tax": total_tax,
            "total_amount": total_amount,
            "rate_breakdown": rate_breakdown,
            "store_id": resolved_store_id,
        }

    def gst_summary(
        self,
        user_or_tenant: Union[User, int],
        start_date: date,
        end_date: date,
        store_id: Optional[int] = None,
    ) -> dict:
        self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        start = datetime.combine(start_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())

        inv_query = self.db.query(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.cgst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.sgst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.igst_amount), Decimal("0.00")),
            func.coalesce(func.sum(Invoice.tax_amount), Decimal("0.00")),
        ).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.created_at >= start,
            Invoice.created_at <= end,
        )
        if resolved_store_id is not None:
            inv_query = inv_query.join(Order, Invoice.order_id == Order.id).filter(
                Order.store_id == resolved_store_id
            )

        res = inv_query.first()
        invoice_count = int(res[0] or 0)
        output_cgst = Decimal(str(res[1] or "0.00"))
        output_sgst = Decimal(str(res[2] or "0.00"))
        output_igst = Decimal(str(res[3] or "0.00"))
        total_output_tax = Decimal(str(res[4] or "0.00"))

        input_tax_credit = Decimal("0.00")
        net_tax_liability = total_output_tax - input_tax_credit

        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "invoice_count": invoice_count,
            "output_cgst": output_cgst,
            "output_sgst": output_sgst,
            "output_igst": output_igst,
            "total_output_tax": total_output_tax,
            "input_tax_credit": input_tax_credit,
            "net_tax_liability": net_tax_liability,
            "store_id": resolved_store_id,
            "note": "Input Tax Credit (ITC) tracking is not supported in current database schema. Net liability equals total output tax.",
        }

    # =========================================================================
    # C. INVENTORY REPORTS
    # =========================================================================

    def current_stock(
        self,
        user_or_tenant: Union[User, int],
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        q = (
            self.db.query(Inventory, Product)
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Product.is_active == True,
            )
        )
        if resolved_store_id is not None:
            q = q.filter(Inventory.store_id == resolved_store_id)

        rows = q.all()
        items = []
        total_quantity = 0

        for inv, prod in rows:
            qty = inv.quantity
            total_quantity += qty
            if qty <= 0:
                status_str = "out_of_stock"
            elif qty <= inv.min_stock_level:
                status_str = "low_stock"
            else:
                status_str = "in_stock"

            items.append({
                "product_id": prod.id,
                "product_name": prod.name,
                "sku": prod.sku,
                "store_id": inv.store_id,
                "quantity": qty,
                "min_stock_level": inv.min_stock_level,
                "reorder_point": inv.reorder_point,
                "stock_status": status_str,
            })

        return {
            "total_items": len(items),
            "total_quantity": total_quantity,
            "items": items,
            "store_id": resolved_store_id,
        }

    def low_stock(
        self,
        user_or_tenant: Union[User, int],
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        q = (
            self.db.query(Inventory, Product)
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Product.is_active == True,
                Inventory.quantity <= Inventory.min_stock_level,
            )
        )
        if resolved_store_id is not None:
            q = q.filter(Inventory.store_id == resolved_store_id)

        rows = q.all()
        items = [
            {
                "product_id": prod.id,
                "product_name": prod.name,
                "sku": prod.sku,
                "store_id": inv.store_id,
                "quantity": inv.quantity,
                "min_stock_level": inv.min_stock_level,
                "reorder_point": inv.reorder_point,
                "deficit": max(0, inv.min_stock_level - inv.quantity),
            }
            for inv, prod in rows
        ]

        return {
            "total_low_stock_products": len(items),
            "items": items,
            "store_id": resolved_store_id,
        }

    def inventory_valuation(
        self,
        user_or_tenant: Union[User, int],
        store_id: Optional[int] = None,
    ) -> dict:
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        q = (
            self.db.query(
                func.count(distinct(Product.id)),
                func.coalesce(func.sum(Inventory.quantity), 0),
                func.coalesce(func.sum(Inventory.quantity * Product.cost_price), Decimal("0.00")),
                func.coalesce(func.sum(Inventory.quantity * Product.selling_price), Decimal("0.00")),
            )
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Product.is_active == True,
            )
        )
        if resolved_store_id is not None:
            q = q.filter(Inventory.store_id == resolved_store_id)

        res = q.first()
        total_products = int(res[0] or 0)
        total_units = int(res[1] or 0)
        cost_valuation = Decimal(str(res[2] or "0.00"))
        retail_valuation = Decimal(str(res[3] or "0.00"))

        return {
            "total_products": total_products,
            "total_units": total_units,
            "cost_valuation": cost_valuation,
            "retail_valuation": retail_valuation,
            "store_id": resolved_store_id,
            "data_limitation_note": "Valuation reflects current product cost_price; historical cost fluctuations are not tracked.",
        }

    # =========================================================================
    # D. PRODUCT ANALYTICS
    # =========================================================================

    def top_selling_products(
        self,
        user_or_tenant: Union[User, int],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 10,
        store_id: Optional[int] = None,
    ) -> dict:
        if start_date and end_date:
            self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )

        q = (
            self.db.query(
                OrderItem.product_id,
                Product.name,
                Product.sku,
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(func.sum(OrderItem.total_amount), Decimal("0.00")),
                func.count(distinct(Order.id)),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(Product, OrderItem.product_id == Product.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if resolved_store_id is not None:
            q = q.filter(Order.store_id == resolved_store_id)
        if start_date:
            q = q.filter(Order.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            q = q.filter(Order.created_at <= datetime.combine(end_date, datetime.max.time()))

        rows = (
            q.group_by(OrderItem.product_id, Product.name, Product.sku)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )

        products = [
            {
                "product_id": r[0],
                "product_name": r[1],
                "sku": r[2],
                "quantity_sold": int(r[3]),
                "revenue": Decimal(str(r[4])),
                "orders_count": int(r[5]),
            }
            for r in rows
        ]

        return {
            "limit": limit,
            "products": products,
            "store_id": resolved_store_id,
        }

    def slow_moving_products(
        self,
        user_or_tenant: Union[User, int],
        threshold: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        store_id: Optional[int] = None,
    ) -> dict:
        """
        Returns products with sales quantity <= caller-supplied threshold.
        No hardcoded default threshold is used.
        """
        if threshold is None or threshold < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Threshold must be a non-negative integer",
            )
        if start_date and end_date:
            self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )

        # Build subquery or join for quantity sold per product in confirmed orders
        sold_q = (
            self.db.query(
                OrderItem.product_id,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("qty_sold"),
                func.coalesce(func.sum(OrderItem.total_amount), Decimal("0.00")).label("rev"),
                func.count(distinct(Order.id)).label("ord_cnt"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if resolved_store_id is not None:
            sold_q = sold_q.filter(Order.store_id == resolved_store_id)
        if start_date:
            sold_q = sold_q.filter(Order.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            sold_q = sold_q.filter(Order.created_at <= datetime.combine(end_date, datetime.max.time()))

        sold_subq = sold_q.group_by(OrderItem.product_id).subquery()

        # Join active products with sold subquery
        prod_q = (
            self.db.query(
                Product.id,
                Product.name,
                Product.sku,
                func.coalesce(sold_subq.c.qty_sold, 0),
                func.coalesce(sold_subq.c.rev, Decimal("0.00")),
                func.coalesce(sold_subq.c.ord_cnt, 0),
            )
            .outerjoin(sold_subq, Product.id == sold_subq.c.product_id)
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active == True,
                func.coalesce(sold_subq.c.qty_sold, 0) <= threshold,
            )
            .order_by(func.coalesce(sold_subq.c.qty_sold, 0).asc())
        )

        rows = prod_q.all()
        products = [
            {
                "product_id": r[0],
                "product_name": r[1],
                "sku": r[2],
                "quantity_sold": int(r[3]),
                "revenue": Decimal(str(r[4])),
                "orders_count": int(r[5]),
            }
            for r in rows
        ]

        return {
            "threshold": threshold,
            "products": products,
            "store_id": resolved_store_id,
        }

    def product_profitability(
        self,
        user_or_tenant: Union[User, int],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        store_id: Optional[int] = None,
    ) -> dict:
        """
        Computes product-level profitability using current Product.cost_price * quantity sold.
        Historical unit cost snapshots are not available in current database schema.
        """
        if start_date and end_date:
            self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )

        q = (
            self.db.query(
                Product.id,
                Product.name,
                Product.sku,
                Product.cost_price,
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(func.sum(OrderItem.total_amount), Decimal("0.00")),
            )
            .join(OrderItem, Product.id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if resolved_store_id is not None:
            q = q.filter(Order.store_id == resolved_store_id)
        if start_date:
            q = q.filter(Order.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            q = q.filter(Order.created_at <= datetime.combine(end_date, datetime.max.time()))

        rows = q.group_by(Product.id, Product.name, Product.sku, Product.cost_price).all()

        total_revenue = Decimal("0.00")
        total_estimated_cost = Decimal("0.00")
        total_estimated_profit = Decimal("0.00")
        products = []

        for p_id, p_name, p_sku, cost_price, qty_sold, rev in rows:
            qty = int(qty_sold or 0)
            revenue = Decimal(str(rev or "0.00"))
            unit_cost = Decimal(str(cost_price or "0.00"))
            est_cost = (unit_cost * qty).quantize(Decimal("0.01"))
            est_profit = revenue - est_cost
            margin_pct = (
                round(float(est_profit / revenue * 100), 2)
                if revenue > Decimal("0.00")
                else None
            )

            total_revenue += revenue
            total_estimated_cost += est_cost
            total_estimated_profit += est_profit

            products.append({
                "product_id": p_id,
                "product_name": p_name,
                "sku": p_sku,
                "quantity_sold": qty,
                "revenue": revenue,
                "estimated_cost": est_cost,
                "estimated_gross_profit": est_profit,
                "margin_pct": margin_pct,
            })

        return {
            "total_revenue": total_revenue,
            "total_estimated_cost": total_estimated_cost,
            "total_estimated_profit": total_estimated_profit,
            "products": products,
            "store_id": resolved_store_id,
            "data_limitation_note": "Estimated cost is computed using current Product.cost_price * quantity sold.",
        }

    # =========================================================================
    # E. CUSTOMER ANALYTICS
    # =========================================================================

    def customers_overview(self, user_or_tenant: Union[User, int]) -> dict:
        tenant_id, _ = self._resolve_tenant_and_store(user_or_tenant)

        total_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        active_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id, Customer.status == "active")
            .scalar()
            or 0
        )
        inactive_customers = total_customers - active_customers

        res = (
            self.db.query(
                func.coalesce(func.sum(Customer.loyalty_points), 0),
                func.coalesce(func.sum(Customer.total_spend), 0),
            )
            .filter(Customer.tenant_id == tenant_id)
            .first()
        )
        total_points = int(res[0] or 0)
        total_spend = Decimal(str(res[1] or "0.00"))

        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "inactive_customers": inactive_customers,
            "total_loyalty_points": total_points,
            "total_spend_all_customers": total_spend,
        }

    def customers_retention(self, user_or_tenant: Union[User, int]) -> dict:
        """
        Uses authoritative Customer.status == 'active'.
        Does not invent an unapproved rolling time window.
        """
        tenant_id, _ = self._resolve_tenant_and_store(user_or_tenant)

        total_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        active_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id, Customer.status == "active")
            .scalar()
            or 0
        )

        repeat_subq = (
            self.db.query(Order.customer_id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.customer_id.isnot(None),
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.customer_id)
            .having(func.count(Order.id) > 1)
            .subquery()
        )
        repeat_customers = (
            self.db.query(func.count(repeat_subq.c.customer_id)).scalar() or 0
        )

        repeat_rate = (
            round(float(repeat_customers / total_customers * 100), 2)
            if total_customers > 0
            else 0.0
        )
        retention_rate = (
            round(float(active_customers / total_customers * 100), 2)
            if total_customers > 0
            else 0.0
        )

        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "repeat_customers": repeat_customers,
            "repeat_purchase_rate": repeat_rate,
            "retention_rate": retention_rate,
        }

    def customers_lifetime_value(
        self, user_or_tenant: Union[User, int], limit: int = 10
    ) -> dict:
        tenant_id, _ = self._resolve_tenant_and_store(user_or_tenant)

        avg_spend = (
            self.db.query(
                func.coalesce(func.avg(Customer.total_spend), Decimal("0.00"))
            )
            .filter(Customer.tenant_id == tenant_id)
            .scalar()
            or Decimal("0.00")
        )
        avg_ltv = Decimal(str(avg_spend)).quantize(Decimal("0.01"))

        # Top customers with their order count
        order_counts_subq = (
            self.db.query(
                Order.customer_id,
                func.count(Order.id).label("ord_cnt"),
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.customer_id)
            .subquery()
        )

        rows = (
            self.db.query(
                Customer.id,
                Customer.name,
                Customer.email,
                Customer.phone,
                Customer.total_spend,
                func.coalesce(order_counts_subq.c.ord_cnt, 0),
            )
            .outerjoin(order_counts_subq, Customer.id == order_counts_subq.c.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(Customer.total_spend.desc())
            .limit(limit)
            .all()
        )

        top_customers = [
            {
                "customer_id": r[0],
                "name": r[1],
                "email": r[2],
                "phone": r[3],
                "total_spend": Decimal(str(r[4] or "0.00")),
                "orders_count": int(r[5]),
            }
            for r in rows
        ]

        return {
            "average_lifetime_value": avg_ltv,
            "top_customers": top_customers,
        }

    def customers_segments(self, user_or_tenant: Union[User, int]) -> dict:
        """
        Uses existing customers.segment values.
        Does not infer VIP or other segments from arbitrary spend thresholds.
        """
        tenant_id, _ = self._resolve_tenant_and_store(user_or_tenant)

        rows = (
            self.db.query(Customer.segment, func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .group_by(Customer.segment)
            .all()
        )

        segment_counts = {r[0]: int(r[1]) for r in rows}
        total_categorized = sum(segment_counts.values())

        return {
            "segment_counts": segment_counts,
            "total_categorized": total_categorized,
        }

    # =========================================================================
    # F. PROFIT & LOSS REPORT
    # =========================================================================

    def profit_loss(
        self,
        user_or_tenant: Union[User, int],
        start_date: date,
        end_date: date,
        store_id: Optional[int] = None,
    ) -> dict:
        """
        Computes transparent multi-field Profit & Loss metrics:
        - gross_sales, discounts, tax_amount, invoiced_revenue
        - net_revenue_tax_exclusive
        - refund_amount
        - cogs (OrderItem.quantity * current Product.cost_price; historical cost snapshots unavailable)
        - operating_expenses (StoreExpense scoped through Store.tenant_id == current tenant)
        - gross_profit
        - net_profit
        """
        self._validate_date_range(start_date, end_date)
        tenant_id, resolved_store_id = self._resolve_tenant_and_store(
            user_or_tenant, store_id
        )
        start = datetime.combine(start_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())

        # Revenue components
        order_q = self.db.query(
            func.coalesce(func.sum(Order.subtotal), Decimal("0.00")),
            func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.tax_amount), Decimal("0.00")),
            func.coalesce(func.sum(Order.total_amount), Decimal("0.00")),
        ).filter(
            Order.tenant_id == tenant_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
        )
        if resolved_store_id is not None:
            order_q = order_q.filter(Order.store_id == resolved_store_id)

        res = order_q.first()
        gross_sales = Decimal(str(res[0] or "0.00"))
        discounts = Decimal(str(res[1] or "0.00"))
        tax_amount = Decimal(str(res[2] or "0.00"))
        invoiced_revenue = Decimal(str(res[3] or "0.00"))
        net_revenue_tax_exclusive = gross_sales - discounts

        # Refunds
        refund_q = self.db.query(
            func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00"))
        ).filter(
            Refund.tenant_id == tenant_id,
            Refund.status == RefundStatus.APPROVED.value,
            Refund.created_at >= start,
            Refund.created_at <= end,
        )
        if resolved_store_id is not None:
            refund_q = (
                refund_q.join(Invoice, Refund.invoice_id == Invoice.id)
                .join(Order, Invoice.order_id == Order.id)
                .filter(Order.store_id == resolved_store_id)
            )
        refund_amount = Decimal(str(refund_q.scalar() or "0.00"))

        # COGS using current Product.cost_price
        cogs_q = (
            self.db.query(
                func.coalesce(
                    func.sum(OrderItem.quantity * Product.cost_price),
                    Decimal("0.00"),
                )
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(Product, OrderItem.product_id == Product.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start,
                Order.created_at <= end,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if resolved_store_id is not None:
            cogs_q = cogs_q.filter(Order.store_id == resolved_store_id)
        cogs = Decimal(str(cogs_q.scalar() or "0.00"))

        # Operating expenses: StoreExpense joined with Store for tenant isolation
        expense_q = (
            self.db.query(
                func.coalesce(func.sum(StoreExpense.amount), Decimal("0.00"))
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                Store.tenant_id == tenant_id,
                StoreExpense.status == "active",
                StoreExpense.expense_date >= start_date,
                StoreExpense.expense_date <= end_date,
            )
        )
        if resolved_store_id is not None:
            expense_q = expense_q.filter(StoreExpense.store_id == resolved_store_id)
        operating_expenses = Decimal(str(expense_q.scalar() or "0.00"))

        gross_profit = net_revenue_tax_exclusive - cogs
        net_profit = gross_profit - operating_expenses - refund_amount

        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "store_id": resolved_store_id,
            "gross_sales": gross_sales,
            "discounts": discounts,
            "tax_amount": tax_amount,
            "invoiced_revenue": invoiced_revenue,
            "net_revenue_tax_exclusive": net_revenue_tax_exclusive,
            "refund_amount": refund_amount,
            "cogs": cogs,
            "operating_expenses": operating_expenses,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "cogs_data_limitation": "COGS is estimated as sum(OrderItem.quantity * current Product.cost_price).",
            # Legacy compatibility fields
            "revenue": float(invoiced_revenue),
            "cost": float(cogs),
            "profit": float(net_profit),
        }

    # =========================================================================
    # G. EXPORT (CSV, EXCEL, PDF)
    # =========================================================================

    def export_report(
        self,
        user: User,
        data: ReportExportRequest,
    ) -> StreamingResponse:
        rtype = data.report_type
        fmt = data.format.lower()

        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer

        branding = None
        try:
            branding = DocumentSettingsService(self.db).resolve_branding(
                tenant_id=user.tenant_id,
                store_id=data.store_id,
            )
        except Exception:
            branding = None

        headers: List[str] = []
        rows: List[List[Any]] = []
        metadata: Dict[str, Any] = {}
        kpis: List[Dict[str, Any]] = []
        title = rtype.replace("_", " ").title()

        if rtype == "sales_daily":
            tdate = data.target_date or (data.start_date or date.today())
            res = self.daily_sales(user, target_date=tdate, store_id=data.store_id)
            title = "Daily Sales Report"
            metadata = {"Date": str(res["date"]), "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Order Count", "value": res["order_count"]},
                {"label": "Gross Sales", "value": res["gross_sales"]},
                {"label": "Net Sales", "value": res["net_sales"]},
                {"label": "AOV", "value": res["average_order_value"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Date", res["date"]],
                ["Order Count", res["order_count"]],
                ["Gross Sales", str(res["gross_sales"])],
                ["Discounts", str(res["discount_amount"])],
                ["Tax Amount", str(res["tax_amount"])],
                ["Total Sales", str(res["total_sales"])],
                ["Refund Amount", str(res["refund_amount"])],
                ["Net Sales", str(res["net_sales"])],
                ["AOV", str(res["average_order_value"])],
            ]

        elif rtype == "sales_monthly":
            year = data.year or date.today().year
            month = data.month or date.today().month
            res = self.monthly_sales(user, year=year, month=month, store_id=data.store_id)
            title = f"Monthly Sales Report ({res['year']}-{res['month']:02d})"
            metadata = {"Year": res["year"], "Month": res["month"], "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Order Count", "value": res["order_count"]},
                {"label": "Gross Sales", "value": res["gross_sales"]},
                {"label": "Net Sales", "value": res["net_sales"]},
                {"label": "Growth Rate", "value": f"{res['growth_rate_pct']}%" if res["growth_rate_pct"] is not None else "N/A"},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Year", res["year"]],
                ["Month", res["month"]],
                ["Order Count", res["order_count"]],
                ["Gross Sales", str(res["gross_sales"])],
                ["Discounts", str(res["discount_amount"])],
                ["Tax Amount", str(res["tax_amount"])],
                ["Total Sales", str(res["total_sales"])],
                ["Refund Amount", str(res["refund_amount"])],
                ["Net Sales", str(res["net_sales"])],
                ["Growth Rate %", str(res["growth_rate_pct"]) if res["growth_rate_pct"] is not None else "N/A"],
            ]

        elif rtype == "sales_yearly":
            year = data.year or date.today().year
            res = self.yearly_sales(user, year=year, store_id=data.store_id)
            title = f"Yearly Sales Report ({res['year']})"
            metadata = {"Year": res["year"], "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Total Orders", "value": res["total_orders"]},
                {"label": "Gross Sales", "value": res["total_gross_sales"]},
                {"label": "Net Sales", "value": res["total_net_sales"]},
            ]
            headers = ["Month", "Orders", "Gross Sales", "Total Sales", "Net Sales"]
            for m in res["monthly_breakdown"]:
                rows.append([
                    m["month_name"],
                    m["order_count"],
                    str(m["gross_sales"]),
                    str(m["total_sales"]),
                    str(m["net_sales"]),
                ])

        elif rtype == "gst_sales":
            sdate = data.start_date or date.today().replace(day=1)
            edate = data.end_date or date.today()
            res = self.gst_sales(user, start_date=sdate, end_date=edate, store_id=data.store_id)
            title = "GST Sales Report"
            metadata = {"Period": f"{res['start_date']} to {res['end_date']}", "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Invoice Count", "value": res["invoice_count"]},
                {"label": "Taxable Amount", "value": res["taxable_amount"]},
                {"label": "Total Tax", "value": res["total_tax"]},
                {"label": "Total Amount", "value": res["total_amount"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Period", f"{res['start_date']} to {res['end_date']}"],
                ["Invoice Count", res["invoice_count"]],
                ["Taxable Amount", str(res["taxable_amount"])],
                ["CGST", str(res["cgst_amount"])],
                ["SGST", str(res["sgst_amount"])],
                ["IGST", str(res["igst_amount"])],
                ["Total Tax", str(res["total_tax"])],
                ["Total Amount", str(res["total_amount"])],
            ]

        elif rtype == "gst_summary":
            sdate = data.start_date or date.today().replace(day=1)
            edate = data.end_date or date.today()
            res = self.gst_summary(user, start_date=sdate, end_date=edate, store_id=data.store_id)
            title = "GST Summary Report"
            metadata = {"Period": f"{res['start_date']} to {res['end_date']}", "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Invoice Count", "value": res["invoice_count"]},
                {"label": "Output Tax", "value": res["total_output_tax"]},
                {"label": "Input Tax Credit", "value": res["input_tax_credit"]},
                {"label": "Net Tax Liability", "value": res["net_tax_liability"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Period", f"{res['start_date']} to {res['end_date']}"],
                ["Invoice Count", res["invoice_count"]],
                ["Output CGST", str(res["output_cgst"])],
                ["Output SGST", str(res["output_sgst"])],
                ["Output IGST", str(res["output_igst"])],
                ["Total Output Tax", str(res["total_output_tax"])],
                ["Input Tax Credit", str(res["input_tax_credit"])],
                ["Net Tax Liability", str(res["net_tax_liability"])],
            ]

        elif rtype == "inventory_stock":
            res = self.current_stock(user, store_id=data.store_id)
            title = "Current Stock Inventory Report"
            metadata = {"Store ID": str(data.store_id or "All Stores")}
            kpis = [{"label": "Total Items", "value": len(res.get("items", []))}]
            headers = ["Product", "SKU", "Store ID", "Quantity", "Min Stock", "Status"]
            for it in res["items"]:
                rows.append([
                    it["product_name"],
                    it["sku"],
                    it["store_id"],
                    it["quantity"],
                    it["min_stock_level"],
                    it["stock_status"],
                ])

        elif rtype == "inventory_low":
            res = self.low_stock(user, store_id=data.store_id)
            title = "Low Stock Alert Report"
            metadata = {"Store ID": str(data.store_id or "All Stores")}
            kpis = [{"label": "Deficit Items", "value": len(res.get("items", []))}]
            headers = ["Product", "SKU", "Store ID", "Quantity", "Min Stock", "Deficit"]
            for it in res["items"]:
                rows.append([
                    it["product_name"],
                    it["sku"],
                    it["store_id"],
                    it["quantity"],
                    it["min_stock_level"],
                    it["deficit"],
                ])

        elif rtype == "inventory_valuation":
            res = self.inventory_valuation(user, store_id=data.store_id)
            title = "Inventory Valuation Report"
            metadata = {"Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Total Products", "value": res["total_products"]},
                {"label": "Total Units", "value": res["total_units"]},
                {"label": "Cost Valuation", "value": res["cost_valuation"]},
                {"label": "Retail Valuation", "value": res["retail_valuation"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Total Products", res["total_products"]],
                ["Total Units", res["total_units"]],
                ["Cost Valuation", str(res["cost_valuation"])],
                ["Retail Valuation", str(res["retail_valuation"])],
            ]

        elif rtype == "products_top_selling":
            res = self.top_selling_products(
                user,
                start_date=data.start_date,
                end_date=data.end_date,
                limit=data.limit or 10,
                store_id=data.store_id,
            )
            title = "Top Selling Products Report"
            metadata = {"Limit": data.limit or 10, "Store ID": str(data.store_id or "All Stores")}
            kpis = [{"label": "Products Listed", "value": len(res.get("products", []))}]
            headers = ["Product", "SKU", "Qty Sold", "Revenue", "Orders"]
            for p in res["products"]:
                rows.append([
                    p["product_name"],
                    p["sku"],
                    p["quantity_sold"],
                    str(p["revenue"]),
                    p["orders_count"],
                ])

        elif rtype == "products_slow_moving":
            res = self.slow_moving_products(
                user,
                threshold=data.threshold if data.threshold is not None else 5,
                start_date=data.start_date,
                end_date=data.end_date,
                store_id=data.store_id,
            )
            title = "Slow Moving Products Report"
            metadata = {"Threshold": res["threshold"], "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Threshold", "value": res["threshold"]},
                {"label": "Slow Products", "value": len(res.get("products", []))},
            ]
            headers = ["Product", "SKU", "Qty Sold", "Revenue", "Orders"]
            for p in res["products"]:
                rows.append([
                    p["product_name"],
                    p["sku"],
                    p["quantity_sold"],
                    str(p["revenue"]),
                    p["orders_count"],
                ])

        elif rtype == "products_profitability":
            res = self.product_profitability(
                user,
                start_date=data.start_date,
                end_date=data.end_date,
                store_id=data.store_id,
            )
            title = "Product Profitability Report"
            metadata = {"Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Total Revenue", "value": res["total_revenue"]},
                {"label": "Estimated Cost", "value": res["total_estimated_cost"]},
                {"label": "Estimated Profit", "value": res["total_estimated_profit"]},
            ]
            headers = ["Product", "SKU", "Qty Sold", "Revenue", "Cost", "Profit", "Margin %"]
            for p in res["products"]:
                rows.append([
                    p["product_name"],
                    p["sku"],
                    p["quantity_sold"],
                    str(p["revenue"]),
                    str(p["estimated_cost"]),
                    str(p["estimated_gross_profit"]),
                    f"{p['margin_pct']}%" if p["margin_pct"] is not None else "N/A",
                ])

        elif rtype == "profit_loss":
            sdate = data.start_date or date.today().replace(day=1)
            edate = data.end_date or date.today()
            res = self.profit_loss(user, start_date=sdate, end_date=edate, store_id=data.store_id)
            title = "Profit and Loss Statement"
            metadata = {"Period": f"{res['start_date']} to {res['end_date']}", "Store ID": str(data.store_id or "All Stores")}
            kpis = [
                {"label": "Gross Sales", "value": res["gross_sales"]},
                {"label": "Gross Profit", "value": res["gross_profit"]},
                {"label": "Net Profit", "value": res["net_profit"]},
            ]
            headers = ["Financial Component", "Amount"]
            rows = [
                ["Gross Sales", str(res["gross_sales"])],
                ["Discounts", str(res["discounts"])],
                ["Tax Amount", str(res["tax_amount"])],
                ["Invoiced Revenue", str(res["invoiced_revenue"])],
                ["Net Revenue (Tax Exclusive)", str(res["net_revenue_tax_exclusive"])],
                ["Refund Amount", str(res["refund_amount"])],
                ["COGS (Cost of Goods Sold)", str(res["cogs"])],
                ["Operating Expenses", str(res["operating_expenses"])],
                ["Gross Profit", str(res["gross_profit"])],
                ["Net Profit", str(res["net_profit"])],
            ]

        elif rtype == "customers_overview":
            res = self.customers_overview(user)
            title = "Customer Overview Report"
            metadata = {"Generated": date.today().isoformat()}
            kpis = [
                {"label": "Total Customers", "value": res["total_customers"]},
                {"label": "Active Customers", "value": res["active_customers"]},
                {"label": "Total Spend", "value": res["total_spend_all_customers"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Total Customers", res["total_customers"]],
                ["Active Customers", res["active_customers"]],
                ["Inactive Customers", res["inactive_customers"]],
                ["Total Loyalty Points", res["total_loyalty_points"]],
                ["Total Customer Spend", str(res["total_spend_all_customers"])],
            ]

        elif rtype == "customers_retention":
            res = self.customers_retention(user)
            title = "Customer Retention Report"
            metadata = {"Generated": date.today().isoformat()}
            kpis = [
                {"label": "Total Customers", "value": res["total_customers"]},
                {"label": "Active Customers", "value": res["active_customers"]},
                {"label": "Repeat Customers", "value": res["repeat_customers"]},
                {"label": "Retention Rate", "value": f"{res['retention_rate']}%"},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Total Customers", res["total_customers"]],
                ["Active Customers", res["active_customers"]],
                ["Repeat Customers", res["repeat_customers"]],
                ["Repeat Purchase Rate", f"{res['repeat_purchase_rate']}%"],
                ["Retention Rate", f"{res['retention_rate']}%"],
            ]

        elif rtype == "customers_lifetime_value":
            res = self.customers_lifetime_value(user, limit=data.limit or 20)
            title = "Customer Lifetime Value Report"
            metadata = {"Average LTV": str(res.get("average_lifetime_value", 0))}
            kpis = [
                {"label": "Average LTV", "value": res.get("average_lifetime_value", 0)},
                {"label": "Top Customers", "value": len(res.get("top_customers", []))},
            ]
            headers = ["Customer ID", "Name", "Phone", "Email", "Total Spend", "Orders Count"]
            for c in res.get("top_customers", []):
                rows.append([
                    c["customer_id"],
                    c["name"],
                    c.get("phone") or "",
                    c.get("email") or "",
                    str(c["total_spend"]),
                    c["orders_count"],
                ])

        elif rtype == "customers_segments":
            res = self.customers_segments(user)
            title = "Customer Segments Report"
            metadata = {"Total Categorized": res["total_categorized"]}
            kpis = [{"label": "Total Categorized", "value": res["total_categorized"]}]
            headers = ["Segment", "Count"]
            for seg, cnt in res["segment_counts"].items():
                rows.append([seg, cnt])

        elif rtype in ("daily_billing", "daily_billing_closure"):
            tdate = data.target_date or (data.start_date or date.today())
            res = self.daily_billing_closure(user.tenant_id, tdate)
            title = f"Daily Billing Closure ({res['date']})"
            metadata = {"Date": res["date"]}
            kpis = [
                {"label": "Invoices", "value": res["invoice_count"]},
                {"label": "Total Sales", "value": res["total_sales"]},
                {"label": "Net Collection", "value": res["net_collection"]},
            ]
            headers = ["Metric", "Value"]
            rows = [
                ["Date", res["date"]],
                ["Invoice Count", res["invoice_count"]],
                ["Total Sales", str(res["total_sales"])],
                ["Cash Sales", str(res["cash_sales"])],
                ["Card Sales", str(res["card_sales"])],
                ["UPI Sales", str(res["upi_sales"])],
                ["Wallet Sales", str(res["wallet_sales"])],
                ["Discount Amount", str(res["discount_amount"])],
                ["Refund Amount", str(res["refund_amount"])],
                ["Net Collection", str(res["net_collection"])],
            ]

        elif rtype == "payment_summary":
            sdate = data.start_date or date.today().replace(day=1)
            edate = data.end_date or date.today()
            res = self.payment_summary(user.tenant_id, sdate, edate)
            title = "Payment Summary Report"
            metadata = {"Period": f"{res['start_date']} to {res['end_date']}"}
            kpis = [
                {"label": "Grand Total", "value": res["grand_total"]},
                {"label": "Payment Methods", "value": len(res["payment_breakdown"])},
            ]
            headers = ["Payment Method", "Transactions", "Total Amount"]
            for method, vals in res["payment_breakdown"].items():
                rows.append([method, str(vals["transaction_count"]), str(vals["total_amount"])])

        elif rtype == "multi_store_revenue":
            from app.services.multi_store_analytics_service import MultiStoreAnalyticsService
            store_ids_list = [data.store_id] if data.store_id else None
            ms_res = MultiStoreAnalyticsService(self.db).revenue_comparison(
                user=user, start_date=data.start_date, end_date=data.end_date, store_ids=store_ids_list
            )
            title = "Multi-Store Revenue Comparison"
            metadata = {"Period": f"{ms_res.start_date} to {ms_res.end_date}"}
            kpis = [
                {"label": "Stores", "value": ms_res.store_count},
                {"label": "Total Orders", "value": ms_res.total_tenant_orders},
                {"label": "Total Net Sales", "value": ms_res.total_tenant_net_sales},
            ]
            headers = ["Store ID", "Store Name", "Orders", "Gross Sales", "Net Sales", "AOV"]
            for s in ms_res.stores:
                rows.append([s.store_id, s.store_name, s.order_count, str(s.gross_sales), str(s.net_sales), str(s.average_order_value)])

        elif rtype == "multi_store_profit":
            from app.services.multi_store_analytics_service import MultiStoreAnalyticsService
            store_ids_list = [data.store_id] if data.store_id else None
            ms_res = MultiStoreAnalyticsService(self.db).profit_comparison(
                user=user, start_date=data.start_date, end_date=data.end_date, store_ids=store_ids_list
            )
            title = "Multi-Store Profit Comparison"
            metadata = {"Period": f"{ms_res.start_date} to {ms_res.end_date}"}
            kpis = [
                {"label": "Stores", "value": ms_res.store_count},
                {"label": "Tenant Revenue", "value": ms_res.total_tenant_revenue},
                {"label": "Tenant Net Profit", "value": ms_res.total_tenant_net_profit},
            ]
            headers = ["Store ID", "Store Name", "Revenue", "COGS", "Gross Profit", "Expenses", "Net Profit", "Margin %"]
            for s in ms_res.stores:
                rows.append([s.store_id, s.store_name, str(s.revenue), str(s.cogs), str(s.gross_profit), str(s.operating_expenses), str(s.net_profit), f"{s.profit_margin_pct}%" if s.profit_margin_pct is not None else "N/A"])

        elif rtype == "multi_store_inventory":
            from app.services.multi_store_analytics_service import MultiStoreAnalyticsService
            store_ids_list = [data.store_id] if data.store_id else None
            ms_res = MultiStoreAnalyticsService(self.db).inventory_comparison(
                user=user, store_ids=store_ids_list
            )
            title = "Multi-Store Inventory Comparison"
            metadata = {"Stores Analyzed": ms_res.store_count}
            kpis = [
                {"label": "Stores", "value": ms_res.store_count},
                {"label": "Stock Units", "value": ms_res.total_tenant_stock_units},
                {"label": "Cost Valuation", "value": ms_res.total_tenant_cost_valuation},
                {"label": "Retail Valuation", "value": ms_res.total_tenant_retail_valuation},
            ]
            headers = ["Store ID", "Store Name", "Stock Units", "Cost Valuation", "Retail Valuation", "Low Stock SKUs"]
            for s in ms_res.stores:
                rows.append([s.store_id, s.store_name, s.total_stock_units, str(s.total_cost_valuation), str(s.total_retail_valuation), s.low_stock_sku_count])

        elif rtype == "multi_store_customer":
            from app.services.multi_store_analytics_service import MultiStoreAnalyticsService
            store_ids_list = [data.store_id] if data.store_id else None
            ms_res = MultiStoreAnalyticsService(self.db).customer_comparison(
                user=user, start_date=data.start_date, end_date=data.end_date, store_ids=store_ids_list
            )
            title = "Multi-Store Customer Comparison"
            metadata = {"Period": f"{ms_res.start_date} to {ms_res.end_date}"}
            kpis = [
                {"label": "Stores", "value": ms_res.store_count},
                {"label": "Unique Customers", "value": ms_res.total_tenant_unique_customers},
                {"label": "Total Sales", "value": ms_res.total_tenant_sales},
            ]
            headers = ["Store ID", "Store Name", "Customers", "Repeat Customers", "Repeat Rate %", "Total Sales", "Sales/Customer"]
            for s in ms_res.stores:
                rows.append([s.store_id, s.store_name, s.total_unique_customers, s.repeat_customers, f"{s.repeat_customer_rate_pct}%", str(s.total_sales), str(s.sales_per_customer)])

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown report_type: {rtype}",
            )

        filename = f"{rtype}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # -------------------------------------------------------------
        # CSV FORMAT
        # -------------------------------------------------------------
        if fmt == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(headers)
            for r in rows:
                writer.writerow(r)
            stream.seek(0)
            return StreamingResponse(
                iter([stream.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
            )

        # -------------------------------------------------------------
        # EXCEL FORMAT (Professional 2-Sheet Workbook)
        # -------------------------------------------------------------
        elif fmt == "excel":
            return ExcelExportService().create_report_streaming_response(
                sheet_title=title,
                headers=headers,
                rows=rows,
                filename=filename,
                metadata=metadata,
                kpis=kpis,
                branding=branding,
            )

        # -------------------------------------------------------------
        # PDF FORMAT (Professional DocumentRenderer ReportLab Platypus)
        # -------------------------------------------------------------
        elif fmt == "pdf":
            from app.services.document_renderer_service import DocumentRenderer
            pdf_bytes = DocumentRenderer().render_report_pdf(
                title=title,
                metadata=metadata,
                kpi_summary=kpis,
                headers=headers,
                rows=rows,
                branding=branding,
            )
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format: {fmt}. Supported formats: 'csv', 'excel', 'pdf'",
            )

    # =========================================================================
    # LEGACY SERVICE METHODS (PRESERVED UNCHANGED)
    # =========================================================================

    def gst_report(self, tenant_id: int, start_date: date, end_date: date) -> dict:
        invoices = (
            self.db.query(Invoice)
            .filter(
                Invoice.tenant_id == tenant_id,
                Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
                Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
            )
            .all()
        )
        return {
            "invoice_count": len(invoices),
            "total_cgst": float(sum((i.cgst_amount for i in invoices), Decimal("0"))),
            "total_sgst": float(sum((i.sgst_amount for i in invoices), Decimal("0"))),
            "total_igst": float(sum((i.igst_amount for i in invoices), Decimal("0"))),
            "total_amount": float(sum((i.total_amount for i in invoices), Decimal("0"))),
        }

    def daily_billing_closure(
        self, tenant_id: int, target_date: date | None = None
    ) -> dict:
        target_date = target_date or date.today()
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)

        invoices = (
            self.db.query(Invoice)
            .filter(
                Invoice.tenant_id == tenant_id,
                Invoice.created_at >= start,
                Invoice.created_at < end,
            )
            .all()
        )
        total_sales = sum((i.total_amount for i in invoices), Decimal("0"))
        discount_total = sum((i.discount_amount for i in invoices), Decimal("0"))

        payments = (
            self.db.query(Payment)
            .join(Order, Payment.order_id == Order.id)
            .filter(
                Payment.tenant_id == tenant_id,
                Payment.created_at >= start,
                Payment.created_at < end,
                Payment.status == PaymentStatus.COMPLETED.value,
            )
            .all()
        )
        cash_sales = sum(
            (p.amount for p in payments if p.payment_method == "cash"),
            Decimal("0"),
        )
        upi_sales = sum(
            (p.amount for p in payments if p.payment_method in ("upi", "qr")),
            Decimal("0"),
        )
        card_sales = sum(
            (
                p.amount
                for p in payments
                if p.payment_method in ("card", "credit_card", "debit_card")
            ),
            Decimal("0"),
        )
        wallet_sales = sum(
            (p.amount for p in payments if p.payment_method == "wallet"),
            Decimal("0"),
        )

        refunds = (
            self.db.query(Refund)
            .filter(
                Refund.tenant_id == tenant_id,
                Refund.status == RefundStatus.APPROVED.value,
                Refund.created_at >= start,
                Refund.created_at < end,
            )
            .all()
        )
        refund_amount = sum((r.refund_amount for r in refunds), Decimal("0"))
        net_collection = total_sales - refund_amount

        return {
            "date": str(target_date),
            "invoice_count": len(invoices),
            "total_sales": float(total_sales),
            "cash_sales": float(cash_sales),
            "card_sales": float(card_sales),
            "upi_sales": float(upi_sales),
            "wallet_sales": float(wallet_sales),
            "discount_amount": float(discount_total),
            "refund_amount": float(refund_amount),
            "net_collection": float(net_collection),
        }

    def payment_summary(
        self, tenant_id: int, start_date: date, end_date: date
    ) -> dict:
        payments = (
            self.db.query(
                Payment.payment_method, func.sum(Payment.amount), func.count(Payment.id)
            )
            .join(Order, Payment.order_id == Order.id)
            .filter(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= datetime.combine(start_date, datetime.min.time()),
                Payment.created_at <= datetime.combine(end_date, datetime.max.time()),
            )
            .group_by(Payment.payment_method)
            .all()
        )
        breakdown = {
            row[0]: {"total_amount": float(row[1]), "transaction_count": row[2]}
            for row in payments
        }
        grand_total = sum((v["total_amount"] for v in breakdown.values()), 0.0)
        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "payment_breakdown": breakdown,
            "grand_total": grand_total,
        }

    def product_performance(self, tenant_id: int, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                OrderItem.product_id,
                Product.name.label("product_name"),
                func.sum(OrderItem.quantity).label("qty"),
                func.sum(OrderItem.total_amount).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(OrderItem.product_id, Product.name)
            .order_by(func.sum(OrderItem.total_amount).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "product_id": r[0],
                "product_name": r[1],
                "quantity_sold": int(r[2]),
                "revenue": float(r[3]),
            }
            for r in rows
        ]

    def customer_analytics(self, tenant_id: int) -> dict:
        total_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .scalar()
        )
        repeat = (
            self.db.query(Order.customer_id)
            .filter(Order.tenant_id == tenant_id, Order.customer_id.isnot(None))
            .group_by(Order.customer_id)
            .having(func.count(Order.id) > 1)
            .count()
        )
        return {"total_customers": total_customers, "repeat_customers": repeat}

    def log_audit(
        self,
        tenant_id: int,
        user_id: int | None,
        action: str,
        resource: str,
        resource_id: int | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
