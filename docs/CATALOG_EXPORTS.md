# Catalog Export Profiles

Catalog Export Profiles are the offline handoff layer after human-confirmed SKU matching.
They create files for downstream commerce/catalog systems without publishing anything.

## Safety contract

Export generation is intentionally fail-closed:

- Every Review Center group must already be human-confirmed in `sku_match_manifest.json`.
- `catalog_ready_for_export` must be true.
- The SKU manifest must still report `publishing_enabled=false`.
- Export generation performs zero network calls.
- Source photos, Review Center state, SKU decisions, and the source catalog are never modified.
- Inventory quantity, fulfillment, shipping promises, tax behavior, and public image URLs are never invented.
- Local image files are written only to an upload manifest for a later explicit publishing/upload stage.

## Profiles

### Shopify draft CSV

`shopify_products_draft.csv` follows Shopify's current product CSV column names used by the official product import/export workflow.

The exporter deliberately writes:

- `Status=draft`
- `Published on online store=false`
- `Option1 name=Default Title`
- `Option1 value=Default Title`
- confirmed catalog SKU/barcode/title/vendor/description/price when available

It does **not** include inventory, fulfillment, shipping/tax, or image URL columns.

Shopify documents that a blank imported Price can default to `0.00`. To avoid silently creating a fake zero price, Shopify export is blocked when a confirmed catalog row has no recognized price or its price contains non-numeric text such as a currency symbol.

Reference: https://help.shopify.com/en/manual/products/import-export/using-csv

### Neutral PIM CSV

`catalog_confirmed_products.csv` is a platform-neutral handoff containing:

- reviewed product group metadata
- confirmed catalog row ID
- ranking score and evidence tier
- SKU/barcode/title/vendor/description/price when present
- local image filenames
- the complete confirmed catalog row snapshot as JSON

PIM-only generation can preserve a missing price as missing data instead of inventing one.

### Local image upload manifest

`image_upload_manifest.csv` contains one row per local product image:

- group ID
- SKU
- image position
- reviewed view
- filename
- resolved local relative path when unique
- blank `public_image_url`
- `status=requires_upload`

A future publishing stage can upload files and populate public URLs explicitly. This exporter never guesses them.

## Validation evidence

`export_validation_issues.csv` records information, warnings, and blocking errors.

Examples:

- missing or unsafe Shopify price: **error**
- duplicate SKU across different groups: warning
- missing barcode: informational
- local image requires upload: informational
- duplicate local filename under the review output: warning

If a blocking error exists, requested import-ready files are not written and stale managed outputs for that requested profile are removed.

## CLI

Generate every safe profile:

```bash
product-sorter \
  --export-catalog path/to/sku_match_manifest.json \
  --export-output path/to/exports \
  --export-profile all
```

Shopify only:

```bash
product-sorter --export-catalog sku_match_manifest.json --export-profile shopify
```

Neutral PIM only:

```bash
product-sorter --export-catalog sku_match_manifest.json --export-profile pim
```

These are standalone actions and do not require an AI provider or API key.

## GUI

The **Exports** workspace uses the same engine as the CLI. It can auto-suggest the SKU match manifest under the current Product Sorter output, choose a profile, generate files in a background worker, and open the resulting folder.

## Current boundary

This feature generates offline staging files only. It does not:

- call Shopify Admin APIs
- upload images
- create or update products remotely
- alter stock/inventory
- publish to sales channels
- write to a PIM/ERP API

Live publishing should remain a separate explicit stage with store credentials, dry-run/preview behavior, idempotency, and rollback/audit requirements.
