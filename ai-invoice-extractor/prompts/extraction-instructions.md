# Extraction instructions (shared by n8n and Make)

Both versions of the pipeline send the AI the same instructions and ask for the same fields, so their results can be compared row for row.

## System instructions

Paste this into the n8n **Information Extractor → Options → System Prompt Template** (already done in the workflow file) and into the Make **Gemini → Extract structured data** instructions field.

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
- vendor_name is the business that issued the invoice (the seller), never the customer in "Bill To".
- vendor_gstin is the seller's 15-character GSTIN, never the buyer's.
- currency is a 3-letter code such as INR or USD. Use INR when amounts are shown with ₹, Rs. or INR.
- category must be exactly one of: Software & Cloud, Hardware & Equipment, Office & Furniture, Travel, Food & Meals, Utilities, Professional Services, Other.
- If the text is NO_TEXT_FOUND, return null for every field and Other for category.
```

## Output fields

| Field | Type | Description |
|---|---|---|
| `vendor_name` | text or null | Business that issued the invoice (the seller) |
| `vendor_gstin` | text or null | Seller's 15-character GSTIN, if shown |
| `invoice_number` | text or null | Invoice or bill number |
| `invoice_date` | text or null | Invoice date as YYYY-MM-DD |
| `due_date` | text or null | Payment due date as YYYY-MM-DD, if shown |
| `currency` | text or null | 3-letter code, for example INR |
| `subtotal` | number or null | Taxable amount before tax |
| `tax_amount` | number or null | Total tax (CGST + SGST, or IGST, plus cess) |
| `total_amount` | number or null | Final amount payable including tax |
| `category` | one of the 8 categories | Expense category |

## Why the rules are written this way

Each rule fixes a mistake language models commonly make on Indian invoices. Without the date rule, 03/11/2026 is often read the American way as 11 March. Without the amount rule, lakh grouping (1,47,500) sometimes comes back as text or loses digits. Without the seller/buyer rules, the model sometimes picks the customer's name and GSTIN, because both appear on the page. Asking for `null` instead of a guess matters most of all: a blank cell gets flagged for review, while a confident wrong number goes straight into your accounts.
