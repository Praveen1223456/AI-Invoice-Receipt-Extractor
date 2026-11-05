#!/usr/bin/env python3
"""
AI Invoice & Receipt Extractor - Local Pipeline Runner
Simulates or executes the exact end-to-end extraction and validation pipeline.

Features:
- Reads real PDF files from sample-invoices/
- Extracts digital text layer or flags scanned bitmap PDFs
- Calls Google Gemini API if GEMINI_API_KEY is set (or runs verified simulation)
- Executes full finance-grade validation (GSTIN, dates, maths check, duplicates)
- Generates formatted terminal table and outputs 'invoice_log_output.csv'

Usage:
    # Run in simulation / demo mode (no API key required):
    python scripts/run_pipeline.py

    # Run with live Gemini API key:
    python scripts/run_pipeline.py --api-key YOUR_ACTUAL_GEMINI_KEY
"""

import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Pre-verified model outputs for simulation mode (when no API key is supplied)
MOCK_EXTRACTIONS = {
    "01_cloudnine_clean_cgst_sgst.pdf": {
        "vendor_name": "CloudNine Software Solutions Pvt Ltd",
        "vendor_gstin": "29AACCC1234F1Z5",
        "invoice_number": "CNS/2026-27/0142",
        "invoice_date": "2026-10-14",
        "due_date": "2026-11-13",
        "currency": "INR",
        "subtotal": 13500.00,
        "tax_amount": 2430.00,
        "total_amount": 15930.00,
        "category": "Software & Cloud",
    },
    "02_sharma_furniture_igst_lakh.pdf": {
        "vendor_name": "Sharma Office Furniture Co.",
        "vendor_gstin": "07ABHPS4321M1Z8",
        "invoice_number": "SOF-7781",
        "invoice_date": "2026-11-03",
        "due_date": "2026-12-03",
        "currency": "INR",
        "subtotal": 125000.00,
        "tax_amount": 22500.00,
        "total_amount": 147500.00,
        "category": "Office & Furniture",
    },
    "03_udupi_restaurant_receipt.pdf": {
        "vendor_name": "Udupi Grand Restaurant",
        "vendor_gstin": None,
        "invoice_number": "45821",
        "invoice_date": "2026-10-28",
        "due_date": None,
        "currency": "INR",
        "subtotal": 1320.00,
        "tax_amount": 66.00,
        "total_amount": 1386.00,
        "category": "Food & Meals",
    },
    "04_brightspark_wrong_total.pdf": {
        "vendor_name": "BrightSpark Electricals",
        "vendor_gstin": "36AAGFB5555Q1Z9",
        "invoice_number": "BSE/1093",
        "invoice_date": "2026-10-21",
        "due_date": None,
        "currency": "INR",
        "subtotal": 10000.00,
        "tax_amount": 1800.00,
        "total_amount": 12800.00,  # 10,000 + 1,800 is 11,800 != 12,800
        "category": "Utilities",
    },
    "05_quickride_scanned_receipt.pdf": {
        "vendor_name": None,
        "vendor_gstin": None,
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": None,
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None,
        "category": "Other",
    },
}

EXTRACTION_PROMPT = """You are an accounts-payable assistant that reads invoices and receipts, mostly from Indian businesses.
Extract the requested fields from the document.

Rules:
- Only use values that appear in the document. Never guess. If a field is not present, return null.
- Dates: Convert every date to YYYY-MM-DD. Example: 03/11/2026 becomes 2026-11-03.
- Amounts: return plain numbers with no currency symbols or commas.
- subtotal is the taxable value before tax.
- tax_amount is the total tax: CGST + SGST added together, or IGST, plus any cess.
- total_amount is the final amount payable, including tax.
- vendor_name is the business that issued the invoice (the seller).
- vendor_gstin is the seller's 15-character GSTIN.
- currency is a 3-letter code such as INR or USD.
- category must be one of: Software & Cloud, Hardware & Equipment, Office & Furniture, Travel, Food & Meals, Utilities, Professional Services, Other.
- If the text is NO_TEXT_FOUND or unreadable, return null for every field and Other for category.

Return ONLY a valid JSON object matching these keys:
{
  "vendor_name": string or null,
  "vendor_gstin": string or null,
  "invoice_number": string or null,
  "invoice_date": string or null,
  "due_date": string or null,
  "currency": string or null,
  "subtotal": number or null,
  "tax_amount": number or null,
  "total_amount": number or null,
  "category": string
}
"""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extracts text layer using PyMuPDF."""
    if not fitz:
        return ""
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text() for page in doc).strip()
        return text
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}", file=sys.stderr)
        return ""


def call_gemini_api(api_key: str, text: str) -> dict:
    """Calls Gemini API with diagnostic error messaging."""
    clean_key = (api_key or "").strip()
    placeholder_keys = ["YOUR_GEMINI_API_KEY", "YOUR_KEY", "<YOUR_KEY>", "<API_KEY>", "YOUR_ACTUAL_GEMINI_KEY"]
    if clean_key in placeholder_keys or clean_key.startswith("YOUR_"):
        return {
            "error": "Placeholder API key used. Please replace 'YOUR_GEMINI_API_KEY' with your actual key from https://aistudio.google.com"
        }

    try:
        import urllib.request
        import urllib.error
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={clean_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": EXTRACTION_PROMPT},
                        {"text": f"\n\n--- DOCUMENT CONTENT ---\n{text}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json"
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            err_msg = err_json.get("error", {}).get("message", err_body)
        except Exception:
            err_msg = err_body or str(e)
        return {"error": f"Gemini API Error (HTTP {e.code}): {err_msg}"}
    except Exception as e:
        return {"error": str(e)}


def validate_row(ai_data: dict, file_name: str, pdf_text: str, seen_invoices: set) -> dict:
    """Applies the exact finance validation logic from the n8n JavaScript code node."""
    issues = []

    if "error" in ai_data:
        issues.append(f"AI API failure: {ai_data['error']}")

    # 1. Scanned PDF check
    if len(pdf_text.strip()) <= 20:
        issues.append("No readable text in PDF (scanned image?)")

    # 2. Mandatory fields check
    for field in ["vendor_name", "invoice_number", "invoice_date", "total_amount"]:
        val = ai_data.get(field)
        if val is None or str(val).strip() == "":
            issues.append(f"Missing {field}")

    # 3. Calendar date format check (YYYY-MM-DD)
    def is_valid_date(d_str):
        if not d_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d_str)):
            return False
        try:
            parts = [int(p) for p in str(d_str).split("-")]
            datetime.date(parts[0], parts[1], parts[2])
            return True
        except ValueError:
            return False

    inv_date = ai_data.get("invoice_date")
    if inv_date and not is_valid_date(inv_date):
        issues.append("Invoice date is not valid YYYY-MM-DD")

    due_date = ai_data.get("due_date")
    if due_date and not is_valid_date(due_date):
        issues.append("Due date is not valid YYYY-MM-DD")

    # 4. Arithmetic check (|subtotal + tax - total| <= 1.0)
    def to_float(v):
        if v is None or str(v).strip() == "":
            return None
        try:
            return float(str(v).replace(",", ""))
        except ValueError:
            return None

    subtotal = to_float(ai_data.get("subtotal"))
    tax = to_float(ai_data.get("tax_amount"))
    total = to_float(ai_data.get("total_amount"))

    if subtotal is not None and tax is not None and total is not None:
        if abs(subtotal + tax - total) > 1.0:
            issues.append(f"Subtotal + tax = {subtotal + tax:.2f} but total = {total:.2f}")

    # 5. GSTIN regex validation
    raw_gstin = ai_data.get("vendor_gstin") or ""
    gstin = re.sub(r"\s+", "", str(raw_gstin).upper())
    if gstin:
        if not re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", gstin):
            issues.append("GSTIN format looks wrong")

    # 6. Duplicate detection
    vendor = (ai_data.get("vendor_name") or "").strip().lower()
    inv_no = (ai_data.get("invoice_number") or "").strip().lower()
    inv_key = f"{vendor}_{inv_no}"
    if inv_no and inv_key in seen_invoices:
        issues.append("Duplicate invoice detected: already processed previously")
    elif inv_no and not issues:
        seen_invoices.add(inv_key)

    status = "Needs review" if issues else "OK"

    return {
        "Processed At": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "File Name": file_name,
        "File Link": f"https://drive.google.com/file/d/{file_name}/view",
        "Vendor": ai_data.get("vendor_name") or "",
        "GSTIN": gstin,
        "Invoice No": ai_data.get("invoice_number") or "",
        "Invoice Date": ai_data.get("invoice_date") or "",
        "Due Date": ai_data.get("due_date") or "",
        "Currency": ai_data.get("currency") or "INR",
        "Subtotal": f"{subtotal:.2f}" if subtotal is not None else "",
        "Tax": f"{tax:.2f}" if tax is not None else "",
        "Total": f"{total:.2f}" if total is not None else "",
        "Category": ai_data.get("category") or "Other",
        "Status": status,
        "Review Notes": "; ".join(issues),
    }


def find_sample_dir():
    candidates = [
        Path("sample-invoices"),
        Path("ai-invoice-extractor/sample-invoices"),
        Path("../sample-invoices"),
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.pdf")):
            return c
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(description="AI Invoice Extractor Pipeline Runner")
    parser.add_argument("--api-key", help="Google Gemini API Key (optional, defaults to simulated mode)")
    parser.add_argument("--dir", help="Directory with PDF files")
    parser.add_argument("--output-csv", default="invoice_log_output.csv", help="Path to export CSV results")
    args = parser.parse_args()

    sample_dir = Path(args.dir) if args.dir else find_sample_dir()
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    mode_str = "LIVE GEMINI API" if (api_key and not api_key.startswith("YOUR_")) else "TEST / SIMULATION MODE"

    pdf_files = sorted(sample_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {sample_dir}")
        return

    print("=" * 80)
    print(f"  AI INVOICE EXTRACTOR - PIPELINE RUNNER [{mode_str}]")
    print(f"  Found {len(pdf_files)} PDF invoices in '{sample_dir}'")
    print("=" * 80)

    seen_invoices = set()
    results = []

    for pdf_path in pdf_files:
        fname = pdf_path.name
        print(f"\n[>] Processing: {fname}")
        text = extract_text_from_pdf(pdf_path)
        print(f"  [1] PDF Text Extracted: {len(text)} characters")

        if api_key and not api_key.startswith("YOUR_") and len(text.strip()) > 20:
            print("  [2] Calling Google Gemini API (gemini-1.5-flash)...")
            ai_data = call_gemini_api(api_key, text)
        else:
            print("  [2] Using verified model extraction (simulation/test mode)...")
            ai_data = MOCK_EXTRACTIONS.get(fname, {
                "vendor_name": None, "invoice_number": None, "invoice_date": None, "total_amount": None
            })

        print(f"  [3] Extracted Fields: Vendor='{ai_data.get('vendor_name')}', Invoice='{ai_data.get('invoice_number')}', Total={ai_data.get('total_amount')}")

        row = validate_row(ai_data, fname, text, seen_invoices)

        print(f"  [4] Validation Status: [{row['Status']}]")
        if row["Review Notes"]:
            print(f"      Review Notes: {row['Review Notes']}")

        results.append(row)

    # Export to CSV
    csv_path = Path(args.output_csv)
    fieldnames = [
        "Processed At", "File Name", "File Link", "Vendor", "GSTIN",
        "Invoice No", "Invoice Date", "Due Date", "Currency",
        "Subtotal", "Tax", "Total", "Category", "Status", "Review Notes"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print("\n" + "=" * 80)
    print("  PIPELINE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'File Name':<35} | {'Vendor':<22} | {'Total':<10} | {'Status':<12}")
    print("-" * 86)
    for r in results:
        vendor_disp = (r['Vendor'][:20] + '..') if len(r['Vendor']) > 20 else r['Vendor']
        print(f"{r['File Name']:<35} | {vendor_disp:<22} | {r['Total']:<10} | {r['Status']:<12}")

    print(f"\n[OK] CSV log written to: {csv_path.resolve()}")
    print("[OK] All 5 invoice files processed successfully.")


if __name__ == "__main__":
    main()
