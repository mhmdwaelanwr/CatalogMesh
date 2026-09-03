# MCP, Automation CLI, and Watched Folders

Product Sorter exposes a safe automation surface for local product-shoot and catalog workflows.

## Safety boundary

The automation layer may scan local images, audit missing assets, generate SKU candidate proposals, read the Review Center queue, prepare offline Shopify draft files, and create local approval requests for future external actions. It does **not** expose an MCP or automation command that publishes to Shopify, PIM, or ERP systems.

SKU candidate generation never confirms a match automatically. `prepare-shopify-draft` succeeds only when the existing SKU match manifest says every approved group was explicitly human-confirmed. The generated Shopify output remains `draft`, unpublished, and performs zero network calls.

The v3.3 approval boundary separates agent intent from human authorization. MCP may create an approval request and validate a previously created grant, but it deliberately has no approval tool. A human must use the CLI with the exact `APPROVE <request_id>` phrase to create a local single-use grant. Creating or validating a grant still performs no external action.

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
product-sorter-automation watch ./shoot --state ./.product-sorter-watch.json --interval 5
```

`open-review-queue` is read-only. It returns pending Review Center groups, their metadata, and any photos that originally required review without approving, moving, or editing anything.

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

There is deliberately no `publish` tool and no MCP approval tool.

A compatible MCP host can therefore orchestrate a flow like:

```text
scan shoot → show missing SKUs → open review queue → propose matches → human review/confirmation → prepare Shopify draft → request external action → human CLI approval
```

The human review/confirmation step cannot be skipped by `prepare_shopify_draft`; the existing catalog exporter fails closed when any match remains pending. The external-action request also cannot approve itself: only a separately executed human CLI confirmation can create the grant.

## What remains outside this milestone

The approval grant is a local authorization artifact only. No remote Shopify/PIM/ERP execution consumes it yet. Before any future remote-write adapter is enabled, it must verify the request/grant pair, enforce single-use semantics, append audit evidence, preserve connector idempotency, and retain rollback-safe publishing behavior.

Remote Google Drive/S3 ingestion, Review Center automation UI, release scheduling, and event/rule orchestration remain separate work.
