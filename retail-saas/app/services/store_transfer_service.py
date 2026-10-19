from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import secrets
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.store_transfer_item import StoreTransferItem
from app.repositories.store_transfer_repo import StoreTransferRepository
from app.schemas.store_transfer import StoreTransferDiscrepancyRequest


class StoreTransferService:

    @staticmethod
    def create_transfer(
        db: Session,
        source_store_id: int,
        destination_store_id: int,
        items: list,
        tenant_id: int
    ):
        if source_store_id == destination_store_id:
            raise ValueError(
                "Source and destination stores cannot be the same"
            )

        source_store = db.query(Store).filter(
            Store.id == source_store_id
        ).first()

        if not source_store:
            raise ValueError(
                "Source store not found"
            )

        if source_store.tenant_id != tenant_id:
            raise ValueError(
                "Source store does not belong to the user's tenant"
            )

        if not source_store.is_active:
            raise ValueError(
                "Source store is inactive or has been deleted"
            )

        destination_store = db.query(Store).filter(
            Store.id == destination_store_id
        ).first()

        if not destination_store:
            raise ValueError(
                "Destination store not found"
            )

        if destination_store.tenant_id != tenant_id:
            raise ValueError(
                "Destination store does not belong to the user's tenant"
            )

        if not destination_store.is_active:
            raise ValueError(
                "Destination store is inactive or has been deleted"
            )

        if not items or len(items) == 0:
            raise ValueError("Transfer must contain at least one item")

        seen_p_ids = set()
        for item in items:
            p_id = item["product_id"] if isinstance(item, dict) else item.product_id
            qty = item["quantity"] if isinstance(item, dict) else getattr(item, "quantity", 0)
            if p_id in seen_p_ids:
                raise ValueError(
                    f"Duplicate product ID {p_id} in transfer items. Please consolidate quantities into a single item line."
                )
            seen_p_ids.add(p_id)

            product = db.query(Product).filter(Product.id == p_id).first()
            if not product:
                raise ValueError(f"Product {p_id} not found")
            if product.tenant_id != tenant_id:
                raise ValueError(f"Product {p_id} does not belong to the user's tenant")
            if not product.is_active:
                raise ValueError(f"Product {p_id} is inactive or deleted")
            if qty <= 0:
                raise ValueError(f"Quantity must be greater than 0 for product {p_id}")

        # Anti-double-click / duplicate transfer check (15 seconds window)
        recent_cutoff = datetime.utcnow() - timedelta(seconds=15)
        recent_pending = (
            db.query(StoreTransfer)
            .filter(
                StoreTransfer.source_store_id == source_store_id,
                StoreTransfer.destination_store_id == destination_store_id,
                StoreTransfer.status == "Pending",
                StoreTransfer.created_at >= recent_cutoff,
            )
            .first()
        )
        if recent_pending and len(recent_pending.items) == len(items):
            pending_map = {it.product_id: it.quantity for it in recent_pending.items}
            curr_map = {
                (it["product_id"] if isinstance(it, dict) else it.product_id): (
                    it["quantity"] if isinstance(it, dict) else it.quantity
                )
                for it in items
            }
            if pending_map == curr_map:
                raise ValueError(
                    f"Duplicate transfer submission detected. Identical pending transfer '{recent_pending.transfer_number}' was just created."
                )

        seq = (
            db.query(StoreTransfer)
            .join(Store, Store.id == StoreTransfer.source_store_id)
            .filter(Store.tenant_id == tenant_id)
            .count()
            + 1
        )
        rand_suffix = secrets.token_hex(2).upper()
        transfer_number = (
            f"TRF-{source_store_id}-"
            f"{destination_store_id}-"
            f"{seq:04d}-{rand_suffix}"
        )

        transfer = StoreTransfer(
            transfer_number=transfer_number,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status="Pending",
            created_at=datetime.utcnow(),
        )

        for item in items:
            p_id = item["product_id"] if isinstance(item, dict) else item.product_id
            qty = item["quantity"] if isinstance(item, dict) else item.quantity
            transfer.items.append(
                StoreTransferItem(
                    product_id=p_id,
                    quantity=qty
                )
            )

        StoreTransferRepository.create(db, transfer)
        return StoreTransferRepository.get_by_id(db, transfer.id, tenant_id=tenant_id)

    @staticmethod
    def get_transfer(
        db: Session,
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferRepository.get_by_id(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if not transfer:
            raise ValueError("Transfer not found")

        return transfer

    @staticmethod
    def get_transfers(
        db: Session,
        tenant_id: int,
        source_store_id: int | None = None,
        destination_store_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
    ):
        return StoreTransferRepository.get_all(
            db,
            tenant_id=tenant_id,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status=status,
            skip=skip,
            limit=limit,
            search=search,
        )

    @staticmethod
    def approve_transfer(
        db: Session,
        transfer_id: int,
        approved_by: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status not in ["Pending", "Draft"]:
            raise ValueError(
                "Only pending transfers can be approved"
            )

        source_store = db.query(Store).filter(Store.id == transfer.source_store_id).first()
        if not source_store or not source_store.is_active:
            raise ValueError("Source store is inactive or has been deleted")

        destination_store = db.query(Store).filter(Store.id == transfer.destination_store_id).first()
        if not destination_store or not destination_store.is_active:
            raise ValueError("Destination store is inactive or has been deleted")

        transfer.status = "Approved"
        transfer.approved_by = approved_by

        StoreTransferRepository.update(
            db,
            transfer
        )
        return StoreTransferRepository.get_by_id(db, transfer.id, tenant_id=tenant_id)

    @staticmethod
    def reject_transfer(
        db: Session,
        transfer_id: int,
        tenant_id: int,
        rejection_reason: str | None = None,
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status not in ["Pending", "Draft"]:
            raise ValueError(
                "Only pending transfers can be rejected"
            )

        transfer.status = "Rejected"

        StoreTransferRepository.update(
            db,
            transfer
        )
        return StoreTransferRepository.get_by_id(db, transfer.id, tenant_id=tenant_id)

    @staticmethod
    def dispatch_transfer(
        db: Session,
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status != "Approved":
            raise ValueError(
                "Only approved transfers can be dispatched"
            )

        source_store = db.query(Store).filter(Store.id == transfer.source_store_id).first()
        if not source_store or not source_store.is_active:
            raise ValueError("Source store is inactive or has been deleted")

        destination_store = db.query(Store).filter(Store.id == transfer.destination_store_id).first()
        if not destination_store or not destination_store.is_active:
            raise ValueError("Destination store is inactive or has been deleted")

        for item in transfer.items:
            qty_dec = Decimal(str(item.quantity))
            src_inv = (
                db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == transfer.source_store_id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )
            prev_stock = Decimal("0.0000")
            new_stock = Decimal("0.0000")

            if src_inv:
                prev_stock = src_inv.quantity
                src_inv.quantity -= qty_dec
                new_stock = src_inv.quantity

            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=item.product_id,
                store_id=transfer.source_store_id,
                movement_type="transfer_out",
                quantity=qty_dec,
                previous_stock=prev_stock,
                new_stock=new_stock,
                reference_id=transfer.id,
                reference_type="store_transfer",
                notes=f"Dispatched to store {transfer.destination_store_id}",
            )
            db.add(movement)

        transfer.status = "Dispatched"

        StoreTransferRepository.update(
            db,
            transfer
        )
        return StoreTransferRepository.get_by_id(db, transfer.id, tenant_id=tenant_id)

    @staticmethod
    def receive_transfer(
        db: Session,
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status != "Dispatched":
            raise ValueError(
                "Only dispatched transfers can be received"
            )

        destination_store = db.query(Store).filter(Store.id == transfer.destination_store_id).first()
        if not destination_store or not destination_store.is_active:
            raise ValueError("Destination store is inactive or has been deleted")

        for item in transfer.items:
            qty_dec = Decimal(str(item.quantity))
            dst_inv = (
                db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == transfer.destination_store_id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )

            if dst_inv:
                prev_stock = dst_inv.quantity
                dst_inv.quantity += qty_dec
                new_stock = dst_inv.quantity
            else:
                prev_stock = Decimal("0.0000")
                new_stock = qty_dec
                dst_inv = Inventory(
                    tenant_id=tenant_id,
                    store_id=transfer.destination_store_id,
                    product_id=item.product_id,
                    quantity=new_stock,
                )
                db.add(dst_inv)

            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=item.product_id,
                store_id=transfer.destination_store_id,
                movement_type="transfer_in",
                quantity=qty_dec,
                previous_stock=prev_stock,
                new_stock=new_stock,
                reference_id=transfer.id,
                reference_type="store_transfer",
                notes=f"Received from store {transfer.source_store_id}",
            )
            db.add(movement)

        transfer.status = "Received"

        StoreTransferRepository.update(
            db,
            transfer
        )
        return StoreTransferRepository.get_by_id(db, transfer.id, tenant_id=tenant_id)

    @staticmethod
    def receive_with_discrepancy(
        db: Session,
        transfer_id: int,
        discrepancy_data: StoreTransferDiscrepancyRequest,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status != "Dispatched":
            raise ValueError(
                "Only dispatched transfers can be received with discrepancy"
            )

        destination_store = db.query(Store).filter(Store.id == transfer.destination_store_id).first()
        if not destination_store or not destination_store.is_active:
            raise ValueError("Destination store is inactive or has been deleted")

        transfer_items_map = {item.product_id: item for item in transfer.items}
        req_items_map = {item.product_id: item for item in discrepancy_data.items}

        for pid, d_item in req_items_map.items():
            if pid not in transfer_items_map:
                raise ValueError(f"Product {pid} was not part of this transfer")
            
            orig_qty = int(transfer_items_map[pid].quantity)
            total_accounted = d_item.received_quantity + d_item.damaged_quantity + d_item.missing_quantity
            if total_accounted != orig_qty:
                raise ValueError(
                    f"Product {pid}: sum of received ({d_item.received_quantity}), "
                    f"damaged ({d_item.damaged_quantity}), and missing ({d_item.missing_quantity}) "
                    f"must equal dispatched quantity ({orig_qty})"
                )

        for pid in transfer_items_map:
            if pid not in req_items_map:
                raise ValueError(f"Product {pid} is missing from the discrepancy receipt details")

        items_response_data = []
        total_dispatched = 0
        total_received = 0
        total_damaged = 0
        total_missing = 0

        for item in transfer.items:
            d_item = req_items_map[item.product_id]
            dispatched_qty = int(item.quantity)
            rcv_qty = d_item.received_quantity
            dmg_qty = d_item.damaged_quantity
            miss_qty = d_item.missing_quantity

            total_dispatched += dispatched_qty
            total_received += rcv_qty
            total_damaged += dmg_qty
            total_missing += miss_qty

            if rcv_qty > 0:
                dst_inv = (
                    db.query(Inventory)
                    .filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == transfer.destination_store_id,
                        Inventory.product_id == item.product_id,
                    )
                    .first()
                )
                rcv_dec = Decimal(str(rcv_qty))
                if dst_inv:
                    prev_stock = dst_inv.quantity
                    dst_inv.quantity += rcv_dec
                    new_stock = dst_inv.quantity
                else:
                    prev_stock = Decimal("0.0000")
                    new_stock = rcv_dec
                    dst_inv = Inventory(
                        tenant_id=tenant_id,
                        store_id=transfer.destination_store_id,
                        product_id=item.product_id,
                        quantity=new_stock,
                    )
                    db.add(dst_inv)

                movement_in = StockMovement(
                    tenant_id=tenant_id,
                    product_id=item.product_id,
                    store_id=transfer.destination_store_id,
                    movement_type="transfer_in",
                    quantity=rcv_dec,
                    previous_stock=prev_stock,
                    new_stock=new_stock,
                    reference_id=transfer.id,
                    reference_type="store_transfer",
                    notes=f"Received from store {transfer.source_store_id}",
                )
                db.add(movement_in)

            if dmg_qty > 0:
                dmg_dec = Decimal(str(dmg_qty))
                movement_dmg = StockMovement(
                    tenant_id=tenant_id,
                    product_id=item.product_id,
                    store_id=transfer.destination_store_id,
                    movement_type="damaged_in_transit",
                    quantity=dmg_dec,
                    previous_stock=Decimal("0.0000"),
                    new_stock=Decimal("0.0000"),
                    reference_id=transfer.id,
                    reference_type="store_transfer",
                    notes=d_item.remarks or "Goods received damaged during inter-store transit",
                )
                db.add(movement_dmg)

            if miss_qty > 0:
                miss_dec = Decimal(str(miss_qty))
                movement_miss = StockMovement(
                    tenant_id=tenant_id,
                    product_id=item.product_id,
                    store_id=transfer.destination_store_id,
                    movement_type="missing_in_transit",
                    quantity=miss_dec,
                    previous_stock=Decimal("0.0000"),
                    new_stock=Decimal("0.0000"),
                    reference_id=transfer.id,
                    reference_type="store_transfer",
                    notes=d_item.remarks or "Goods missing / short received during inter-store transit",
                )
                db.add(movement_miss)

            items_response_data.append({
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "sku": item.product.sku if item.product else None,
                "dispatched_quantity": dispatched_qty,
                "received_quantity": rcv_qty,
                "damaged_quantity": dmg_qty,
                "missing_quantity": miss_qty,
                "remarks": d_item.remarks,
            })

        transfer.status = "Received"
        StoreTransferRepository.update(db, transfer)

        has_disc = (total_damaged > 0) or (total_missing > 0)
        return {
            "transfer_id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "source_store_id": transfer.source_store_id,
            "source_store_name": transfer.source_store.name if transfer.source_store else None,
            "destination_store_id": transfer.destination_store_id,
            "destination_store_name": transfer.destination_store.name if transfer.destination_store else None,
            "status": transfer.status,
            "has_discrepancy": has_disc,
            "total_dispatched_quantity": total_dispatched,
            "total_received_quantity": total_received,
            "total_damaged_quantity": total_damaged,
            "total_missing_quantity": total_missing,
            "discrepancy_notes": discrepancy_data.notes,
            "items": items_response_data,
            "message": "Transfer received with discrepancy logged successfully" if has_disc else "Transfer received successfully without discrepancy",
        }

    @staticmethod
    def get_summary(
        db: Session,
        tenant_id: int,
        store_id: int | None = None,
    ):
        query = (
            db.query(StoreTransfer)
            .options(
                joinedload(StoreTransfer.items).joinedload(StoreTransferItem.product),
                joinedload(StoreTransfer.source_store),
                joinedload(StoreTransfer.destination_store),
                joinedload(StoreTransfer.approver),
            )
            .join(Store, StoreTransfer.source_store_id == Store.id)
            .filter(Store.tenant_id == tenant_id)
        )

        if store_id is not None:
            query = query.filter(
                (StoreTransfer.source_store_id == store_id) | (StoreTransfer.destination_store_id == store_id)
            )

        all_transfers = query.order_by(StoreTransfer.id.desc()).all()

        total_transfers = len(all_transfers)
        pending_count = 0
        approved_count = 0
        dispatched_count = 0
        received_count = 0
        rejected_count = 0
        total_units = 0

        source_counts = Counter()
        dest_counts = Counter()
        store_names = {}
        prod_quantities = defaultdict(int)
        prod_meta = {}

        for t in all_transfers:
            s_val = (t.status or "").lower()
            if s_val == "pending":
                pending_count += 1
            elif s_val == "approved":
                approved_count += 1
            elif s_val == "dispatched":
                dispatched_count += 1
            elif s_val == "received":
                received_count += 1
            elif s_val == "rejected":
                rejected_count += 1

            if t.source_store_id:
                source_counts[t.source_store_id] += 1
                if t.source_store and t.source_store_id not in store_names:
                    store_names[t.source_store_id] = t.source_store.name

            if t.destination_store_id:
                dest_counts[t.destination_store_id] += 1
                if t.destination_store and t.destination_store_id not in store_names:
                    store_names[t.destination_store_id] = t.destination_store.name

            for item in t.items:
                qty = int(item.quantity)
                total_units += qty
                prod_quantities[item.product_id] += qty
                if item.product and item.product_id not in prod_meta:
                    prod_meta[item.product_id] = (item.product.name, item.product.sku)

        top_sources = [
            {
                "store_id": sid,
                "store_name": store_names.get(sid, f"Store {sid}"),
                "transfer_count": cnt,
            }
            for sid, cnt in source_counts.most_common(5)
        ]

        top_dests = [
            {
                "store_id": sid,
                "store_name": store_names.get(sid, f"Store {sid}"),
                "transfer_count": cnt,
            }
            for sid, cnt in dest_counts.most_common(5)
        ]

        sorted_prods = sorted(prod_quantities.items(), key=lambda x: x[1], reverse=True)[:5]
        top_products = []
        for pid, qty in sorted_prods:
            p_name, p_sku = prod_meta.get(pid, (f"Product {pid}", None))
            top_products.append({
                "product_id": pid,
                "product_name": p_name,
                "sku": p_sku,
                "total_quantity": qty,
            })

        recent_list = []
        for t in all_transfers[:5]:
            recent_list.append({
                "id": t.id,
                "transfer_number": t.transfer_number,
                "source_store_name": t.source_store.name if t.source_store else None,
                "destination_store_name": t.destination_store.name if t.destination_store else None,
                "status": t.status,
                "created_at": t.created_at,
                "total_items": len(t.items),
            })

        return {
            "total_transfers": total_transfers,
            "pending_transfers": pending_count,
            "approved_transfers": approved_count,
            "dispatched_transfers": dispatched_count,
            "received_transfers": received_count,
            "rejected_transfers": rejected_count,
            "in_transit_transfers": dispatched_count,
            "total_units_transferred": total_units,
            "top_source_stores": top_sources,
            "top_destination_stores": top_dests,
            "top_transferred_products": top_products,
            "recent_transfers": recent_list,
        }
