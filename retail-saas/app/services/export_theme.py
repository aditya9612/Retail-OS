from dataclasses import dataclass
from typing import Optional
from reportlab.lib import colors


@dataclass(frozen=True)
class ExportTheme:
    name: str
    primary_hex: str        # e.g. "#15803D"
    secondary_hex: str      # e.g. "#166534"
    bg_light_hex: str       # e.g. "#F0FDF4"
    border_hex: str         # e.g. "#BBF7D0"
    text_dark_hex: str      # e.g. "#14532D"
    accent_kpi_hex: str     # e.g. "#15803D"

    @property
    def primary_color(self) -> colors.HexColor:
        return colors.HexColor(self.primary_hex)

    @property
    def secondary_color(self) -> colors.HexColor:
        return colors.HexColor(self.secondary_hex)

    @property
    def bg_light_color(self) -> colors.HexColor:
        return colors.HexColor(self.bg_light_hex)

    @property
    def border_color(self) -> colors.HexColor:
        return colors.HexColor(self.border_hex)

    @property
    def text_dark_color(self) -> colors.HexColor:
        return colors.HexColor(self.text_dark_hex)

    @property
    def excel_header_hex(self) -> str:
        return self.primary_hex.lstrip("#")

    @property
    def excel_kpi_fill_hex(self) -> str:
        return self.bg_light_hex.lstrip("#")

    @property
    def excel_border_hex(self) -> str:
        return self.border_hex.lstrip("#")

    @property
    def excel_text_hex(self) -> str:
        return self.text_dark_hex.lstrip("#")


THEMES = {
    # 1. Emerald Green (Bill / Receipt)
    "bill": ExportTheme(
        name="Emerald Green",
        primary_hex="#1B5E20",
        secondary_hex="#2E7D32",
        bg_light_hex="#E8F5E9",
        border_hex="#A5D6A7",
        text_dark_hex="#0A3610",
        accent_kpi_hex="#1B5E20",
    ),
    # 2. Corporate Navy Blue (Tax Invoice)
    "tax_invoice": ExportTheme(
        name="Corporate Navy Blue",
        primary_hex="#1F497D",
        secondary_hex="#112B4A",
        bg_light_hex="#F0F4F8",
        border_hex="#CBD5E1",
        text_dark_hex="#1E293B",
        accent_kpi_hex="#1F497D",
    ),
    # 3. Red / Coral (Credit Note)
    "credit_note": ExportTheme(
        name="Coral Red",
        primary_hex="#DC2626",
        secondary_hex="#B91C1C",
        bg_light_hex="#FEF2F2",
        border_hex="#FECACA",
        text_dark_hex="#991B1B",
        accent_kpi_hex="#DC2626",
    ),
    # 4. Purple / Indigo (Purchase Order & Product Profitability)
    "purchase_order": ExportTheme(
        name="Purple Indigo",
        primary_hex="#6D28D9",
        secondary_hex="#581C87",
        bg_light_hex="#FAF5FF",
        border_hex="#E9D5FF",
        text_dark_hex="#4C1D95",
        accent_kpi_hex="#6D28D9",
    ),
    # 5. Green (Sales Reports & Top Selling)
    "green": ExportTheme(
        name="Forest Green",
        primary_hex="#15803D",
        secondary_hex="#166534",
        bg_light_hex="#F0FDF4",
        border_hex="#BBF7D0",
        text_dark_hex="#14532D",
        accent_kpi_hex="#15803D",
    ),
    # 6. Blue (Stock, Inventory Valuation, GST, Payment)
    "blue": ExportTheme(
        name="Cobalt Blue",
        primary_hex="#1E40AF",
        secondary_hex="#1E3A8A",
        bg_light_hex="#EFF6FF",
        border_hex="#BFDBFE",
        text_dark_hex="#172554",
        accent_kpi_hex="#1E40AF",
    ),
    # 7. Teal (Customer Overview, Retention, Segments)
    "teal": ExportTheme(
        name="Teal",
        primary_hex="#0F766E",
        secondary_hex="#115E59",
        bg_light_hex="#F0FDFA",
        border_hex="#99F6E4",
        text_dark_hex="#134E4A",
        accent_kpi_hex="#0F766E",
    ),
    # 8. Amber / Orange (Low Stock, Slow Moving)
    "amber": ExportTheme(
        name="Amber Orange",
        primary_hex="#D97706",
        secondary_hex="#B45309",
        bg_light_hex="#FFFBEB",
        border_hex="#FDE68A",
        text_dark_hex="#78350F",
        accent_kpi_hex="#D97706",
    ),
    # 9. Dark Green (Daily Billing Closure, POS Z-Report)
    "dark_green": ExportTheme(
        name="Dark Green POS",
        primary_hex="#14532D",
        secondary_hex="#052E16",
        bg_light_hex="#F0FDF4",
        border_hex="#86EFAC",
        text_dark_hex="#052E16",
        accent_kpi_hex="#14532D",
    ),
}


def get_theme_for_report(report_type: Optional[str]) -> ExportTheme:
    """
    Returns the designated ExportTheme for any given report or document type,
    strictly adhering to the visual design map.
    """
    rtype = (report_type or "").lower().strip().replace("-", "_")

    # Document types
    if rtype in ("bill", "receipt"):
        return THEMES["bill"]
    if rtype in ("invoice", "tax_invoice"):
        return THEMES["tax_invoice"]
    if rtype in ("credit_note", "credit-note"):
        return THEMES["credit_note"]
    if rtype in ("purchase_order", "purchase-order", "po"):
        return THEMES["purchase_order"]

    # Sales reports
    if rtype in ("sales_daily", "sales_monthly", "sales_yearly", "products_top_selling"):
        return THEMES["green"]

    # Profit & Loss
    if rtype == "profit_loss":
        return THEMES["green"]

    # Stock & Inventory Valuation & GST & Payment
    if rtype in ("inventory_stock", "inventory_valuation", "gst_sales", "gst_summary", "payment_summary", "multi_store_revenue", "multi_store_inventory"):
        return THEMES["blue"]

    # Low Stock & Slow Moving
    if rtype in ("inventory_low", "products_slow_moving"):
        return THEMES["amber"]

    # Customers & Retention & Segments & Multi-Store Customer
    if rtype in ("customers_overview", "customers_retention", "customers_segments", "multi_store_customer", "customer_directory"):
        return THEMES["teal"]

    # Product Profitability, Customer Lifetime Value, Multi-Store Profit
    if rtype in ("products_profitability", "customers_lifetime_value", "multi_store_profit"):
        return THEMES["purchase_order"]

    # Daily Billing & POS Shift Z-Report
    if rtype in ("daily_billing", "daily_billing_closure", "pos_z_report", "z_report"):
        return THEMES["dark_green"]

    # Fallback to Corporate Navy Blue
    return THEMES["tax_invoice"]

