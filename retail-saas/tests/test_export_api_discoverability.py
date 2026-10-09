"""
Tests verifying Export API Discoverability and Swagger / OpenAPI Tag Architecture.

Ensures that:
1. Export endpoints are not collapsed into a single generic black-box endpoint.
2. Every document and report export route is independently visible and properly tagged.
3. Tags and schema descriptions are accurately registered in OpenAPI schema.
4. ReportType enum exposes all 22+ supported report types for Swagger UI interactive exploration.
5. All file formats (PDF, Excel, CSV) have documented media types.
"""

from fastapi.testclient import TestClient
from app.main import app
from app.schemas.report import ReportType, ExportFormat


client = TestClient(app)


def test_openapi_schema_generated():
    """Verify that OpenAPI schema is successfully generated and accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, f"Failed to retrieve openapi.json: {response.text}"
    schema = response.json()
    assert "paths" in schema
    assert "tags" in schema
    assert "components" in schema


def test_openapi_tags_metadata_registered():
    """Verify all 16 designated export and reporting tags are present in openapi metadata."""
    response = client.get("/openapi.json")
    schema = response.json()
    tag_names = [t["name"] for t in schema.get("tags", [])]

    expected_tags = [
        "Invoice Documents",
        "Bill / Receipt",
        "Credit Notes",
        "Purchase Orders",
        "POS Z-Reports",
        "Report Exports",
        "Sales Reports",
        "Inventory Reports",
        "GST Reports",
        "Customer Reports",
        "Payment Reports",
        "Profitability Reports",
        "Multi-Store Reports",
        "Customer Exports",
        "Delivery Exports",
        "Document Settings",
    ]

    for tag in expected_tags:
        assert tag in tag_names, f"Expected tag '{tag}' missing from OpenAPI metadata tags"


def test_invoice_and_bill_export_discoverability():
    """Verify Invoice and POS Bill PDF route discoverability and tagging."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})
    route = paths.get("/api/v1/invoices/{invoice_id}/pdf", {}).get("get")

    assert route is not None, "Route /api/v1/invoices/{invoice_id}/pdf not found in OpenAPI"
    assert "Invoice Documents" in route.get("tags", [])
    assert "Bill / Receipt" in route.get("tags", [])
    assert "application/pdf" in route.get("responses", {}).get("200", {}).get("content", {})


def test_credit_note_export_discoverability():
    """Verify Credit Note PDF route discoverability and tagging."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})
    route = paths.get("/api/v1/credit-notes/{credit_note_id}/pdf", {}).get("get")

    assert route is not None, "Route /api/v1/credit-notes/{credit_note_id}/pdf not found in OpenAPI"
    assert "Credit Notes" in route.get("tags", [])
    assert "application/pdf" in route.get("responses", {}).get("200", {}).get("content", {})


def test_purchase_order_export_discoverability():
    """Verify Purchase Order PDF route discoverability and tagging."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})
    route = paths.get("/api/v1/purchase-orders/{purchase_order_id}/pdf", {}).get("get")

    assert route is not None, "Route /api/v1/purchase-orders/{purchase_order_id}/pdf not found in OpenAPI"
    assert "Purchase Orders" in route.get("tags", [])
    assert "application/pdf" in route.get("responses", {}).get("200", {}).get("content", {})


def test_pos_z_report_export_discoverability():
    """Verify POS Z-Report JSON, PDF, and Excel export route discoverability and tagging."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})

    # JSON preview
    json_route = paths.get("/api/v1/pos/shifts/{shift_id}/z-report", {}).get("get")
    assert json_route is not None, "Route /api/v1/pos/shifts/{shift_id}/z-report not found"
    assert "POS Z-Reports" in json_route.get("tags", [])

    # PDF export
    pdf_route = paths.get("/api/v1/pos/shifts/{shift_id}/z-report/pdf", {}).get("get")
    assert pdf_route is not None, "Route /api/v1/pos/shifts/{shift_id}/z-report/pdf not found"
    assert "POS Z-Reports" in pdf_route.get("tags", [])
    assert "application/pdf" in pdf_route.get("responses", {}).get("200", {}).get("content", {})

    # Excel export
    excel_route = paths.get("/api/v1/pos/shifts/{shift_id}/z-report/excel", {}).get("get")
    assert excel_route is not None, "Route /api/v1/pos/shifts/{shift_id}/z-report/excel not found"
    assert "POS Z-Reports" in excel_route.get("tags", [])
    content = excel_route.get("responses", {}).get("200", {}).get("content", {})
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content


def test_customer_and_delivery_export_discoverability():
    """Verify Customer and Delivery directory export routes."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})

    customer_export = paths.get("/api/v1/customers/export-directory", {}).get("get")
    assert customer_export is not None, "Route /api/v1/customers/export-directory not found"
    assert "Customer Exports" in customer_export.get("tags", [])

    delivery_export = paths.get("/api/v1/delivery/export", {}).get("get")
    assert delivery_export is not None, "Route /api/v1/delivery/export not found"
    assert "Delivery Exports" in delivery_export.get("tags", [])


def test_reports_export_unified_endpoints():
    """Verify Report Exports POST and GET routes with multi-format streaming content."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})

    post_export = paths.get("/api/v1/reports/export", {}).get("post")
    assert post_export is not None, "Route POST /api/v1/reports/export not found"
    assert "Report Exports" in post_export.get("tags", [])
    content = post_export.get("responses", {}).get("200", {}).get("content", {})
    assert "text/csv" in content
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content
    assert "application/pdf" in content

    get_export = paths.get("/api/v1/reports/export", {}).get("get")
    assert get_export is not None, "Route GET /api/v1/reports/export not found"
    assert "Report Exports" in get_export.get("tags", [])


def test_report_type_enum_in_openapi():
    """Verify ReportType enum is defined and includes all 22+ supported report types."""
    response = client.get("/openapi.json")
    components = response.json().get("components", {})
    schemas = components.get("schemas", {})

    report_type_schema = schemas.get("ReportType", {})
    assert report_type_schema is not None, "ReportType schema not found in components.schemas"
    enum_values = report_type_schema.get("enum", [])

    required_types = [
        "sales_daily",
        "sales_monthly",
        "sales_yearly",
        "gst_sales",
        "gst_summary",
        "inventory_stock",
        "inventory_low",
        "inventory_valuation",
        "products_top_selling",
        "products_slow_moving",
        "products_profitability",
        "profit_loss",
        "customers_overview",
        "customers_retention",
        "customers_lifetime_value",
        "customers_segments",
        "daily_billing",
        "payment_summary",
        "multi_store_revenue",
        "multi_store_profit",
        "multi_store_inventory",
        "multi_store_customer",
    ]

    for rt in required_types:
        assert rt in enum_values, f"Report type '{rt}' missing from ReportType enum schema"


def test_analytical_report_endpoints_tagged():
    """Verify individual analytical endpoints are categorized under specific functional tags."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})

    # Sales Reports
    assert "Sales Reports" in paths.get("/api/v1/reports/sales/daily", {}).get("get", {}).get("tags", [])
    assert "Sales Reports" in paths.get("/api/v1/reports/sales/monthly", {}).get("get", {}).get("tags", [])
    assert "Sales Reports" in paths.get("/api/v1/reports/sales/yearly", {}).get("get", {}).get("tags", [])

    # GST Reports
    assert "GST Reports" in paths.get("/api/v1/reports/gst/sales", {}).get("get", {}).get("tags", [])
    assert "GST Reports" in paths.get("/api/v1/reports/gst/summary", {}).get("get", {}).get("tags", [])

    # Inventory Reports
    assert "Inventory Reports" in paths.get("/api/v1/reports/inventory/current-stock", {}).get("get", {}).get("tags", [])
    assert "Inventory Reports" in paths.get("/api/v1/reports/inventory/low-stock", {}).get("get", {}).get("tags", [])
    assert "Inventory Reports" in paths.get("/api/v1/reports/inventory/valuation", {}).get("get", {}).get("tags", [])

    # Profitability Reports
    assert "Profitability Reports" in paths.get("/api/v1/reports/profit-loss", {}).get("get", {}).get("tags", [])
    assert "Profitability Reports" in paths.get("/api/v1/reports/products/profitability", {}).get("get", {}).get("tags", [])

    # Customer Reports
    assert "Customer Reports" in paths.get("/api/v1/reports/customers/overview", {}).get("get", {}).get("tags", [])
    assert "Customer Reports" in paths.get("/api/v1/reports/customers/retention", {}).get("get", {}).get("tags", [])
    assert "Customer Reports" in paths.get("/api/v1/reports/customers/lifetime-value", {}).get("get", {}).get("tags", [])
    assert "Customer Reports" in paths.get("/api/v1/reports/customers/segments", {}).get("get", {}).get("tags", [])

    # Payment Reports
    assert "Payment Reports" in paths.get("/api/v1/reports/daily-billing", {}).get("get", {}).get("tags", [])
    assert "Payment Reports" in paths.get("/api/v1/reports/payment-summary", {}).get("get", {}).get("tags", [])

    # Multi-Store Reports
    assert "Multi-Store Reports" in paths.get("/api/v1/multi-store/revenue-comparison", {}).get("get", {}).get("tags", [])
    assert "Multi-Store Reports" in paths.get("/api/v1/multi-store/profit-comparison", {}).get("get", {}).get("tags", [])
    assert "Multi-Store Reports" in paths.get("/api/v1/multi-store/inventory-comparison", {}).get("get", {}).get("tags", [])
    assert "Multi-Store Reports" in paths.get("/api/v1/multi-store/customer-comparison", {}).get("get", {}).get("tags", [])


def test_no_single_generic_blackbox_export_endpoint():
    """Verify that exports are NOT hidden behind a generic black-box /api/v1/exports/{key}/download."""
    response = client.get("/openapi.json")
    paths = response.json().get("paths", {})

    generic_pattern = "/api/v1/exports/{export_key}/download"
    assert generic_pattern not in paths, f"Forbidden generic black-box endpoint '{generic_pattern}' found in OpenAPI paths"
