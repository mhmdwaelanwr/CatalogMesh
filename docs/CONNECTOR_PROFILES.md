# PIM / ERP connector profiles

Product Sorter can prepare deterministic, zero-network write plans for future PIM/ERP integrations without embedding credentials or exposing a generic remote writer.

## Profile contract

A connector profile is local JSON with `mode: catalog_connector_profile`, `schema_version: 1`, a stable `profile_id`, `connector_kind` (`pim` or `erp`), an `entity`, an `identity_source`, and an explicit `field_map` from Product Sorter's neutral PIM CSV columns to target-system field names.

Credential-like keys are rejected anywhere in the profile. Authentication values belong in a future connector-specific environment/keyring configuration, never in profile JSON, approval payloads, plans, or audit files.

Example:

```json
{
  "schema_version": 1,
  "mode": "catalog_connector_profile",
  "profile_id": "example-pim-products",
  "connector_kind": "pim",
  "entity": "product",
  "identity_source": "sku",
  "field_map": {
    "sku": "code",
    "title": "name",
    "description": "description",
    "price": "price"
  },
  "required_source_fields": ["sku", "title"]
}
```

## Prepare a write plan

```text
product-sorter-automation prepare-connector-plan <catalog_export_manifest.json> <profile.json>
```

The command consumes the existing offline `neutral_pim_csv`, validates required fields, maps only explicitly declared fields, and writes `connector_write_plan.json`.

The plan contains deterministic record fingerprints and an action such as `pim.apply_profile` or `erp.apply_profile`, but it always reports:

- `network_calls_performed: 0`
- `external_action_performed: false`
- `human_approval_required: true`
- `credentials_embedded: false`

## Safety boundary

This milestone does **not** add PIM/ERP network execution. There is no `execute-connector` command and no generic MCP mutation tool. The next connector milestone must consume a valid action-specific approval reservation, use connector-specific validation and authentication, reuse deterministic idempotency evidence, record redacted results, and define rollback/reconciliation behavior before any remote write is enabled.
