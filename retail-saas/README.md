# Retail SaaS Backend

Smart Retail POS & E-Commerce API built with FastAPI, SQLAlchemy 2.0, MySQL, JWT, Redis, Celery, and AWS S3.

## Stack

- **Backend:** FastAPI
- **Database:** MySQL (AWS RDS compatible)
- **ORM:** SQLAlchemy 2.0
- **Migrations:** Alembic
- **Auth:** JWT
- **Cache/Queue:** Redis + Celery
- **Storage:** AWS S3
- **Container:** Docker

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
# Edit .env — DATABASE_URL example:
# DATABASE_URL=mysql+pymysql://root:root@localhost:3306/retel_os

# Initialize MySQL database and tables
python scripts/init_db.py

# Run API
uvicorn app.main:app --reload

# Or with Docker
docker-compose up --build
```

## Bootstrap

```bash
python scripts/create_admin.py "My Store" mystore admin@store.com "Admin User" secretpass
python scripts/seed_data.py
```

## API Docs

- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Modules

| Module | Prefix |
|--------|--------|
| Auth | `/api/v1/auth` |
| Users | `/api/v1/users` |
| Stores | `/api/v1/stores` |
| Products | `/api/v1/products` |
| Inventory | `/api/v1/inventory` |
| Suppliers | `/api/v1/suppliers` |
| Orders | `/api/v1/orders` |
| Billing | `/api/v1/billing` |
| Payments | `/api/v1/payments` |
| Customers | `/api/v1/customers` |
| WhatsApp | `/api/v1/whatsapp` |
| Reports | `/api/v1/reports` |
| Analytics | `/api/v1/analytics` |
| AI | `/api/v1/ai` |

## Migrations

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Tests

```bash
pytest tests/ -v
```
