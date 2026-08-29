# Local-first architecture

Product Sorter's local-first direction is intentionally broader than adding one more AI provider.
The goal is a measurable, reviewable pipeline that keeps routine work local and spends cloud-model
latency/cost only where it adds value.

## Delivery order

1. **Ollama Local Vision** — run the existing production classification prompt against an installed
   Ollama vision model with no API key, no internet requirement, provider fallback compatibility,
   and the same CLI/GUI/Benchmark engine.
2. **Hybrid visual clustering** — use a dedicated image-embedding adapter (not Ollama text
   embeddings) for inexpensive similarity evidence. It starts in Shadow Mode and can become a
   routing layer only after labeled benchmarks validate its thresholds.
3. **Performance / parallel pipeline** — cache image preprocessing, prefetch non-overlapping work,
   parallelize safe CPU/I/O stages, and keep deterministic commit ordering.
4. **Review Center** — thumbnail groups with merge/split/move/correct/approve actions backed by an
   auditable correction store.
5. **SKU matching** — OCR/barcode/catalog candidates plus confidence-aware human confirmation.
6. **Shopify / PIM exports** — reusable export profiles built on approved catalog data.

## Provider contract

`AI_PROVIDERS` remains the ordered source of truth. Examples:

```text
AI_PROVIDERS=ollama
AI_PROVIDERS=ollama,gemini
AI_PROVIDERS=ollama,openai,anthropic
```

Ollama is a normal provider in the shared engine rather than a separate sorter implementation.
That preserves crash-safe SQLite resume, failure reporting, Benchmark Center instrumentation, and
future review/export workflows.

## Local vision configuration

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4
OLLAMA_KEEP_ALIVE=10m
OLLAMA_TIMEOUT=300
PRODUCT_SORTER_IMAGE_CACHE_ENTRIES=24
```

The desktop UI exposes these settings and can detect installed vision-capable models. The CLI also
accepts `--local`, `--ollama-model`, `--ollama-url`, `--ollama-keep-alive`, and
`--ollama-timeout`.

## Performance principles

- Cache compressed API JPEG bytes across overlapping batches and provider fallbacks.
- Keep a local model loaded between batches when memory permits.
- Never parallelize SQLite commits or output mutations in a way that can reorder operation state.
- Measure before/after performance through Benchmark Center instead of publishing guessed claims.
- Preserve source files and existing crash-safe resume semantics.

## Hybrid routing target

The target path is:

```text
photos
  -> metadata / perceptual duplicate checks
  -> local visual embeddings
  -> candidate product clusters + ambiguity score
  -> OCR / barcode hints
  -> Vision LLM only for ambiguous boundaries or semantic labeling
  -> Review Center
  -> approved SKU/catalog export
```

Ollama's `/api/embed` endpoint produces text embeddings, so Product Sorter does not treat it as a
visual-embedding backend. Image embeddings use a dedicated local vision embedding adapter. The
current implementation is **Shadow Mode only**: it computes adjacent-boundary similarity and
Benchmark Center evidence without changing production grouping. See
[`HYBRID_EMBEDDINGS.md`](HYBRID_EMBEDDINGS.md).

When a ground-truth CSV includes an optional `product_group` column, Shadow Mode reports confident
boundary accuracy against those labels. Without `product_group`, it reports only diagnostic
agreement with the normal sorter and does not call that accuracy.

## Promotion gate for real routing

Embedding decisions must not skip Vision LLM work until a representative labeled dataset establishes
acceptable behavior. The promotion decision should consider at least:

- confident boundary coverage;
- ground-truth confident boundary accuracy;
- ambiguous-case concentration;
- embedding throughput and memory footprint;
- simulated Vision LLM call reduction;
- end-to-end time and cloud-cost reduction;
- failure cases involving near-identical variants, packaging-only shots, reflections, and reordered captures.

Thresholds remain model- and dataset-specific; they are measured, not hard-coded as marketing claims.

## Benchmark scenarios

Every local-first milestone should be measurable with the same labeled dataset:

- Cloud-only Vision LLM
- Ollama-only Vision LLM
- Hybrid Shadow Mode + Ollama
- Hybrid Shadow Mode + cloud provider
- Future routed hybrid + Ollama
- Future routed hybrid + cloud fallback

Track grouping accuracy, view accuracy, boundary accuracy, wall time, photos/minute, peak memory,
provider calls, token usage, and estimated cloud cost. Local inference is reported as zero API cost,
not zero compute cost.
