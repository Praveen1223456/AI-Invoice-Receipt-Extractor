# Make.com Implementation Guide: AI Invoice Extractor

This guide documents the **Make.com** implementation of the AI Invoice & Receipt Extractor. It mirrors the exact logic of the n8n pipeline, allowing direct architectural and functional comparison.

---

## 🏗️ Architecture Overview

```
[Google Drive: Watch Files in a Folder]
        │  Filter: PDFs only (`mimeType = application/pdf`)
        ▼
[Google Drive: Download a File]
        ▼
[Google Gemini AI: Extract structured data]
        ▼
     [Router]
        ├── Route 1: "Valid & Verified" (Filters: required fields + math check) ──► [Google Sheets: Add a Row] (Status = OK)
        └── Route 2: "Needs review"     (Fallback Route)                     ──► [Google Sheets: Add a Row] (Status = Needs review)
```

> **Key Architectural Insight:**  
> In n8n, text is first parsed from the PDF and sent to the LLM. In Make.com, the raw PDF binary is passed directly to the Gemini module. This enables Gemini's multimodal vision to process scanned receipts (such as `05_quickride_scanned_receipt.pdf`) directly, whereas purely text-based extraction pipelines flag scanned documents as unreadable.

---

## 🚀 Quick Option: Import Blueprint JSON

If you want to get started instantly without configuring every module manually:
1. Open [Make.com](https://make.com) and create a new Scenario.
2. Click the **…** (Options) icon in the bottom toolbar and select **Import Blueprint**.
3. Choose the file: [`make/invoice-extractor.make-blueprint.json`](make/invoice-extractor.make-blueprint.json).
4. Re-link your Google Drive, Google Gemini, and Google Sheets connections.

---

## 🛠️ Step-by-Step Manual Build

### Prerequisites
1. **Google Drive Folder:** Create a dedicated folder named `Invoices-Make` (separate from `Invoices-n8n`).
2. **Google Sheet:** In your `Invoice Log` spreadsheet, ensure a tab named `make_log` exists with these headers in row 1:
   ```text
   Processed At, File Name, File Link, Vendor, GSTIN, Invoice No, Invoice Date, Due Date, Currency, Subtotal, Tax, Total, Category, Status, Review Notes
   ```
3. **Gemini API Key:** Obtain an API key from [Google AI Studio](https://aistudio.google.com).

---

### Step 1: Watch Drive Folder (Trigger)
1. Add module: **Google Drive → Watch Files in a Folder**.
2. Connect your Google account.
3. Configure:
   - **Choose a Drive:** `My Drive`
   - **Folder:** `/Invoices-Make`
   - **Watch:** `New files only`
   - **Limit:** `5`
4. Choose **From now on** when prompted.

---

### Step 2: Filter & Download PDF
1. Add module: **Google Drive → Download a File**.
2. Map **File ID**: `{{1.id}}` from the Watch module.
3. Click the link between Module 1 and Module 2 and set up a **Filter**:
   - **Label:** `PDFs only`
   - **Condition:** `{{1.mimeType}}` **Text operators: Equal to** `application/pdf`

---

### Step 3: AI Extraction (Gemini)
1. Add module: **Google Gemini AI → Extract structured data**.
   *(Note: If not available on your Make tier, use **Upload a file** + **Generate a response** with JSON output schema).*
2. Connect your Gemini API Key.
3. **Model:** `gemini-1.5-flash`
4. **Input Data:** Map `{{2.data}}` (binary payload from Download module).
5. **System Instructions:**
   ```text
   You are an accounts-payable assistant that reads invoices and receipts, mostly from Indian businesses.
   Extract the requested fields from the document.

   Rules:
   - Only use values that appear in the document. Never guess. If a field is not present, return null.
   - Dates: Indian documents usually write dates as DD/MM/YYYY or DD-MM-YYYY. Convert every date to YYYY-MM-DD. Example: 03/11/2026 becomes 2026-11-03 (3 November, not 11 March).
   - Amounts: return plain numbers with no currency symbols, words or commas. Indian digit grouping like 1,47,500.00 becomes 147500.
   - subtotal is the taxable value before tax.
   - tax_amount is the total tax: CGST + SGST added together, or IGST, plus any cess.
   - total_amount is the final amount payable, including tax.
   - vendor_name is the business that issued the invoice (the seller), never the customer in 'Bill To'.
   - vendor_gstin is the seller's 15-character GSTIN, never the buyer's.
   - currency is a 3-letter code such as INR or USD. Use INR when amounts are shown with ₹, Rs. or INR.
   - category must be exactly one of: Software & Cloud, Hardware & Equipment, Office & Furniture, Travel, Food & Meals, Utilities, Professional Services, Other.
   - If the text is unreadable or empty, return null for every field and Other for category.
   ```
6. **Data Structure (10 Fields):**
   - `vendor_name` (Text)
   - `vendor_gstin` (Text)
   - `invoice_number` (Text)
   - `invoice_date` (Text)
   - `due_date` (Text)
   - `currency` (Text)
   - `subtotal` (Number)
   - `tax_amount` (Number)
   - `total_amount` (Number)
   - `category` (Text)

---

### Step 4: Router with Dual Paths
Add a **Flow Control → Router** after Module 3.

#### Route 1: Valid & Verified (Status = OK)
Click the link for Route 1 to configure filter conditions (all joined with **AND**):
- `{{3.vendor_name}}` **Exists**
- `{{3.invoice_number}}` **Exists**
- `{{3.invoice_date}}` **Exists**
- `{{3.total_amount}}` **Exists**
- **Math check:** `{{round(3.subtotal + 3.tax_amount)}}` **Numeric operators: Equal to** `{{round(3.total_amount)}}`

Connect **Google Sheets → Add a Row**:
- **Spreadsheet:** `Invoice Log` | **Sheet:** `make_log`
- Map values:
  - `Processed At`: `{{formatDate(now; "YYYY-MM-DD HH:mm"; "Asia/Kolkata")}}`
  - `File Name`: `{{1.name}}`
  - `File Link`: `{{1.webViewLink}}`
  - `Vendor`: `{{3.vendor_name}}`
  - `GSTIN`: `{{3.vendor_gstin}}`
  - `Invoice No`: `{{3.invoice_number}}`
  - `Invoice Date`: `{{3.invoice_date}}`
  - `Due Date`: `{{3.due_date}}`
  - `Currency`: `{{ifempty(3.currency; "INR")}}`
  - `Subtotal`: `{{3.subtotal}}`
  - `Tax`: `{{3.tax_amount}}`
  - `Total`: `{{3.total_amount}}`
  - `Category`: `{{ifempty(3.category; "Other")}}`
  - `Status`: `OK`
  - `Review Notes`: *(leave blank)*

#### Route 2: Needs Review (Fallback)
Click the link for Route 2:
- Set **Fallback route**: **Yes** (Executes automatically when Route 1 filters fail).

Clone the Google Sheets module and change:
- `Status`: `Needs review`
- `Review Notes`: `Missing required field (vendor, invoice no, date, total) or subtotal + tax != total`

---

## 🧪 Test Data & Expected Outcomes

| Test Sample | Features Tested | Expected Status in Make.com |
|---|---|---|
| `01_cloudnine_clean_cgst_sgst.pdf` | Clean intra-state GST (CGST + SGST), DD/MM/YYYY date | **OK** |
| `02_sharma_furniture_igst_lakh.pdf` | Inter-state IGST, lakh digit formatting (`1,47,500.00`) | **OK** |
| `03_udupi_restaurant_receipt.pdf` | Retail receipt without GSTIN | **OK** |
| `04_brightspark_wrong_total.pdf` | Math mismatch (10,000 + 1,800 != 12,800) | **Needs review** |
| `05_quickride_scanned_receipt.pdf` | Scanned image receipt (no text layer) | **OK** *(Gemini multimodal processes image)* |
