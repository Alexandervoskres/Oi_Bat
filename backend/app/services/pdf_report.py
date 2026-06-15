from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from ..models import Product
from .analytics import product_to_dict


def _register_font() -> str:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("ReportFont", str(path)))
            return "ReportFont"
    return "Helvetica"


def build_risk_pdf(db: Session) -> bytes:
    font_name = _register_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleRu",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        textColor=colors.HexColor("#111111"),
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "BodyRu",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=12,
    )

    products = [product_to_dict(item) for item in db.query(Product).order_by(Product.category, Product.name).all()]
    risks = [
        item
        for item in products
        if item["status"] in {"Нет в наличии", "Срочно заказать", "Мертвый груз", "Сделать скидку"}
    ]

    story = [
        Paragraph("СкладAI - отчет по рискам", title),
        Paragraph(
            "Отчет показывает товары, которые требуют закупки, скидки или отдельного контроля.",
            body,
        ),
        Spacer(1, 5 * mm),
    ]

    data = [["Товар", "Категория", "Остаток", "Продано/мес", "Дней осталось", "Статус", "Действие"]]
    for item in risks[:40]:
        data.append(
            [
                Paragraph(item["name"], body),
                item["category"],
                str(item["stock"]),
                str(item["sold_month"]),
                str(item["days_left"] or "-"),
                item["status"],
                item["action"],
            ]
        )

    if len(data) == 1:
        data.append(["Нет критических рисков", "-", "-", "-", "-", "Норма", "Следить по плану"])

    table = Table(data, colWidths=[72 * mm, 35 * mm, 20 * mm, 25 * mm, 28 * mm, 35 * mm, 42 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F1A12")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFD34D")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFC7B8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF8E6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
