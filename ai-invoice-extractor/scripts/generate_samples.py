"""
Generate fictional sample invoices for testing the n8n and Make.com workflows.

Each sample tests a different part of the pipeline:
  01  clean intra-state GST invoice (CGST + SGST)   -> should be "OK"
  02  inter-state invoice with IGST, lakh formatting -> should be "OK"
  03  restaurant receipt with no GSTIN               -> should be "OK"
  04  invoice whose total does not add up            -> should be "Needs review"
  05  scanned receipt (image only, no text layer)    -> should be "Needs review" (n8n)

All companies, GSTINs and numbers are made up.

Usage:
    pip install -r scripts/requirements.txt
    python scripts/generate_samples.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent.parent / "sample-invoices"
OUT_DIR.mkdir(exist_ok=True)

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("title", parent=styles["Title"], fontSize=18, spaceAfter=4)
SMALL = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, leading=12)
BOLD = ParagraphStyle("bold", parent=SMALL, fontName="Helvetica-Bold")


def build_invoice(filename, seller, buyer, meta, items, tax_rows, total_text, footer=""):
    """Lay out a simple, realistic-looking tax invoice."""
    doc = SimpleDocTemplate(
        str(OUT_DIR / filename), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    story = [Paragraph("TAX INVOICE", TITLE), Spacer(1, 4)]

    header = Table(
        [[Paragraph(seller, SMALL), Paragraph(meta, SMALL)]],
        colWidths=[100 * mm, 74 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 8), Paragraph("<b>Bill To:</b><br/>" + buyer, SMALL), Spacer(1, 10)]

    rows = [["#", "Description", "HSN/SAC", "Qty", "Rate (INR)", "Amount (INR)"]]
    rows += [[str(i + 1), *item] for i, item in enumerate(items)]
    item_table = Table(rows, colWidths=[8 * mm, 72 * mm, 22 * mm, 12 * mm, 28 * mm, 32 * mm])
    item_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA5B1")),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
    ]))
    story += [item_table, Spacer(1, 8)]

    totals = Table(tax_rows + [["Total Amount Payable", total_text]], colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
    ]))
    story += [totals, Spacer(1, 14)]
    if footer:
        story.append(Paragraph(footer, SMALL))
    doc.build(story)


# 01 - Clean intra-state invoice (Karnataka -> Karnataka, so CGST + SGST)
build_invoice(
    "01_cloudnine_clean_cgst_sgst.pdf",
    seller="<b>CloudNine Software Solutions Pvt Ltd</b><br/>4th Floor, Prestige Tech Park, Bengaluru 560103<br/>"
           "GSTIN: 29AACCC1234F1Z5<br/>Email: billing@cloudnine.example",
    buyer="Acme Analytics LLP<br/>Koramangala, Bengaluru 560034<br/>GSTIN: 29AAKFA9876K1Z2",
    meta="<b>Invoice No:</b> CNS/2026-27/0142<br/><b>Invoice Date:</b> 14/10/2026<br/>"
         "<b>Due Date:</b> 13/11/2026<br/><b>Place of Supply:</b> Karnataka (29)",
    items=[
        ["Cloud hosting - October 2026", "998315", "1", "12,000.00", "12,000.00"],
        ["Domain renewal (1 year)", "998319", "1", "1,500.00", "1,500.00"],
    ],
    tax_rows=[["Taxable Value", "13,500.00"], ["CGST @ 9%", "1,215.00"], ["SGST @ 9%", "1,215.00"]],
    total_text="INR 15,930.00",
    footer="Amount in words: Fifteen Thousand Nine Hundred Thirty Rupees Only.",
)

# 02 - Inter-state invoice (Delhi -> Telangana, so IGST), Indian lakh digit grouping
build_invoice(
    "02_sharma_furniture_igst_lakh.pdf",
    seller="<b>Sharma Office Furniture Co.</b><br/>Plot 22, Okhla Industrial Area Phase II, New Delhi 110020<br/>"
           "GSTIN: 07ABHPS4321M1Z8",
    buyer="Acme Analytics LLP<br/>HITEC City, Hyderabad 500081<br/>GSTIN: 36AAKFA9876K1Z4",
    meta="<b>Bill No:</b> SOF-7781<br/><b>Date:</b> 03-11-2026<br/><b>Place of Supply:</b> Telangana (36)",
    items=[
        ["Ergonomic office chair", "9401", "10", "8,500.00", "85,000.00"],
        ["Height-adjustable desk", "9403", "2", "20,000.00", "40,000.00"],
    ],
    tax_rows=[["Taxable Value", "1,25,000.00"], ["IGST @ 18%", "22,500.00"]],
    total_text="Rs. 1,47,500.00",
    footer="Payment due within 30 days. Bank: Example Bank, A/c 000123456789, IFSC EXMP0000123.",
)

# 03 - Restaurant receipt, no GSTIN shown
build_invoice(
    "03_udupi_restaurant_receipt.pdf",
    seller="<b>Udupi Grand Restaurant</b><br/>Sayyaji Rao Road, Mysuru 570001<br/>Ph: 0821-0000000",
    buyer="Walk-in customer (team lunch)",
    meta="<b>Bill No:</b> 45821<br/><b>Date:</b> 28/10/2026<br/><b>Table:</b> 7",
    items=[
        ["Meals (unlimited)", "996331", "6", "180.00", "1,080.00"],
        ["Filter coffee", "996331", "6", "40.00", "240.00"],
    ],
    tax_rows=[["Sub Total", "1,320.00"], ["CGST @ 2.5%", "33.00"], ["SGST @ 2.5%", "33.00"]],
    total_text="Rs. 1,386.00",
    footer="Thank you! Visit again.",
)

# 04 - Totals deliberately do not add up (10,000 + 1,800 is 11,800, not 12,800)
build_invoice(
    "04_brightspark_wrong_total.pdf",
    seller="<b>BrightSpark Electricals</b><br/>Ameerpet, Hyderabad 500016<br/>GSTIN: 36AAGFB5555Q1Z9",
    buyer="Acme Analytics LLP<br/>HITEC City, Hyderabad 500081",
    meta="<b>Invoice No:</b> BSE/1093<br/><b>Invoice Date:</b> 21/10/2026",
    items=[["Office rewiring and inspection", "995461", "1", "10,000.00", "10,000.00"]],
    tax_rows=[["Taxable Value", "10,000.00"], ["CGST @ 9%", "900.00"], ["SGST @ 9%", "900.00"]],
    total_text="INR 12,800.00",
)


# 05 - "Scanned" receipt: text drawn into an image, so the PDF has no text layer
def build_scanned_receipt(filename):
    img = Image.new("RGB", (900, 1100), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except OSError:
        font = big = ImageFont.load_default()
    lines = [
        ("QUICKRIDE CABS", big), ("", font),
        ("Trip Receipt No: QR-559201", font), ("Date: 30/10/2026", font),
        ("From: Airport  To: T. Nagar", font), ("", font),
        ("Base fare           Rs. 420.00", font), ("GST @ 5%            Rs.  21.00", font),
        ("-------------------------------", font), ("TOTAL               Rs. 441.00", big),
    ]
    y = 80
    for text, f in lines:
        draw.text((80, y), text, fill="black", font=f)
        y += 60
    img = img.rotate(1.2, fillcolor="white")  # slight tilt, like a phone photo
    img.save(OUT_DIR / filename, "PDF", resolution=150)


build_scanned_receipt("05_quickride_scanned_receipt.pdf")
print(f"Sample invoices written to {OUT_DIR}")
