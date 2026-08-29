# SKU / Catalog Candidate Matching

Product Sorter's SKU matching stage connects **human-approved product groups** to an existing product catalog without silently trusting OCR, barcodes, or fuzzy text.

The workflow is intentionally:

```text
Review Center approved groups
        +
optional local OCR / barcode evidence
        +
existing XLSX / XLSM / CSV catalog
        ↓
ranked catalog candidates
        ↓
explicit human confirmation
        ↓
confirmed_catalog_matches.csv
```

## Safety contract

Candidate generation does **not** create a catalog match automatically, even when an EAN/UPC/GTIN barcode is exact.

Every generated manifest reports:

- `automatic_matching_enabled = false`
- `human_confirmation_required = true`
- `publishing_enabled = false`

A group becomes confirmed only after a human selects a current candidate through the CLI or desktop workspace. Product photos, Review Center state, and the source catalog are never modified by SKU matching.

## Inputs

### Approved Review Center groups

SKU matching consumes `approved_product_groups.csv`, not the raw classification report and not pending Review Center groups. This keeps downstream catalog work behind the human review gate.

### Catalog

Supported catalog files:

- `.xlsx`
- `.xlsm`
- `.csv`

Recognized structured fields include common SKU/model/MPN/item/part identifiers and barcode aliases such as EAN, UPC, and GTIN. Files without recognized headers are still read as generic columns.

Catalog rows receive stable evidence-local IDs such as:

```text
Products!R42
```

The ID identifies the worksheet and original row number; the source file itself is not edited.

### Optional Local Evidence

`local_catalog_evidence.json` from the Local OCR + Barcode Evidence stage can strengthen ranking with:

- decoded barcode values;
- OCR-labeled SKU/model/MPN identifiers;
- weaker OCR identifier tokens.

Only evidence belonging to filenames inside the approved product group is aggregated for that group.

## Ranking order

The deterministic matcher favors evidence in this order:

1. exact barcode evidence;
2. exact labeled SKU/model identifier;
3. exact approved model;
4. OCR identifier evidence;
5. brand/model/category/context overlap.

`ranking_score` is a **ranking signal, not a calibrated probability**. A score of `1.0` does not authorize an automatic match.

Each candidate includes a `tier`, supporting reasons, original catalog fields, display text, and rank.

## CLI

Generate candidates:

```bash
product-sorter \
  --sku-match output/approved_product_groups.csv \
  --sku-catalog As3ar.xlsx \
  --sku-evidence output/product_sorter_local_evidence/local_catalog_evidence.json \
  --sku-output output/sku_matching \
  --sku-top-k 5
```

The evidence file is optional.

Confirm one current candidate:

```bash
product-sorter \
  --sku-confirm output/sku_matching/sku_match_manifest.json \
  --sku-group Product_0001_Example_M100 \
  --sku-row 'Catalog!R17'
```

Clear a confirmation:

```bash
product-sorter \
  --sku-clear output/sku_matching/sku_match_manifest.json \
  --sku-group Product_0001_Example_M100
```

No AI provider or API key is required for these standalone actions.

## Desktop workspace

The **SKU Match** workspace uses the same engine as the CLI. It provides:

- Approved groups, catalog, and optional evidence paths;
- background candidate generation for large catalogs;
- group confirmation state;
- ranked candidate rows with score, evidence tier, catalog row ID, and reasons;
- an explicit **Confirm selected** action;
- clear-confirmation and confirmed-CSV actions.

The confirmation dialog explicitly states that no publish action will run.

## Outputs

`sku_matching/` contains:

- `sku_match_manifest.json` — candidates, evidence, decisions, and safety state;
- `sku_match_candidates.csv` — flattened ranked suggestions;
- `confirmed_catalog_matches.csv` — only human-confirmed groups;
- `sku_match_audit.jsonl` — append-only confirmation/clear events.

`catalog_ready_for_export=true` means every current approved product group has a human-confirmed catalog row. It does **not** mean Shopify, ERP, PIM, or any other external system has been updated.

## CI evidence

The deterministic mock pipeline now exercises:

```text
Mock grouping / Hybrid evidence
→ Review Center corrections and approval
→ SKU candidate generation
→ zero automatic confirmations
→ explicit mock human confirmations
→ catalog-ready confirmed export
```

The same pipeline snapshots all product JPG paths and SHA-256 hashes before Review/SKU actions and verifies them afterward, so metadata workflows cannot silently mutate the product photos.

Synthetic CI results are engineering evidence only and are not a claim about real-catalog matching accuracy.
