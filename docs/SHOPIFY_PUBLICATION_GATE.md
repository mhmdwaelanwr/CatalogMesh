# Shopify publication approval gate

Product Sorter treats publication as a distinct external mutation from draft staging.

## Required flow

1. Stage products with a separately approved `shopify.stage_drafts` reservation.
2. Inspect the resulting Shopify state and confirm every intended product is still `draft_staged` and unpublished.
3. Create a **new** approval request with action `shopify.publish_staged` and payload containing `state_path`, optional `store_domain`, and the exact `publication_id`.
4. A human approves that request through the existing CLI exact-confirmation flow.
5. Convert the grant to a single-use reservation.
6. Run `product-sorter-automation execute-shopify-publish <request> <reservation>`.

The publish executor accepts no generic stage approval. It verifies action, request/reservation identity, deterministic idempotency integrity, store binding, publication GID, and reserved state before consuming the reservation. It then delegates to the existing explicit Shopify publisher and records the result in the shared execution audit.

Publication execution intentionally has no retry loop. A partially completed or failed publication must be inspected before a new human approval is created.

## Rollback

Rollback is also a separate mutation and requires its own action, `shopify.rollback_publication`, its own human approval, and its own single-use reservation. Run it with `product-sorter-automation execute-shopify-rollback <request> <reservation>`.

## Agent boundary

Neither publish nor rollback is exposed as an MCP tool. Agents may prepare local approval requests, but they cannot grant approval or execute these publication mutations through MCP. Shopify credentials remain environment-only in the automation CLI.
