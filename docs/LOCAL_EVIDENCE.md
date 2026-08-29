# Local OCR + Barcode Evidence

Product Sorter can collect catalog-identification evidence from product photos entirely on the local machine before any future SKU/catalog matching step.

This stage is intentionally **evidence-only**. It does not change product grouping, choose a catalog row, rename a product from a detected code, or publish anything.

## Optional local runtime

The default Product Sorter install remains lightweight. Install the evidence runtime only when needed:

```bash
python -m pip install "ai-product-photo-sorter[local-evidence]"
```

The optional extra contains:

- **RapidOCR** — offline OCR using compact local models;
- **ONNX Runtime** — local inference engine used by RapidOCR;
- **ZXing-C++** — local barcode/QR decoder.

No cloud API key is required for this workflow.

## Evidence types

### OCR

OCR records recognized text and confidence scores from product packaging, labels, stickers, model plates, and printed SKU/MPN text.

The evidence layer also extracts candidate identifiers from labels such as:

```text
SKU: ABC-1234
MODEL M185
MPN: 920-002478
```

Generic mixed alphanumeric tokens are retained as weaker OCR candidates rather than treated as verified SKU values.

### Barcode / QR

ZXing-C++ is used for formats including product EAN/UPC codes, Code128, QR, and DataMatrix when present in the image.

A decoded barcode is high-value deterministic evidence, but it is still only a candidate until a later catalog-matching layer confirms what the code represents in the user's catalog.

## CLI

```bash
product-sorter \
  --local-evidence /path/to/product-photos \
  --local-evidence-output ./local-evidence
```

Optional controls:

```text
--local-evidence-no-ocr
--local-evidence-no-barcode
--local-evidence-ocr-score 0.60
```

## Desktop GUI

Open **Benchmark Center → Local OCR + Barcode Evidence**.

The card lets the user enable/disable OCR and barcode scanning and choose a source/output folder. The scan runs on a worker thread so the Tkinter interface remains responsive while local OCR is running.

## Outputs

The scan writes:

- `local_catalog_evidence.json` — complete per-photo structured evidence plus run summary;
- `local_catalog_evidence.csv` — spreadsheet-friendly evidence summary.

Run metrics include:

- OCR photo coverage;
- barcode photo coverage;
- identifier-candidate coverage;
- OCR region count;
- decoded barcode count;
- local throughput;
- backend errors by photo.

A backend failure on one photo is recorded on that photo and does not abort the entire evidence scan.

## Safety contract

Every run reports:

```text
mode = local_evidence
production_matching_enabled = false
production_routing_enabled = false
```

The evidence layer does not decide that two photos belong together and does not decide which SKU a product is. Those decisions remain separate measured stages.

## Why this matters for the hybrid pipeline

Visual embeddings answer **"does this look like the same product?"** while OCR/barcodes can answer **"what printed identifier evidence is visible?"**.

Combining those signals later allows Product Sorter to distinguish visually similar variants more reliably and gives SKU matching deterministic evidence before asking a Vision LLM or a human reviewer.
