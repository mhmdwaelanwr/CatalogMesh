# MCP, Automation CLI, and Watched Folders

Product Sorter exposes a safe automation surface for local product-shoot and catalog workflows.

## Safety boundary

The automation layer may scan local images, audit missing assets, generate SKU candidate proposals, and prepare offline Shopify draft files. It does **not** expose an MCP or automation command that publishes to Shopify, PIM, or ERP systems.

SKU candidate generation never confirms a match automatically. `prepare-shopify-draft` succeeds only when the existing SKU match manifest says every approved group was explicitly human-confirmed. The generated Shopify output remains `draft`, unpublished, and performs zero network calls.

## Automation CLI

After installation, use `product-sorter-automation`:

```text
product-sorter-automation scan ./shoot
product-sorter-automation missing-assets ./catalog.xlsx
product-sorter-automation missing-local ./catalog.xlsx ./shoot
product-sorter-automation propose-matches ./approved_groups.csv ./catalog.xlsx --top-k 5
product-sorter-automation prepare-shopify-draft ./sku_matching/sku_match_manifest.json
product-sorter-automation watch ./shoot --state ./.product-sorter-watch.json --interval 5
```

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
- `prepare_shopify_draft`

There is deliberately no `publish` tool in the MCP surface.

A compatible MCP host can therefore orchestrate a flow like:

```text
scan shoot → show missing SKUs → propose matches → human review/confirmation → prepare Shopify draft
```

The human review/confirmation step cannot be skipped by `prepare_shopify_draft`; the existing catalog exporter fails closed when any match remains pending.

## What remains outside this milestone

Remote Google Drive/S3 ingestion, Review Center automation UI, approval-aware remote Shopify/PIM/ERP mutation tools, release scheduling, and event/rule orchestration remain separate work. Any future remote-write tool must preserve explicit approval, audit, idempotency, and rollback boundaries.
