from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.sale import Sale, SaleItem
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.repositories.sale_repo import SaleRepository
from app.schemas.sale import SaleCreate


class SaleService:

    @staticmethod
    def create_sale(
        db: Session,
        data: SaleCreate
    ):
        if not data.items:
            raise ValueError("Sale must contain at least one item")

        store_exists = (
            db.query(Store)
            .filter(Store.id == data.store_id)
            .first()
        )

        if not store_exists:
            raise ValueError(f"Store with id {data.store_id} not found")

        if data.customer_id is not None:
            from app.models.customer import Customer
            customer = (
                db.query(Customer)
                .filter(Customer.id == data.customer_id)
                .first()
            )
            if not customer:
                raise ValueError(f"Customer with id {data.customer_id} not found")

        subtotal = Decimal("0")
        total_discount = Decimal("0")
        tax_amount = Decimal("0")

        sale_items = []

        for item in data.items:
            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .first()
            )

            if not product:
                raise ValueError(f"Product {item.product_id} not found")

            if not product.is_active:
                raise ValueError(f"Product {item.product_id} is inactive")

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.store_id == data.store_id,
                    Inventory.product_id == item.product_id
                )
                .first()
            )

            if not inventory:
                raise ValueError(
                    f"Product {item.product_id} is not available in this store inventory"
                )

            if item.stock <= 0:
                raise ValueError(
                    f"Quantity must be greater than 0 for product {item.product_id}"
                )

            if item.stock > inventory.quantity:
                raise ValueError(
                    f"Insufficient stock for product {item.product_id}. Available stock: {inventory.quantity}"
                )

            item_gross = Decimal(str(product.price)) * Decimal(str(item.stock))
            item_discount = Decimal(str(item.discount or 0))

            if item_discount < 0:
                raise ValueError(f"Discount cannot be negative for product {item.product_id}")

            if item_discount > item_gross:
                raise ValueError(f"Discount cannot exceed item value for product {item.product_id}")

            taxable_amount = item_gross - item_discount
            gst_rate = Decimal(str(product.gst_rate or 0))
            item_tax = taxable_amount * gst_rate / Decimal("100")
            item_total = taxable_amount + item_tax

            subtotal += taxable_amount
            total_discount += item_discount
            tax_amount += item_tax

            sale_items.append(
                SaleItem(
                    product_id=item.product_id,
                    quantity=item.stock,
                    unit_price=product.price,
                    discount=item_discount,
                    tax=item_tax,
                    total_price=item_total
                )
            )

            inventory.quantity -= item.stock

        invoice_number = f"INV-{data.store_id}-{db.query(Sale).count() + 1:06d}"

        sale = Sale(
            store_id=data.store_id,
            customer_id=data.customer_id,
            invoice_number=invoice_number,
            subtotal=subtotal,
            discount=total_discount,
            tax=tax_amount,
            total_amount=subtotal + tax_amount,
            payment_method=data.payment_method,
            status="completed"
        )

        sale.items = sale_items

        return SaleRepository.create(db, sale)

    @staticmethod
    def get_sales(
        db: Session,
        store_id: int = None
    ):
        return SaleRepository.get_all(db, store_id)

    @staticmethod
    def get_sale(
        db: Session,
        sale_id: int
    ):
        sale = SaleRepository.get_by_id(db, sale_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")
        return sale

    @staticmethod
    def update_sale(
        db: Session,
        sale_id: int,
        data: SaleCreate
    ):
        sale = SaleRepository.get_by_id(db, sale_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")

        if not data.items:
            raise ValueError("Sale must contain at least one item")

        store_exists = db.query(Store).filter(Store.id == data.store_id).first()
        if not store_exists:
            raise ValueError(f"Store with id {data.store_id} not found")

        if data.customer_id is not None:
            from app.models.customer import Customer
            customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                raise ValueError(f"Customer with id {data.customer_id} not found")

        for old_item in sale.items:
            old_inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.store_id == sale.store_id,
                    Inventory.product_id == old_item.product_id
                )
                .first()
            )
            if old_inventory:
                old_inventory.quantity += old_item.quantity

        sale.items.clear()

        subtotal = Decimal("0")
        total_discount = Decimal("0")
        tax_amount = Decimal("0")

        for item in data.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise ValueError(f"Product {item.product_id} not found")

            if not product.is_active:
                raise ValueError(f"Product {item.product_id} is inactive")

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.store_id == data.store_id,
                    Inventory.product_id == item.product_id
                )
                .first()
            )

            if not inventory:
                raise ValueError(f"Product {item.product_id} is not available in this store inventory")

            if item.stock <= 0:
                raise ValueError(f"Quantity must be greater than 0 for product {item.product_id}")

            if item.stock > inventory.quantity:
                raise ValueError(
                    f"Insufficient stock for product {item.product_id}. Available stock: {inventory.quantity}"
                )

            item_gross = Decimal(str(product.price)) * Decimal(str(item.stock))
            item_discount = Decimal(str(item.discount or 0))

            if item_discount < 0:
                raise ValueError(f"Discount cannot be negative for product {item.product_id}")

            if item_discount > item_gross:
                raise ValueError(f"Discount cannot exceed item value for product {item.product_id}")

            taxable_amount = item_gross - item_discount
            gst_rate = Decimal(str(product.gst_rate or 0))
            item_tax = taxable_amount * gst_rate / Decimal("100")
            item_total = taxable_amount + item_tax

            subtotal += taxable_amount
            total_discount += item_discount
            tax_amount += item_tax

            sale_item = SaleItem(
                product_id=item.product_id,
                quantity=item.stock,
                unit_price=product.price,
                discount=item_discount,
                tax=item_tax,
                total_price=item_total
            )

            sale.items.append(sale_item)
            inventory.quantity -= item.stock

        sale.store_id = data.store_id
        sale.customer_id = data.customer_id
        sale.payment_method = data.payment_method
        sale.subtotal = subtotal
        sale.discount = total_discount
        sale.tax = tax_amount
        sale.total_amount = subtotal + tax_amount
        sale.status = "completed"

        return SaleRepository.update(db, sale)

    @staticmethod
    def delete_sale(
        db: Session,
        sale_id: int
    ):
        sale = SaleRepository.get_by_id(db, sale_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")

        for item in sale.items:
            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.store_id == sale.store_id,
                    Inventory.product_id == item.product_id
                )
                .first()
            )
            if inventory:
                inventory.quantity += item.quantity

        SaleRepository.delete(db, sale)

        return {
            "message": "Sale deleted successfully",
            "sale_id": sale_id
        }