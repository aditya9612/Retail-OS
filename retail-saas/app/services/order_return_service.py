from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_return import OrderReturn
from app.schemas.order_return import (
    OrderReturnCreate,
    OrderReturnStatusUpdate,
    OrderReturnUpdate,
)
from app.repositories.order_return_repo import OrderReturnRepository


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
                OrderReturn.status.in_(
                    ["requested", "approved"]
                ),
            )
        )

        if existing_return:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Active return already exists for order "
                    f"{data.order_id}"
                ),
            )

        order_return = OrderReturn(
            tenant_id=tenant_id,
            order_id=data.order_id,
            customer_id=data.customer_id,
            reason=data.reason.strip(),
            remarks=data.remarks.strip(),
            status="requested",
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
            tenant_id,
            skip,
            limit,
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
                detail=(
                    f"Return cannot be updated when status is "
                    f"'{order_return.status}'"
                ),
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
    ) -> OrderReturn:

        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        current_status = order_return.status
        new_status = data.status.strip().lower()


        if current_status == new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Return is already in '{current_status}' status"
                ),
            )

        allowed_statuses = (
            OrderReturnService.VALID_STATUS_TRANSITIONS.get(
                current_status,
                set(),
            )
        )

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status transition: "
                    f"{current_status} -> {new_status}"
                ),
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
    ) -> OrderReturn:

        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "requested":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Only requested returns can be approved"
                ),
            )

        order_return.status = "approved"

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
    ) -> OrderReturn:

        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "requested":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Only requested returns can be rejected"
                ),
            )

        remarks = remarks.strip()

        if not remarks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rejection remarks are required",
            )

        order_return.status = "rejected"
        order_return.remarks = remarks

        return OrderReturnRepository.update(
            db,
            order_return,
        )

    @staticmethod
    def complete_return(
        db: Session,
        return_id: int,
        tenant_id: int,
    ) -> OrderReturn:

        order_return = OrderReturnService.get_return(
            db,
            return_id,
            tenant_id,
        )

        if order_return.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Only approved returns can be completed"
                ),
            )

        order_return.status = "completed"

        return OrderReturnRepository.update(
            db,
            order_return,
        )