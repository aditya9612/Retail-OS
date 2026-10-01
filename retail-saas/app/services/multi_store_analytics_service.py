from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.refund import Refund
from app.models.store import Store
from app.models.store_expense import StoreExpense
from app.models.user import User
from app.schemas.multi_store_analytics import (
    StoreCustomerComparisonItem,
    StoreCustomerComparisonResponse,
    StoreInventoryComparisonItem,
    StoreInventoryComparisonResponse,
    StoreProfitComparisonItem,
    StoreProfitComparisonResponse,
    StoreRevenueComparisonItem,
    StoreRevenueComparisonResponse,
)
from app.utils.constants import OrderStatus, RefundStatus


class MultiStoreAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def _validate_and_get_stores(
        self,
        user: User,
        store_ids: Optional[List[int]] = None,
    ) -> List[Store]:
        """
        Validates tenant-ownership of requested stores and enforces store-assignment restrictions:
        1. Tenant ID is derived strictly from authenticated user.tenant_id.
        2. If user.store_id is set (Store Manager / Staff), user may only access their assigned store.
           Requesting a different store or mixed stores returns HTTP 403 Forbidden.
        3. If user.store_id is None (Tenant Owner / Admin):
           - If store_ids is supplied, every ID must belong to user.tenant_id (fails closed with 404).
           - If store_ids is omitted, defaults to all active stores of the tenant.
        """
        if not user or not user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no tenant assigned",
            )

        all_tenant_stores = (
            self.db.query(Store)
            .filter(Store.tenant_id == user.tenant_id)
            .all()
        )
        tenant_store_map = {s.id: s for s in all_tenant_stores}

        # Store-assigned manager / staff restriction
        if user.store_id is not None:
            if store_ids is not None:
                if any(sid != user.store_id for sid in store_ids):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: store-assigned users cannot view comparison across other stores",
                    )
            assigned_store = tenant_store_map.get(user.store_id)
            if not assigned_store:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assigned store not found",
                )
            return [assigned_store]

        # Tenant Owner / Admin path
        if store_ids is not None:
            if not store_ids:
                return []
            for sid in store_ids:
                if sid not in tenant_store_map:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Store not found: {sid}",
                    )
            return [tenant_store_map[sid] for sid in store_ids]

        # Default to all active stores
        return [s for s in all_tenant_stores if s.is_active is True]

    def _resolve_date_range(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> Tuple[date, date, datetime, datetime]:
        """
        Resolves query dates to inclusive boundaries:
        - If both omitted: start_date is first day of current month, end_date is today.
        - If start_date > end_date: raises HTTP 400 Bad Request.
        - Returns (start_date, end_date, start_datetime, end_datetime).
        """
        today = date.today()
        if start_date is None and end_date is None:
            start_d = date(today.year, today.month, 1)
            end_d = today
        elif start_date is not None and end_date is None:
            start_d = start_date
            end_d = today
        elif start_date is None and end_date is not None:
            start_d = date(end_date.year, end_date.month, 1)
            end_d = end_date
        else:
            start_d = start_date  # type: ignore[assignment]
            end_d = end_date  # type: ignore[assignment]

        if start_d > end_d:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before or equal to end_date",
            )

        start_dt = datetime.combine(start_d, time.min)
        end_dt = datetime.combine(end_d, time.max)
        return start_d, end_d, start_dt, end_dt

    # =========================================================================
    # 1. REVENUE COMPARISON
    # =========================================================================

    def revenue_comparison(
        self,
        user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        store_ids: Optional[List[int]] = None,
    ) -> StoreRevenueComparisonResponse:
        stores = self._validate_and_get_stores(user, store_ids)
        start_d, end_d, start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        if not stores:
            return StoreRevenueComparisonResponse(
                start_date=start_d,
                end_date=end_d,
                total_tenant_gross_sales=Decimal("0.00"),
                total_tenant_net_sales=Decimal("0.00"),
                total_tenant_orders=0,
                store_count=0,
                stores=[],
            )

        target_sids = [s.id for s in stores]

        # Set-based SQL aggregation for Orders grouped by store_id
        order_rows = (
            self.db.query(
                Order.store_id,
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.subtotal), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")).label("discount_amount"),
                func.coalesce(func.sum(Order.tax_amount), Decimal("0.00")).label("tax_amount"),
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")).label("total_sales"),
            )
            .filter(
                Order.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.store_id)
            .all()
        )
        order_map = {r[0]: r for r in order_rows}

        # Set-based SQL aggregation for Refunds grouped by store_id
        refund_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00")).label("refund_amount"),
            )
            .join(Invoice, Refund.invoice_id == Invoice.id)
            .join(Order, Invoice.order_id == Order.id)
            .filter(
                Refund.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Refund.status == RefundStatus.APPROVED.value,
                Refund.created_at >= start_dt,
                Refund.created_at <= end_dt,
            )
            .group_by(Order.store_id)
            .all()
        )
        refund_map = {r[0]: Decimal(str(r[1] or "0.00")) for r in refund_rows}

        store_items: List[StoreRevenueComparisonItem] = []
        for s in stores:
            ord_data = order_map.get(s.id)
            order_count = int(ord_data[1]) if ord_data else 0
            gross_sales = Decimal(str(ord_data[2])) if ord_data else Decimal("0.00")
            discount_amount = Decimal(str(ord_data[3])) if ord_data else Decimal("0.00")
            tax_amount = Decimal(str(ord_data[4])) if ord_data else Decimal("0.00")
            total_sales = Decimal(str(ord_data[5])) if ord_data else Decimal("0.00")
            refund_amount = refund_map.get(s.id, Decimal("0.00"))
            net_sales = total_sales - refund_amount
            aov = (
                (total_sales / order_count).quantize(Decimal("0.01"))
                if order_count > 0
                else Decimal("0.00")
            )

            store_items.append(
                StoreRevenueComparisonItem(
                    store_id=s.id,
                    store_name=s.name,
                    store_code=s.code,
                    city=s.city,
                    is_main=s.is_main,
                    gross_sales=gross_sales,
                    discount_amount=discount_amount,
                    tax_amount=tax_amount,
                    total_sales=total_sales,
                    refund_amount=refund_amount,
                    net_sales=net_sales,
                    order_count=order_count,
                    average_order_value=aov,
                    share_of_total_revenue_pct=0.0,
                )
            )

        total_tenant_gross_sales = sum(it.gross_sales for it in store_items)
        total_tenant_net_sales = sum(it.net_sales for it in store_items)
        total_tenant_orders = sum(it.order_count for it in store_items)

        # Calculate share of total revenue
        for it in store_items:
            if total_tenant_net_sales > 0:
                it.share_of_total_revenue_pct = round(
                    float((it.net_sales / total_tenant_net_sales) * 100), 2
                )
            else:
                it.share_of_total_revenue_pct = 0.0

        # Sort descending by net_sales
        store_items.sort(key=lambda x: x.net_sales, reverse=True)

        return StoreRevenueComparisonResponse(
            start_date=start_d,
            end_date=end_d,
            total_tenant_gross_sales=total_tenant_gross_sales,
            total_tenant_net_sales=total_tenant_net_sales,
            total_tenant_orders=total_tenant_orders,
            store_count=len(store_items),
            stores=store_items,
        )

    # =========================================================================
    # 2. PROFIT COMPARISON
    # =========================================================================

    def profit_comparison(
        self,
        user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        store_ids: Optional[List[int]] = None,
    ) -> StoreProfitComparisonResponse:
        stores = self._validate_and_get_stores(user, store_ids)
        start_d, end_d, start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        if not stores:
            return StoreProfitComparisonResponse(
                start_date=start_d,
                end_date=end_d,
                total_tenant_net_revenue=Decimal("0.00"),
                total_tenant_cogs=Decimal("0.00"),
                total_tenant_expenses=Decimal("0.00"),
                total_tenant_gross_profit=Decimal("0.00"),
                total_tenant_net_profit=Decimal("0.00"),
                store_count=0,
                stores=[],
            )

        target_sids = [s.id for s in stores]

        # 1. Orders revenue components
        order_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(func.sum(Order.subtotal), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")).label("discounts"),
            )
            .filter(
                Order.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.store_id)
            .all()
        )
        order_map = {r[0]: r for r in order_rows}

        # 2. COGS aggregation
        cogs_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(
                    func.sum(OrderItem.quantity * Product.cost_price),
                    Decimal("0.00"),
                ).label("cogs"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(Product, OrderItem.product_id == Product.id)
            .filter(
                Order.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.store_id)
            .all()
        )
        cogs_map = {r[0]: Decimal(str(r[1] or "0.00")) for r in cogs_rows}

        # 3. Operating Expenses aggregation
        expense_rows = (
            self.db.query(
                StoreExpense.store_id,
                func.coalesce(func.sum(StoreExpense.amount), Decimal("0.00")).label("expenses"),
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                Store.tenant_id == user.tenant_id,
                StoreExpense.store_id.in_(target_sids),
                StoreExpense.status == "active",
                StoreExpense.expense_date >= start_d,
                StoreExpense.expense_date <= end_d,
            )
            .group_by(StoreExpense.store_id)
            .all()
        )
        expense_map = {r[0]: Decimal(str(r[1] or "0.00")) for r in expense_rows}

        # 4. Refunds aggregation
        refund_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(func.sum(Refund.refund_amount), Decimal("0.00")).label("refund_amount"),
            )
            .join(Invoice, Refund.invoice_id == Invoice.id)
            .join(Order, Invoice.order_id == Order.id)
            .filter(
                Refund.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Refund.status == RefundStatus.APPROVED.value,
                Refund.created_at >= start_dt,
                Refund.created_at <= end_dt,
            )
            .group_by(Order.store_id)
            .all()
        )
        refund_map = {r[0]: Decimal(str(r[1] or "0.00")) for r in refund_rows}

        store_items: List[StoreProfitComparisonItem] = []
        for s in stores:
            ord_data = order_map.get(s.id)
            gross_sales = Decimal(str(ord_data[1])) if ord_data else Decimal("0.00")
            discounts = Decimal(str(ord_data[2])) if ord_data else Decimal("0.00")
            net_revenue = gross_sales - discounts
            cogs = cogs_map.get(s.id, Decimal("0.00"))
            operating_expenses = expense_map.get(s.id, Decimal("0.00"))
            refund_amount = refund_map.get(s.id, Decimal("0.00"))
            gross_profit = net_revenue - cogs
            net_profit = gross_profit - operating_expenses - refund_amount
            margin = (
                round(float((net_profit / net_revenue) * 100), 2)
                if net_revenue > 0
                else 0.0
            )

            store_items.append(
                StoreProfitComparisonItem(
                    store_id=s.id,
                    store_name=s.name,
                    store_code=s.code,
                    city=s.city,
                    is_main=s.is_main,
                    gross_sales=gross_sales,
                    discounts=discounts,
                    net_revenue=net_revenue,
                    cogs=cogs,
                    operating_expenses=operating_expenses,
                    refund_amount=refund_amount,
                    gross_profit=gross_profit,
                    net_profit=net_profit,
                    net_profit_margin_pct=margin,
                )
            )

        total_tenant_net_revenue = sum(it.net_revenue for it in store_items)
        total_tenant_cogs = sum(it.cogs for it in store_items)
        total_tenant_expenses = sum(it.operating_expenses for it in store_items)
        total_tenant_gross_profit = sum(it.gross_profit for it in store_items)
        total_tenant_net_profit = sum(it.net_profit for it in store_items)

        # Sort descending by net_profit
        store_items.sort(key=lambda x: x.net_profit, reverse=True)

        return StoreProfitComparisonResponse(
            start_date=start_d,
            end_date=end_d,
            total_tenant_net_revenue=total_tenant_net_revenue,
            total_tenant_cogs=total_tenant_cogs,
            total_tenant_expenses=total_tenant_expenses,
            total_tenant_gross_profit=total_tenant_gross_profit,
            total_tenant_net_profit=total_tenant_net_profit,
            store_count=len(store_items),
            stores=store_items,
        )

    # =========================================================================
    # 3. INVENTORY COMPARISON
    # =========================================================================

    def inventory_comparison(
        self,
        user: User,
        store_ids: Optional[List[int]] = None,
    ) -> StoreInventoryComparisonResponse:
        stores = self._validate_and_get_stores(user, store_ids)
        today = date.today()

        if not stores:
            return StoreInventoryComparisonResponse(
                as_of_date=today,
                total_tenant_units=0,
                total_tenant_cost_valuation=Decimal("0.00"),
                total_tenant_retail_valuation=Decimal("0.00"),
                store_count=0,
                stores=[],
            )

        target_sids = [s.id for s in stores]

        inventory_rows = (
            self.db.query(
                Inventory.store_id,
                func.count(distinct(Product.id)).label("total_products"),
                func.coalesce(func.sum(Inventory.quantity), 0).label("total_units"),
                func.coalesce(
                    func.sum(Inventory.quantity * Product.cost_price),
                    Decimal("0.00"),
                ).label("cost_valuation"),
                func.coalesce(
                    func.sum(Inventory.quantity * Product.selling_price),
                    Decimal("0.00"),
                ).label("retail_valuation"),
                func.coalesce(
                    func.sum(
                        case(
                            (Inventory.quantity <= Inventory.min_stock_level, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("low_stock_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (Inventory.quantity <= 0, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("out_of_stock_count"),
            )
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == user.tenant_id,
                Inventory.store_id.in_(target_sids),
                Product.is_active == True,
            )
            .group_by(Inventory.store_id)
            .all()
        )
        inv_map = {r[0]: r for r in inventory_rows}

        store_items: List[StoreInventoryComparisonItem] = []
        for s in stores:
            inv_data = inv_map.get(s.id)
            total_products = int(inv_data[1]) if inv_data else 0
            total_units = int(inv_data[2]) if inv_data else 0
            cost_valuation = Decimal(str(inv_data[3])) if inv_data else Decimal("0.00")
            retail_valuation = Decimal(str(inv_data[4])) if inv_data else Decimal("0.00")
            low_stock_count = int(inv_data[5]) if inv_data else 0
            out_of_stock_count = int(inv_data[6]) if inv_data else 0

            store_items.append(
                StoreInventoryComparisonItem(
                    store_id=s.id,
                    store_name=s.name,
                    store_code=s.code,
                    city=s.city,
                    is_main=s.is_main,
                    total_products=total_products,
                    total_units=total_units,
                    cost_valuation=cost_valuation,
                    retail_valuation=retail_valuation,
                    low_stock_count=low_stock_count,
                    out_of_stock_count=out_of_stock_count,
                )
            )

        total_tenant_units = sum(it.total_units for it in store_items)
        total_tenant_cost_valuation = sum(it.cost_valuation for it in store_items)
        total_tenant_retail_valuation = sum(it.retail_valuation for it in store_items)

        # Sort descending by cost_valuation
        store_items.sort(key=lambda x: x.cost_valuation, reverse=True)

        return StoreInventoryComparisonResponse(
            as_of_date=today,
            total_tenant_units=total_tenant_units,
            total_tenant_cost_valuation=total_tenant_cost_valuation,
            total_tenant_retail_valuation=total_tenant_retail_valuation,
            store_count=len(store_items),
            stores=store_items,
        )

    # =========================================================================
    # 4. CUSTOMER COMPARISON
    # =========================================================================

    def customer_comparison(
        self,
        user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        store_ids: Optional[List[int]] = None,
    ) -> StoreCustomerComparisonResponse:
        stores = self._validate_and_get_stores(user, store_ids)
        start_d, end_d, start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        if not stores:
            return StoreCustomerComparisonResponse(
                start_date=start_d,
                end_date=end_d,
                total_tenant_orders=0,
                total_tenant_unique_customers=0,
                total_tenant_spend=Decimal("0.00"),
                store_count=0,
                stores=[],
            )

        target_sids = [s.id for s in stores]

        customer_order_rows = (
            self.db.query(
                Order.store_id,
                func.count(distinct(Order.customer_id)).label("unique_customers"),
                func.coalesce(
                    func.sum(case((Order.customer_id.is_(None), 1), else_=0)),
                    0,
                ).label("guest_orders"),
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")).label("total_spend"),
            )
            .filter(
                Order.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .group_by(Order.store_id)
            .all()
        )
        cust_map = {r[0]: r for r in customer_order_rows}

        store_items: List[StoreCustomerComparisonItem] = []
        for s in stores:
            c_data = cust_map.get(s.id)
            unique_customers = int(c_data[1]) if c_data else 0
            guest_orders = int(c_data[2]) if c_data else 0
            total_orders = int(c_data[3]) if c_data else 0
            total_spend = Decimal(str(c_data[4])) if c_data else Decimal("0.00")
            avg_bill = (
                (total_spend / total_orders).quantize(Decimal("0.01"))
                if total_orders > 0
                else Decimal("0.00")
            )

            store_items.append(
                StoreCustomerComparisonItem(
                    store_id=s.id,
                    store_name=s.name,
                    store_code=s.code,
                    city=s.city,
                    is_main=s.is_main,
                    unique_customers=unique_customers,
                    guest_orders=guest_orders,
                    total_orders=total_orders,
                    total_spend=total_spend,
                    average_bill_size=avg_bill,
                    share_of_total_orders_pct=0.0,
                )
            )

        total_tenant_orders = sum(it.total_orders for it in store_items)
        total_tenant_spend = sum(it.total_spend for it in store_items)

        # Tenant-wide unique customers (across target stores in date range)
        tenant_unique_customers_count = (
            self.db.query(func.count(distinct(Order.customer_id)))
            .filter(
                Order.tenant_id == user.tenant_id,
                Order.store_id.in_(target_sids),
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.customer_id.isnot(None),
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .scalar()
            or 0
        )

        for it in store_items:
            if total_tenant_orders > 0:
                it.share_of_total_orders_pct = round(
                    float((it.total_orders / total_tenant_orders) * 100), 2
                )
            else:
                it.share_of_total_orders_pct = 0.0

        # Sort descending by total_spend
        store_items.sort(key=lambda x: x.total_spend, reverse=True)

        return StoreCustomerComparisonResponse(
            start_date=start_d,
            end_date=end_d,
            total_tenant_orders=total_tenant_orders,
            total_tenant_unique_customers=int(tenant_unique_customers_count),
            total_tenant_spend=total_tenant_spend,
            store_count=len(store_items),
            stores=store_items,
        )
