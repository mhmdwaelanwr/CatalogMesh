# Production verification checklist

`v3.3.0` is the current stable **CatalogMesh** release. This checklist separates what CI proves automatically from checks that still need real hardware, funded provider accounts, representative labeled data, or non-production connector environments.

## Verified automatically for v3.3.0

- Unit, integration, synthetic end-to-end and package-layout tests.
- CLI/core identity, Python compilation, shell syntax and wheel/sdist build coverage.
- Database migrations, locking, resume, failure handling and usage/report generation.
- Benchmark JSON/Markdown generation and mock benchmark coverage.
- 12-workspace GUI/CLI capability-parity checks.
- Connector-profile, execution-boundary, Shopify publication-gate, Akeneo execution/rollback and Odoo execution safety workflows.
- Archive integrity, release artifact verification and secret-pattern scanning.
- Windows, Linux and macOS packaging builds.
- Packaged Windows GUI smoke launch/capture from the built executable.
- Exactly 12 light + 12 dark canonical GUI screenshots, with visual-noise filtering before documentation refresh.
- `gui-docs-sync` keeps tracked screenshots and the README hero generated from those canonical captures visually current after successful `main` builds.

Automated checks prove the tested code and bounded safety contracts. They do **not** prove the quality of a real product catalog, paid-provider account, external store configuration, or every desktop/DPI combination.

## Real desktop validation

For future stable releases, run `python -m scripts.smoke.gui_smoke` on representative desktop machines and visually verify:

- English, Arabic and Chinese runtime layouts;
- light and dark themes;
- all 12 workspaces in the documented order;
- Workspace picker and `Ctrl+Tab` / `Ctrl+Shift+Tab` / `Alt+W` navigation;
- file and folder pickers;
- scaling/high-DPI behavior and smaller-window scrolling;
- Start / Stop / Resume processing controls;
- Review, SKU Match, Exports, Storage, Automation, Reports and Benchmark interactions;
- **Open latest report** resolves the correct newly generated report.

The packaged-Windows CI captures are useful regression evidence, but they are not a substitute for representative manual accessibility, high-DPI and multi-platform desktop checks.

## Provider-account validation

**Historical live check:** the v3.1 line completed a non-sensitive two-image Gemini verification. OpenAI and Anthropic continue to have automated integration/compatibility coverage unless funded live credentials are available.

Use:

```bash
python -m scripts.smoke.live_api_smoke
python -m scripts.smoke.live_provider_sample_smoke
```

The credential smoke must not upload product images. Use the provider sample smoke only with non-sensitive images and funded accounts.

Before publishing Benchmark Center results, run the same non-sensitive subset with the exact provider/model being reported and keep the generated `benchmark.json` and `BENCHMARK_REPORT.md` as evidence. Never publish estimated or manually invented timing/accuracy values.

## Representative labeled catalog data

Copy `examples/ground_truth.example.csv`, label a representative real product-shoot dataset, then run the sorter/benchmark with `--ground-truth`.

At minimum, review:

- boundary/grouping precision and false product merges;
- `Needs_Review` behavior and quality scores;
- Hybrid Shadow confident coverage and every unsafe confident misroute;
- real-catalog SKU top-1 / top-k candidate accuracy and ambiguity cases before promoting matching claims.

Visual embeddings remain Shadow Mode until representative labeled benchmarks establish acceptable confident coverage, boundary precision and review evidence.

## Storage validation

Before using a real remote, validate the configured rclone installation with read-only/test and dry-run operations first.

- Automatic post-sort transfer must remain **Copy-only**.
- Manual Sync must require the exact `SYNC <full-target>` confirmation phrase.
- CatalogMesh must not start the rclone RC server or become a generic remote executor.
- Do not treat a successful dry-run as proof that destination credentials, quotas or permissions will permit a later write.

## External connector validation

Use development/staging environments and non-sensitive mock catalogs before treating remote connector behavior as production-verified.

- **Shopify:** validate draft staging, exact-SKU collision protection, separate publication approval and rollback against a development store.
- **Akeneo:** validate mapped writes, reconciliation and rollback drift detection against a non-production instance.
- **Odoo:** validate bounded existing-product updates/reconciliation by `default_code` against a non-production database.

Never bypass the human SKU/publication boundary while testing. Credentials must remain outside approval payloads/logs, mutation reservations remain single-use, and ambiguous writes require reconciliation instead of blind retry.

## Stable release gate

Before promoting a future stable release:

1. All required CI and safety workflows for the exact release head must pass.
2. Platform packages and the packaged Windows GUI smoke must pass.
3. Release metadata/changelog/README must match the intended version and display brand.
4. Any published benchmark or production-verification claim must have retained evidence from the corresponding real environment or labeled dataset.
5. Tag/release/PyPI publication must occur only from the explicitly armed release path; ordinary `main` housekeeping must not republish an existing version.
