# Shopify Approval-Aware Execution Boundary

This milestone connects the local human-approval artifacts to the existing guarded Shopify draft-staging workflow without exposing publication to agents or MCP.

## Approved action

The connector accepts exactly one automation action:

```text
shopify.stage_drafts
```

The approval-request payload must contain `export_manifest` and may contain `output_dir`, `upload_images`, and `store_domain`.

Example payload:

```json
{
  "export_manifest": "./exports/catalog_export_manifest.json",
  "output_dir": "./exports/shopify_remote",
  "upload_images": true,
  "store_domain": "example-store.myshopify.com"
}
```

## Flow

```text
request-external-action
→ human approve-external-action
→ reserve-approved-action
→ execute-shopify-stage
→ Shopify products remain DRAFT and unpublished
```

A typical CLI flow is:

```text
product-sorter-automation request-external-action shopify.stage_drafts ./shopify-stage-payload.json ./approval-request.json
product-sorter-automation approve-external-action ./approval-request.json ./approval-grant.json --confirm "APPROVE apr_..."
product-sorter-automation reserve-approved-action ./approval-request.json ./approval-grant.json ./.product-sorter-execution
product-sorter-automation execute-shopify-stage ./approval-request.json ./.product-sorter-execution/reservations/apr_....json
```

Shopify credentials are read from `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_ACCESS_TOKEN`, and optionally `SHOPIFY_API_VERSION`. The automation command deliberately has no token argument.

## Safety properties

Before any remote staging call, the executor verifies the request/reservation pair, the exact action, request ID, deterministic idempotency key, reservation status, and optional approved store domain. It then atomically marks the reservation consumed before attempting a remote mutation.

Only transient transport/upload failures are retried, using the reservation's existing retry policy and the same deterministic idempotency key. Guard failures such as duplicate or unmanaged SKUs fail closed without repeated mutation attempts. The underlying Shopify staging workflow still enforces exact-SKU collision protection, managed-state checks, DRAFT status, unpublished state, no inventory writes, and local state/audit persistence.

The execution audit records reservation consumption and each connector result. Credential-shaped fields are redacted by the shared execution-control layer.

## Publication remains separate

This connector does not call `publish_staged`, does not activate products, and does not expose any publish tool through MCP. Shopify publication remains a separate interactive confirmation boundary with the existing rollback path.

A failed consumed reservation is not reusable. A new human approval and reservation are required for a new execution attempt after the configured in-process retry budget is exhausted.
