import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import openpyxl
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


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
    ) -> openpyxl.Workbook:
        """
        Creates and styles an openpyxl Workbook with the given headers and data rows.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        # Excel sheet titles cannot exceed 31 chars
        ws.title = (sheet_title or "Export")[:31].replace(":", "").replace("/", "_").replace("\\", "_")

        # Freeze the top header row so it stays visible during scrolling
        ws.freeze_panes = "A2"

        # 1. Header row
        ws.append(headers)
        ws.row_dimensions[1].height = 26

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
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
    ) -> io.BytesIO:
        """Generates an in-memory BytesIO stream containing the complete .xlsx file."""
        wb = self.create_workbook(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            enable_zebra=enable_zebra,
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
    ) -> bytes:
        """Generates raw .xlsx bytes."""
        stream = self.export_to_stream(sheet_title, headers, rows, enable_zebra)
        return stream.getvalue()

    def create_streaming_response(
        self,
        sheet_title: str,
        headers: list[str],
        rows: list[list[Any]],
        filename: str,
        enable_zebra: bool = True,
    ) -> StreamingResponse:
        """Creates a FastAPI StreamingResponse with proper Excel MIME type and Content-Disposition."""
        clean_name = filename if filename.endswith(".xlsx") else f"{filename}.xlsx"
        stream = self.export_to_stream(sheet_title, headers, rows, enable_zebra)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={clean_name}"},
        )
