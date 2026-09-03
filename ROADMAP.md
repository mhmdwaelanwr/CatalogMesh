# Roadmap

This roadmap describes direction, not a guarantee or delivery schedule. Stable
releases are promoted only after automated builds and the manual checks in
`PRODUCTION_CHECKLIST.md` succeed.

## 3.1 — First stable desktop release

- [x] Shared GUI and CLI processing engine.
- [x] Gemini, OpenAI, and Anthropic provider pools.
- [x] One to four keys per provider with quota rotation.
- [x] Crash-safe SQLite resume and operation reports.
- [x] Live model discovery and multi-key compatibility checks.
- [x] Multilingual dark/light desktop dashboard.
- [x] Cross-platform brand and application icons.
- [x] Automated Linux, Windows, and macOS build pipeline.
- [x] Validate produced artifacts on real desktop machines.
- [x] Validate the selected funded live provider with a non-sensitive two-image sample; OpenAI and Anthropic remain covered by automated integration tests until funded keys are available.
- [x] Publish signed-off `v3.1.0` release artifacts.
- [x] Publish `ai-product-photo-sorter` 3.1.0 to PyPI using Trusted Publishing.
- [x] Publish the backward-compatible `v3.1.1` maintenance release with the canonical `src/ai_product_photo_sorter/` package layout.

## 3.2 — Quality and workflow

`v3.2.0` is the current stable feature release target for GitHub Releases and
PyPI. It combines the quality/benchmark work, local-first catalog pipeline, and
safe MCP/automation surface developed after `v3.1.1`.

- [x] Benchmark Center for isolated real-pipeline timing, provider/model metrics, machine-readable JSON history, Markdown reports, optional ground-truth accuracy, CLI mode, and desktop GUI workflow.
- [x] Provider preflight and canonical provider selection before desktop/benchmark runs, including safe correction of the observed `gemeni` typo and explicit failure for unknown providers.
- [x] In-app Environment Center for validated `.env` editing, masked API-key management, OS-keyring clearing, reload/save/delete actions, and persistent desktop settings.
- [x] In-app Report Center with operation/benchmark artifact discovery, native GitHub-inspired Markdown preview, raw view, copy/open actions, and automatic refresh when output configuration changes.
- [x] Package and document `v3.2.0` as a minor feature release with Windows, Linux, macOS, wheel, sdist, checksums, and PyPI Trusted Publishing.
- [ ] Configurable category profiles beyond electronics.
- [ ] Richer operation statistics and provider cost estimates.
- [ ] Export/import operation profiles without secrets.
- [ ] Improved accessibility, keyboard navigation, and high-DPI validation.

## 3.3 — Local-first catalog pipeline

The strategic order is **Ollama / Local Vision → Hybrid visual clustering → Performance / parallel pipeline → Review Center → SKU matching → Shopify/PIM exports**. See [`docs/LOCAL_FIRST_ARCHITECTURE.md`](docs/LOCAL_FIRST_ARCHITECTURE.md) for the design contract.

- [x] First-class Ollama local vision provider in the shared CLI/GUI engine with no API key requirement.
- [x] Local-only and Ollama-first cloud-fallback modes.
- [x] Local vision-model discovery from the Ollama endpoint with vision-capability filtering.
- [x] Structured JSON-schema responses for the Ollama classification path.
- [x] Offline operation when Ollama is selected.
- [x] Shared compressed-image LRU cache across overlapping batches/provider fallbacks.
- [x] Benchmark reporting for Ollama provider timing, token counts, requested local model, and image-cache hit rate.
- [ ] Validate representative local vision models on labeled real product-shoot datasets and publish measured results rather than guessed claims.
- [x] Dedicated local **image** embedding Shadow Mode using an optional ONNX/FastEmbed backend, with CLI + GUI controls, conservative ambiguity thresholds, Benchmark Center metrics, and optional `product_group` boundary ground truth. See [`docs/HYBRID_EMBEDDINGS.md`](docs/HYBRID_EMBEDDINGS.md).
- [x] Labeled-dataset preparation, structural validation, and conservative Hybrid Shadow threshold calibration in CLI + Benchmark GUI, optimizing confident coverage only after precision gates are met. See [`docs/THRESHOLD_CALIBRATION.md`](docs/THRESHOLD_CALIBRATION.md).
- [x] Hybrid Routing Lab simulation in CLI + Benchmark GUI, replaying calibrated local decisions, measuring estimated Vision boundary-work reduction, and surfacing every unsafe confident misroute while keeping actual provider calls unchanged. See [`docs/HYBRID_ROUTING_LAB.md`](docs/HYBRID_ROUTING_LAB.md).
- [ ] Promote visual embeddings from Shadow Mode to production routing only after representative labeled benchmarks establish acceptable confident coverage, boundary precision, and review evidence.
- [x] Optional local OCR + barcode evidence extraction in CLI + Benchmark GUI with RapidOCR/ONNX and ZXing-C++, candidate identifier reporting, per-photo error isolation, and no automatic catalog match. See [`docs/LOCAL_EVIDENCE.md`](docs/LOCAL_EVIDENCE.md).
- [x] Memory-aware parallel image preprocessing with bounded cache reuse, CLI + GUI controls, and Benchmark Center metrics while keeping provider inference, SQLite commits, and output mutation ordered. See [`docs/PERFORMANCE_PIPELINE.md`](docs/PERFORMANCE_PIPELINE.md).
- [ ] Adaptive batch sizing and hardware-aware inference scheduling based on measured RAM/VRAM pressure and recent latency.
- [x] Non-destructive visual Review Center with photo preview, merge/split/move, metadata/view correction, approval state, append-only audit log, CLI review plans, and approved-group export. Review mutations never move source or materialized photos. See [`docs/REVIEW_CENTER.md`](docs/REVIEW_CENTER.md).
- [ ] Review UX polish: thumbnail grid, multi-select, drag-and-drop grouping, keyboard-first editing, and larger-set navigation.
- [x] Deterministic SKU/catalog candidate matching in CLI + GUI, consuming approved groups plus optional local OCR/barcode evidence, with ranked reasons, append-only decision audit, and mandatory human confirmation before a catalog row becomes confirmed. See [`docs/SKU_MATCHING.md`](docs/SKU_MATCHING.md).
- [ ] Real-catalog SKU matching evaluation with representative labeled store data, including top-1/top-k candidate accuracy and ambiguity analysis.
- [x] Safe offline Shopify draft + neutral PIM export profiles in CLI + GUI, built only from fully human-confirmed matches, with fail-closed validation, local image upload manifest, no inventory/shipping/tax invention, and zero publishing/network calls. See [`docs/CATALOG_EXPORTS.md`](docs/CATALOG_EXPORTS.md).
- [x] Guarded Shopify Admin GraphQL workflow with zero-network local plan, query-only remote preview, explicit draft staging, staged local image upload for new products, exact-SKU collision protection, local idempotency state, append-only remote audit, separately confirmed publication, and rollback to unpublished `DRAFT`. See [`docs/SHOPIFY_PUBLISHING.md`](docs/SHOPIFY_PUBLISHING.md).
- [ ] Validate the guarded Shopify workflow against a development store using a non-sensitive mock catalog before treating remote publishing as production-verified.
- [ ] PIM/ERP connector profiles with explicit field mapping, validation, and authenticated write boundaries.

## 3.4 — Catalog automation and agents

See [`docs/CATALOG_AUTOMATION.md`](docs/CATALOG_AUTOMATION.md) for the safety contract. The goal is to expose the existing local-first pipeline to modern catalog workflows without allowing agents or connectors to bypass human-reviewed SKU and publishing boundaries.

- [x] Non-destructive local shoot ingestion snapshots and deterministic added/changed/removed diffing.
- [x] Deterministic Missing Asset Audit for catalog rows and conservative exact-stem local-image reconciliation.
- [x] Read-only Agent Tool Registry foundation with explicit external-mutation metadata and fail-closed execution.
- [x] Persistent polling-based watched folders with crash-safe JSON checkpoints and deterministic incremental change events. See [`docs/MCP_AUTOMATION.md`](docs/MCP_AUTOMATION.md).
- [ ] Debouncing and automatic ingest/classify processing triggers on watched-folder events.
- [ ] Google Drive ingestion adapter using the same local ingestion contract.
- [ ] S3-compatible object-storage ingestion adapter with scoped credentials and local materialization.
- [x] Missing Asset Audit automation CLI for catalog image references and exact-stem local reconciliation.
- [ ] Missing Asset Audit in the desktop Review Center, including unresolved-SKU queues and exportable reports.
- [x] MCP stdio server using the official Python SDK v2 with safe tools for shoot scanning, missing-SKU audits, candidate proposals, and Shopify draft preparation. See [`docs/MCP_AUTOMATION.md`](docs/MCP_AUTOMATION.md).
- [x] Dedicated automation CLI and console entry points for scan → missing assets → proposal → human-confirmed Shopify draft workflows.
- [x] `open_review_queue` MCP/automation tool tied to Review Center state.
- [x] Local human-approval boundary with request/grant integrity validation and no Agent/MCP self-approval.
- [x] Single-use execution reservations with deterministic idempotency keys, retry-policy metadata, append-only redacted execution audit, and credential redaction foundation.
- [x] Approval-aware Shopify **draft staging** executor that consumes one valid reservation, retries only transient connector failures under the same idempotency key, records execution audit evidence, and always keeps remote products unpublished `DRAFT`.
- [x] Shopify publication and rollback gates require new action-specific human approvals and single-use reservations; neither mutation is exposed through MCP automation. See [`docs/SHOPIFY_PUBLICATION_GATE.md`](docs/SHOPIFY_PUBLICATION_GATE.md).
- [ ] Extend the reservation-consumption execution layer to PIM/ERP writes with connector-specific validation, audit, and rollback rules.
- [ ] Variant-level asset mapping and lifecycle state for SKU variants/options.
- [ ] Release scheduling for approved product assets with rollback-safe draft state.
- [ ] Automation rules/triggers for ingest → classify → review queue → match proposal → draft preparation.

## 4.0 — Extensibility

- [ ] Provider plugin interface and custom OpenAI-compatible endpoints.
- [ ] Pluggable local visual-embedding, OCR, and barcode backends.
- [ ] Extension API for custom grouping, naming, review, and export policies.
- [ ] Team/automation interfaces for connecting Product Sorter to larger catalog workflows.

Contributions should start with an issue describing the user problem, expected
behavior, privacy impact, and a practical verification plan.
