# Hybrid threshold calibration

Product Sorter keeps visual embeddings in **Shadow Mode** until labeled evidence supports safe routing. Calibration does not switch routing on. It recommends conservative same-product and different-product thresholds from real adjacent product boundaries.

## 1. Prepare a labeled dataset

Use a real product-shoot folder, not UI screenshots or synthetic similarity data.

```bash
product-sorter --prepare-ground-truth /path/to/product-photos
```

The command writes `product_sorter_ground_truth.csv` beside the source folder. A custom output path is also supported:

```bash
product-sorter \
  --prepare-ground-truth /path/to/product-photos \
  --ground-truth-out /path/to/ground_truth.csv
```

The CSV contains:

```csv
filename,category,view,brand,model,product_group
IMG_0001.jpg,mouse,front,Logitech,M185,P001
IMG_0002.jpg,mouse,back,Logitech,M185,P001
IMG_0003.jpg,keyboard,front,Logitech,K120,P002
```

`product_group` is the required label for boundary calibration. Category/view/brand/model remain useful for the existing quality scorer but are not required to decide whether two adjacent photos belong to the same product.

The Benchmark tab exposes the same workflow through **Prepare label CSV** and **Validate labels**.

## 2. Produce Shadow evidence

Run the normal sorter/Benchmark Center with Hybrid visual embeddings enabled and supply the labeled ground truth. Shadow Mode writes:

- `hybrid_embedding_shadow.csv`
- `hybrid_embedding_summary.json`

Routing remains disabled. The shadow CSV records cosine similarity and, when labels are available, the ground-truth same/different relation for each adjacent boundary.

## 3. Calibrate thresholds

```bash
product-sorter \
  --calibrate-hybrid /path/to/hybrid_embedding_shadow.csv \
  --calibration-ground-truth /path/to/ground_truth.csv \
  --calibration-min-precision 0.98
```

If the shadow CSV already contains ground-truth relations, `--calibration-ground-truth` is optional.

Outputs:

- `hybrid_threshold_calibration.json`
- `HYBRID_THRESHOLD_CALIBRATION.md`

The Benchmark GUI provides **Calibrate thresholds** and copies a successful recommendation into the existing Hybrid Shadow threshold fields. It does not enable production routing.

## Selection policy

The calibration objective is intentionally conservative:

1. Require a minimum precision for confident **same-product** decisions.
2. Require the same precision gate for confident **different-product** decisions.
3. Require a minimum number of decisions on each side.
4. Require `different_threshold < same_threshold`, leaving an ambiguity region between them.
5. Among threshold pairs that pass those gates, maximize confident coverage.

Default gates:

- minimum precision: `98%`
- minimum labeled adjacent boundaries: `30`
- minimum confident decisions per side: `5`

These values are calibration defaults, not universal guarantees. Representative datasets should include visually similar variants, packaging changes, reflections, different angles, and realistic shoot-order mistakes.

## Interpreting the output

A recommendation includes:

- same-product threshold and precision
- different-product threshold and precision
- confident coverage
- accuracy across confident decisions
- number of ambiguous boundaries retained for Vision AI
- whether the minimum sample-size gate passed

`promotion_ready=true` means the calibration gates passed for that dataset. It does **not** mean production routing is automatically safe across all catalogs.

## Promotion gate

Production Hybrid Routing should remain disabled until all of the following are true:

- multiple representative labeled shoots have been evaluated;
- same/different precision remains acceptable across those shoots;
- confident coverage provides a meaningful reduction in Vision AI work;
- false confident decisions have been manually reviewed;
- Ollama/cloud fallback behavior remains correct for ambiguous boundaries;
- crash-safe resume and deterministic operation ordering remain unchanged.

Only after that evidence should the routing layer be promoted from Shadow Mode.
