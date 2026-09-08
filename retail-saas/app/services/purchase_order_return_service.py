from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.purchase_order_return import (
    PurchaseOrderReturn,
    PurchaseOrderReturnItem,
)
from app.repositories.purchase_order_return_repo import (
    PurchaseOrderReturnRepository,
)
from app.schemas.purchase_order_return import (
    PurchaseOrderReturnCreate,
    PurchaseOrderReturnUpdate,
    PurchaseOrderReturnStatusUpdate,
)
from app.services.inventory_service import InventoryService
from app.schemas.inventory import StockOutRequest


class PurchaseOrderReturnService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = PurchaseOrderReturnRepository(db)

    def _get_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:

        if return_id <= 0:
            raise NotFoundException(
                "Purchase Order Return not found"
            )

        purchase_order_return = self.repo.get_by_id(
            return_id,
            tenant_id,
        )

        if not purchase_order_return:
            raise NotFoundException(
                "Purchase Order Return not found"
            )

        return purchase_order_return

    def _get_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> PurchaseOrder:

        if purchase_order_id <= 0:
            raise NotFoundException(
                "Purchase Order not found"
            )

        purchase_order = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.tenant_id == tenant_id,
            )
            .first()
        )

        if not purchase_order:
            raise NotFoundException(
                "Purchase Order not found"
            )

        return purchase_order

    def create_return(
        self,
        tenant_id: int,
        data: PurchaseOrderReturnCreate,
    ) -> PurchaseOrderReturn:

        purchase_order = self._get_purchase_order(
            tenant_id,
            data.purchase_order_id,
        )

        if purchase_order.status not in {
            "received",
        }:
            raise AppException(
                "Only received purchase orders can be returned"
            )

        return_item_ids = {
            item.purchase_order_item_id
            for item in data.items
        }

        po_items = (
            self.db.query(PurchaseOrderItem)
            .filter(
                PurchaseOrderItem.purchase_order_id
                == purchase_order.id,
                PurchaseOrderItem.id.in_(return_item_ids),
            )
            .all()
        )

        if len(po_items) != len(return_item_ids):
            raise NotFoundException(
                "One or more Purchase Order Items not found"
            )

        po_item_map = {
            item.id: item
            for item in po_items
        }

        # Calculate quantities already returned
        existing_return_items = (
            self.db.query(PurchaseOrderReturnItem)
            .join(
                PurchaseOrderReturn,
                PurchaseOrderReturn.id
                == PurchaseOrderReturnItem.purchase_order_return_id,
            )
            .filter(
                PurchaseOrderReturn.tenant_id == tenant_id,
                PurchaseOrderReturn.purchase_order_id
                == purchase_order.id,
                PurchaseOrderReturn.status.in_(
                    {
                        "requested",
                        "approved",
                        "completed",
                    }
                ),
                PurchaseOrderReturnItem.purchase_order_item_id.in_(
                    return_item_ids
                ),
            )
            .all()
        )

        already_returned = {}

        for return_item in existing_return_items:
            already_returned[
                return_item.purchase_order_item_id
            ] = (
                already_returned.get(
                    return_item.purchase_order_item_id,
                    0,
                )
                + return_item.quantity
            )

        purchase_order_return = PurchaseOrderReturn(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order.id,
            reason=data.reason,
            remarks=data.remarks,
            status="requested",
            total_amount=Decimal("0.00"),
        )

        total_amount = Decimal("0.00")

        for data_item in data.items:

            po_item = po_item_map[
                data_item.purchase_order_item_id
            ]

            returned_quantity = already_returned.get(
                po_item.id,
                0,
            )

            remaining_quantity = (
                po_item.quantity - returned_quantity
            )

            if data_item.quantity > remaining_quantity:
                raise AppException(
                    f"Return quantity for Purchase Order Item "
                    f"{po_item.id} cannot exceed remaining quantity "
                    f"{remaining_quantity}"
                )

            item_total = (
                Decimal(data_item.quantity)
                * po_item.unit_price
            )

            purchase_order_return.items.append(
                PurchaseOrderReturnItem(
                    purchase_order_item_id=po_item.id,
                    product_id=po_item.product_id,
                    quantity=data_item.quantity,
                    unit_price=po_item.unit_price,
                    total=item_total,
                )
            )

            total_amount += item_total

        if total_amount <= Decimal("0.00"):
            raise AppException(
                "Return amount must be greater than zero"
            )

        if total_amount > purchase_order.total_amount:
            raise AppException(
                "Return amount cannot exceed Purchase Order total amount"
            )

        purchase_order_return.total_amount = total_amount

        try:
            self.db.add(purchase_order_return)
            self.db.commit()
            self.db.refresh(purchase_order_return)

        except Exception:
            self.db.rollback()
            raise

        return purchase_order_return

    def list_returns(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
    ):

        if page < 1:
            page = 1

        if page_size < 1:
            page_size = 20

        if page_size > 100:
            page_size = 100

        skip = (page - 1) * page_size

        return self.repo.list_returns(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
        )

    def get_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:

        return self._get_return(
            tenant_id,
            return_id,
        )

    def update_return(
        self,
        tenant_id: int,
        return_id: int,
        data: PurchaseOrderReturnUpdate,
    ) -> PurchaseOrderReturn:

        purchase_order_return = self._get_return(
            tenant_id,
            return_id,
        )

        if purchase_order_return.status != "requested":
            raise AppException(
                "Only requested returns can be updated"
            )

        if data.reason is not None:
            purchase_order_return.reason = data.reason

        if data.remarks is not None:
            purchase_order_return.remarks = data.remarks

        return self.repo.update(
            purchase_order_return
        )

    def update_status(
        self,
        tenant_id: int,
        return_id: int,
        data: PurchaseOrderReturnStatusUpdate,
    ) -> PurchaseOrderReturn:

        purchase_order_return = self._get_return(
            tenant_id,
            return_id,
        )

        current_status = purchase_order_return.status
        new_status = data.status

        allowed_transitions = {
            "requested": {
                "approved",
                "rejected",
            },
            "approved": {
                "completed",
            },
            "rejected": set(),
            "completed": set(),
        }

        if new_status == current_status:
            raise AppException(
                f"Purchase Order Return is already {current_status}"
            )

        if new_status not in allowed_transitions.get(
            current_status,
            set(),
        ):
            raise AppException(
                f"Cannot change return status from "
                f"'{current_status}' to '{new_status}'"
            )

        purchase_order_return.status = new_status

        return self.repo.update(
            purchase_order_return
        )

    def approve_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:

        return self.update_status(
            tenant_id,
            return_id,
            PurchaseOrderReturnStatusUpdate(
                status="approved"
            ),
        )

    def reject_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:

        return self.update_status(
            tenant_id,
            return_id,
            PurchaseOrderReturnStatusUpdate(
                status="rejected"
            ),
        )

    def complete_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:

        purchase_order_return = self._get_return(
            tenant_id,
            return_id,
        )

        if purchase_order_return.status != "approved":
            raise AppException(
                "Only approved returns can be completed"
            )

        purchase_order = self._get_purchase_order(
            tenant_id,
            purchase_order_return.purchase_order_id,
        )

        inventory_service = InventoryService(
            self.db
        )

        try:

            for item in purchase_order_return.items:

                inventory_service.stock_out(
                    tenant_id,
                    StockOutRequest(
                        store_id=purchase_order.store_id,
                        product_id=item.product_id,
                        quantity=item.quantity,
                        notes=(
                            f"Purchase Order Return "
                            f"#{purchase_order_return.id} "
                            f"for {purchase_order.po_number}"
                        ),
                    ),
                )

            purchase_order_return.status = "completed"

            self.db.commit()
            self.db.refresh(
                purchase_order_return
            )

        except Exception:
            self.db.rollback()
            raise

        return purchase_order_return