"""
Synthetic Sample Bank Statement Generator.
Generates test digital vector PDFs and simulated scanned PDFs for testing.
"""

import io
import os
from typing import Tuple
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

SAMPLE_TRANSACTIONS = [
    ["Date", "Description", "Debit", "Credit", "Balance"],
    ["2024-01-02", "EMPLOYER PAYROLL DIRECT DEPOSIT", "", "$4,250.00", "$4,250.00"],
    ["2024-01-03", "BUNNINGS 3045 CHATSWOOD", "$185.50", "", "$4,064.50"],
    ["2024-01-05", "OFFICEWORKS SYDNEY CBD", "$249.00", "", "$3,815.50"],
    ["2024-01-08", "SHELL COLES EXPRESS FUEL", "$85.20", "", "$3,730.30"],
    ["2024-01-12", "XERO MONTHLY SUBSCRIPTION", "$65.00", "", "$3,665.30"],
    ["2024-01-15", "LINKT TOLLS ETOLL SYDNEY", "$24.50", "", "$3,640.80"],
    ["2024-01-18", "TELSTRA MOBILE BILL", "$89.00", "", "$3,551.80"],
    ["2024-01-22", "WOOLWORTHS SUPERMARKET", "$142.30", "", "$3,409.50"],
    ["2024-01-25", "SALVATION ARMY DGR DONATION", "$50.00", "", "$3,359.50"],
    ["2024-01-30", "MONTHLY ACCOUNT KEEPING FEE", "$5.00", "", "$3,354.50"]
]


def generate_vector_pdf_bytes() -> bytes:
    """
    Generates a clean digital vector PDF bank statement with embedded text tables.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D")
    )
    normal_style = styles['Normal']

    elements = [
        Paragraph("FIRST NATIONAL BANK - MONTHLY STATEMENT", title_style),
        Spacer(1, 10),
        Paragraph("<b>Account Holder:</b> John Doe | <b>Account Number:</b> XXXX-XXXX-4829", normal_style),
        Paragraph("<b>Statement Period:</b> Jan 01, 2024 - Jan 31, 2024", normal_style),
        Spacer(1, 15),
    ]

    table = Table(SAMPLE_TRANSACTIONS, colWidths=[80, 240, 70, 70, 70])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))

    elements.append(table)
    doc.build(elements)

    return buffer.getvalue()
