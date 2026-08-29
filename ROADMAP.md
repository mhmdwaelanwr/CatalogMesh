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
- [ ] Thumbnail-based manual review and correction workflow.
- [ ] Configurable category profiles beyond electronics.
- [ ] Richer operation statistics and provider cost estimates.
- [ ] Export/import operation profiles without secrets.
- [ ] Improved accessibility, keyboard navigation, and high-DPI validation.

## 3.3 — Local-first AI, performance, and desktop UX

Local execution is now a primary product direction rather than a future plugin
experiment. New local capabilities must use the same engine in CLI, desktop GUI,
resume, reports, and Benchmark Center.

- [x] First-class Ollama vision provider with no API key requirement.
- [x] Local-only and local-first-with-cloud-fallback provider chains.
- [x] CLI shortcuts for Ollama endpoint, model, keep-alive, and timeout settings.
- [x] Dedicated Ollama controls inside the Models & API keys desktop workspace.
- [x] Discover installed Ollama models and filter to models advertising vision capability.
- [x] Preserve Ollama configuration through the desktop Environment Center and setup wizard.
- [x] Skip public-internet preflight for operations that include Ollama.
- [x] Keep local models warm between batches with configurable Ollama `keep_alive`.
- [x] Add a bounded encoded-image LRU cache to avoid reprocessing overlap/fallback images.
- [ ] Hardware-aware local model recommendations based on available RAM/VRAM and measured benchmark throughput.
- [ ] Adaptive batch sizing for local models based on memory pressure and recent latency.
- [ ] Optional local visual-embedding pre-clustering so expensive multimodal inference is reserved for ambiguous groups.
- [ ] Local OCR/barcode pre-pass for SKU and packaging evidence.
- [ ] Surface local load time, prompt-eval time, token generation rate, and cache hit rate directly in Benchmark Center.
- [ ] Continue desktop visual refinement around clearer provider state, local/cloud privacy indicators, and operation health.

See [`LOCAL_AI.md`](LOCAL_AI.md) for the local runtime and CLI/GUI workflow.

## 4.0 — Extensibility and commerce integrations

- [ ] Provider plugin interface and custom OpenAI-compatible endpoints.
- [ ] Additional local runtime adapters beyond Ollama while preserving the 3.3 local-provider contract.
- [ ] Catalog integrations and reusable export templates.
- [ ] Extension API for custom grouping and naming policies.

Contributions should start with an issue describing the user problem, expected
behavior, privacy impact, and a practical verification plan.
