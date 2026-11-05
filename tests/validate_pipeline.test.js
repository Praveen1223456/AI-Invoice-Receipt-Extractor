/**
 * Unit tests for AI Invoice Extractor validation logic
 * Tests all 5 sample invoice scenarios, edge cases, malformed outputs, and error handling.
 */

const assert = require('assert');

// The validation logic function extracted directly from n8n Code Node
function validateAndFormatRow(itemJson, fileMeta, pdfText = '', staticData = { processedInvoices: [] }) {
  let ai = itemJson.output ?? {};
  const issues = [];

  // Upstream error handling (API failures / rate limits)
  if (itemJson.error) {
    const errorMsg = typeof itemJson.error === 'object'
      ? (itemJson.error.message || JSON.stringify(itemJson.error))
      : String(itemJson.error);
    issues.push(`AI API failure: ${errorMsg}`);
  }

  // Defensive parsing for malformed AI response (strings / markdown fences)
  if (typeof ai === 'string') {
    try {
      const cleaned = ai.replace(/```(?:json)?/gi, '').replace(/```/g, '').trim();
      ai = JSON.parse(cleaned);
    } catch (e) {
      issues.push('Malformed AI output: could not parse JSON');
      ai = {};
    }
  }

  // 1. Scanned PDFs have no readable text layer
  if (typeof pdfText === 'string' && pdfText.trim().length <= 20) {
    issues.push('No readable text in PDF (scanned image?)');
  }

  // 2. Mandatory fields check
  for (const field of ['vendor_name', 'invoice_number', 'invoice_date', 'total_amount']) {
    if (ai[field] === null || ai[field] === undefined || String(ai[field]).trim() === '') {
      issues.push(`Missing ${field}`);
    }
  }

  // 3. Strict calendar date validation (YYYY-MM-DD)
  const isValidDate = (d) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d ?? '')) return false;
    const [year, month, day] = d.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
  };

  if (ai.invoice_date && !isValidDate(ai.invoice_date)) {
    issues.push('Invoice date is not valid YYYY-MM-DD');
  }
  if (ai.due_date && !isValidDate(ai.due_date)) {
    issues.push('Due date is not valid YYYY-MM-DD');
  }

  // 4. Arithmetic consistency check (subtotal + tax = total, tolerance Rs. 1.0)
  const toNumber = (v) =>
    v === null || v === undefined || v === '' ? null : Number(String(v).replace(/,/g, ''));
  const subtotal = toNumber(ai.subtotal);
  const tax = toNumber(ai.tax_amount);
  const total = toNumber(ai.total_amount);

  if (subtotal !== null && tax !== null && total !== null && Math.abs(subtotal + tax - total) > 1.0) {
    issues.push(`Subtotal + tax = ${(subtotal + tax).toFixed(2)} but total = ${total.toFixed(2)}`);
  }

  // 5. Indian GSTIN regex validation (when present)
  const gstin = (ai.vendor_gstin ?? '').toUpperCase().replace(/\s/g, '');
  if (gstin && !/^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(gstin)) {
    issues.push('GSTIN format looks wrong');
  }

  // 6. Duplicate detection check
  const invoiceKey = `${(ai.vendor_name || '').trim().toLowerCase()}_${(ai.invoice_number || '').trim().toLowerCase()}`;
  if (ai.invoice_number && staticData.processedInvoices.includes(invoiceKey)) {
    issues.push('Duplicate invoice detected: already processed previously');
  } else if (ai.invoice_number && issues.length === 0) {
    staticData.processedInvoices.push(invoiceKey);
  }

  const status = issues.length ? 'Needs review' : 'OK';

  return {
    'Processed At': '2026-11-05 15:00',
    'File Name': fileMeta.name ?? '',
    'File Link': fileMeta.webViewLink ?? `https://drive.google.com/file/d/${fileMeta.id}/view`,
    'Vendor': ai.vendor_name ?? '',
    'GSTIN': gstin,
    'Invoice No': ai.invoice_number ?? '',
    'Invoice Date': ai.invoice_date ?? '',
    'Due Date': ai.due_date ?? '',
    'Currency': ai.currency ?? 'INR',
    'Subtotal': subtotal ?? '',
    'Tax': tax ?? '',
    'Total': total ?? '',
    'Category': ai.category ?? 'Other',
    'Status': status,
    'Review Notes': issues.join('; '),
  };
}

console.log('--- Starting Test Suite for AI Invoice Extractor ---');

let passed = 0;
let totalTests = 0;

function runTest(testName, fn) {
  totalTests++;
  try {
    fn();
    console.log(`  PASS: ${testName}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL: ${testName}`);
    console.error(`    ${err.message}`);
  }
}

// Global state for duplicate checks
const testState = { processedInvoices: [] };

// Test 1: Sample 01 - Clean intra-state GST invoice
runTest('Sample 01: Clean intra-state invoice with CGST+SGST', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'CloudNine Software Solutions Pvt Ltd',
        vendor_gstin: '29AACCC1234F1Z5',
        invoice_number: 'CNS/2026-27/0142',
        invoice_date: '2026-10-14',
        due_date: '2026-11-13',
        currency: 'INR',
        subtotal: 13500.00,
        tax_amount: 2430.00,
        total_amount: 15930.00,
        category: 'Software & Cloud',
      },
    },
    { name: '01_cloudnine_clean_cgst_sgst.pdf', id: 'drive-file-01' },
    'TAX INVOICE CloudNine Software Solutions Pvt Ltd GSTIN: 29AACCC1234F1Z5 Cloud hosting 12,000 Taxable Value 13,500 Total Amount 15,930',
    testState
  );

  assert.strictEqual(result['Status'], 'OK');
  assert.strictEqual(result['Vendor'], 'CloudNine Software Solutions Pvt Ltd');
  assert.strictEqual(result['GSTIN'], '29AACCC1234F1Z5');
  assert.strictEqual(result['Total'], 15930);
  assert.strictEqual(result['Review Notes'], '');
});

// Test 2: Sample 02 - Inter-state IGST with lakh grouping
runTest('Sample 02: Inter-state invoice with IGST & lakh grouping', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'Sharma Office Furniture Co.',
        vendor_gstin: '07ABHPS4321M1Z8',
        invoice_number: 'SOF-7781',
        invoice_date: '2026-11-03',
        due_date: '2026-12-03',
        currency: 'INR',
        subtotal: 125000.00,
        tax_amount: 22500.00,
        total_amount: 147500.00,
        category: 'Office & Furniture',
      },
    },
    { name: '02_sharma_furniture_igst_lakh.pdf', id: 'drive-file-02' },
    'TAX INVOICE Sharma Office Furniture Co. GSTIN: 07ABHPS4321M1Z8 Bill No: SOF-7781 Taxable Value 1,25,000.00 IGST 22,500.00 Rs. 1,47,500.00',
    testState
  );

  assert.strictEqual(result['Status'], 'OK');
  assert.strictEqual(result['Total'], 147500);
});

// Test 3: Sample 03 - Restaurant receipt without GSTIN
runTest('Sample 03: Restaurant receipt without GSTIN', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'Udupi Grand Restaurant',
        vendor_gstin: null,
        invoice_number: '45821',
        invoice_date: '2026-10-28',
        due_date: null,
        currency: 'INR',
        subtotal: 1320.00,
        tax_amount: 66.00,
        total_amount: 1386.00,
        category: 'Food & Meals',
      },
    },
    { name: '03_udupi_restaurant_receipt.pdf', id: 'drive-file-03' },
    'Udupi Grand Restaurant Bill No: 45821 Date: 28/10/2026 Meals 1,080 Sub Total 1,320 CGST 33 SGST 33 Rs. 1,386.00',
    testState
  );

  assert.strictEqual(result['Status'], 'OK');
  assert.strictEqual(result['GSTIN'], '');
});

// Test 4: Sample 04 - Maths discrepancy (subtotal + tax != total)
runTest('Sample 04: Math check flags arithmetic discrepancy', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'BrightSpark Electricals',
        vendor_gstin: '36AAGFB5555Q1Z9',
        invoice_number: 'BSE/1093',
        invoice_date: '2026-10-21',
        due_date: null,
        currency: 'INR',
        subtotal: 10000.00,
        tax_amount: 1800.00,
        total_amount: 12800.00, // 10000 + 1800 is 11800, NOT 12800
        category: 'Utilities',
      },
    },
    { name: '04_brightspark_wrong_total.pdf', id: 'drive-file-04' },
    'TAX INVOICE BrightSpark Electricals Invoice No: BSE/1093 Taxable Value 10,000 Total 12,800',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /Subtotal \+ tax = 11800\.00 but total = 12800\.00/);
});

// Test 5: Sample 05 - Scanned PDF (no text layer)
runTest('Sample 05: Scanned PDF with no text layer flagged for review', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: null,
        vendor_gstin: null,
        invoice_number: null,
        invoice_date: null,
        due_date: null,
        currency: null,
        subtotal: null,
        tax_amount: null,
        total_amount: null,
        category: 'Other',
      },
    },
    { name: '05_quickride_scanned_receipt.pdf', id: 'drive-file-05' },
    '', // empty text extracted from image
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /No readable text in PDF \(scanned image\?\)/);
});

// Test 6: Missing required fields
runTest('Edge Case: Missing required fields (vendor, invoice_number, etc.)', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: '',
        vendor_gstin: '29AACCC1234F1Z5',
        invoice_number: null,
        invoice_date: '2026-10-14',
        total_amount: null,
      },
    },
    { name: 'missing_fields.pdf', id: 'id-6' },
    'Some text content here that has more than twenty characters',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /Missing vendor_name/);
  assert.match(result['Review Notes'], /Missing invoice_number/);
  assert.match(result['Review Notes'], /Missing total_amount/);
});

// Test 7: Invalid date format and nonexistent calendar date
runTest('Edge Case: Invalid date format (e.g. DD/MM/YYYY or Feb 31)', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'Test Corp',
        invoice_number: 'INV-001',
        invoice_date: '2026-02-31', // invalid date
        total_amount: 500,
        subtotal: 500,
        tax_amount: 0,
      },
    },
    { name: 'bad_date.pdf', id: 'id-7' },
    'Invoice text with more than twenty characters present',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /Invoice date is not valid YYYY-MM-DD/);
});

// Test 8: Malformed GSTIN
runTest('Edge Case: Malformed GSTIN format', () => {
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'Test Corp',
        invoice_number: 'INV-002',
        invoice_date: '2026-10-10',
        vendor_gstin: '29INVALIDGSTIN', // invalid format
        total_amount: 500,
        subtotal: 500,
        tax_amount: 0,
      },
    },
    { name: 'bad_gstin.pdf', id: 'id-8' },
    'Invoice text with more than twenty characters present',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /GSTIN format looks wrong/);
});

// Test 9: Malformed AI output (JSON string inside markdown codeblock)
runTest('Resilience: Stringified AI response with markdown fences parsed gracefully', () => {
  const stringifiedJson = '```json\n{\n  "vendor_name": "Markdown Vendor",\n  "invoice_number": "MD-99",\n  "invoice_date": "2026-10-10",\n  "total_amount": 1000,\n  "subtotal": 900,\n  "tax_amount": 100\n}\n```';
  const result = validateAndFormatRow(
    { output: stringifiedJson },
    { name: 'markdown_ai.pdf', id: 'id-9' },
    'Invoice text with more than twenty characters present',
    testState
  );

  assert.strictEqual(result['Status'], 'OK');
  assert.strictEqual(result['Vendor'], 'Markdown Vendor');
  assert.strictEqual(result['Invoice No'], 'MD-99');
});

// Test 10: AI API Failure handling
runTest('Resilience: Upstream API failure handled cleanly without workflow crash', () => {
  const result = validateAndFormatRow(
    {
      error: { message: 'Gemini API 429: Resource has been exhausted (rate limit)' },
    },
    { name: 'failed_api.pdf', id: 'id-10' },
    'Invoice text with more than twenty characters present',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /AI API failure: Gemini API 429/);
});

// Test 11: Duplicate invoice detection
runTest('Detection: Duplicate invoice detected and flagged', () => {
  // First run with Sample 01 succeeded and added key to testState
  // Now submit the same invoice number and vendor again:
  const result = validateAndFormatRow(
    {
      output: {
        vendor_name: 'CloudNine Software Solutions Pvt Ltd',
        vendor_gstin: '29AACCC1234F1Z5',
        invoice_number: 'CNS/2026-27/0142',
        invoice_date: '2026-10-14',
        total_amount: 15930.00,
        subtotal: 13500.00,
        tax_amount: 2430.00,
      },
    },
    { name: '01_cloudnine_duplicate.pdf', id: 'drive-file-01-dup' },
    'TAX INVOICE CloudNine Software Solutions Pvt Ltd GSTIN: 29AACCC1234F1Z5',
    testState
  );

  assert.strictEqual(result['Status'], 'Needs review');
  assert.match(result['Review Notes'], /Duplicate invoice detected/);
});

console.log(`\nTest Summary: ${passed} / ${totalTests} tests passed.`);
if (passed === totalTests) {
  console.log('ALL TESTS PASSED SUCCESSFULLY! \u2713\n');
} else {
  console.error('SOME TESTS FAILED! \u2717\n');
  process.exit(1);
}
