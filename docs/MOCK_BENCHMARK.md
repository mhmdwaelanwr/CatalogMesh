# Mock Product Benchmark

The mock benchmark is a deterministic engineering fixture for validating Product Sorter's labeled-dataset, Hybrid threshold-calibration, and routing-simulation workflow.

It is **not** a real-world accuracy benchmark and must never be used to approve production Hybrid Routing.

## What it generates

Running:

```bash
python scripts/generate_mock_product_benchmark.py --output mock-benchmark-output
```

creates:

- `photos/` — 48 generated JPG product-shoot images across 8 mock products.
- `ground_truth.csv` — complete category/view/brand/model/product_group labels.
- `hybrid_embedding_shadow.csv` — synthetic similarity evidence with easy and deliberately ambiguous cases.
- `calibration/hybrid_threshold_calibration.json` — calibration output from the real threshold engine.
- `calibration/HYBRID_THRESHOLD_CALIBRATION.md` — human-readable calibration report.
- `routing-lab/hybrid_routing_simulation.json` — machine-readable routing simulation.
- `routing-lab/HYBRID_ROUTING_SIMULATION.md` — human-readable routing simulation report.
- `routing-lab/hybrid_routing_simulation.csv` — per-boundary local/vision routing evidence.
- `mock_benchmark_summary.json` — machine-readable fixture summary.

The mock products include lookalike mouse and keyboard variants so the fixture contains intentionally difficult neighboring product boundaries instead of perfectly separated toy classes.

## What it proves

The fixture is useful for regression testing that:

1. labeled product groups remain complete and ordered;
2. same/different adjacent boundaries reach the calibration engine correctly;
3. threshold selection preserves a non-overlapping ambiguous region;
4. conservative precision gates remain enforced;
5. calibrated thresholds can be replayed by Hybrid Routing Lab;
6. ambiguous boundaries stay assigned to Vision;
7. confident mistakes surface as `unsafe_local_misroutes`;
8. reports are generated reproducibly;
9. production routing remains disabled and actual provider calls skipped remains zero.

## What it does not prove

The mock similarities are synthetic. Therefore this fixture does not measure:

- FastEmbed or another embedding model's real product-photo accuracy;
- Ollama/cloud provider grouping quality;
- real catalog boundary precision;
- real API-call reduction;
- real cost or latency savings;
- whether Hybrid Routing is safe to enable in production.

Those claims require representative labeled product-shoot photos.

## CI artifact

`.github/workflows/mock-benchmark.yml` runs the fixture on pull requests and `main`, verifies the safety contract, and publishes the complete generated output as the `product-sorter-mock-benchmark` artifact.

The CI assertions deliberately require:

```text
production_evidence = false
production_routing_enabled = false
actual_provider_calls_skipped = 0
```

Even when the synthetic fixture obtains a promotion-ready calibration recommendation and zero mock misroutes, a green mock benchmark cannot be mistaken for production validation.
