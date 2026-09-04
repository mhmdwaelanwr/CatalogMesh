# CatalogMesh

**CatalogMesh** is a cross-platform AI workspace for product catalog operations: product-photo grouping, human review, SKU matching, exports, storage and guarded catalog automation.

## Install

Requires Python 3.10 or newer.

```bash
python -m pip install --upgrade catalogmesh
```

Launch the desktop GUI:

```bash
catalogmesh-gui
```

Or use the main CLI:

```bash
catalogmesh --help
```

Optional runtimes:

```bash
python -m pip install "catalogmesh[local-embeddings]"
python -m pip install "catalogmesh[local-evidence]"
python -m pip install "catalogmesh[mcp]"
```

## What CatalogMesh includes

- Cloud vision providers: Gemini, OpenAI and Anthropic.
- Ollama local vision and local-first/cloud-fallback workflows.
- Crash-safe resumable product-photo grouping.
- Non-destructive Review Center with human approval state.
- Deterministic SKU/catalog candidate matching with mandatory human confirmation.
- Safe offline Shopify/PIM exports.
- Approval-aware Shopify, Akeneo and Odoo connector workflows.
- Local-first rclone Storage Center.
- Reports, benchmarks, environment management and automation tools.
- English, Arabic and Chinese desktop localization.

## Safety model

CatalogMesh never treats an AI guess as confirmed catalog identity. SKU confirmation remains human-controlled. Publication and remote connector mutations keep explicit approval/reservation boundaries, and MCP does not expose autonomous publication or generic remote mutation.

## Compatibility

`catalogmesh` is the primary PyPI project name.

The historical package name `ai-product-photo-sorter`, legacy `product-sorter-*` command aliases and `PRODUCT_SORTER_*` settings were used by earlier v3.x releases. The command aliases and persisted configuration identifiers remain supported so existing local workflows are not unnecessarily broken.

## Desktop builds

Ready-to-run Windows, Linux and macOS artifacts are published on the GitHub Releases page for the project repository.

Repository: https://github.com/mhmdwaelanwr/CatalogMesh
