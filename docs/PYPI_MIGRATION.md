# PyPI migration: ai-product-photo-sorter -> catalogmesh

`catalogmesh` is the primary Python distribution name going forward. The import package remains `ai_product_photo_sorter` in v3.x so existing Python imports, persisted settings and compatibility command aliases are not renamed destructively.

## One-time PyPI setup before the first CatalogMesh publish

Create a **pending Trusted Publisher** in the PyPI account that owns the release process with these exact values:

- PyPI project name: `catalogmesh`
- Owner: `mhmdwaelanwr`
- Repository: `CatalogMesh`
- Workflow filename: `release.yml`
- Environment: `pypi`

Do not create an API token. The existing GitHub Actions release job uses OIDC Trusted Publishing.

A pending publisher does not create or reserve the project until the first successful upload. PyPI converts it to a normal Trusted Publisher automatically after that first successful publish.

## Packaging identity

Primary distribution:

```text
catalogmesh
```

Python import namespace retained for v3.x compatibility:

```text
ai_product_photo_sorter
```

Preferred commands:

```text
catalogmesh
catalogmesh-gui
catalogmesh-setup
catalogmesh-config
catalogmesh-reports
catalogmesh-storage
catalogmesh-automation
catalogmesh-watch
catalogmesh-mcp
```

Historical `product-sorter-*` command aliases and `PRODUCT_SORTER_*` configuration keys remain supported during v3.x.

## Release behavior

`.github/workflows/release.yml` builds `catalogmesh-<version>-py3-none-any.whl` and the matching source distribution and publishes them through the protected `pypi` GitHub environment.

The old `ai-product-photo-sorter` PyPI project remains part of project history. New users should install `catalogmesh` after the first CatalogMesh PyPI release is published.
