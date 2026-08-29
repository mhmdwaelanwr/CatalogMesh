# Hybrid Routing Lab

Hybrid Routing Lab is a **simulation-only** step between measured embedding Shadow Mode and any future production routing.

It answers one practical question:

> If Product Sorter trusted the calibrated same/different thresholds, how many adjacent product boundaries could be handled locally, how many would still require Vision AI, and would any confident local decisions be wrong on the supplied labels?

## Inputs

The lab consumes:

1. `hybrid_embedding_shadow.csv`
2. `hybrid_threshold_calibration.json`
3. optional ground-truth CSV containing `product_group` when the Shadow CSV does not already contain `ground_truth_relation`

## CLI

```bash
product-sorter \
  --simulate-hybrid-routing hybrid_embedding_shadow.csv \
  --routing-calibration calibration/hybrid_threshold_calibration.json \
  --routing-ground-truth ground_truth.csv \
  --routing-output routing-lab
```

The ground-truth argument is optional when truth relations are already embedded in the Shadow evidence.

## Desktop GUI

Open **Benchmark Center → Hybrid Routing Lab**, then choose:

- the Hybrid Shadow CSV;
- the calibration JSON.

If a labeled ground-truth CSV was already selected in Dataset & Threshold Calibration, the Routing Lab reuses it automatically.

## Outputs

The lab writes:

- `hybrid_routing_simulation.json`
- `HYBRID_ROUTING_SIMULATION.md`
- `hybrid_routing_simulation.csv`

Important metrics include:

- `local_routed_boundaries`
- `vision_boundaries_remaining`
- `local_routing_coverage`
- `estimated_vision_boundary_work_reduction`
- `local_routing_accuracy`
- `unsafe_local_misroutes`

## What the reduction metric means

`estimated_vision_boundary_work_reduction` measures the fraction of adjacent **boundary decisions** that calibrated local embeddings could potentially answer.

It is deliberately **not** called API-call reduction. Product Sorter can send multiple images in one provider request, so boundary reduction and provider-request reduction are not equivalent.

## Safety contract

Hybrid Routing Lab never intercepts a provider call and never changes grouping output.

Every report therefore contains:

```text
mode = simulation
production_routing_enabled = false
actual_provider_calls_skipped = 0
```

A confident mistake is counted in `unsafe_local_misroutes`; it is never hidden by overall accuracy or coverage.

Even a perfect result on the deterministic mock benchmark is engineering evidence only. Production routing still requires representative labeled product shoots with measured local embeddings.
