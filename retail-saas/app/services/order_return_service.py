from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerWallet, WalletTransaction
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn, OrderReturnItem
from app.models.product import Product
from app.repositories.order_return_repo import OrderReturnRepository
from app.schemas.order_return import (
    OrderReturnCreate,
    OrderReturnExchangeRequest,
    OrderReturnSlipItem,
    OrderReturnSlipResponse,
    OrderReturnStatusUpdate,
    OrderReturnUpdate,
)
from app.utils.constants import StockMovementType


class OrderReturnService:

    VALID_STATUS_TRANSITIONS = {
        "requested": {"approved", "rejected"},
        "approved": {"completed"},
        "rejected": set(),
        "completed": set(),
    }

    @staticmethod
    def create_return(
        db: Session,
        data: OrderReturnCreate,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        if not tenant_id or tenant_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant ID",
            )

        order = db.scalar(
            select(Order).where(
                Order.id == data.order_id,
                Order.tenant_id == tenant_id,
            )
        )

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {data.order_id} not found",
            )

        customer = db.scalar(
            select(Customer).where(
                Customer.id == data.customer_id,
                Customer.tenant_id == tenant_id,
            )
        )

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {data.customer_id} not found",
            )

        if order.customer_id != data.customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order does not belong to the specified customer",
            )

        existing_return = db.scalar(
            select(OrderReturn).where(
                OrderReturn.order_id == data.order_id,
                OrderReturn.tenant_id == tenant_id,
                OrderReturn.status.in_(["requested", "approved"]),
            )
        )

        if existing_return:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Active return already exists for order {data.order_id}",
            )

        # Process return items
        return_items: list[OrderReturnItem] = []
        total_amount = Decimal("0.00")
        order_items_map = {item.id: item for item in order.items} if order.items else {}

        if data.items and len(data.items) > 0:
            for item_in in data.items:
                if item_in.order_item_id not in order_items_map:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Order item with ID {item_in.order_item_id} does not belong to order {data.order_id}",
                    )

                order_item = order_items_map[item_in.order_item_id]

                # Calculate already returned quantity for this item
                already_returned = db.scalar(
                    select(func.coalesce(func.sum(OrderReturnItem.quantity), 0))
                    .join(OrderReturn, OrderReturn.id == OrderReturnItem.order_return_id)
                    .where(
                        OrderReturnItem.tenant_id == tenant_id,
                        OrderReturnItem.order_item_id == item_in.order_item_id,
                        OrderReturn.status.in_(["requested", "approved", "completed"]),
                    )
                ) or 0

                available_qty = order_item.quantity - already_returned
                if item_in.quantity > available_qty:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Cannot return {item_in.quantity} units for order item {item_in.order_item_id}. "
                            f"Only {max(0, available_qty)} units available for return."
                        ),
                    )

                item_total = Decimal(str(order_item.unit_price)) * Decimal(str(item_in.quantity))
                total_amount += item_total

                return_item = OrderReturnItem(
                    tenant_id=tenant_id,
                    order_item_id=order_item.id,
                    product_id=order_item.product_id,
                    quantity=item_in.quantity,
                    unit_price=order_item.unit_price,
                    total_amount=item_total,
                    condition=item_in.condition or "sellable",
                    reason=item_in.reason or data.reason.strip(),
                )
                return_items.append(return_item)
        elif order.items and len(order.items) > 0:
            # Auto-populate all unreturned items from the order
            for order_item in order.items:
                already_returned = db.scalar(
                    select(func.coalesce(func.sum(OrderReturnItem.quantity), 0))
                    .join(OrderReturn, OrderReturn.id == OrderReturnItem.order_return_id)
                    .where(
                        OrderReturnItem.tenant_id == tenant_id,
                        OrderReturnItem.order_item_id == order_item.id,
                        OrderReturn.status.in_(["requested", "approved", "completed"]),
                    )
                ) or 0

                available_qty = order_item.quantity - already_returned
                if available_qty > 0:
                    item_total = Decimal(str(order_item.unit_price)) * Decimal(str(available_qty))
                    total_amount += item_total

                    return_item = OrderReturnItem(
                        tenant_id=tenant_id,
                        order_item_id=order_item.id,
                        product_id=order_item.product_id,
                        quantity=available_qty,
                        unit_price=order_item.unit_price,
                        total_amount=item_total,
                        condition="sellable",
                        reason=data.reason.strip(),
                    )
                    return_items.append(return_item)

        return_number = f"RMA-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        order_return = OrderReturn(
            tenant_id=tenant_id,
            order_id=data.order_id,
            customer_id=data.customer_id,
            return_number=return_number,
            return_type=data.return_type or "refund",
            reason=data.reason.strip(),
            remarks=data.remarks.strip() if data.remarks else None,
            status="requested",
            total_amount=total_amount,
            refund_amount=Decimal("0.00"),
            created_by_id=user_id,
            items=return_items,
        )

        return OrderReturnRepository.create(
            db,
            order_return,
        )

    @staticmethod
    def get_return(
        db: Session,
        return_id: int,
        tenant_id: int,
    ) -> OrderReturn:
        if return_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Return not found",
            )

        order_return = OrderReturnRepository.get_by_id(
            db,
            return_id,
            tenant_id,
        )

        if not order_return:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Return with ID {return_id} not found",
            )

        return order_return

    @staticmethod
    def list_returns(
        db: Session,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> list[OrderReturn]:
        if tenant_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant ID",
            )

        if skip < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Skip cannot be negative",
            )

        if limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 100",
            )

        return OrderReturnRepository.list(
            db,
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            store_id=store_id,
            status=status,
            customer_id=customer_id,
            order_id=order_id,
            search=search,
        )

    @staticmethod
    def count_returns(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> int:
        return OrderReturnRepository.count(
            db,
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            customer_id=customer_id,
            order_id=order_id,
            search=search,
        )

    @staticmethod
    def get_stats(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        return OrderReturnRepository.get_stats(
            db,
            tenant_id=tenant_id,
            store_id=store_id,
        )

    @staticmethod
    def update_return(
        db: Session,
        return_id: int,
        data: OrderReturnUpdate,
        tenant_id: int,
    ) -> OrderReturn:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status in {"completed", "rejected"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Return cannot be updated when status is '{order_return.status}'",
            )

        if data.reason is None and data.remarks is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field is required for update",
            )

        if data.reason is not None:
            order_return.reason = data.reason.strip()

        if data.remarks is not None:
            order_return.remarks = data.remarks.strip()

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def update_status(
        db: Session,
        return_id: int,
        data: OrderReturnStatusUpdate,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        new_status = data.status.strip().lower()

        if new_status == "approved":
            return OrderReturnService.approve_return(
                db=db,
                return_id=return_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        elif new_status == "rejected":
            return OrderReturnService.reject_return(
                db=db,
                return_id=return_id,
                tenant_id=tenant_id,
                remarks=data.remarks,
                user_id=user_id,
            )
        elif new_status == "completed":
            return OrderReturnService.complete_return(
                db=db,
                return_id=return_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )
        current_status = order_return.status

        if current_status == new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Return is already in '{current_status}' status",
            )

        allowed_statuses = OrderReturnService.VALID_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        )

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition: {current_status} -> {new_status}",
            )

        order_return.status = new_status
        order_return.remarks = data.remarks.strip()

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def approve_return(
        db: Session,
        return_id: int,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "requested":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only requested returns can be approved",
            )

        order_return.status = "approved"
        order_return.approved_by_id = user_id
        order_return.approved_at = datetime.utcnow()

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def reject_return(
        db: Session,
        return_id: int,
        tenant_id: int,
        remarks: str,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "requested":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only requested returns can be rejected",
            )

        remarks = remarks.strip()
        if not remarks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rejection remarks are required",
            )

        order_return.status = "rejected"
        order_return.remarks = remarks
        order_return.rejection_reason = remarks
        order_return.rejected_by_id = user_id
        order_return.rejected_at = datetime.utcnow()

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def complete_return(
        db: Session,
        return_id: int,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only approved returns can be completed",
            )

        order = order_return.order
        store_id = order.store_id if order else None

        # 1. Restock sellable items into inventory
        if store_id and order_return.items:
            for item in order_return.items:
                if item.condition == "sellable":
                    inventory = db.query(Inventory).filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == store_id,
                        Inventory.product_id == item.product_id,
                    ).first()

                    if not inventory:
                        inventory = Inventory(
                            tenant_id=tenant_id,
                            store_id=store_id,
                            product_id=item.product_id,
                            quantity=0,
                        )
                        db.add(inventory)
                        db.flush()

                    prev_stock = inventory.quantity
                    inventory.quantity += item.quantity
                    new_stock = inventory.quantity

                    movement = StockMovement(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        product_id=item.product_id,
                        movement_type=StockMovementType.RETURN.value,
                        quantity=item.quantity,
                        previous_stock=prev_stock,
                        new_stock=new_stock,
                        reference_id=order_return.id,
                        reference_type="order_return",
                        notes=f"Restocked from Return {order_return.return_number}",
                    )
                    db.add(movement)

        # 2. Refund calculation & Wallet credit if store credit
        order_return.refund_amount = order_return.total_amount
        if order_return.return_type == "store_credit" and order_return.refund_amount > Decimal("0.00"):
            wallet = db.query(CustomerWallet).filter(
                CustomerWallet.customer_id == order_return.customer_id,
            ).first()

            if not wallet:
                wallet = CustomerWallet(
                    customer_id=order_return.customer_id,
                    current_balance=Decimal("0.00"),
                )
                db.add(wallet)
                db.flush()

            wallet.current_balance = Decimal(str(wallet.current_balance or 0)) + order_return.refund_amount
            tx = WalletTransaction(
                wallet_id=wallet.id,
                transaction_type="CREDIT",
                amount=order_return.refund_amount,
                reference_no=f"RET-{order_return.return_number}",
                remarks=f"Store credit for return {order_return.return_number}",
            )
            db.add(tx)

        # 3. Synchronize Order Status (returned or partially_returned)
        if order and order.items:
            total_order_qty = sum(it.quantity for it in order.items)
            completed_returns_qty = db.scalar(
                select(func.coalesce(func.sum(OrderReturnItem.quantity), 0))
                .join(OrderReturn, OrderReturn.id == OrderReturnItem.order_return_id)
                .where(
                    OrderReturnItem.tenant_id == tenant_id,
                    OrderReturn.order_id == order.id,
                    OrderReturn.status == "completed",
                    OrderReturn.id != order_return.id,
                )
            ) or 0

            current_return_qty = sum(it.quantity for it in order_return.items)
            total_returned_qty = completed_returns_qty + current_return_qty

            if total_returned_qty >= total_order_qty and total_order_qty > 0:
                order.status = "returned"
            elif total_returned_qty > 0:
                order.status = "partially_returned"

        # 4. Mark return as completed
        order_return.status = "completed"
        order_return.completed_by_id = user_id
        order_return.completed_at = datetime.utcnow()

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def process_exchange(
        db: Session,
        return_id: int,
        data: OrderReturnExchangeRequest,
        tenant_id: int,
        user_id: Optional[int] = None,
    ) -> OrderReturn:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status not in {"approved", "completed"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot process exchange for return with status '{order_return.status}'. Must be approved or completed.",
            )

        if order_return.exchange_order_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Exchange order already created (Order ID {order_return.exchange_order_id})",
            )

        original_order = order_return.order
        if not original_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original order not found",
            )

        exchange_order_items: list[OrderItem] = []
        exchange_total = Decimal("0.00")

        for ex_item in data.exchange_items:
            product = db.query(Product).filter(
                Product.id == ex_item.product_id,
                Product.tenant_id == tenant_id,
            ).first()

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Exchange product ID {ex_item.product_id} not found",
                )

            unit_price = ex_item.unit_price if ex_item.unit_price is not None else product.selling_price
            item_total = Decimal(str(unit_price)) * Decimal(str(ex_item.quantity))
            exchange_total += item_total

            exchange_order_items.append(
                OrderItem(
                    product_id=product.id,
                    variant_id=ex_item.variant_id,
                    quantity=ex_item.quantity,
                    unit_price=unit_price,
                    total_amount=item_total,
                )
            )

        exchange_order_number = f"EXCH-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        exchange_order = Order(
            tenant_id=tenant_id,
            store_id=original_order.store_id,
            customer_id=order_return.customer_id,
            user_id=user_id,
            order_number=exchange_order_number,
            order_type="exchange",
            status="confirmed",
            subtotal=exchange_total,
            total_amount=exchange_total,
            notes=data.notes or f"Exchange replacement for return {order_return.return_number}",
            items=exchange_order_items,
        )

        db.add(exchange_order)
        db.flush()

        order_return.exchange_order_id = exchange_order.id
        order_return.return_type = "exchange"

        db.commit()
        db.refresh(order_return)
        return order_return

    @staticmethod
    def get_return_slip(
        db: Session,
        return_id: int,
        tenant_id: int,
    ) -> OrderReturnSlipResponse:
        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        slip_items = []
        for item in order_return.items:
            slip_items.append(
                OrderReturnSlipItem(
                    order_item_id=item.order_item_id,
                    product_id=item.product_id,
                    product_name=item.product_name,
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_amount=item.total_amount,
                    condition=item.condition,
                    reason=item.reason,
                )
            )

        order = order_return.order
        customer = order_return.customer

        return OrderReturnSlipResponse(
            return_id=order_return.id,
            return_number=order_return.return_number or f"RMA-{order_return.id}",
            status=order_return.status,
            return_type=order_return.return_type,
            created_at=order_return.created_at,
            order_id=order_return.order_id,
            order_number=order.order_number if order else None,
            customer_id=order_return.customer_id,
            customer_name=customer.name if customer else None,
            customer_phone=customer.phone if customer else None,
            store_id=order.store_id if order else None,
            store_name=order.store.name if order and getattr(order, "store", None) else None,
            total_amount=order_return.total_amount,
            refund_amount=order_return.refund_amount,
            reason=order_return.reason,
            remarks=order_return.remarks,
            items=slip_items,
        )
