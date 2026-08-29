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

`v3.1.1` is the current stable patch release on GitHub Releases and PyPI. It
preserves the v3.1 command/configuration surface while moving the canonical
runtime into a maintainable `src/` package layout. Gemini passed the funded
end-to-end synthetic live sample. OpenAI and Anthropic integration paths remain
covered by automated request, key-pool, and compatibility tests, with optional
funded live verification available through the manual `live-provider-smoke`
workflow whenever usable API credit is available.

## 3.2 — Quality and workflow

- [x] Benchmark Center for isolated real-pipeline timing, provider/model metrics, machine-readable JSON history, Markdown reports, optional ground-truth accuracy, CLI mode, and desktop GUI workflow.
- [x] Provider preflight and canonical provider selection before desktop/benchmark runs, including safe correction of the observed `gemeni` typo and explicit failure for unknown providers.
- [x] In-app Environment Center for validated `.env` editing, masked API-key management, OS-keyring clearing, reload/save/delete actions, and persistent desktop settings.
- [x] In-app Report Center with operation/benchmark artifact discovery, native GitHub-inspired Markdown preview, raw view, copy/open actions, and automatic refresh when output configuration changes.
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
- [ ] OCR and barcode extraction as local SKU/model evidence.
- [x] Memory-aware parallel image preprocessing with bounded cache reuse, CLI + GUI controls, and Benchmark Center metrics while keeping provider inference, SQLite commits, and output mutation ordered. See [`docs/PERFORMANCE_PIPELINE.md`](docs/PERFORMANCE_PIPELINE.md).
- [ ] Adaptive batch sizing and hardware-aware inference scheduling based on measured RAM/VRAM pressure and recent latency.
- [ ] Thumbnail Review Center with merge/split/move/correct/approve actions and auditable corrections.
- [ ] SKU/catalog candidate matching with confidence-aware human confirmation.
- [ ] Shopify, PIM/ERP, and reusable catalog export profiles built only from approved product groups.

## 4.0 — Extensibility

- [ ] Provider plugin interface and custom OpenAI-compatible endpoints.
- [ ] Pluggable local visual-embedding, OCR, and barcode backends.
- [ ] Extension API for custom grouping, naming, review, and export policies.
- [ ] Team/automation interfaces for connecting Product Sorter to larger catalog workflows.

Contributions should start with an issue describing the user problem, expected
behavior, privacy impact, and a practical verification plan.
