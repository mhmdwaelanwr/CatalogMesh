# Akeneo PIM execution boundary

Product Sorter supports Akeneo as a **connector-specific** PIM writer. It does not provide a generic PIM/ERP remote executor.

The Akeneo REST API supports product lookup and update/create by identifier. Product Sorter uses that identifier-scoped path, stores a pre-write snapshot for every planned product, applies only the mapped scalar attribute values, and never performs an automatic rollback.

## 1. Prepare an Akeneo-compatible connector profile

The profile remains credential-free. Use `identifier` (or `code`) for the identity target and `values.<attribute_code>` for simple scalar Akeneo attributes.

```json
{
  "schema_version": 1,
  "mode": "catalog_connector_profile",
  "profile_id": "akeneo-products",
  "connector_kind": "pim",
  "entity": "product",
  "identity_source": "sku",
  "field_map": {
    "sku": "identifier",
    "title": "values.name",
    "vendor": "values.brand"
  },
  "required_source_fields": ["sku", "title"]
}
```

This first adapter intentionally does not guess Akeneo attribute types, locales, scopes, currencies, categories, families, or associations. The mapped `values.*` fields are emitted as unscoped/unlocalized scalar values only. Use it only with compatible Akeneo attributes.

## 2. Generate a zero-network plan

```text
product-sorter-automation prepare-connector-plan catalog_export_manifest.json akeneo-profile.json
```

Review the plan before approval. It must remain `network_calls_performed: 0` and `external_action_performed: false`.

## 3. Create a connector-specific approval

The approval action is exactly:

```text
akeneo.apply_products
```

The approval payload binds execution to the exact local plan and Akeneo origin:

```json
{
  "plan_path": "/absolute/path/connector_write_plan.json",
  "plan_id": "cplan_...",
  "base_url": "https://example.cloud.akeneo.com"
}
```

`base_url` must be a credential-free HTTPS origin. The action cannot be replaced with `pim.apply_profile` or another generic connector action.

Use the existing request → human approval → single-use reservation flow. The Akeneo executor consumes only a matching `akeneo.apply_products` reservation.

## 4. Credentials

Credentials are environment-only and are never accepted in the profile, approval payload, plan, or execution state:

- `AKENEO_BASE_URL`
- `AKENEO_CLIENT_ID`
- `AKENEO_CLIENT_SECRET`
- `AKENEO_USERNAME`
- `AKENEO_PASSWORD`

The connector obtains an access token from Akeneo's OAuth token endpoint and uses Bearer authentication for product requests.

## 5. Execute

```text
product-sorter-automation execute-akeneo-products request.json reservation.json
```

Before the first PATCH, the executor reads every target product and writes an atomic local execution state containing the pre-write snapshots. It then applies products sequentially by identifier and records each applied item.

There is no automatic retry and no automatic rollback. If the connection becomes ambiguous or a partial write occurs, the reservation is finalized as failed and the state marks reconciliation as required.

## 6. Reconcile without writing

```text
product-sorter-automation reconcile-akeneo-execution akeneo_execution_state.json
```

Reconciliation performs GET requests only. It compares the current remote product fingerprints with the stored pre-write snapshots and reports what changed. It performs zero network writes.

Rollback is deliberately not automatic. A future rollback executor must be a separate action with a new human approval and must distinguish products created by the execution from products that existed before it.

## Agent boundary

Akeneo remote execution is not an MCP tool. Agents may inspect safe plans and local approval artifacts, but they cannot use MCP to consume an approval or perform the remote product writes.
