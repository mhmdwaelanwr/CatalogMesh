# Changelog

All notable project changes are documented here.

## Unreleased

## 3.3.0 — 2026-09-04

### CatalogMesh desktop and GUI/CLI parity

- Promoted **CatalogMesh** as the desktop display brand while preserving the `ai-product-photo-sorter` PyPI package, `product-sorter-*` entry points, `PRODUCT_SORTER_*` settings, and v3.x compatibility paths.
- Expanded the desktop into the canonical 12-workspace workflow: Operation setup, Models & API keys, Results & activity, Review, SKU Match, Exports, Storage, Automation, Reports, Benchmark, Environment, and About.
- Added first-class `catalogmesh-*` aliases plus bounded Config, Reports, Storage, and Automation CLIs backed by shared application capabilities.
- Added a capability parity registry and CI coverage so non-visual desktop capabilities cannot silently lose their corresponding CLI/shared backend surface.
- Added the parser-driven Automation Center, responsive workspace navigation, scrollable long workspaces, and dark-mode field fixes without re-parenting Tk notebook pages.
- Added a final runtime EN/AR/ZH translation pass and Arabic shaping/BiDi compatibility while preserving technical tokens and diagnostic text.
- Added deterministic packaged-Windows GUI documentation for all 12 workspaces in light and dark themes, protected-main PR synchronization, and visual-noise filtering for hosted-runner screenshot churn.
- Fixed frozen-build configuration persistence so packaged apps use stable per-user config locations instead of PyInstaller `_MEI...` temporary extraction paths, while preserving an explicit portable `.env` beside the executable when already present.

### Storage Center · rclone

- Added a local-first Storage Center and first-class Storage CLI for rclone version/remotes discovery, read-only connectivity tests, dry-run previews, Copy, and manually confirmed Sync.
- Kept automatic post-sort cloud transfer strictly **Copy-only** and required the exact `SYNC <full-target>` confirmation for manual mirror operations.
- Added bounded bandwidth/transfers/checkers controls, live activity, cancellation, and credential-free storage audit behavior.
- Kept rclone execution argv-based with no shell executor, no rclone RC server, no credential-file ownership/parsing, and no MCP storage-transfer surface.

### Human approval and connector execution safety

- Added a read-only Review queue automation bridge plus local approval request/grant artifacts; agents/MCP can request or validate approval state but cannot self-approve actions.
- Added single-use execution reservations, deterministic idempotency keys, bounded retry metadata, atomic approval writes, append-only redacted execution audit evidence, and recursive rejection/redaction of credential-like payload fields.
- Routed Shopify draft staging through explicit approved reservations while keeping staged products DRAFT/unpublished and restricting retries to bounded transient failures with the same idempotency identity.
- Added separately approved Shopify publication and rollback actions so staging approval cannot publish and publication approval cannot authorize rollback.
- Added zero-network PIM/ERP connector profiles and deterministic write plans that reject embedded credentials and do not expose a generic connector executor.
- Added approval-aware Akeneo product execution, read-only reconciliation, separately approved rollback, pre-write snapshots, and fresh remote-drift fingerprint checks before rollback reservation consumption.
- Added approval-aware Odoo updates for existing `product.product` records by `default_code`, with bounded supported fields, full target preflight, read-only reconciliation, and no create/delete path.
- Hardened execution boundaries against legacy direct Shopify mutation installation, request/action tampering, invalid retry policy values, secret leakage, audit races, ambiguous-write blind retries, generic mutation surfaces, and MCP remote execution.

### Packaging and reliability

- Added validated support for the current `google-genai` 2.x line (`>=2.21,<3`) across tests, safety workflows, cross-platform packages, and packaged Windows GUI smoke.
- Kept GitHub release packaging for Windows x64, Linux x64/DEB, macOS Apple Silicon, macOS Intel, Python wheel/sdist, and SHA-256 checksums.
- Preserved the PyPI OIDC Trusted Publishing path and release-trigger/version consistency checks for the v3.3.0 publication.

### Safety boundaries retained

- SKU/catalog identity remains human-confirmed; AI/ranking evidence never auto-confirms a catalog row.
- External publication remains action-specific and explicitly human-approved; there is no autonomous publish path.
- Partial or ambiguous connector writes fail closed into reconciliation instead of blind retries.
- Credentials remain environment/keyring based and are not stored in approval payloads or execution logs.
- MCP exposes no generic remote mutation, publication, rollback, or rclone transfer executor.

## 3.2.0 — 2026-09-03

### Catalog automation and agents

- Added deterministic local shoot ingestion snapshots plus added/changed/removed diffing without mutating source photos.
- Added Missing Asset Audit helpers for catalog image references and conservative exact-stem local image reconciliation.
- Added a read-only Agent Tool Registry foundation with explicit mutation and human-approval metadata plus fail-closed execution.
- Added a persistent polling-based watched-folder daemon with crash-safe JSON checkpoints and deterministic incremental events.
- Hardened watched-folder checkpoints against concurrent temp-file collisions, invalid state paths, and corrupted snapshot entries.
- Added `product-sorter-automation` commands for scanning shoots, missing-asset audits, local reconciliation, SKU candidate proposals, offline Shopify draft preparation, and watched folders.
- Added `product-sorter-watch` as a dedicated watched-folder console entry point.
- Added optional MCP support through `ai-product-photo-sorter[mcp]` and the `product-sorter-mcp` stdio server.
- Added MCP tools for shoot scanning, missing-SKU audits, ranked candidate proposals, and offline Shopify draft preparation while deliberately exposing no publish tool.
- Preserved mandatory human confirmation before SKU matches become confirmed or Shopify draft preparation can succeed.

### Local-first catalog pipeline

- Added first-class Ollama local vision support with local-only and local-first/cloud-fallback operation modes.
- Added local image-embedding Shadow Mode, labeled threshold calibration, and Hybrid Routing Lab simulation for evidence-driven future routing promotion.
- Added optional local OCR and barcode evidence extraction without automatic catalog confirmation.
- Added memory-aware parallel image preprocessing with bounded cache reuse and benchmark metrics.
- Added the non-destructive Review Center with merge/split/move, metadata corrections, approvals, and append-only audit history.
- Added deterministic SKU/catalog candidate matching with ranked reasons and mandatory human confirmation.
- Added safe offline Shopify draft and neutral PIM exports built only from fully confirmed matches.
- Added guarded Shopify Admin GraphQL planning, preview, draft staging, exact-SKU collision protection, idempotency state, separately confirmed publication, and rollback to draft.

### Desktop workflow and reliability

- Added canonical provider preflight shared by CLI and GUI, including safe correction of the observed `gemeni` typo to `gemini` and clear rejection of unknown providers before a run starts.
- Added a live Benchmark elapsed timer and post-run success/failure summary with completed photos, logical provider calls, throughput, and seconds per photo.
- Added an in-app Environment Center for validated configuration editing, masked API-key management, reload/save/delete actions, and complete key removal from both `.env` and the optional OS keyring.
- Fixed desktop persistence for `APP_THEME`, `PRODUCT_SORTER_MD_REPORT`, `BENCHMARK_LIMIT`, and `PRODUCT_SORTER_OUTPUT_MODE`, which were previously collected by the GUI but not serialized by the legacy fixed `.env` writer.
- Added an in-app Report Center that discovers operation and benchmark evidence, renders Product Sorter Markdown reports with a GitHub-inspired native preview, and provides Raw, Copy, and Open externally actions.
- Added automatic Report Center refresh after saved configuration/output paths load or are reloaded, and routed the Benchmark tab's latest-report action into the in-app viewer when available.
- Bounded in-app report reads to 5 MiB and limited discovery to known report locations so large photo trees are never recursively scanned by the viewer.
- Reduced duplicate CI work by running feature-branch tests on pull requests while retaining push validation on `main`.

### Benchmark Center

- Added an opt-in `--benchmark` mode that measures the real sorting pipeline in a fresh isolated run instead of reusing cached batches.
- Added deterministic `BENCHMARK_REPORT.md` and `benchmark.json` artifacts plus append-only benchmark history and a latest-report pointer.
- Added provider/model timing, throughput, image-encoding metrics, token/cost totals, process-memory reporting, hardware snapshots, and optional ground-truth accuracy.
- Added reproducibility metadata for application version/revision, model and batch configuration, and connectivity-probe latency so cloud comparisons expose their test conditions.
- Added a synthetic end-to-end benchmark CI test that runs the real pipeline twice and verifies isolation, reporting, token accounting, and source preservation without live credentials.
- Fixed deterministic SQLite connection and operation-lock cleanup on every engine exit path, preventing retained Windows file handles after successful or interrupted runs.
- Added a dedicated desktop Benchmark tab that reuses the configured workspace, provider priority, model, and API credentials.
- Added `BENCHMARK.md` with reproducible comparison methodology and explicit caveats for cloud versus local-provider measurements.

## 3.1.1 — 2026-08-26

### Repository and package architecture

- Moved the canonical runtime into `src/ai_product_photo_sorter/` while preserving the existing source launchers and top-level compatibility imports.
- Added package-native CLI, GUI, and setup entry points backed by the same shared engine.
- Centralized source-checkout, installed-package, and frozen-application path resolution.
- Reorganized tests, smoke tools, examples, and packaging assets into dedicated project directories and documented the architecture.

### Packaging and reliability

- Updated PyInstaller and release workflows for the `src/` package layout across Windows, Linux, macOS Apple Silicon, and macOS Intel.
- Updated the frozen GUI so CLI worker execution can run through the same packaged executable rather than depending on a loose source script.
- Added regression coverage for the package boundary, legacy configuration location, release metadata, and compatibility shims.
- Preserved the v3.1 command surface and user data/configuration behavior while modernizing the internal layout.

## 3.1.0 — 2026-08-22

### Desktop experience

- Redesigned the desktop GUI as a four-workspace dashboard for operation setup, models and API keys, results and activity, and project information.
- Added persistent dark and light themes plus Arabic, English, and Chinese interface support.
- Added real application screenshots, a high-resolution README hero, and the Smart Photo Stack visual identity across the GUI and distribution assets.
- Added native folder selection, live progress and ETA, completed/pending/failed views, graceful stopping, resume support, and direct output-folder opening.

### AI providers and model handling

- Added Gemini, OpenAI, and Anthropic provider pools with ordered fallback.
- Added one to four API keys per provider, for up to 12 configured keys, with automatic quota and rate-limit rotation.
- Added live provider model discovery and shared-model validation across every key in a provider pool.
- Preserved completed batches when the selected model changes and fail fast on invalid 4xx requests that should not trigger key rotation.
- Added `provider_models.json` as the offline fallback model catalog.

### Reliability and reporting

- Added crash-safe SQLite progress, schema migrations, operation locking, backups, failure records, usage reporting, and resumable output folders.
- Fixed Windows-specific SQLite cleanup and lock-file behavior.
- Kept Unix `.env` permission validation without applying Unix permission assumptions on Windows.
- Reduced captured GUI/CI log noise by rendering live terminal progress only when stdout is interactive.
- Added ground-truth quality scoring, review folders, status exports, failure exports, run history, and usage reports.

### Packaging and delivery

- Added Python package metadata, console and GUI entry points, PyInstaller desktop packaging, Linux `.deb` packaging, and cross-platform brand icons.
- Added automated build pipelines for Windows, Linux, and macOS, plus wheel and source distributions.
- Added Windows x64 EXE, Linux x64 binary/DEB, and separate native macOS Apple Silicon (`arm64`) and Intel (`x86_64`) application bundles.
- Added project roadmap, known limitations, security guidance, contributing guidance, and production verification checklist.

## 3.1.0-rc1

- Added shared-model discovery for multi-key provider pools and cached-batch reuse after model changes.
- Added live model catalogs for Gemini, OpenAI, and Anthropic.
- Added one to four independent keys per provider and quota/rate-limit rotation across all three providers.
- Added interactive replacement-key requests after all configured keys are exhausted.
- Added GUI management for all provider key slots and compatibility with older settings.

## 3.0.0-rc1

- Added graceful stop after the current batch.
- Added cross-platform file locking and output-folder opening.
- Added Windows `start.bat` and macOS `start.command` launchers.
- Added optional operating-system keyring storage for API secrets.
- Added schema-versioned SQLite migrations and token/cost usage reporting.
- Added `pyproject.toml`, PyInstaller build specification and release builder.
- Added GitHub Actions across Linux, Windows, macOS and Python 3.10/3.12.
- Added synthetic image-to-report integration testing.
- Added opt-in live credential smoke testing without uploading product images.

## 2.1.0

- Split the shared processing implementation into `sorter_core.py`.
- Kept `product_sorter.py` as a compatible CLI entry point.
- Added `product_sorter_gui.py` with settings, API keys, start/stop/resume, live progress, ETA, logs, completed/pending/failed tables, and output opening.
- Added safe non-interactive engine mode for GUI subprocess control.
- Updated `start.sh` to let users choose GUI or CLI.

## 2.0.0

- Added Gemini, OpenAI and Anthropic provider configuration with fallback.
- Added API-key validation, request/cost estimates and configuration checks.
- Added single-instance output locking and automatic progress backups.
- Added persistent failure records, `error_report.csv`, and `--retry-failed`.
- Added ground-truth quality scoring with `--ground-truth expected.csv`.
- Added log rotation, version reporting, and beginner `start.sh` launcher.

## 1.0.0

- Initial multilingual product-photo sorter with progress, resume, `.env`, internet checks, API-key rotation, status lists, and setup wizard.
