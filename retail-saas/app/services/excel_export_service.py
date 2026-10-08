import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import openpyxl
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.services.export_theme import get_theme_for_report


class ExcelExportService:
    """
    Reusable, production-grade Excel (.xlsx) export engine using openpyxl.

    Provides:
    - Clean workbook and worksheet initialization
    - Standardized corporate header styling (dark navy blue #1F497D, white bold text, row height)
    - Auto column width calculation based on maximum cell content length + safety margin
    - Thin borders and clean typography
    - Number/decimal/date cell formatting preservation
    - In-memory BytesIO generation and FastAPI StreamingResponse integration
    """

    # Corporate styling constants
    HEADER_FILL_COLOR = "1F497D"      # Dark navy blue
    HEADER_FONT_COLOR = "FFFFFF"      # White
    ZEBRA_FILL_COLOR = "F9FAFB"       # Very light gray / slate
    BORDER_COLOR = "D1D5DB"           # Soft gray border

    def __init__(self):
        self.header_font = Font(name="Calibri", size=11, bold=True, color=self.HEADER_FONT_COLOR)
        self.header_fill = PatternFill(
            start_color=self.HEADER_FILL_COLOR,
            end_color=self.HEADER_FILL_COLOR,
            fill_type="solid",
        )
        self.header_alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)

        self.data_font = Font(name="Calibri", size=10, bold=False, color="111827")
        self.zebra_fill = PatternFill(
            start_color=self.ZEBRA_FILL_COLOR,
            end_color=self.ZEBRA_FILL_COLOR,
            fill_type="solid",
        )

        thin_side = Side(style="thin", color=self.BORDER_COLOR)
        self.cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    def create_workbook(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        enable_zebra: bool = True,
        min_col_width: int = 12,
        max_col_width: int = 50,
        report_type: str | None = None,
    ) -> openpyxl.Workbook:
        """
        Creates and styles an openpyxl Workbook with the given headers and data rows.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        # Excel sheet titles cannot exceed 31 chars
        ws.title = (sheet_title or "Export")[:31].replace(":", "").replace("/", "_").replace("\\", "_")

        theme = get_theme_for_report(report_type or sheet_title)
        header_fill = (
            PatternFill(start_color=theme.excel_header_hex, end_color=theme.excel_header_hex, fill_type="solid")
            if theme else self.header_fill
        )

        # Freeze the top header row so it stays visible during scrolling
        ws.freeze_panes = "A2"

        # 1. Header row
        ws.append(headers)
        ws.row_dimensions[1].height = 26

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = header_fill
            cell.alignment = self.header_alignment
            cell.border = self.cell_border

        # 2. Data rows
        for row_idx, r in enumerate(rows, start=2):
            ws.append(self._sanitize_row(r))
            ws.row_dimensions[row_idx].height = 20

            is_even = (row_idx % 2 == 0)
            fill_to_use = self.zebra_fill if (enable_zebra and not is_even) else None

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = self.data_font
                cell.border = self.cell_border
                if fill_to_use:
                    cell.fill = fill_to_use

                # Format specific data types
                val = cell.value
                if isinstance(val, (int, float, Decimal)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if isinstance(val, (float, Decimal)):
                        cell.number_format = "#,##0.00"
                    else:
                        cell.number_format = "#,##0"
                elif isinstance(val, (datetime, date)):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.number_format = "YYYY-MM-DD"
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # 3. Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val_str = str(cell.value or "")
                max_len = max(max_len, len(val_str))
            col_letter = get_column_letter(col[0].column)
            calc_width = max(max_len + 4, min_col_width)
            ws.column_dimensions[col_letter].width = min(calc_width, max_col_width)

        return wb

    def _sanitize_row(self, row: list[Any]) -> list[Any]:
        """Convert objects or unsupported types to Excel-friendly representations."""
        sanitized: list[Any] = []
        for val in row:
            if val is None:
                sanitized.append("")
            elif isinstance(val, (Decimal,)):
                sanitized.append(float(val))
            elif isinstance(val, (int, float, str, bool, datetime, date)):
                sanitized.append(val)
            else:
                sanitized.append(str(val))
        return sanitized

    def export_to_stream(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        enable_zebra: bool = True,
        report_type: str | None = None,
    ) -> io.BytesIO:
        """Generates an in-memory BytesIO stream containing the complete .xlsx file."""
        wb = self.create_workbook(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            enable_zebra=enable_zebra,
            report_type=report_type,
        )
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    def export_to_bytes(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        enable_zebra: bool = True,
        report_type: str | None = None,
    ) -> bytes:
        """Generates raw .xlsx bytes."""
        stream = self.export_to_stream(sheet_title, headers, rows, enable_zebra, report_type=report_type)
        return stream.getvalue()

    def create_streaming_response(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        filename: str,
        enable_zebra: bool = True,
        report_type: str | None = None,
    ) -> StreamingResponse:
        """Creates a FastAPI StreamingResponse with proper Excel MIME type and Content-Disposition."""
        clean_name = filename if filename.endswith(".xlsx") else f"{filename}.xlsx"
        stream = self.export_to_stream(sheet_title, headers, rows, enable_zebra, report_type=report_type)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={clean_name}"},
        )

    def create_report_workbook(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        metadata: dict[str, Any] | None = None,
        kpis: list[dict[str, Any]] | None = None,
        branding: Any = None,
        enable_zebra: bool = True,
        report_type: str | None = None,
    ) -> openpyxl.Workbook:
        """
        Creates a professional 2-sheet corporate Excel workbook:
        - Sheet 1: 'Overview' (Branded header, report metadata, KPI summary)
        - Sheet 2: 'Detailed Data' (Full tabular dataset with zebra striping, currency formatting, auto-filter)
        """
        wb = openpyxl.Workbook()

        theme = get_theme_for_report(report_type or sheet_title)
        header_hex = theme.excel_header_hex
        theme_header_fill = PatternFill(
            start_color=header_hex,
            end_color=header_hex,
            fill_type="solid",
        )

        # ----------------------------------------------------
        # SHEET 1: OVERVIEW / SUMMARY
        # ----------------------------------------------------
        ws_summary = wb.active
        ws_summary.title = "Overview"

        title_font = Font(name="Calibri", size=15, bold=True, color=header_hex)
        subtitle_font = Font(name="Calibri", size=11, bold=True, color="374151")
        section_font = Font(name="Calibri", size=11, bold=True, color=self.HEADER_FONT_COLOR)
        key_font = Font(name="Calibri", size=10, bold=True, color="1F2937")
        val_font = Font(name="Calibri", size=10, bold=False, color="111827")

        current_row = 1
        # Title
        display_title = (sheet_title or "Business Report").strip()
        ws_summary.cell(row=current_row, column=1, value=display_title).font = title_font
        current_row += 1

        # Company branding
        biz_name = getattr(branding, "business_name", None) if branding else None
        if biz_name:
            ws_summary.cell(row=current_row, column=1, value=str(biz_name)).font = subtitle_font
            current_row += 1

        current_row += 1  # blank line

        # Metadata Section
        if metadata:
            ws_summary.cell(row=current_row, column=1, value="REPORT PARAMETERS").font = section_font
            ws_summary.cell(row=current_row, column=1).fill = theme_header_fill
            ws_summary.cell(row=current_row, column=2, value="DETAILS").font = section_font
            ws_summary.cell(row=current_row, column=2).fill = theme_header_fill
            ws_summary.row_dimensions[current_row].height = 22
            current_row += 1

            for k, v in metadata.items():
                c1 = ws_summary.cell(row=current_row, column=1, value=str(k))
                c2 = ws_summary.cell(row=current_row, column=2, value=str(v if v is not None else "N/A"))
                c1.font = key_font
                c2.font = val_font
                c1.border = self.cell_border
                c2.border = self.cell_border
                current_row += 1

            current_row += 1  # blank line

        # KPI Section
        if kpis:
            ws_summary.cell(row=current_row, column=1, value="KEY METRICS (KPIs)").font = section_font
            ws_summary.cell(row=current_row, column=1).fill = theme_header_fill
            ws_summary.cell(row=current_row, column=2, value="VALUE").font = section_font
            ws_summary.cell(row=current_row, column=2).fill = theme_header_fill
            ws_summary.row_dimensions[current_row].height = 22
            current_row += 1

            for item in kpis:
                lbl = item.get("label") or item.get("metric") or "Metric"
                val = item.get("value")
                c1 = ws_summary.cell(row=current_row, column=1, value=str(lbl))
                c2 = ws_summary.cell(row=current_row, column=2, value=val)
                c1.font = key_font
                c2.font = val_font
                c1.border = self.cell_border
                c2.border = self.cell_border

                if isinstance(val, (int, float, Decimal)):
                    c2.alignment = Alignment(horizontal="right", vertical="center")
                    c2.number_format = "#,##0.00" if isinstance(val, (float, Decimal)) else "#,##0"
                else:
                    c2.alignment = Alignment(horizontal="left", vertical="center")
                current_row += 1

        # Auto-adjust summary column widths
        for col in ws_summary.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            col_letter = get_column_letter(col[0].column)
            ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 22)

        # ----------------------------------------------------
        # SHEET 2: DETAILED DATA
        # ----------------------------------------------------
        data_sheet_title = (sheet_title or "Details")[:31].replace(":", "").replace("/", "_").replace("\\", "_")
        if data_sheet_title.lower() == "overview":
            data_sheet_title = "Data"
        ws_data = wb.create_sheet(title=data_sheet_title)
        ws_data.freeze_panes = "A2"

        # Headers
        ws_data.append(headers)
        ws_data.row_dimensions[1].height = 26
        for col_idx in range(1, len(headers) + 1):
            cell = ws_data.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = theme_header_fill
            cell.alignment = self.header_alignment
            cell.border = self.cell_border

        # Data rows
        for row_idx, r in enumerate(rows, start=2):
            ws_data.append(self._sanitize_row(r))
            ws_data.row_dimensions[row_idx].height = 20

            is_even = (row_idx % 2 == 0)
            fill_to_use = self.zebra_fill if (enable_zebra and not is_even) else None

            for col_idx in range(1, len(headers) + 1):
                cell = ws_data.cell(row=row_idx, column=col_idx)
                cell.font = self.data_font
                cell.border = self.cell_border
                if fill_to_use:
                    cell.fill = fill_to_use

                val = cell.value
                if isinstance(val, (int, float, Decimal)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if isinstance(val, (float, Decimal)):
                        cell.number_format = "#,##0.00"
                    else:
                        cell.number_format = "#,##0"
                elif isinstance(val, (datetime, date)):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.number_format = "YYYY-MM-DD"
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # Auto-filter & column widths
        if len(headers) > 0 and len(rows) > 0:
            ws_data.auto_filter.ref = ws_data.dimensions

        for col in ws_data.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            col_letter = get_column_letter(col[0].column)
            ws_data.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 50)

        wb.active = ws_data
        return wb

    def create_report_streaming_response(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        filename: str,
        metadata: dict[str, Any] | None = None,
        kpis: list[dict[str, Any]] | None = None,
        branding: Any = None,
        enable_zebra: bool = True,
        report_type: str | None = None,
    ) -> StreamingResponse:
        """Generates a professional 2-sheet report workbook and returns a StreamingResponse."""
        clean_name = filename if filename.endswith(".xlsx") else f"{filename}.xlsx"
        wb = self.create_report_workbook(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            metadata=metadata,
            kpis=kpis,
            branding=branding,
            enable_zebra=enable_zebra,
            report_type=report_type,
        )
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={clean_name}"},
        )

