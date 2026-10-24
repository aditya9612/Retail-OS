import io
import logging
from typing import Optional, Union
from fastapi.responses import Response

logger = logging.getLogger(__name__)


def render_pdf_or_preview(
    pdf_content: Union[bytes, io.BytesIO],
    filename_base: str,
    mode: str = "download",
    dpi: int = 150,
) -> Response:
    """
    Standardized PDF / Preview response generator for Retail-OS endpoints.

    Behavior:
    - mode="download": Returns attachment application/pdf (triggers browser file download).
    - mode="preview": Converts the first page of the PDF to a high-resolution PNG image (media_type="image/png")
      with Content-Disposition: inline. This allows Swagger UI and browser visual clients to immediately
      display the rendered document preview directly in the response window (matching thermal print preview).
    """
    if isinstance(pdf_content, io.BytesIO):
        pdf_bytes = pdf_content.getvalue()
    elif isinstance(pdf_content, (bytes, bytearray)):
        pdf_bytes = bytes(pdf_content)
    else:
        pdf_bytes = bytes(pdf_content)

    mode_str = str(mode or "download").lower().strip()
    clean_base = str(filename_base).rstrip(".pdf").rstrip(".png")

    if mode_str == "preview":
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) > 0:
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=dpi)
                png_bytes = pix.tobytes("png")
                return Response(
                    content=png_bytes,
                    media_type="image/png",
                    headers={
                        "Content-Disposition": f"inline; filename={clean_base}.png",
                        "X-Document-Preview-Type": "Visual-PNG-Preview",
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to render preview PNG with PyMuPDF: {e}")
            # Fallback to inline PDF if rendering fails
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"inline; filename={clean_base}.pdf"
                },
            )

    # mode="download" (default): Download PDF attachment
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={clean_base}.pdf"
        },
    )

