# Repository Architecture

AI Product Photo Sorter uses a `src/` package layout so application code, compatibility entry points, tests, packaging, documentation, and assets have clear ownership.

## Layout

```text
.
├── .github/                         # CI, releases, security and repository automation
├── assets/branding/                 # Product identity and desktop icons
├── docs/                            # Architecture, screenshots and release notes
├── examples/                        # Small non-sensitive sample inputs
├── packaging/                       # Platform-specific packaging definitions
│   ├── linux/
│   └── pyinstaller/
├── scripts/                         # Maintenance and manual smoke utilities
├── src/
│   ├── ai_product_photo_sorter/     # Canonical application package
│   │   ├── core.py                  # Shared processing engine facade
│   │   ├── cli.py                   # CLI entry point
│   │   ├── gui.py                   # Tkinter desktop entry point
│   │   ├── setup_wizard.py          # Guided configuration
│   │   ├── providers.py             # Provider REST integrations
│   │   ├── model_catalog.py         # Provider model discovery/catalog
│   │   ├── professional.py          # Persistence, reporting and safeguards
│   │   ├── i18n.py                  # Localization
│   │   ├── secrets_store.py         # Optional OS-keyring integration
│   │   └── paths.py                 # Source/install/frozen filesystem policy
│   └── *.py                         # Thin v3.1 import-compatibility shims
├── tests/                           # Automated unit/integration/regression tests
├── product_sorter.py                # Source-checkout CLI compatibility launcher
├── product_sorter_gui.py            # Source-checkout GUI/PyInstaller launcher
├── set_data.py                      # Source-checkout setup compatibility launcher
└── pyproject.toml                   # Package metadata and console entry points
```

## Dependency direction

The canonical direction is:

```text
CLI / GUI / setup
        │
        ▼
      core
        │
        ├── providers ── model catalog
        ├── professional / persistence
        ├── i18n
        └── secrets store
```

Presentation layers do not duplicate sorting logic. CLI and GUI both reach the same engine and the same SQLite operation state.

## Compatibility boundary

Version 3.1 published top-level modules such as `sorter_core`, `providers`, and `set_data`. The files directly under `src/` preserve those import names while forwarding to `ai_product_photo_sorter`. New code should import the package namespace instead.

The three small root Python launchers exist only so existing source-checkout commands such as `python product_sorter.py` keep working. Business logic must not be added to those launchers or to compatibility shims.

## Filesystem policy

`ai_product_photo_sorter.paths` is the single authority for runtime paths. A source checkout continues to use the repository-root `.env`; an installed wheel preserves the v3.1 site-packages compatibility root; a PyInstaller build resolves bundled resources from the frozen application root.

## Change rule

New runtime code belongs under `src/ai_product_photo_sorter/`. Tests belong under `tests/`; developer utilities under `scripts/`; platform packaging under `packaging/`. Moving behavior back into the repository root is considered an architectural regression.
