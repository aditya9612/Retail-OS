import csv
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
import secrets
from typing import Optional

from fastapi import status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.models.coupon import Coupon, CouponRedemption
from app.models.order import Order
from app.repositories.coupon_repo import CouponRepository
from app.schemas.coupon import (
    ApplicableCouponItem,
    ApplicableCouponsResponse,
    BulkGenerateCouponsRequest,
    BulkGenerateCouponsResponse,
    CouponCreate,
    CouponResponse,
    CouponUpdate,
)
from app.services.excel_export_service import ExcelExportService


class CouponService:

    def __init__(self, db):
        self.db = db
        self.repo = CouponRepository(db)

    def create_coupon(
        self,
        tenant_id: int,
        data: CouponCreate,
    ) -> Coupon:
        code = data.code.strip().upper()

        existing_coupon = self.repo.get_by_code(
            code,
            tenant_id,
        )

        if existing_coupon:
            raise ConflictException(
                "Coupon code already exists"
            )

        coupon = Coupon(
            tenant_id=tenant_id,
            code=code,
            description=data.description.strip(),
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            minimum_order_amount=data.minimum_order_amount,
            maximum_discount=data.maximum_discount,
            usage_limit=data.usage_limit,
            used_count=0,
            usage_limit_per_customer=data.usage_limit_per_customer,
            applicable_categories=data.applicable_categories,
            applicable_products=data.applicable_products,
            store_id=data.store_id,
            first_order_only=data.first_order_only or False,
            is_deleted=False,
            start_date=data.start_date,
            end_date=data.end_date,
            is_active=True,
        )

        return self.repo.create(coupon)

    def list_coupons(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: Optional[int] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> list[Coupon]:
        skip = (page - 1) * page_size if page_size else 0
        coupons = self.repo.list_coupons(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
            is_active=is_active,
            search=search,
        )

        if not coupons:
            raise NotFoundException(
                "No coupons found"
            )

        return coupons

    def get_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ) -> Coupon:
        coupon = self.repo.get_by_id(
            coupon_id,
            tenant_id,
        )

        if not coupon:
            raise NotFoundException(
                "Coupon not found"
            )

        return coupon

    def update_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
        data: CouponUpdate,
    ) -> Coupon:
        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise AppException(
                "At least one field is required for update"
            )

        final_start_date = update_data.get(
            "start_date",
            coupon.start_date,
        )

        final_end_date = update_data.get(
            "end_date",
            coupon.end_date,
        )

        final_discount_type = update_data.get(
            "discount_type",
            coupon.discount_type,
        )

        final_discount_value = update_data.get(
            "discount_value",
            coupon.discount_value,
        )

        final_usage_limit = update_data.get(
            "usage_limit",
            coupon.usage_limit,
        )

        if "start_date" in update_data and final_start_date < date.today():
            raise AppException(
               "Start date cannot be in the past"
            )

        if final_end_date < final_start_date:
            raise AppException(
                "End date must be on or after start date"
            )

        if final_discount_type not in (
            "percentage",
            "fixed",
        ):
            raise AppException(
               "discount_type must be either 'percentage' or 'fixed'"
            )

        if final_discount_type == "percentage":
            if final_discount_value < Decimal("1"):
                raise AppException(
                    "Percentage discount must be greater than or equal to 1",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if final_discount_value > Decimal("100"):
                raise AppException(
                    "Percentage discount cannot be greater than 100",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        if final_usage_limit < coupon.used_count:
            raise AppException(
                f"Usage limit cannot be less than used count ({coupon.used_count})"
            )

        final_maximum_discount = update_data.get(
           "maximum_discount",
            coupon.maximum_discount,
        )

        if (
            final_maximum_discount is not None
            and final_discount_type == "percentage"
            and final_maximum_discount <= 0
        ):
            raise AppException(
                 "Maximum discount must be greater than 0"
            )

        for key, value in update_data.items():
            if key == "description" and isinstance(value, str):
                value = value.strip()
            if key == "code" and isinstance(value, str):
                value = value.strip().upper()
            setattr(
               coupon,
               key,
               value,
            )

        return self.repo.update(coupon)

    def delete_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ):
        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        used_count = coupon.used_count
        self.repo.delete(coupon)

        if used_count > 0:
            return {
                "message": "Coupon has been used in past orders; it has been deactivated and archived safely.",
                "coupon_id": coupon_id,
            }

        return {
            "message": "Coupon deleted successfully",
            "coupon_id": coupon_id,
        }

    def update_coupon_status(
        self,
        tenant_id: int,
        coupon_id: int,
        is_active: bool,
    ):
        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        if coupon.is_active == is_active:
            raise AppException(
                f"Coupon is already {'active' if is_active else 'inactive'}"
            )

        coupon.is_active = is_active
        return self.repo.update_status(coupon)

    def get_valid_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
        customer_id: Optional[int] = None,
        customer_phone: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> Coupon:
        code = coupon_code.strip().upper()

        coupon = self.repo.get_by_code(
            code,
            tenant_id,
        )

        if not coupon:
            raise NotFoundException(
                "Coupon not found"
            )

        today = date.today()

        if not coupon.is_active:
            raise AppException(
                "Coupon is inactive"
            )

        if today < coupon.start_date:
            raise AppException(
                "Coupon is not active yet"
            )

        if today > coupon.end_date:
            raise AppException(
                "Coupon expired"
            )

        if order_amount < coupon.minimum_order_amount:
            raise AppException(
                f"Minimum order amount is {coupon.minimum_order_amount}"
            )

        if coupon.used_count >= coupon.usage_limit:
            raise AppException(
                "Coupon usage limit exceeded"
            )

        # Check store restriction if configured
        if coupon.store_id is not None and store_id is not None and coupon.store_id != store_id:
            raise AppException(
                "Coupon is not valid for this store"
            )

        # Check per-customer usage limit
        if coupon.usage_limit_per_customer is not None and (customer_id is not None or customer_phone is not None):
            cust_used = self.repo.count_customer_redemptions(
                tenant_id=tenant_id,
                coupon_id=coupon.id,
                customer_id=customer_id,
                customer_phone=customer_phone,
            )
            if cust_used >= coupon.usage_limit_per_customer:
                raise AppException(
                    f"Coupon usage limit of {coupon.usage_limit_per_customer} exceeded for this customer"
                )

        # Check first-order-only restriction
        if coupon.first_order_only and customer_id is not None:
            existing_orders = (
                self.db.query(Order)
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.customer_id == customer_id,
                    Order.status.in_(["completed", "delivered", "paid"]),
                )
                .count()
            )
            if existing_orders > 0:
                raise AppException(
                    "Coupon is only valid on your first order"
                )

        return coupon

    def validate_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
        customer_id: Optional[int] = None,
        customer_phone: Optional[str] = None,
        store_id: Optional[int] = None,
    ):
        self.get_valid_coupon(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            order_amount=order_amount,
            customer_id=customer_id,
            customer_phone=customer_phone,
            store_id=store_id,
        )

        return {
            "valid": True,
            "message": "Coupon is valid",
        }

    def apply_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
        customer_id: Optional[int] = None,
        customer_phone: Optional[str] = None,
        store_id: Optional[int] = None,
        order_id: Optional[int] = None,
        record_redemption: bool = False,
    ):
        coupon = self.get_valid_coupon(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            order_amount=order_amount,
            customer_id=customer_id,
            customer_phone=customer_phone,
            store_id=store_id,
        )

        if coupon.discount_type == "fixed":
            discount = coupon.discount_value
        else:
            discount = (
                order_amount
                * coupon.discount_value
                / Decimal("100")
            )

        if (
            coupon.maximum_discount is not None
            and discount > coupon.maximum_discount
        ):
            discount = coupon.maximum_discount

        discount = min(
            discount,
            order_amount,
        )
        
        final_amount = max(
            Decimal("0.00"),
            order_amount - discount,
        )

        # Record redemption if explicitly requested or linked to an order
        if record_redemption:
            redemption = CouponRedemption(
                tenant_id=tenant_id,
                coupon_id=coupon.id,
                order_id=order_id,
                customer_id=customer_id,
                customer_phone=customer_phone,
                discount_amount=discount,
                order_amount=order_amount,
                redeemed_at=datetime.utcnow(),
            )
            self.repo.create_redemption(redemption)
            coupon.used_count += 1
            self.repo.update(coupon)

        return {
            "coupon_code": coupon.code,
            "original_amount": float(round(order_amount, 2)),
            "discount_amount": float(round(discount, 2)),
            "final_amount": float(round(final_amount, 2)),
            "message": "Coupon applied successfully",
        }

    def get_active_coupons(
        self,
        tenant_id: int,
    ):
        coupons = self.repo.get_active_coupons(
            tenant_id
        )

        if not coupons:
            raise NotFoundException(
                "No active coupons found"
            )

        return coupons

    def get_expired_coupons(
        self,
        tenant_id: int,
    ):
        coupons = self.repo.get_expired_coupons(
            tenant_id
        )

        if not coupons:
            raise NotFoundException(
                "No expired coupons found"
            )

        return coupons

    def get_coupon_stats(
        self,
        tenant_id: int,
    ):
        today = date.today()
        coupons = self.repo.list_all_for_stats(
            tenant_id
        )

        total = len(coupons)

        active = sum(
            1
            for coupon in coupons
            if (
                coupon.is_active
                and coupon.start_date <= today
                and coupon.end_date >= today
            )
        )

        expired = sum(
            1
            for coupon in coupons
            if coupon.end_date < today
        )

        inactive = sum(
            1
            for coupon in coupons
            if not coupon.is_active
        )

        scheduled = sum(
            1
            for coupon in coupons
            if (
                coupon.is_active
                and coupon.start_date > today
            )
        )

        total_used = sum(
            coupon.used_count
            for coupon in coupons
        )

        return {
            "total_coupons": total,
            "active_coupons": active,
            "expired_coupons": expired,
            "inactive_coupons": inactive,
            "scheduled_coupons": scheduled,
            "total_used": total_used,
        }

    # -------------------------------------------------------------
    # NEW ENTERPRISE APIS
    # -------------------------------------------------------------
    def list_redemptions(
        self,
        tenant_id: int,
        coupon_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> list[CouponRedemption]:
        # Ensure coupon exists
        self.get_coupon(tenant_id, coupon_id)
        skip = (page - 1) * page_size
        return self.repo.list_redemptions(
            tenant_id=tenant_id,
            coupon_id=coupon_id,
            skip=skip,
            limit=page_size,
        )

    def bulk_generate(
        self,
        tenant_id: int,
        data: BulkGenerateCouponsRequest,
    ) -> BulkGenerateCouponsResponse:
        prefix = data.prefix.strip().upper()
        coupons_to_create = []

        for i in range(data.count):
            # Ensure generated code has letters and digits for validator regex compatibility
            suffix_hex = secrets.token_hex(3).upper()  # 6 chars alphanumeric
            unique_code = f"{prefix}{suffix_hex}"

            # Check collision
            while self.repo.get_by_code(unique_code, tenant_id) or any(c.code == unique_code for c in coupons_to_create):
                suffix_hex = secrets.token_hex(3).upper()
                unique_code = f"{prefix}{suffix_hex}"

            cpn = Coupon(
                tenant_id=tenant_id,
                code=unique_code,
                description=f"{data.description} (#{i+1})",
                discount_type=data.discount_type,
                discount_value=data.discount_value,
                minimum_order_amount=data.minimum_order_amount,
                maximum_discount=data.maximum_discount,
                usage_limit=data.usage_limit,
                used_count=0,
                usage_limit_per_customer=data.usage_limit_per_customer,
                start_date=data.start_date,
                end_date=data.end_date,
                is_active=True,
                is_deleted=False,
            )
            coupons_to_create.append(cpn)

        created_coupons = self.repo.bulk_create(coupons_to_create)
        return BulkGenerateCouponsResponse(
            success=True,
            message=f"Successfully generated {len(created_coupons)} unique voucher codes",
            generated_count=len(created_coupons),
            coupons=[CouponResponse.model_validate(c) for c in created_coupons],
        )

    def export_coupons(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        format: str = "excel",
    ) -> tuple[BytesIO, str, str]:
        coupons = self.repo.get_for_export(tenant_id, status=status)
        today = date.today()
        f_clean = format.strip().lower()

        if f_clean == "excel":
            headers = [
                "ID",
                "Coupon Code",
                "Description",
                "Discount Type",
                "Discount Value",
                "Min Order (Rs)",
                "Max Discount (Rs)",
                "Usage Limit",
                "Used Count",
                "Per Customer Limit",
                "Start Date",
                "End Date",
                "Status",
            ]
            rows = []
            for c in coupons:
                cpn_status = (
                    "Active"
                    if (c.is_active and c.start_date <= today <= c.end_date)
                    else ("Expired" if c.end_date < today else "Inactive")
                )
                rows.append([
                    c.id,
                    c.code,
                    c.description or "",
                    c.discount_type.title(),
                    float(c.discount_value),
                    float(c.minimum_order_amount),
                    float(c.maximum_discount) if c.maximum_discount else "",
                    c.usage_limit,
                    c.used_count,
                    c.usage_limit_per_customer or 1,
                    c.start_date.isoformat(),
                    c.end_date.isoformat(),
                    cpn_status,
                ])
            output = ExcelExportService().export_to_stream(
                sheet_title="Coupons",
                headers=headers,
                rows=rows,
            )
            return (
                output,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "coupons.xlsx",
            )

        elif f_clean == "csv":
            str_output = StringIO()
            writer = csv.writer(str_output)
            writer.writerow([
                "ID",
                "Coupon Code",
                "Description",
                "Discount Type",
                "Discount Value",
                "Min Order (Rs)",
                "Max Discount (Rs)",
                "Usage Limit",
                "Used Count",
                "Per Customer Limit",
                "Start Date",
                "End Date",
                "Status",
            ])
            for c in coupons:
                cpn_status = (
                    "Active"
                    if (c.is_active and c.start_date <= today <= c.end_date)
                    else ("Expired" if c.end_date < today else "Inactive")
                )
                writer.writerow([
                    c.id,
                    c.code,
                    c.description or "",
                    c.discount_type.title(),
                    float(c.discount_value),
                    float(c.minimum_order_amount),
                    float(c.maximum_discount) if c.maximum_discount else "",
                    c.usage_limit,
                    c.used_count,
                    c.usage_limit_per_customer or 1,
                    c.start_date.isoformat(),
                    c.end_date.isoformat(),
                    cpn_status,
                ])
            bytes_output = BytesIO(str_output.getvalue().encode("utf-8"))
            bytes_output.seek(0)
            return (
                bytes_output,
                "text/csv",
                "coupons.csv",
            )

        elif f_clean == "pdf":
            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=30,
            )
            elements = []
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                name="CouponTitle",
                parent=styles["Heading1"],
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#1F497D"),
                alignment=1,
            )
            elements.append(Paragraph("Coupons & Promotional Vouchers Report", title_style))
            elements.append(Spacer(1, 15))

            table_data = [[
                "Code",
                "Type",
                "Value",
                "Min Order",
                "Limit",
                "Used",
                "Start Date",
                "End Date",
                "Status",
            ]]
            for c in coupons:
                cpn_status = (
                    "Active"
                    if (c.is_active and c.start_date <= today <= c.end_date)
                    else ("Expired" if c.end_date < today else "Inactive")
                )
                val_str = f"{c.discount_value}%" if c.discount_type == "percentage" else f"Rs. {c.discount_value}"
                table_data.append([
                    c.code,
                    c.discount_type[:4].title(),
                    val_str,
                    f"Rs. {c.minimum_order_amount}",
                    str(c.usage_limit),
                    str(c.used_count),
                    c.start_date.isoformat(),
                    c.end_date.isoformat(),
                    cpn_status,
                ])

            t = Table(table_data, colWidths=[80, 50, 60, 65, 45, 45, 65, 65, 55])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F497D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ]))
            elements.append(t)
            doc.build(elements)
            buffer.seek(0)
            return (
                buffer,
                "application/pdf",
                "coupons.pdf",
            )

        raise AppException(
            f"Unsupported format: '{format}'. Supported formats are: excel, csv, pdf",
            status_code=422,
        )

    def get_applicable_coupons(
        self,
        tenant_id: int,
        order_amount: Decimal,
        customer_id: Optional[int] = None,
        customer_phone: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> ApplicableCouponsResponse:
        active_coupons = self.repo.get_active_coupons(tenant_id)
        applicable_list: list[ApplicableCouponItem] = []
        locked_list: list[ApplicableCouponItem] = []

        for c in active_coupons:
            # Check store
            if c.store_id is not None and store_id is not None and c.store_id != store_id:
                continue

            # Check usage limit
            if c.used_count >= c.usage_limit:
                continue

            # Check per-customer limit
            if c.usage_limit_per_customer is not None and (customer_id is not None or customer_phone is not None):
                cust_used = self.repo.count_customer_redemptions(tenant_id, c.id, customer_id, customer_phone)
                if cust_used >= c.usage_limit_per_customer:
                    continue

            resp_item = CouponResponse.model_validate(c)

            if order_amount >= c.minimum_order_amount:
                # Calculate discount
                if c.discount_type == "fixed":
                    disc = min(c.discount_value, order_amount)
                else:
                    disc = (order_amount * c.discount_value) / Decimal("100")
                    if c.maximum_discount is not None:
                        disc = min(disc, c.maximum_discount)
                    disc = min(disc, order_amount)
                fin = max(Decimal("0.00"), order_amount - disc)

                applicable_list.append(
                    ApplicableCouponItem(
                        coupon=resp_item,
                        is_applicable=True,
                        discount_amount=float(round(disc, 2)),
                        final_amount=float(round(fin, 2)),
                        message="Coupon is ready to apply!",
                        shortfall=None,
                    )
                )
            else:
                shortfall = float(round(c.minimum_order_amount - order_amount, 2))
                disc_label = f"{c.discount_value}%" if c.discount_type == "percentage" else f"Rs. {c.discount_value}"
                locked_list.append(
                    ApplicableCouponItem(
                        coupon=resp_item,
                        is_applicable=False,
                        discount_amount=0.0,
                        final_amount=float(round(order_amount, 2)),
                        message=f"Add Rs. {shortfall:.2f} more to unlock {disc_label} discount",
                        shortfall=shortfall,
                    )
                )

        return ApplicableCouponsResponse(
            order_amount=float(round(order_amount, 2)),
            applicable_coupons=applicable_list,
            locked_coupons=locked_list,
        )
