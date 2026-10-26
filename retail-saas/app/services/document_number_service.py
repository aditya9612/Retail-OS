from datetime import datetime
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.document_sequence import DocumentSequence
from app.models.invoice import Invoice
from app.models.credit_note import CreditNote
from app.models.store import Store
from app.models.purchase_order import PurchaseOrder
from app.models.grn import GRN


class DocumentNumberService:
    """
    Enterprise-grade Document Numbering Engine for Retail-OS.
    Generates structured, atomic, concurrency-safe serial numbers for:
    - Invoices:       INV-{STORE}-{POS}-{YYYYMMDD}-{SEQUENCE}  (e.g. INV-STR01-POS01-20261013-000001)
    - Credit Notes:   CN-{STORE}-{YYYYMMDD}-{SEQUENCE}    (e.g. CN-STR01-20261013-000001)
    - Orders:         ORD-{STORE}-{POS}-{YYYYMMDD}-{SEQ}  (e.g. ORD-STR01-POS01-20261013-000001)
    - Purchase Orders:PO-{STORE}-{YYYYMMDD}-{SEQUENCE}    (e.g. PO-STR01-20261013-000001)
    - GRN Receipts:   GRN-{STORE}-{YYYYMMDD}-{SEQUENCE}   (e.g. GRN-STR01-20261013-000001)
    - Transfers:      TR-{FROM}-{TO}-{YYYYMMDD}-{SEQ}     (e.g. TR-STR01-STR02-20261013-000001)
    """

    def __init__(self, db: Session):
        self.db = db

    def _resolve_store_code(self, tenant_id: int, store_id: Optional[int]) -> str:
        """Resolve clean store code like STR01, STR02 or custom store.code."""
        if not store_id:
            return "STR01"
        try:
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if store and store.code and store.code.strip():
                clean = "".join(
                    c for c in store.code.strip().upper() if c.isalnum() or c == "-"
                )
                if clean:
                    return clean
            return f"STR{store_id:02d}"
        except Exception:
            return f"STR{store_id:02d}"

    def _resolve_pos_code(self, pos_id: Optional[int]) -> str:
        """Resolve POS counter code like POS01, POS02."""
        if not pos_id:
            return "POS01"
        return f"POS{pos_id:02d}"

    def _next_sequence(self, tenant_id: int, series_key: str, period_key: int) -> int:
        """Atomic, concurrency-safe counter increment using row-level locking."""
        bind = self.db.get_bind()
        if bind.dialect.name == "mysql":
            self.db.execute(
                text(
                    "INSERT INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, NOW(), NOW()) "
                    "ON DUPLICATE KEY UPDATE id=id"
                ),
                {"tenant_id": tenant_id, "doc_type": series_key, "year": period_key},
            )
            self.db.flush()
        else:
            self.db.execute(
                text(
                    "INSERT OR IGNORE INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"tenant_id": tenant_id, "doc_type": series_key, "year": period_key},
            )
            self.db.flush()

        row = (
            self.db.query(DocumentSequence)
            .filter(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.doc_type == series_key,
                DocumentSequence.year == period_key,
            )
            .with_for_update()
            .first()
        )
        if not row:
            row = DocumentSequence(
                tenant_id=tenant_id,
                doc_type=series_key,
                year=period_key,
                last_number=0,
            )
            self.db.add(row)
            self.db.flush()

        row.last_number += 1
        self.db.flush()
        return row.last_number

    def generate_invoice_number(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        pos_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate invoice number in standard enterprise format:
        INV-STR01-POS01-YYYYMMDD-000001
        """
        from app.services.document_settings_service import DocumentSettingsService
        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=store_id,
        )
        prefix = (branding.invoice_prefix or "INV").strip().rstrip("-") or "INV"
        padding_length = int(getattr(branding, "padding_length", 6) or 6)

        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=store_id,
        )
        prefix = (branding.invoice_prefix or "INV").strip().rstrip("-") or "INV"
        store_code = self._resolve_store_code(tenant_id, store_id)
        pos_code = self._resolve_pos_code(pos_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")

        if prefix.upper() != "INV":
            period_key = dt.year
            series_key = f"inv_{prefix.lower()}"[:64]
            while True:
                seq = self._next_sequence(tenant_id, series_key, period_key)
                inv_number = f"{prefix}-{period_key}-{seq:0{padding_length}d}"
                collision = (
                    self.db.query(Invoice)
                    .filter(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_number == inv_number,
                    )
                    .first()
                )
                if not collision:
                    return inv_number
        else:
            period_key = int(date_str)
            series_key = f"inv_{store_code.lower()}_{pos_code.lower()}"[:64]
            while True:
                seq = self._next_sequence(tenant_id, series_key, period_key)
                inv_number = f"INV-{store_code}-{pos_code}-{date_str}-{seq:0{padding_length}d}"
                collision = (
                    self.db.query(Invoice)
                    .filter(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_number == inv_number,
                    )
                    .first()
                )
                if not collision:
                    return inv_number

    def generate_credit_note_number(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate credit note number in standard enterprise format:
        CN-STR01-YYYYMMDD-000001
        """
        store_code = self._resolve_store_code(tenant_id, store_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")
        period_key = int(date_str)
        series_key = f"cn_{store_code.lower()}"[:64]

        while True:
            seq = self._next_sequence(tenant_id, series_key, period_key)
            cn_number = f"CN-{store_code}-{date_str}-{seq:06d}"
            collision = (
                self.db.query(CreditNote)
                .filter(
                    CreditNote.credit_note_no == cn_number,
                )
                .first()
            )
            if not collision:
                return cn_number

    def generate_order_number(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        pos_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate order number in standard enterprise format:
        ORD-STR01-POS01-YYYYMMDD-000001
        """
        store_code = self._resolve_store_code(tenant_id, store_id)
        pos_code = self._resolve_pos_code(pos_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")
        period_key = int(date_str)
        series_key = f"ord_{store_code.lower()}_{pos_code.lower()}"[:64]

        seq = self._next_sequence(tenant_id, series_key, period_key)
        return f"ORD-{store_code}-{pos_code}-{date_str}-{seq:06d}"

    def generate_purchase_order_number(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate purchase order number in standard enterprise format:
        PO-STR01-YYYYMMDD-000001
        """
        store_code = self._resolve_store_code(tenant_id, store_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")
        period_key = int(date_str)
        series_key = f"po_{store_code.lower()}"[:64]

        while True:
            seq = self._next_sequence(tenant_id, series_key, period_key)
            po_number = f"PO-{store_code}-{date_str}-{seq:06d}"
            collision = (
                self.db.query(PurchaseOrder)
                .filter(PurchaseOrder.order_number == po_number)
                .first()
            )
            if not collision:
                return po_number

    def generate_grn_number(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate GRN receipt number:
        GRN-STR01-YYYYMMDD-000001
        """
        store_code = self._resolve_store_code(tenant_id, store_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")
        period_key = int(date_str)
        series_key = f"grn_{store_code.lower()}"[:64]

        while True:
            seq = self._next_sequence(tenant_id, series_key, period_key)
            grn_number = f"GRN-{store_code}-{date_str}-{seq:06d}"
            collision = (
                self.db.query(GRN)
                .filter(
                    GRN.tenant_id == tenant_id,
                    GRN.grn_number == grn_number,
                )
                .first()
            )
            if not collision:
                return grn_number

    def generate_transfer_number(
        self,
        tenant_id: int,
        from_store_id: Optional[int] = None,
        to_store_id: Optional[int] = None,
        doc_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate stock transfer number:
        TR-STR01-STR02-YYYYMMDD-000001
        """
        from_code = self._resolve_store_code(tenant_id, from_store_id)
        to_code = self._resolve_store_code(tenant_id, to_store_id)
        dt = doc_date or datetime.utcnow()
        date_str = dt.strftime("%Y%m%d")
        period_key = int(date_str)
        series_key = f"tr_{from_code.lower()}_{to_code.lower()}"[:64]

        seq = self._next_sequence(tenant_id, series_key, period_key)
        return f"TR-{from_code}-{to_code}-{date_str}-{seq:06d}"
