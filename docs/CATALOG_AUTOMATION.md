# Catalog Automation Foundation

Product Sorter is expanding from a desktop photo sorter into a local-first catalog-image automation layer. This phase adds orchestration primitives without weakening the existing human-review and guarded publishing boundaries.

## Included in this phase

### Shoot ingestion snapshots

`ai_product_photo_sorter.ingestion` scans local image folders without moving, renaming, uploading, or editing source files. Snapshots contain only path, size, and modification metadata. `diff_snapshots()` reports added, changed, and removed assets so a later watched-folder service can react incrementally instead of reprocessing an entire shoot.

### Missing Asset Audit

`ai_product_photo_sorter.missing_assets` provides deterministic catalog audits for:

- SKUs with no image reference in configured catalog columns.
- SKUs with no exact same-stem local image candidate.

The exact-stem helper is deliberately conservative. It is evidence for review, not an automatic SKU confirmation mechanism.

### Agent tool registry

`ai_product_photo_sorter.agent_tools` introduces a small tool registry intended to be adapted to MCP, desktop automation, CLI automation, and workflow engines such as n8n later.

The default registry exposes only read-only/local operations:

- `scan_shoot`
- `find_missing_assets`

The registry refuses any tool marked `mutates_external_state=True`. Shopify, PIM, ERP, DAM, and other remote write operations must use a separate approval-aware execution boundary and must preserve the existing human confirmation, audit, idempotency, and rollback rules.

## Planned next adapters

1. Persistent watched folders with debouncing and crash-safe checkpoints.
2. Google Drive and S3-compatible ingestion adapters that materialize into the same local ingestion contract.
3. Missing-asset reports in CLI and desktop Review Center.
4. MCP transport exposing safe tools such as `scan_shoot`, `find_unmatched_skus`, `propose_matches`, `open_review_queue`, and `prepare_shopify_draft`.
5. Approval-gated write tool surface for Shopify/PIM/ERP connectors.
6. Variant-level asset mapping, release scheduling, and append-only automation audit events.

## Security and privacy rules

- Local scans must not upload image bytes.
- Agent calls must never bypass Review Center or SKU confirmation.
- External writes must be explicit, authenticated, idempotent, and audited.
- Publishing must remain a separate confirmation from staging/draft preparation.
- Connector credentials must never appear in manifests, reports, or agent responses.
