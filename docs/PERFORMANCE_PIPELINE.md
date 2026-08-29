# Performance pipeline

Product Sorter accelerates only the image-preparation stage that is safe to run concurrently.
Provider inference, product-order context, SQLite commits, checkpoint/resume state, and output
mutation remain sequential and deterministic.

## What is parallelized

For each provider batch, independent source images can be prepared concurrently:

```text
source photos
  -> EXIF transpose / RGB conversion
  -> resize / JPEG encode
  -> bounded encoded-image cache
  -> ordered AI provider call
```

The provider consumes the same canonical `compressed_image_bytes()` output as before. The
performance layer only warms that shared cache before inference.

## Safety controls

Concurrency is capped by all of the following:

- configured worker limit
- logical CPU count when `auto` is selected
- current batch size
- decoded image dimensions
- configurable memory safety budget
- encoded-image cache capacity

If a batch cannot fit in the configured encoded-image cache, prewarming is skipped rather than
performing work that may be evicted before the provider uses it. If image dimensions indicate that
parallel decoding would exceed the memory budget, the batch falls back to one preprocessing worker.

## CLI

```bash
product-sorter \
  --source ./photos \
  --preprocess-workers auto \
  --preprocess-memory-mb 512 \
  --image-cache-entries 24
```

Available controls:

- `--preprocess-workers auto|off|1..16`
- `--preprocess-memory-mb 128..8192`
- `--image-cache-entries 0..512`

`off` disables proactive preprocessing but leaves the existing on-demand image encoder unchanged.

## Desktop GUI

The Operation workspace contains a **Performance · Safe preprocessing** card with the same worker,
memory-budget, and cache controls. Values are persisted through the Environment Center and passed
to the same CLI worker used by normal desktop operations.

## Benchmark evidence

Benchmark Center records:

- configured and resolved worker limits
- maximum workers actually used
- preprocessing time
- images preprocessed
- measured images/second
- parallel batches
- sequential memory-safety fallbacks
- cache-capacity skips

These numbers describe preprocessing only. They do not claim end-to-end speedup. End-to-end gains
must be established by comparing complete benchmark runs on the same source dataset, provider,
model, hardware, and configuration.

## Why inference is still sequential

Adjacent product photos carry ordering context (`same_product_as_previous`) and operation state is
committed incrementally for crash-safe resume. Parallel AI batches could reorder context or commits,
so this milestone deliberately avoids that optimization. Future adaptive scheduling must preserve
the same deterministic state contract before it can be enabled.
