# Akeneo PIM execution boundary

Product Sorter supports Akeneo as a **connector-specific** PIM writer. It does not provide a generic PIM/ERP remote executor.

The Akeneo REST API supports product lookup and update/create by identifier. Product Sorter uses that identifier-scoped path, stores a pre-write snapshot for every planned product, applies only the mapped scalar attribute values, and never performs an automatic rollback.

## Apply products

Prepare and review a credential-free connector plan, then create a human approval for exactly:

```text
akeneo.apply_products
```

The approval payload binds the exact `plan_path`, `plan_id`, and credential-free HTTPS `base_url`. Credentials remain environment-only through `AKENEO_BASE_URL`, `AKENEO_CLIENT_ID`, `AKENEO_CLIENT_SECRET`, `AKENEO_USERNAME`, and `AKENEO_PASSWORD`.

Execute only after the normal request → human approval → single-use reservation flow:

```text
product-sorter-automation execute-akeneo-products request.json reservation.json
```

Before the first PATCH, the executor reads every target product and atomically stores its pre-write snapshot. There is no automatic retry and no automatic rollback. Partial or ambiguous writes require reconciliation.

## Reconcile without writing

```text
product-sorter-automation reconcile-akeneo-execution akeneo_execution_state.json
```

Reconciliation performs GET requests only and zero network writes. Its `current_fingerprint` values are the SHA-256 fingerprints that must be reviewed and copied into a rollback approval if a rollback is required.

## Separately approved rollback

Rollback is a new external action, never an automatic continuation of apply. It requires a fresh read-only reconciliation followed by a fresh approval for exactly:

```text
akeneo.rollback_products
```

The rollback approval payload binds the original execution state, plan, Akeneo origin, and the exact current remote fingerprint for every restorable product:

```json
{
  "state_path": "/absolute/path/akeneo_execution_state.json",
  "plan_id": "cplan_...",
  "base_url": "https://example.cloud.akeneo.com",
  "expected_current_fingerprints": {
    "SKU-001": "<64-character SHA-256 current_fingerprint>"
  }
}
```

After the fresh request is explicitly approved and reserved, execute:

```text
product-sorter-automation execute-akeneo-rollback rollback-request.json rollback-reservation.json
```

The rollback executor is deliberately conservative:

- it restores only products that were actually applied and **already existed** before the apply execution;
- it restores only a bounded set of Akeneo product fields captured in the pre-write snapshot;
- it refuses to delete products that were created by the apply execution;
- creation deletion would require a different, separately designed and separately approved destructive action;
- it requires a fresh reconciliation fingerprint for every restorable product;
- immediately before consuming the rollback reservation, it GETs every target and compares the live fingerprint against the exact fingerprint approved by the human;
- any missing target or remote drift blocks the rollback before reservation consumption and before any PATCH;
- a partial rollback is marked failed and requires reconciliation; it is never retried automatically;
- the rollback reservation is single-use and cannot reuse the original apply approval.

This fingerprint gate prevents a rollback approval from silently overwriting remote changes that occur after the reviewed reconciliation snapshot. Local approval artifacts remain integrity-checked local files; they are not cryptographically signed against a hostile local user.

## Agent boundary

Akeneo apply and rollback remote execution are not MCP tools. Agents may inspect safe plans and local approval artifacts, but cannot consume approvals or perform Akeneo remote writes through MCP. Generic connector execution and generic connector rollback commands remain forbidden.
