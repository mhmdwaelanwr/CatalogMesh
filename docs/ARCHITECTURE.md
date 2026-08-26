# Repository Architecture

AI Product Photo Sorter is organized by responsibility so runtime code, tests, release tooling, documentation, and examples are easy to find.

## Layout

```text
.
├── .github/                 # CI, release, security and contribution automation
├── assets/branding/         # Product identity and application icons
├── docs/                    # User/developer documentation, screenshots and release notes
├── examples/                # Small non-sensitive sample inputs
├── packaging/               # Platform-specific packaging definitions
│   ├── linux/
│   └── pyinstaller/
├── scripts/                 # Maintenance and developer utilities
│   └── smoke/               # Manual smoke-test entry points
├── tests/                   # Automated unit/integration/regression tests
├── sorter_core.py           # Shared processing engine
├── product_sorter.py        # CLI entry point
├── product_sorter_gui.py    # Desktop GUI entry point
├── providers.py             # Provider REST integrations
├── model_catalog.py         # Provider model discovery/catalog
├── set_data.py              # Guided configuration
└── pyproject.toml           # Python package metadata and console entry points
```

## Dependency direction

`product_sorter.py` and `product_sorter_gui.py` are presentation entry points. Both use the same `sorter_core.py` engine. The engine delegates provider-specific network work to `providers.py`, model discovery to `model_catalog.py`, localization to `i18n.py`, operational safeguards/reporting to `professional.py`, and credential persistence to `secrets_store.py`.

Tests live separately under `tests/` and import the production modules; release and smoke tooling must never contain duplicated business logic.

## Stability rule

The v3.1 line keeps the existing top-level Python module names because they are already published on PyPI. A future namespace/package migration should be performed as an explicit compatibility change, not mixed into repository housekeeping.
