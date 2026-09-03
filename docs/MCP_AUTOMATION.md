# MCP, Automation CLI, and Watched Folders

Product Sorter exposes a safe automation surface for local product-shoot and catalog workflows.

## Safety boundary

The automation layer may scan local images, audit missing assets, generate SKU candidate proposals, read the Review Center queue, prepare offline Shopify draft files, and create local approval requests for future external actions. It does **not** expose an MCP or automation command that publishes to Shopify, PIM, or ERP systems.

SKU candidate generation never confirms a match automatically. `prepare-shopify-draft` succeeds only when the existing SKU match manifest says every approved group was explicitly human-confirmed. The generated Shopify output remains `draft`, unpublished, and performs zero network calls.

The v3.3 approval boundary separates agent intent from human authorization. MCP may create an approval request and validate a previously created grant, but it deliberately has no approval tool. A human must use the CLI with the exact `APPROVE <request_id>` phrase to create a local single-use grant. Creating or validating a grant still performs no external action.

A valid grant can now be converted into a **single-use local execution reservation**. Reservation is an atomic local bookkeeping step: it prevents the same approval request from being reserved twice, generates a deterministic idempotency key, stores retry-policy metadata, redacts known credential fields, and appends an execution audit event. It still performs zero network calls and does not execute Shopify/PIM/ERP mutations.

## Automation CLI

After installation, use `product-sorter-automation`:

```text
product-sorter-automation scan ./shoot
product-sorter-automation missing-assets ./catalog.xlsx
product-sorter-automation missing-local ./catalog.xlsx ./shoot
product-sorter-automation propose-matches ./approved_groups.csv ./catalog.xlsx --top-k 5
product-sorter-automation open-review-queue ./product_review_manifest.json
product-sorter-automation prepare-shopify-draft ./sku_matching/sku_match_manifest.json
product-sorter-automation request-external-action shopify.publish ./payload.json ./approval-request.json
product-sorter-automation approve-external-action ./approval-request.json ./approval-grant.json --confirm "APPROVE apr_..."
product-sorter-automation validate-approval ./approval-request.json ./approval-grant.json
product-sorter-automation reserve-approved-action ./approval-request.json ./approval-grant.json ./.execution-state
product-sorter-automation record-execution-result ./.execution-state/reservations/apr_....json ./.execution-state/execution_audit.jsonl --status failed --attempt 1
product-sorter-automation watch ./shoot --state ./.product-sorter-watch.json --interval 5
```

`open-review-queue` is read-only. It returns pending Review Center groups, their metadata, and any photos that originally required review without approving, moving, or editing anything.

`reserve-approved-action` consumes the approval into a local reservation exactly once. Re-running the command for the same request fails closed. The reservation includes a deterministic idempotency key and default retry policy metadata, but does not perform the external action.

`record-execution-result` only appends a local audit record for a future connector execution layer. Known credential fields such as tokens, API keys, passwords, authorization headers, and client secrets are replaced with `[REDACTED]` before being written to the audit log.

`product-sorter-watch` is also available as a direct watched-folder entry point.

The watcher is polling-based and dependency-free. It stores a crash-safe JSON checkpoint containing file path, byte size, and modification time, then emits deterministic `added`, `changed`, and `removed` events. It does not modify or move source images.

## MCP server

MCP support is optional so normal installs stay lightweight:

```text
pip install "ai-product-photo-sorter[mcp]"
product-sorter-mcp
```

The server uses the official Python MCP SDK v2 and stdio transport. It exposes:

- `scan_shoot`
- `show_missing_skus`
- `show_missing_local_skus`
- `propose_matches`
- `open_review_queue`
- `prepare_shopify_draft`
- `request_external_action`
- `validate_external_approval`

There is deliberately no `publish` tool, no MCP approval tool, and no MCP execution tool.

A compatible MCP host can therefore orchestrate a flow like:

```text
scan shoot → show missing SKUs → open review queue → propose matches → human review/confirmation → prepare Shopify draft → request external action → human CLI approval → local single-use reservation
```

The human review/confirmation step cannot be skipped by `prepare_shopify_draft`; the existing catalog exporter fails closed when any match remains pending. The external-action request also cannot approve itself: only a separately executed human CLI confirmation can create the grant. Reservation is kept outside MCP so the agent cannot consume its own approval token.

## What remains outside this milestone

No remote Shopify/PIM/ERP execution consumes the reservation yet. A future connector execution layer must require a valid reservation, reuse its idempotency key across retries, respect retry limits, append redacted execution-result evidence, preserve rollback behavior, and keep publication separately confirmed.

Remote Google Drive/S3 ingestion, Review Center automation UI, release scheduling, and event/rule orchestration remain separate work.
