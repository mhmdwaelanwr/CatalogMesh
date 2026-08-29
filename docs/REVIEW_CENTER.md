# Review Center

Review Center is the human-verification stage between Product Sorter's automated grouping and any future SKU/catalog matching or commerce export.

The core rule is simple:

> Review corrections update review state, not photo files.

Source photos and already-materialized Product Sorter outputs are never moved, renamed, deleted, or modified by Review Center.

## Input

Review Center starts from an existing Product Sorter output directory containing:

```text
classification_report.csv
```

The report already records the automated product group, category, view, brand, model, confidence, review status, and generated output filename for every photo.

## Review state

Initializing review creates:

- `product_review_manifest.json` — current editable review state;
- `product_review_summary.csv` — spreadsheet-friendly group summary.

Every group starts with:

```text
approved = false
```

A group becomes eligible for downstream SKU matching/export only after a human explicitly approves it.

The manifest tracks:

- group id;
- category;
- brand;
- model;
- notes;
- photo membership;
- per-photo view;
- original confidence/status/reason;
- relative path to the existing materialized photo;
- approval state;
- revision and audit counters.

## Visual desktop workflow

The desktop app adds a dedicated **Review** workspace.

It provides:

- product-group list with approved/pending state;
- photo list with view, confidence and original state;
- selected-photo preview;
- category / brand / model / notes correction;
- per-photo view correction;
- move photo to another group;
- split a selected photo into a new group;
- merge another group into the selected group;
- approve / unapprove group;
- export approved groups.

Any content-changing correction automatically clears approval for the affected group(s), forcing the edited state to be reviewed again before it can become catalog-ready.

## CLI

### Initialize review

```bash
product-sorter --review-init /path/to/output
```

### Inspect state

```bash
product-sorter \
  --review-summary /path/to/output/product_review_manifest.json
```

### Apply a review plan

```bash
product-sorter \
  --review-apply /path/to/output/product_review_manifest.json \
  --review-plan review-plan.json
```

Example plan:

```json
{
  "operations": [
    {
      "action": "set_group",
      "group": "Product_0004_Logitech_M185",
      "model": "M185",
      "notes": "Model confirmed from packaging"
    },
    {
      "action": "set_view",
      "filename": "IMG_0042.jpg",
      "view": "packaging_detail"
    },
    {
      "action": "split",
      "group": "Product_0005_Mouse",
      "filenames": ["IMG_0051.jpg"],
      "new_group": "Product_0005B_Mouse"
    },
    {
      "action": "approve",
      "group": "Product_0004_Logitech_M185"
    }
  ]
}
```

Supported actions:

- `approve`
- `unapprove`
- `set_group`
- `set_view`
- `move_photo`
- `split`
- `merge`

## Audit trail

Every persisted operation appends one JSON object to:

```text
product_review_audit.jsonl
```

Each event contains:

- monotonically increasing revision;
- UTC timestamp;
- action;
- affected values/details.

The manifest also stores the current revision and total audit-event count.

## Approved-only downstream contract

Export approved groups with:

```bash
product-sorter \
  --review-export-approved /path/to/output/product_review_manifest.json
```

This writes:

```text
approved_product_groups.csv
```

Only explicitly approved groups appear in that file. Pending groups are never silently included.

The manifest reports:

```text
catalog_ready = true
```

only when every current group is approved.

Future SKU matching, Shopify/PIM/ERP export, and publish workflows must consume approved review state rather than raw automated grouping.

## Non-destructive safety contract

Review operations change only:

- `product_review_manifest.json`;
- `product_review_summary.csv`;
- `product_review_audit.jsonl`;
- `approved_product_groups.csv` when explicitly exported.

They do not mutate source images or existing Product Sorter image outputs.

The deterministic mock workflow snapshots SHA-256 hashes and relative paths for all mock review photos before corrections and requires the exact same snapshot after split/correction/approval/export operations.

## Current UX scope

The first Review Center release uses group/photo tables plus a selected-photo preview. It provides the complete safe correction/approval workflow without adding drag-and-drop complexity to the initial implementation.

A richer thumbnail grid, multi-select editing, drag-and-drop grouping, and keyboard-first review are suitable follow-up UX improvements once the state/audit contract is stable.
