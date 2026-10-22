from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Optional, Union
import uuid

from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.models.customer import (
    Customer,
    CustomerFeedback,
    CustomerWallet,
    WalletTransaction,
    LoyaltyPoint,
    CustomerCommunication,
    CustomerReferral,
    CustomerNote,
    CustomerLedgerEntry,
)
from app.models.invoice import Invoice
from app.models.order import Order
from app.repositories.customer_repo import (
    get_filtered_customers,
    get_customer_stats,
    get_customers_for_export,
)
from app.schemas.customer import (
    CustomerLedgerStatementResponse,
    FeedbackAnalyticsResponse,
)
from app.services.excel_export_service import ExcelExportService


def fetch_customers(
    db: Session,
    tenant_id: int,
    name: Optional[str] = None,
    mobile: Optional[str] = None,
    segment: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
):
    return get_filtered_customers(
        db=db,
        tenant_id=tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


def fetch_customer_stats(
    db: Session,
    tenant_id: int,
):
    return get_customer_stats(
        db=db,
        tenant_id=tenant_id,
    )


class CustomerService:

    def __init__(self, db: Session):
        self.db = db

    def create_customer(
        self,
        tenant_id: int,
        data,
    ) -> Customer:

        if data.email:
            email_val = str(data.email).strip().lower()
            existing_email = (
                self.db.query(Customer)
                .filter(
                    Customer.email == email_val,
                    Customer.tenant_id == tenant_id,
                )
                .first()
            )
            if existing_email:
                raise ConflictException("Customer with this email already exists")

        existing_phone = (
            self.db.query(Customer)
            .filter(
                Customer.phone == data.phone,
                Customer.tenant_id == tenant_id,
            )
            .first()
        )
        if existing_phone:
            raise ConflictException("Customer with this phone number already exists")

        if data.gstin:
            existing_gstin = (
                self.db.query(Customer)
                .filter(
                    Customer.gstin == data.gstin,
                    Customer.tenant_id == tenant_id,
                )
                .first()
            )
            if existing_gstin:
                raise ConflictException("GSTIN already exists")

        customer_data = data.model_dump()
        if customer_data.get("email"):
            customer_data["email"] = str(customer_data["email"]).strip().lower()

        customer = Customer(
            tenant_id=tenant_id,
            total_spend=0,
            loyalty_points=0,
            **customer_data,
        )

        try:
            self.db.add(customer)
            self.db.commit()
            self.db.refresh(customer)
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc).lower()
            if "ix_customers_phone" in err_msg or "customers.phone" in err_msg or "uq_customer_tenant_phone" in err_msg or "phone" in err_msg:
                raise ConflictException("Customer with this phone number already exists")
            if "ix_customers_email" in err_msg or "customers.email" in err_msg or "uq_customer_tenant_email" in err_msg or "email" in err_msg:
                raise ConflictException("Customer with this email already exists")
            if "gstin" in err_msg:
                raise ConflictException("GSTIN already exists")
            raise

        return customer

    def get_customer(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> Customer:

        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
            )
            .first()
        )
        if not customer:
            raise NotFoundException("Customer not found")

        return customer

    def list_customers(
        self,
        tenant_id: int,
    ) -> list[Customer]:
        return (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .all()
        )

    def update_customer(
        self,
        tenant_id: int,
        customer_id: int,
        data,
    ) -> Customer:

        customer = self.get_customer(tenant_id, customer_id)
        dump_data = data.model_dump(exclude_unset=True)

        if "email" in dump_data and dump_data["email"]:
            email_val = str(dump_data["email"]).strip().lower()
            existing_email = (
                self.db.query(Customer)
                .filter(
                    Customer.email == email_val,
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )
            if existing_email:
                raise ConflictException("Customer with this email already exists")
            dump_data["email"] = email_val

        if "phone" in dump_data and dump_data["phone"]:
            existing_phone = (
                self.db.query(Customer)
                .filter(
                    Customer.phone == dump_data["phone"],
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )
            if existing_phone:
                raise ConflictException("Customer with this phone number already exists")

        if "gstin" in dump_data and dump_data["gstin"]:
            existing_gstin = (
                self.db.query(Customer)
                .filter(
                    Customer.gstin == dump_data["gstin"],
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )
            if existing_gstin:
                raise ConflictException("GSTIN already exists")

        for key, value in dump_data.items():
            setattr(customer, key, value)

        try:
            self.db.commit()
            self.db.refresh(customer)
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc).lower()
            if "ix_customers_phone" in err_msg or "customers.phone" in err_msg or "uq_customer_tenant_phone" in err_msg or "phone" in err_msg:
                raise ConflictException("Customer with this phone number already exists")
            if "ix_customers_email" in err_msg or "customers.email" in err_msg or "uq_customer_tenant_email" in err_msg or "email" in err_msg:
                raise ConflictException("Customer with this email already exists")
            if "gstin" in err_msg:
                raise ConflictException("GSTIN already exists")
            raise

        return customer

    def update_customer_status(
        self,
        tenant_id: int,
        customer_id: int,
        status: str,
    ):
        customer = self.get_customer(tenant_id, customer_id)
        customer.status = status
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def add_loyalty_points(
        self,
        tenant_id: int,
        customer_id: int,
        points: int,
    ):
        customer = self.get_customer(tenant_id, customer_id)
        current_points = customer.loyalty_points or 0
        new_balance = current_points + points
        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=customer_id,
            points_earned=points,
            points_redeemed=0,
            balance_points=new_balance,
        )

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)
        return loyalty

    def get_birthday_customers(
        self,
        tenant_id: int,
        month: int,
        day: int,
    ):
        customers = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.birthday.isnot(None),
                func.extract("month", Customer.birthday) == month,
                func.extract("day", Customer.birthday) == day,
            )
            .all()
        )
        if not customers:
            return {
                "success": True,
                "message": "No customers with birthdays found",
                "data": [],
            }
        return customers

    def create_feedback(
        self,
        tenant_id: int,
        data,
    ):
        self.get_customer(tenant_id, data.customer_id)

        if data.invoice_id is not None:
            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == data.invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )
            if not invoice:
                raise NotFoundException("Invoice not found")

        feedback = CustomerFeedback(
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            rating=data.rating,
            comments=data.comments,
            suggestions=data.suggestions,
        )

        try:
            self.db.add(feedback)
            self.db.commit()
            self.db.refresh(feedback)
        except IntegrityError:
            self.db.rollback()
            raise

        return feedback

    def get_feedback(
        self,
        tenant_id: int,
        customer_id: int | None = None,
    ):
        if customer_id is not None:
            self.get_customer(tenant_id, customer_id)

        query = (
            self.db.query(CustomerFeedback)
            .join(Customer, Customer.id == CustomerFeedback.customer_id)
            .filter(Customer.tenant_id == tenant_id)
        )

        if customer_id is not None:
            query = query.filter(CustomerFeedback.customer_id == customer_id)

        feedbacks = query.order_by(CustomerFeedback.created_at.desc()).all()

        if customer_id is not None and not feedbacks:
            return {
                "success": True,
                "message": "No feedback found for this customer",
                "data": [],
            }

        return feedbacks

    def get_wallet(
        self,
        tenant_id: int,
        customer_id: int,
        for_update: bool = False,
    ):
        customer = self.get_customer(tenant_id, customer_id)

        query = (
            self.db.query(CustomerWallet)
            .filter(CustomerWallet.customer_id == customer.id)
        )
        if for_update:
            try:
                query = query.with_for_update()
            except Exception:
                pass

        wallet = query.first()

        if not wallet:
            wallet = CustomerWallet(
                customer_id=customer.id,
                current_balance=Decimal("0.00"),
            )
            try:
                self.db.add(wallet)
                self.db.commit()
                self.db.refresh(wallet)
            except IntegrityError:
                self.db.rollback()
                wallet = (
                    self.db.query(CustomerWallet)
                    .filter(CustomerWallet.customer_id == customer.id)
                    .first()
                )

        return wallet

    def credit_wallet(
        self,
        tenant_id: int,
        data,
    ):
        wallet = self.get_wallet(tenant_id, data.customer_id, for_update=True)

        existing_tx = (
            self.db.query(WalletTransaction)
            .join(CustomerWallet, CustomerWallet.id == WalletTransaction.wallet_id)
            .join(Customer, Customer.id == CustomerWallet.customer_id)
            .filter(
                Customer.tenant_id == tenant_id,
                WalletTransaction.reference_no == data.reference_no,
            )
            .first()
        )
        if existing_tx:
            raise ConflictException("Reference number already exists")

        current_balance = Decimal(str(wallet.current_balance or 0)) + Decimal(str(data.amount))
        wallet.current_balance = current_balance

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="CREDIT",
            amount=data.amount,
            reference_no=data.reference_no,
            remarks=data.remarks,
        )

        try:
            self.db.add(transaction)
            self.db.commit()
            self.db.refresh(wallet)
            self.db.refresh(transaction)
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc).lower()
            if "reference_no" in err_msg or "unique" in err_msg:
                raise ConflictException("Reference number already exists")
            raise

        return {
            "id": transaction.id,
            "customer_id": data.customer_id,
            "amount": float(data.amount),
            "reference_no": data.reference_no,
            "remarks": data.remarks,
            "balance": float(wallet.current_balance),
            "current_balance": float(wallet.current_balance),
        }

    def debit_wallet(
        self,
        tenant_id: int,
        data,
    ):
        wallet = self.get_wallet(tenant_id, data.customer_id, for_update=True)

        existing_tx = (
            self.db.query(WalletTransaction)
            .join(CustomerWallet, CustomerWallet.id == WalletTransaction.wallet_id)
            .join(Customer, Customer.id == CustomerWallet.customer_id)
            .filter(
                Customer.tenant_id == tenant_id,
                WalletTransaction.reference_no == data.reference_no,
            )
            .first()
        )
        if existing_tx:
            raise ConflictException("Reference number already exists")

        current_balance = Decimal(str(wallet.current_balance or 0))
        debit_amount = Decimal(str(data.amount))

        if current_balance < debit_amount:
            raise AppException("Insufficient wallet balance")

        wallet.current_balance = current_balance - debit_amount

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="DEBIT",
            amount=data.amount,
            reference_no=data.reference_no,
            remarks=data.remarks,
        )

        try:
            self.db.add(transaction)
            self.db.commit()
            self.db.refresh(wallet)
            self.db.refresh(transaction)
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc).lower()
            if "reference_no" in err_msg or "unique" in err_msg:
                raise ConflictException("Reference number already exists")
            raise

        return {
            "id": transaction.id,
            "customer_id": data.customer_id,
            "amount": float(data.amount),
            "reference_no": data.reference_no,
            "remarks": data.remarks,
            "balance": float(wallet.current_balance),
            "current_balance": float(wallet.current_balance),
        }

    def get_wallet_transactions(
        self,
        tenant_id: int,
        customer_id: int,
    ):
        wallet = self.get_wallet(tenant_id, customer_id)
        transactions = (
            self.db.query(WalletTransaction)
            .filter(WalletTransaction.wallet_id == wallet.id)
            .order_by(WalletTransaction.created_at.desc())
            .all()
        )
        if not transactions:
            return {
                "success": True,
                "message": "No wallet transactions found for this customer",
                "data": [],
            }
        return transactions

    def earn_loyalty_points(
        self,
        tenant_id: int,
        data,
    ):
        customer = self.get_customer(tenant_id, data.customer_id)

        if data.invoice_id is not None:
            invoice = (
                self.db.query(Invoice)
                .join(Order, Order.id == Invoice.order_id)
                .filter(
                    Invoice.id == data.invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )
            if not invoice:
                raise NotFoundException("Invoice not found")

            if invoice.order and invoice.order.customer_id is not None and invoice.order.customer_id != data.customer_id:
                raise AppException("Invoice belongs to a different customer", status_code=422)

        current_points = customer.loyalty_points or 0
        new_balance = current_points + data.points
        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            points_earned=data.points,
            points_redeemed=0,
            balance_points=new_balance,
        )

        try:
            self.db.add(loyalty)
            self.db.commit()
            self.db.refresh(loyalty)
        except IntegrityError:
            self.db.rollback()
            raise

        return loyalty

    def redeem_loyalty_points(
        self,
        tenant_id: int,
        data,
    ):
        customer = self.get_customer(tenant_id, data.customer_id)
        current_points = customer.loyalty_points or 0

        if current_points < data.points:
            raise AppException("Insufficient loyalty points")

        new_balance = current_points - data.points
        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            points_earned=0,
            points_redeemed=data.points,
            balance_points=new_balance,
        )

        try:
            self.db.add(loyalty)
            self.db.commit()
            self.db.refresh(loyalty)
        except IntegrityError:
            self.db.rollback()
            raise

        return loyalty

    def get_loyalty(
        self,
        tenant_id: int,
        customer_id: int,
    ):
        self.get_customer(tenant_id, customer_id)
        loyalty = (
            self.db.query(LoyaltyPoint)
            .filter(LoyaltyPoint.customer_id == customer_id)
            .order_by(LoyaltyPoint.created_at.desc())
            .first()
        )
        if loyalty is None:
            raise NotFoundException("No loyalty record found")

        return loyalty

    def get_loyalty_history(
        self,
        tenant_id: int,
        customer_id: int,
    ):
        self.get_customer(tenant_id, customer_id)
        history = (
            self.db.query(LoyaltyPoint)
            .filter(LoyaltyPoint.customer_id == customer_id)
            .order_by(LoyaltyPoint.created_at.desc())
            .all()
        )
        if not history:
            return {
                "success": True,
                "message": "No loyalty history found for this customer",
                "data": [],
            }
        return history

    def send_communication(
        self,
        tenant_id: int,
        data,
    ):
        self.get_customer(tenant_id, data.customer_id)
        comm_type = data.communication_type.strip().upper()

        communication = CustomerCommunication(
            customer_id=data.customer_id,
            communication_type=comm_type,
            message=data.message.strip(),
            delivery_status="SENT",
        )

        try:
            self.db.add(communication)
            self.db.commit()
            self.db.refresh(communication)
        except IntegrityError:
            self.db.rollback()
            raise

        return communication

    def get_communications(
        self,
        tenant_id: int,
    ):
        return (
            self.db.query(CustomerCommunication)
            .join(Customer, Customer.id == CustomerCommunication.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(CustomerCommunication.sent_at.desc())
            .all()
        )

    def get_communications_by_type(
        self,
        tenant_id: int,
        communication_type: str,
    ):
        return (
            self.db.query(CustomerCommunication)
            .join(Customer, Customer.id == CustomerCommunication.customer_id)
            .filter(
                Customer.tenant_id == tenant_id,
                CustomerCommunication.communication_type == communication_type.strip().upper(),
            )
            .order_by(CustomerCommunication.sent_at.desc())
            .all()
        )

    def create_referral(
        self,
        tenant_id: int,
        data,
    ):
        self.get_customer(tenant_id, data.customer_id)

        if data.referred_customer_id:
            if data.referred_customer_id == data.customer_id:
                raise AppException("Customer cannot refer themselves", status_code=422)

            self.get_customer(tenant_id, data.referred_customer_id)
            existing = (
                self.db.query(CustomerReferral)
                .filter(
                    CustomerReferral.customer_id == data.customer_id,
                    CustomerReferral.referred_customer_id == data.referred_customer_id,
                )
                .first()
            )
            if existing:
                raise ConflictException("Referral already exists for this customer")

        code = f"REF-{uuid.uuid4().hex[:8].upper()}"
        for _ in range(5):
            existing_code = (
                self.db.query(CustomerReferral)
                .filter(CustomerReferral.referral_code == code)
                .first()
            )
            if not existing_code:
                break
            code = f"REF-{uuid.uuid4().hex[:8].upper()}"

        referral = CustomerReferral(
            customer_id=data.customer_id,
            referred_customer_id=data.referred_customer_id,
            referral_code=code,
            reward_amount=100 if data.referred_customer_id else 0,
        )

        try:
            self.db.add(referral)
            self.db.commit()
            self.db.refresh(referral)
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc).lower()
            if "referral_code" in err_msg or "unique" in err_msg:
                raise ConflictException("Referral already exists for this customer")
            raise

        return referral

    def get_referrals(
        self,
        tenant_id: int,
    ):
        return (
            self.db.query(CustomerReferral)
            .join(Customer, Customer.id == CustomerReferral.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .all()
        )

    def create_note(
        self,
        tenant_id: int,
        data,
        user_id: int | None = None,
    ):
        self.get_customer(tenant_id, data.customer_id)

        note = CustomerNote(
            customer_id=data.customer_id,
            note=data.note.strip(),
            created_by=user_id,
        )

        try:
            self.db.add(note)
            self.db.commit()
            self.db.refresh(note)
        except IntegrityError:
            self.db.rollback()
            raise

        return note

    def get_notes(
        self,
        tenant_id: int,
        customer_id: int | None = None,
    ):
        if customer_id is not None:
            self.get_customer(tenant_id, customer_id)

        query = (
            self.db.query(CustomerNote)
            .join(Customer, Customer.id == CustomerNote.customer_id)
            .filter(Customer.tenant_id == tenant_id)
        )

        if customer_id is not None:
            query = query.filter(CustomerNote.customer_id == customer_id)

        notes = query.order_by(CustomerNote.created_at.desc()).all()

        if customer_id is not None and not notes:
            return {
                "success": True,
                "message": "No notes found for this customer",
                "data": [],
            }

        return notes

    def send_campaign(
        self,
        tenant_id: int,
        data,
    ):
        if not data.customer_ids:
            raise AppException("customer_ids cannot be empty")

        comm_type = data.communication_type.strip().upper()
        if comm_type not in ("SMS", "WHATSAPP", "EMAIL"):
            raise AppException("Invalid communication type")

        for customer_id in data.customer_ids:
            self.get_customer(tenant_id, customer_id)

        sent_count = 0
        failed_count = 0

        for customer_id in data.customer_ids:
            communication = CustomerCommunication(
                customer_id=customer_id,
                communication_type=comm_type,
                message=data.message.strip(),
                delivery_status="SENT",
            )
            self.db.add(communication)
            sent_count += 1

        self.db.commit()

        return {
            "campaign_id": data.campaign_id,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "message": "Campaign sent successfully",
            "total_customers": len(data.customer_ids),
        }

    def get_top_customers(
        self,
        tenant_id: int,
    ):
        return (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(Customer.total_spend.desc())
            .limit(10)
            .all()
        )

    def get_retention_report(
        self,
        tenant_id: int,
    ):
        total = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .count()
        )
        active = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status == "active",
            )
            .count()
        )
        inactive = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status == "inactive",
            )
            .count()
        )

        retention_rate = 0.0
        if total > 0:
            retention_rate = round((active / total) * 100, 2)

        return {
            "total_customers": total,
            "active_customers": active,
            "inactive_customers": inactive,
            "retention_rate": retention_rate,
        }

    def get_lifetime_value(
        self,
        tenant_id: int,
    ):
        customers = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(Customer.total_spend.desc())
            .all()
        )
        result = []
        for customer in customers:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "total_spend": customer.total_spend,
                "loyalty_points": customer.loyalty_points,
            })
        return result

    def get_loyalty_report(
        self,
        tenant_id: int,
    ):
        loyalty = (
            self.db.query(LoyaltyPoint)
            .join(Customer, Customer.id == LoyaltyPoint.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .all()
        )
        result = []
        for item in loyalty:
            result.append({
                "customer_id": item.customer_id,
                "customer_name": item.customer.name,
                "points_earned": item.points_earned,
                "points_redeemed": item.points_redeemed,
                "balance_points": item.balance_points,
            })
        return result

    def export_directory(
        self,
        tenant_id: int,
        status="all",
        format="excel",
    ):
        customers = get_customers_for_export(
            self.db,
            tenant_id,
            status,
        )
        if format == "excel":
            return self._create_excel(customers)
        elif format == "pdf":
            return self._create_pdf(customers)

        raise ValueError("Invalid format")

    def _create_excel(
        self,
        customers,
    ):
        headers = [
            "ID",
            "Name",
            "Email",
            "Phone",
            "Status",
            "Loyalty Points",
        ]
        rows = [
            [
                customer.id,
                customer.name,
                customer.email or "",
                customer.phone or "",
                customer.status,
                customer.loyalty_points or 0,
            ]
            for customer in customers
        ]
        return ExcelExportService().export_to_stream(
            sheet_title="Customer Directory",
            headers=headers,
            rows=rows,
        )

    def _create_pdf(
        self,
        customers,
    ):
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
        )
        data = [
            [
                "ID",
                "Name",
                "Email",
                "Phone",
                "Status",
                "Points",
            ]
        ]
        for customer in customers:
            data.append([
                customer.id,
                customer.name,
                customer.email or "",
                customer.phone or "",
                customer.status,
                customer.loyalty_points or 0,
            ])

        table = Table(data)
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("PADDING", (0, 0), (-1, -1), 5),
            ])
        )
        document.build([table])
        output.seek(0)
        return output

    # --- Enterprise Enhancements: Credit Limits, Khata Ledger, Feedback Analytics & Delete ---

    def update_credit_limit(
        self,
        tenant_id: int,
        customer_id: int,
        credit_limit: Decimal,
    ) -> Customer:
        customer = self.get_customer(tenant_id, customer_id)
        customer.credit_limit = credit_limit
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def record_customer_payment(
        self,
        tenant_id: int,
        customer_id: int,
        data,
    ) -> CustomerLedgerEntry:
        customer = self.get_customer(tenant_id, customer_id)
        current_balance = Decimal(str(customer.outstanding_balance or Decimal("0.00")))
        payment_amount = Decimal(str(data.amount))
        new_balance = current_balance - payment_amount
        customer.outstanding_balance = new_balance

        notes = data.notes or f"Payment received via {data.payment_method}"
        ledger_entry = CustomerLedgerEntry(
            tenant_id=tenant_id,
            customer_id=customer.id,
            entry_type="CREDIT",
            amount=payment_amount,
            balance_after=new_balance,
            reference_no=data.reference_no,
            notes=notes,
        )
        self.db.add(ledger_entry)
        self.db.commit()
        self.db.refresh(customer)
        self.db.refresh(ledger_entry)
        return ledger_entry

    def get_customer_ledger(
        self,
        tenant_id: int,
        customer_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> CustomerLedgerStatementResponse:
        customer = self.get_customer(tenant_id, customer_id)
        query = (
            self.db.query(CustomerLedgerEntry)
            .filter(
                CustomerLedgerEntry.tenant_id == tenant_id,
                CustomerLedgerEntry.customer_id == customer_id,
            )
        )
        if from_date:
            query = query.filter(CustomerLedgerEntry.created_at >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            query = query.filter(CustomerLedgerEntry.created_at <= datetime.combine(to_date, datetime.max.time()))

        entries = query.order_by(CustomerLedgerEntry.created_at.asc()).all()

        total_debit = sum((e.amount for e in entries if e.entry_type == "DEBIT"), Decimal("0.00"))
        total_credit = sum((e.amount for e in entries if e.entry_type == "CREDIT"), Decimal("0.00"))

        return CustomerLedgerStatementResponse(
            success=True,
            customer_id=customer.id,
            customer_name=customer.name,
            credit_limit=customer.credit_limit,
            outstanding_balance=customer.outstanding_balance,
            total_debit=total_debit,
            total_credit=total_credit,
            entries=entries,
        )

    def get_feedback_analytics(
        self,
        tenant_id: int,
    ) -> FeedbackAnalyticsResponse:
        feedbacks = (
            self.db.query(CustomerFeedback)
            .join(Customer, Customer.id == CustomerFeedback.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .all()
        )
        total = len(feedbacks)
        if total == 0:
            return FeedbackAnalyticsResponse(
                success=True,
                total_feedbacks=0,
                average_rating=0.0,
                rating_breakdown={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                nps_score=0.0,
            )

        breakdown = {str(i): 0 for i in range(1, 6)}
        for fb in feedbacks:
            r_str = str(int(fb.rating))
            if r_str in breakdown:
                breakdown[r_str] += 1
            else:
                breakdown[r_str] = 1

        avg_rating = round(sum(fb.rating for fb in feedbacks) / total, 2)
        # Promoters: 4 & 5 stars, Detractors: 1 & 2 stars, Passives: 3 stars
        promoters = sum(1 for fb in feedbacks if fb.rating >= 4)
        detractors = sum(1 for fb in feedbacks if fb.rating <= 2)
        nps = round(((promoters - detractors) / total) * 100, 2)

        return FeedbackAnalyticsResponse(
            success=True,
            total_feedbacks=total,
            average_rating=avg_rating,
            rating_breakdown=breakdown,
            nps_score=nps,
        )

    def delete_customer(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> dict:
        customer = self.get_customer(tenant_id, customer_id)
        customer.status = "inactive"
        self.db.commit()
        return {
            "success": True,
            "message": "Customer deactivated successfully",
            "customer_id": customer.id,
        }
