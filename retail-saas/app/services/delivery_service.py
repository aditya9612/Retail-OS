import csv
from datetime import datetime
from io import BytesIO, StringIO

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.delivery_zone import DeliveryZone
from app.models.delivery_partner import DeliveryPartner
from app.models.order import Order, OrderTracking
from app.repositories.delivery_repo import DeliveryRepository
from app.schemas.delivery import (
    DeliveryLabelData,
    DeliveryMethodCreate,
    DeliveryMethodUpdate,
    DeliveryPartnerConnect,
    DeliveryPartnerUpdate,
    DeliveryStatsData,
    DeliveryStatsResponse,
    DeliveryTrackingData,
    DeliveryZoneCreate,
    DeliveryZoneUpdate,
    ServiceabilityData,
    ServiceabilityUploadData,
)
from app.utils.barcode_generator import generate_barcode


DELIVERY_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"assigned", "out_for_delivery", "delivered", "cancelled"},
    "assigned": {"out_for_delivery", "delivered", "cancelled"},
    "out_for_delivery": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


class DeliveryService:

    def __init__(self, db):
        self.db = db
        self.repo = DeliveryRepository(db)

    def list_deliveries(self, tenant_id: int):
        return self.repo.list_deliveries(tenant_id)

    def get_delivery(self, tenant_id: int, delivery_id: int):
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.repo.get_by_id(delivery_id, tenant_id)

        if not delivery:
            raise NotFoundException("Delivery not found")

        return delivery

    def update_status(
        self,
        tenant_id: int,
        delivery_id: int,
        status: str,
    ):
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(
            tenant_id,
            delivery_id,
        )

        target_status = status.strip().lower()
        current_status = (
            delivery.status.strip().lower() if delivery.status else "pending"
        )

        if target_status == current_status:
            raise ConflictException(f"Delivery is already {current_status}")

        allowed_next = DELIVERY_STATUS_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_next:
            raise ConflictException(
                f"Cannot change delivery status from '{current_status}' to '{target_status}'"
            )

        delivery.status = target_status

        if target_status == "delivered":
            if not delivery.delivered_at:
                delivery.delivered_at = datetime.utcnow()

        if delivery.order:
            delivery.order.delivery_status = target_status

        tracking = OrderTracking(
            order_id=delivery.order_id,
            status=target_status,
            remarks=f"Order {target_status.replace('_', ' ')}",
        )
        self.db.add(tracking)

        return self.repo.update(delivery)

    def create_delivery(
        self,
        tenant_id: int,
        order_id: int,
        delivery_person: str | None = None,
        tracking_number: str | None = None,
    ) -> Delivery:
        if not isinstance(order_id, int) or order_id <= 0:
            raise AppException(
                "Order ID must be a positive integer",
                status_code=422,
            )

        order = (
            self.db.query(Order)
            .filter(Order.id == order_id, Order.tenant_id == tenant_id)
            .first()
        )
        if not order:
            raise NotFoundException("Order not found")

        if order.delivery is not None:
            raise ConflictException(f"Delivery already exists for order {order_id}")

        order_status = (order.status or "").strip().lower()
        if order_status in {"cancelled", "returned", "refunded"}:
            raise ConflictException(
                f"Cannot create delivery for order in '{order_status}' status"
            )

        status = "assigned" if delivery_person else "pending"
        delivery = Delivery(
            tenant_id=tenant_id,
            order_id=order_id,
            status=status,
            delivery_person=delivery_person,
            tracking_number=tracking_number,
        )
        self.repo.create(delivery)

        order.delivery_status = status
        tracking = OrderTracking(
            order_id=order_id,
            status=status,
            remarks=f"Delivery created with status '{status}'",
        )
        self.db.add(tracking)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def cancel_delivery(
        self,
        tenant_id: int,
        delivery_id: int,
        reason: str | None = None,
    ) -> Delivery:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        current_status = (delivery.status or "pending").strip().lower()

        if current_status == "cancelled":
            raise ConflictException("Delivery is already cancelled")

        if current_status == "delivered":
            raise ConflictException("Cannot cancel a delivered shipment")

        allowed_next = DELIVERY_STATUS_TRANSITIONS.get(current_status, set())
        if "cancelled" not in allowed_next:
            raise ConflictException(
                f"Cannot cancel delivery in '{current_status}' status"
            )

        delivery.status = "cancelled"
        if delivery.order:
            delivery.order.delivery_status = "cancelled"

        remarks = f"Delivery cancelled: {reason}" if reason else "Delivery cancelled"
        tracking = OrderTracking(
            order_id=delivery.order_id,
            status="cancelled",
            remarks=remarks,
        )
        self.db.add(tracking)

        return self.repo.update(delivery)

    def assign_partner(
        self,
        tenant_id: int,
        delivery_id: int,
        delivery_person: str,
        tracking_number: str | None = None,
    ) -> Delivery:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        current_status = (delivery.status or "pending").strip().lower()

        if current_status in {"delivered", "cancelled"}:
            raise ConflictException(
                f"Cannot assign delivery partner to delivery in '{current_status}' status"
            )

        delivery.delivery_person = delivery_person
        if tracking_number:
            delivery.tracking_number = tracking_number

        if current_status == "pending":
            delivery.status = "assigned"
            if delivery.order:
                delivery.order.delivery_status = "assigned"

        remarks = f"Delivery assigned to {delivery_person}"
        if tracking_number:
            remarks += f" (Tracking: {tracking_number})"
        tracking = OrderTracking(
            order_id=delivery.order_id,
            status=delivery.status,
            remarks=remarks,
        )
        self.db.add(tracking)

        return self.repo.update(delivery)

    def update_address(
        self,
        tenant_id: int,
        delivery_id: int,
        delivery_address: str,
    ) -> Delivery:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        current_status = (delivery.status or "pending").strip().lower()

        if current_status in {"delivered", "cancelled"}:
            raise ConflictException(
                f"Cannot update delivery address for delivery in '{current_status}' status"
            )

        order = delivery.order
        if not order:
            order = (
                self.db.query(Order)
                .filter(Order.id == delivery.order_id, Order.tenant_id == tenant_id)
                .first()
            )
        if not order:
            raise NotFoundException("Associated order not found")

        order.delivery_address = delivery_address

        tracking = OrderTracking(
            order_id=delivery.order_id,
            status=delivery.status,
            remarks=f"Delivery address updated: {delivery_address}",
        )
        self.db.add(tracking)

        return self.repo.update(delivery)

    def get_label(
        self,
        tenant_id: int,
        delivery_id: int,
    ) -> DeliveryLabelData:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        order = delivery.order
        if not order:
            order = (
                self.db.query(Order)
                .filter(Order.id == delivery.order_id, Order.tenant_id == tenant_id)
                .first()
            )
        if not order:
            raise NotFoundException("Associated order not found")

        if order.customer:
            recipient_name = order.customer.name
            recipient_phone = order.customer.phone
        else:
            recipient_name = "Retail Customer"
            recipient_phone = None

        raw_barcode = generate_barcode(f"{order.order_number}-{delivery.id}")

        return DeliveryLabelData(
            delivery_id=delivery.id,
            order_id=order.id,
            order_number=order.order_number,
            tracking_number=delivery.tracking_number,
            delivery_person=delivery.delivery_person,
            status=delivery.status,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            delivery_address=order.delivery_address,
            barcode=raw_barcode,
            created_at=delivery.created_at,
        )

    def get_tracking(
        self,
        tenant_id: int,
        delivery_id: int,
    ) -> DeliveryTrackingData:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        latest_tracking = self.repo.get_latest_tracking(delivery.order_id)

        if latest_tracking:
            return DeliveryTrackingData(
                delivery_id=delivery.id,
                order_id=delivery.order_id,
                status=delivery.status,
                tracking_number=delivery.tracking_number,
                delivery_person=delivery.delivery_person,
                tracking_id=latest_tracking.id,
                remarks=latest_tracking.remarks,
                updated_at=latest_tracking.created_at,
            )

        return DeliveryTrackingData(
            delivery_id=delivery.id,
            order_id=delivery.order_id,
            status=delivery.status,
            tracking_number=delivery.tracking_number,
            delivery_person=delivery.delivery_person,
            tracking_id=None,
            remarks=None,
            updated_at=delivery.updated_at or delivery.created_at,
        )

    def get_history(
        self,
        tenant_id: int,
        delivery_id: int,
    ) -> list[OrderTracking]:
        if not isinstance(delivery_id, int) or delivery_id <= 0:
            raise AppException(
                "Delivery ID must be a positive integer",
                status_code=422,
            )

        delivery = self.get_delivery(tenant_id, delivery_id)
        return self.repo.get_tracking_history(delivery.order_id)

    def get_stats(self, tenant_id: int) -> DeliveryStatsResponse:
        stats_dict = self.repo.get_stats(tenant_id)
        data = DeliveryStatsData(**stats_dict)
        return DeliveryStatsResponse(
            success=True,
            message="Delivery statistics retrieved successfully",
            data=data,
        )

    def export_deliveries(
        self,
        tenant_id: int,
        status: str | None = None,
        format: str = "excel",
    ) -> tuple[BytesIO, str, str]:
        deliveries = self.repo.get_for_export(tenant_id, status=status)

        if format == "excel":
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Deliveries"
            worksheet.append([
                "ID",
                "Order Number",
                "Status",
                "Delivery Person",
                "Tracking Number",
                "Delivery Address",
                "Delivered At",
                "Created At",
            ])
            for d in deliveries:
                worksheet.append([
                    d.id,
                    d.order.order_number if d.order else "",
                    d.status,
                    d.delivery_person or "",
                    d.tracking_number or "",
                    (d.order.delivery_address or "") if d.order else "",
                    d.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if d.delivered_at else "",
                    d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else "",
                ])
            output = BytesIO()
            workbook.save(output)
            output.seek(0)
            return (
                output,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "deliveries.xlsx",
            )

        elif format == "csv":
            str_output = StringIO()
            writer = csv.writer(str_output)
            writer.writerow([
                "ID",
                "Order Number",
                "Status",
                "Delivery Person",
                "Tracking Number",
                "Delivery Address",
                "Delivered At",
                "Created At",
            ])
            for d in deliveries:
                writer.writerow([
                    d.id,
                    d.order.order_number if d.order else "",
                    d.status,
                    d.delivery_person or "",
                    d.tracking_number or "",
                    (d.order.delivery_address or "") if d.order else "",
                    d.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if d.delivered_at else "",
                    d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else "",
                ])
            bytes_output = BytesIO(str_output.getvalue().encode("utf-8"))
            bytes_output.seek(0)
            return (
                bytes_output,
                "text/csv",
                "deliveries.csv",
            )

        raise AppException(f"Unsupported format: '{format}'", status_code=422)

    def list_methods(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryMethod]:
        return self.repo.list_methods(tenant_id, is_active=is_active)

    def get_method(
        self,
        tenant_id: int,
        method_id: int,
    ) -> DeliveryMethod:
        if not isinstance(method_id, int) or method_id <= 0:
            raise AppException(
                "Delivery method ID must be a positive integer",
                status_code=422,
            )

        method = self.repo.get_method_by_id(method_id, tenant_id)
        if not method:
            raise NotFoundException("Delivery method not found")

        return method

    def create_method(
        self,
        tenant_id: int,
        data: DeliveryMethodCreate,
    ) -> DeliveryMethod:
        existing = self.repo.get_method_by_code(data.code, tenant_id)
        if existing:
            raise ConflictException(
                f"Delivery method with code '{data.code}' already exists"
            )

        method = DeliveryMethod(
            tenant_id=tenant_id,
            name=data.name,
            code=data.code,
            description=data.description,
            cost=data.cost,
            estimated_days=data.estimated_days,
            is_active=data.is_active,
        )
        return self.repo.create_method(method)

    def update_method(
        self,
        tenant_id: int,
        method_id: int,
        data: DeliveryMethodUpdate,
    ) -> DeliveryMethod:
        method = self.get_method(tenant_id, method_id)

        if data.code is not None and data.code != method.code:
            existing = self.repo.get_method_by_code(data.code, tenant_id)
            if existing and existing.id != method.id:
                raise ConflictException(
                    f"Delivery method with code '{data.code}' already exists"
                )
            method.code = data.code

        if data.name is not None:
            method.name = data.name

        if data.description is not None:
            method.description = data.description

        if data.cost is not None:
            method.cost = data.cost

        if data.estimated_days is not None:
            method.estimated_days = data.estimated_days

        if data.is_active is not None:
            method.is_active = data.is_active

        return self.repo.update_method(method)

    def toggle_method(
        self,
        tenant_id: int,
        method_id: int,
    ) -> DeliveryMethod:
        method = self.get_method(tenant_id, method_id)
        method.is_active = not method.is_active
        return self.repo.update_method(method)

    def delete_method(
        self,
        tenant_id: int,
        method_id: int,
    ) -> None:
        method = self.get_method(tenant_id, method_id)
        self.repo.delete_method(method)

    def list_zones(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryZone]:
        return self.repo.list_zones(tenant_id, is_active=is_active)

    def get_zone(
        self,
        tenant_id: int,
        zone_id: int,
    ) -> DeliveryZone:
        if not isinstance(zone_id, int) or zone_id <= 0:
            raise AppException(
                "Delivery zone ID must be a positive integer",
                status_code=422,
            )

        zone = self.repo.get_zone_by_id(zone_id, tenant_id)
        if not zone:
            raise NotFoundException("Delivery zone not found")

        return zone

    def create_zone(
        self,
        tenant_id: int,
        data: DeliveryZoneCreate,
    ) -> DeliveryZone:
        existing = self.repo.get_zone_by_code(data.code, tenant_id)
        if existing:
            raise ConflictException(
                f"Delivery zone with code '{data.code}' already exists"
            )

        zone = DeliveryZone(
            tenant_id=tenant_id,
            name=data.name,
            code=data.code,
            description=data.description,
            city=data.city,
            state=data.state,
            pincodes=data.pincodes,
            is_active=data.is_active,
        )
        return self.repo.create_zone(zone)

    def update_zone(
        self,
        tenant_id: int,
        zone_id: int,
        data: DeliveryZoneUpdate,
    ) -> DeliveryZone:
        zone = self.get_zone(tenant_id, zone_id)

        if data.code is not None and data.code != zone.code:
            existing = self.repo.get_zone_by_code(data.code, tenant_id)
            if existing and existing.id != zone.id:
                raise ConflictException(
                    f"Delivery zone with code '{data.code}' already exists"
                )
            zone.code = data.code

        if data.name is not None:
            zone.name = data.name

        if data.description is not None:
            zone.description = data.description

        if data.city is not None:
            zone.city = data.city

        if data.state is not None:
            zone.state = data.state

        if data.pincodes is not None:
            zone.pincodes = data.pincodes

        if data.is_active is not None:
            zone.is_active = data.is_active

        return self.repo.update_zone(zone)

    def delete_zone(
        self,
        tenant_id: int,
        zone_id: int,
    ) -> None:
        zone = self.get_zone(tenant_id, zone_id)
        self.repo.delete_zone(zone)

    def list_partners(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryPartner]:
        return self.repo.list_partners(tenant_id, is_active=is_active)

    def get_partner(
        self,
        tenant_id: int,
        partner_id: int,
    ) -> DeliveryPartner:
        if not isinstance(partner_id, int) or partner_id <= 0:
            raise AppException(
                "Delivery partner ID must be a positive integer",
                status_code=422,
            )

        partner = self.repo.get_partner_by_id(partner_id, tenant_id)
        if not partner:
            raise NotFoundException("Delivery partner not found")

        return partner

    def create_partner(
        self,
        tenant_id: int,
        data: DeliveryPartnerConnect,
    ) -> DeliveryPartner:
        existing = self.repo.get_partner_by_code(data.code, tenant_id)
        if existing:
            raise ConflictException(
                f"Delivery partner with code '{data.code}' already exists"
            )

        partner = DeliveryPartner(
            tenant_id=tenant_id,
            name=data.name,
            code=data.code,
            description=data.description,
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            api_key=data.api_key,
            api_secret=data.api_secret,
            tracking_url_template=data.tracking_url_template,
            is_active=data.is_active,
        )
        return self.repo.create_partner(partner)

    def update_partner(
        self,
        tenant_id: int,
        partner_id: int,
        data: DeliveryPartnerUpdate,
    ) -> DeliveryPartner:
        partner = self.get_partner(tenant_id, partner_id)

        if data.code is not None and data.code != partner.code:
            existing = self.repo.get_partner_by_code(data.code, tenant_id)
            if existing and existing.id != partner.id:
                raise ConflictException(
                    f"Delivery partner with code '{data.code}' already exists"
                )
            partner.code = data.code

        if data.name is not None:
            partner.name = data.name

        if data.description is not None:
            partner.description = data.description

        if data.contact_email is not None:
            partner.contact_email = data.contact_email

        if data.contact_phone is not None:
            partner.contact_phone = data.contact_phone

        if data.api_key is not None:
            partner.api_key = data.api_key

        if data.api_secret is not None:
            partner.api_secret = data.api_secret

        if data.tracking_url_template is not None:
            partner.tracking_url_template = data.tracking_url_template

        if data.is_active is not None:
            partner.is_active = data.is_active

        return self.repo.update_partner(partner)

    def delete_partner(
        self,
        tenant_id: int,
        partner_id: int,
    ) -> None:
        partner = self.get_partner(tenant_id, partner_id)
        self.repo.delete_partner(partner)

    def check_serviceability(
        self,
        tenant_id: int,
        pincode: str,
    ) -> ServiceabilityData:
        if not isinstance(pincode, str):
            raise AppException("Pincode must be a string", status_code=422)
        p = pincode.strip()
        if not p.isdigit() or len(p) != 6 or not (100000 <= int(p) <= 999999):
            raise AppException(
                f"Invalid pincode: '{pincode}'. Pincode must contain exactly 6 numeric digits (100000-999999)",
                status_code=422,
            )

        active_zone = self.repo.find_active_zone_by_pincode(tenant_id, p)
        if active_zone:
            return ServiceabilityData(
                pincode=p,
                is_serviceable=True,
                zone_id=active_zone.id,
                zone_name=active_zone.name,
                zone_code=active_zone.code,
                city=active_zone.city,
                state=active_zone.state,
            )

        return ServiceabilityData(
            pincode=p,
            is_serviceable=False,
            zone_id=None,
            zone_name=None,
            zone_code=None,
            city=None,
            state=None,
        )

    def upload_serviceability(
        self,
        tenant_id: int,
        filename: str,
        contents: bytes,
    ) -> ServiceabilityUploadData:
        filename_clean = (filename or "").strip().lower()
        if not (filename_clean.endswith(".csv") or filename_clean.endswith(".xlsx")):
            raise AppException(
                "Unsupported file format. Only CSV (.csv) and Excel (.xlsx) files are supported",
                status_code=422,
            )

        if not contents or len(contents) == 0:
            raise AppException("Uploaded file is empty", status_code=422)

        raw_rows: list[dict[str, Any]] = []

        if filename_clean.endswith(".csv"):
            try:
                text = contents.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = contents.decode("latin-1")
                except Exception:
                    raise AppException("Malformed or unreadable CSV file", status_code=422)

            reader = csv.DictReader(StringIO(text))
            if not reader.fieldnames:
                raise AppException("Uploaded CSV file has no header row", status_code=422)

            field_map = {name.strip().lower(): name for name in reader.fieldnames if name}
            if "pincode" not in field_map or "zone_code" not in field_map:
                raise AppException(
                    "CSV file is missing required columns. Both 'zone_code' and 'pincode' columns are required",
                    status_code=422,
                )

            for row in reader:
                if not any(v.strip() for v in row.values() if isinstance(v, str)):
                    continue
                raw_rows.append({
                    "zone_code": row.get(field_map["zone_code"]),
                    "pincode": row.get(field_map["pincode"]),
                })
        else:
            try:
                wb = load_workbook(filename=BytesIO(contents), data_only=True)
                ws = wb.active
            except Exception:
                raise AppException("Malformed or corrupted Excel file", status_code=422)

            rows_iter = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter)
            except StopIteration:
                raise AppException("Uploaded Excel file is empty", status_code=422)

            if not header_row:
                raise AppException("Uploaded Excel file has no header row", status_code=422)

            col_map: dict[str, int] = {}
            for idx, col_name in enumerate(header_row):
                if col_name is not None:
                    col_map[str(col_name).strip().lower()] = idx

            if "pincode" not in col_map or "zone_code" not in col_map:
                raise AppException(
                    "Excel file is missing required columns. Both 'zone_code' and 'pincode' columns are required",
                    status_code=422,
                )

            for row in rows_iter:
                if not any(row):
                    continue
                raw_rows.append({
                    "zone_code": row[col_map["zone_code"]],
                    "pincode": row[col_map["pincode"]],
                })

        if not raw_rows:
            raise AppException("Uploaded file contains no data rows", status_code=422)

        all_zones = self.repo.list_zones(tenant_id)
        zones_by_code: dict[str, DeliveryZone] = {
            z.code.strip().upper(): z for z in all_zones
        }

        db_pincode_to_zone: dict[str, str] = {}
        for z in all_zones:
            z_code = z.code.strip().upper()
            for p in (z.pincodes or []):
                db_pincode_to_zone[p] = z_code

        file_pincode_to_zone: dict[str, str] = {}
        parsed_items: list[tuple[str, str]] = []

        for row_idx, r in enumerate(raw_rows, start=2):
            raw_zone_code = r.get("zone_code")
            if raw_zone_code is None:
                raise AppException(f"Missing zone_code at row {row_idx}", status_code=422)
            zone_code = str(raw_zone_code).strip().upper()
            if not zone_code:
                raise AppException(f"Empty zone_code at row {row_idx}", status_code=422)

            if zone_code not in zones_by_code:
                raise AppException(
                    f"Delivery zone with code '{zone_code}' does not exist for this tenant (row {row_idx})",
                    status_code=422,
                )

            raw_p = r.get("pincode")
            if raw_p is None:
                raise AppException(f"Missing pincode at row {row_idx}", status_code=422)

            if isinstance(raw_p, float) or isinstance(raw_p, bool):
                raise AppException(
                    f"Invalid pincode '{raw_p}' at row {row_idx}. Pincode must be exactly 6 numeric digits (floats/booleans not allowed)",
                    status_code=422,
                )

            p_str = str(raw_p).strip()
            if not p_str.isdigit() or len(p_str) != 6 or not (100000 <= int(p_str) <= 999999):
                raise AppException(
                    f"Invalid pincode '{raw_p}' at row {row_idx}. Pincode must contain exactly 6 numeric digits (100000-999999)",
                    status_code=422,
                )

            if p_str in file_pincode_to_zone and file_pincode_to_zone[p_str] != zone_code:
                raise ConflictException(
                    f"Pincode '{p_str}' is assigned to multiple zones ('{file_pincode_to_zone[p_str]}' and '{zone_code}') in upload file (row {row_idx})"
                )
            file_pincode_to_zone[p_str] = zone_code

            if p_str in db_pincode_to_zone and db_pincode_to_zone[p_str] != zone_code:
                raise ConflictException(
                    f"Pincode '{p_str}' is already assigned to delivery zone '{db_pincode_to_zone[p_str]}'"
                )

            parsed_items.append((zone_code, p_str))

        zone_pincodes_map: dict[str, list[str]] = {
            z_code: list(z.pincodes or []) for z_code, z in zones_by_code.items()
        }

        total_rows_processed = len(parsed_items)
        pincodes_added = 0
        pincodes_existing = 0
        zones_affected: set[str] = set()

        for zone_code, p_str in parsed_items:
            current_list = zone_pincodes_map[zone_code]
            if p_str in current_list:
                pincodes_existing += 1
            else:
                current_list.append(p_str)
                pincodes_added += 1
                zones_affected.add(zone_code)

        try:
            for zone_code in zones_affected:
                zone = zones_by_code[zone_code]
                zone.pincodes = zone_pincodes_map[zone_code]
                flag_modified(zone, "pincodes")
            self.db.commit()
            for zone_code in zones_affected:
                self.db.refresh(zones_by_code[zone_code])
        except Exception as exc:
            self.db.rollback()
            raise exc

        return ServiceabilityUploadData(
            total_rows_processed=total_rows_processed,
            pincodes_added=pincodes_added,
            pincodes_existing=pincodes_existing,
            zones_updated=sorted(list(zones_affected)),
        )

