# Guarded Shopify Publishing

Product Sorter can move from human-confirmed catalog matches to Shopify without making publishing automatic.

The remote workflow is intentionally split into four gates:

1. **Local Plan** — zero network access.
2. **Remote Preview** — Shopify queries only, zero remote writes.
3. **Stage Drafts** — explicit remote write gate; products remain `DRAFT` and unpublished.
4. **Explicit Publish** — requires a publication ID and the exact confirmation text `PUBLISH`.

A fifth **Rollback** action unpublishes Product Sorter-managed products and returns them to `DRAFT` after the exact confirmation text `UNPUBLISH`.

## Shopify API

The implementation targets Shopify Admin GraphQL API `2026-07` by default. Override it with `SHOPIFY_API_VERSION` only after validating compatibility.

Primary operations:

- `productVariants` exact-SKU lookup before writes
- `stagedUploadsCreate` for local product images
- `productCreate` for new draft products
- `productUpdate` for Product Sorter-managed draft products and status transitions
- `productVariantsBulkUpdate` for the initial variant price, barcode and SKU
- `publishablePublish` for the explicit publication step
- `publishableUnpublish` for rollback

Shopify's REST Admin API is not used.

## Configuration

Use Environment Center or `.env`:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_API_VERSION=2026-07
SHOPIFY_PUBLICATION_ID=gid://shopify/Publication/123456789
USE_KEYRING=true
```

Store `SHOPIFY_ADMIN_ACCESS_TOKEN` as a sensitive value in Environment Center / OS keyring. Do **not** pass it as a CLI argument.

The integration needs the Shopify permissions required by the operations you enable, including product writes and publication writes. Image staging must also be permitted by the installed app configuration.

## CLI

### 1. Local plan — no Shopify credentials required

```bash
product-sorter \
  --shopify-plan output/exports/catalog_export_manifest.json \
  --shopify-output output/exports/shopify_remote
```

Creates:

- `shopify_publish_plan.json`

The plan records product fingerprints, SKU, price, images, the forced remote `DRAFT` status, and `inventory_writes_enabled=false`.

### 2. Remote preview — queries only

```bash
product-sorter \
  --shopify-preview output/exports/catalog_export_manifest.json \
  --shopify-output output/exports/shopify_remote
```

Creates:

- `shopify_remote_preview.json`

The preview checks exact remote SKU matches and reports whether each product is a create candidate or a collision. It performs no remote mutation.

### 3. Stage drafts — explicit remote write

```bash
product-sorter \
  --shopify-stage output/exports/catalog_export_manifest.json \
  --shopify-output output/exports/shopify_remote \
  --shopify-apply
```

Without `--shopify-apply`, the CLI refuses to write.

New products are created as `DRAFT`. Product Sorter records their Shopify product/variant IDs in `shopify_publish_manifest.json` and appends every mutation to `shopify_publish_audit.jsonl`.

Local product images are uploaded through Shopify staged uploads only for a newly created managed product. Existing unmanaged SKUs are blocked rather than overwritten.

Use `--shopify-no-images` when you intentionally want draft product staging without image upload.

### 4. Publish — second explicit gate

```bash
product-sorter \
  --shopify-publish output/exports/shopify_remote/shopify_publish_manifest.json \
  --shopify-publication-id gid://shopify/Publication/123456789 \
  --shopify-confirm PUBLISH
```

Publishing first activates the managed product, then publishes it to the specified publication. No staged product is made active automatically during the draft stage.

### 5. Rollback publication

```bash
product-sorter \
  --shopify-rollback output/exports/shopify_remote/shopify_publish_manifest.json \
  --shopify-confirm UNPUBLISH
```

Rollback unpublishes the Product Sorter-managed product from the recorded publication and returns its Shopify product status to `DRAFT`.

## Idempotency / collision policy

Product Sorter keeps a local state manifest with a deterministic fingerprint for every staged SKU.

Before each stage operation it also performs an exact-SKU remote lookup:

- no remote SKU → create a new draft
- exactly one remote SKU already mapped to this Product Sorter state → managed update is allowed
- remote SKU exists but isn't mapped to this state → **blocked**
- multiple exact remote SKU matches → **blocked**
- unchanged managed fingerprint → skipped

This prevents normal retries from creating duplicate products and prevents Product Sorter from silently adopting or overwriting an existing merchant product.

## Inventory safety

This feature does not set inventory quantities, locations, fulfillment behavior, shipping promises, tax settings, or stock availability.

`inventory_writes_enabled` remains `false` in plan/state evidence. The SKU is written to the variant inventory item, but quantity is not changed.

Inventory synchronization should be a separate integration with its own source-of-truth policy and safety checks.

## Audit evidence

Remote mutations append records to:

- `shopify_publish_audit.jsonl`

State is persisted atomically in:

- `shopify_publish_manifest.json`

The audit records draft creation/update, explicit publishing, and rollback separately.

## Current image behavior

For newly created products, local images are uploaded using `stagedUploadsCreate` and attached as product media during `productCreate`.

For an already managed existing product, metadata and variant data can be refreshed, but this first implementation intentionally does not replace/delete its existing media gallery. Media reconciliation should be implemented as a separate measured stage to avoid accidental duplication or deletion.

## Safety contract

The feature must continue to preserve these rules:

- offline export remains the required upstream source
- products must already be human-confirmed before the offline export exists
- local plan has zero network calls
- remote preview has zero writes
- stage requires explicit apply and keeps products draft
- unmanaged existing SKUs are never overwritten
- inventory quantities are never modified
- publish requires exact explicit confirmation
- rollback is available and audited
- Shopify access token is never printed or accepted as a normal CLI argument
