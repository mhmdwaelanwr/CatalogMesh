# Odoo ERP execution boundary

Product Sorter supports Odoo as a **connector-specific** ERP product updater. It does not provide a generic ERP remote executor.

## Scope

This first Odoo adapter intentionally updates **existing `product.product` records only**. It identifies products by `default_code` and supports only a bounded field set:

- `default_code` — identity only, never changed
- `name`
- `barcode`
- `active`

Product creation, deletion, stock moves, pricing rules, accounting records, purchase/sales documents, categories, variants, templates and arbitrary model writes are out of scope.

## Prepare a profile

Use an ERP profile whose identity maps to `default_code`, for example:

```json
{
  "schema_version": 1,
  "mode": "catalog_connector_profile",
  "profile_id": "odoo-products",
  "connector_kind": "erp",
  "entity": "product",
  "identity_source": "sku",
  "field_map": {
    "sku": "default_code",
    "title": "name",
    "barcode": "barcode"
  },
  "required_source_fields": ["sku", "title"]
}
```

Generate the normal zero-network connector plan and review it before approval.

## Human approval

Remote execution accepts only the exact action:

```text
odoo.apply_products
```

The approval payload binds the exact local plan and Odoo target:

```json
{
  "plan_path": "/absolute/path/connector_write_plan.json",
  "plan_id": "cplan_...",
  "base_url": "https://erp.example.com",
  "database": "production"
}
```

`base_url` must be a credential-free HTTPS origin. The generic planning action `erp.apply_profile` cannot execute Odoo writes.

Use the existing request → explicit human approval → single-use reservation flow before execution.

## Credentials

Credentials remain environment-only:

- `ODOO_BASE_URL`
- `ODOO_DATABASE`
- `ODOO_USERNAME`
- `ODOO_API_KEY`

They are not stored in connector profiles, plans, approval payloads or execution state.

## Execute

```text
product-sorter-automation execute-odoo-products request.json reservation.json
```

Before consuming the reservation, the executor performs a full preflight for every planned identity. Every product must already exist and `default_code` must resolve uniquely. If any target is missing, execution fails before the approval is consumed.

After preflight, the executor stores pre-write snapshots and applies updates sequentially. There is no automatic retry and no automatic rollback. Partial writes fail closed and mark reconciliation as required.

## Reconcile without writing

```text
product-sorter-automation reconcile-odoo-execution odoo_execution_state.json
```

Reconciliation performs reads only and reports whether current remote records differ from the stored pre-write snapshots. It performs zero network writes.

## Agent boundary

Odoo remote execution is not exposed through MCP. There is no generic `execute-erp` or `execute-connector` command. Agents may prepare and inspect safe plans, but cannot consume approvals or perform Odoo writes through MCP.
