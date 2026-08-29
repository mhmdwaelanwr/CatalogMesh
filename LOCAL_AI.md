# Local AI with Ollama

Product Sorter can run product-photo classification on a local Ollama vision
model without an API key. Local mode uses the same grouping engine, SQLite
resume, reports, Benchmark Center, and GUI worker as the cloud providers.

## Why local-first

- Product photos can stay on the workstation.
- No per-image cloud API charge.
- Sorting can continue without public internet access.
- Ollama can be first in the provider chain with Gemini/OpenAI/Anthropic kept as
  optional fallbacks.
- Benchmark Center can compare local and cloud runs on the same dataset.

## Requirements

Install and start Ollama, then install at least one model that advertises the
`vision` capability. Product Sorter discovers installed models through Ollama's
local `/api/tags` endpoint and verifies vision support through `/api/show`.

Example:

```bash
ollama serve
ollama pull gemma4
```

The exact model you should use depends on your hardware and the models installed
in your Ollama library. The GUI detects local vision-capable models instead of
assuming that every installed text model can process product images.

## CLI

### Local only

```bash
product-sorter \
  --local \
  --ollama-model gemma4 \
  --source ./Products \
  --output ./Sorted_Products
```

### Local first, cloud fallback

```bash
product-sorter \
  --providers ollama,gemini,openai \
  --ollama-model gemma4 \
  --source ./Products \
  --output ./Sorted_Products
```

### Custom Ollama endpoint

```bash
product-sorter \
  --local \
  --ollama-url http://127.0.0.1:11434 \
  --ollama-model gemma4 \
  --ollama-keep-alive 15m \
  --ollama-timeout 600 \
  --source ./Products \
  --output ./Sorted_Products
```

Equivalent `.env` settings:

```dotenv
AI_PROVIDERS=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4
OLLAMA_KEEP_ALIVE=10m
OLLAMA_TIMEOUT=300
PRODUCT_SORTER_IMAGE_CACHE_ENTRIES=24
```

Set `AI_PROVIDERS=ollama,gemini` (or another ordered chain) to keep a cloud
fallback.

## Desktop GUI

Open **Models & API keys → OLLAMA · LOCAL**.

The Local AI panel provides:

- Ollama server address.
- Vision-model selection.
- **Detect vision models**, which queries the local Ollama server and filters the
  installed list to models advertising vision capability.
- Model keep-alive and inference timeout controls.
- **Use Ollama first**, which places Ollama before the existing provider chain.
- **Local only**, which switches the operation to Ollama without cloud fallback.

The same values are also visible in the in-app Environment Center and are saved
with the rest of the desktop configuration.

## Performance behavior

### Model keep-alive

`OLLAMA_KEEP_ALIVE` defaults to `10m`. Keeping the selected model loaded avoids a
full model load before every small photo batch. Ollama reports load/evaluation
metrics and token counts; Product Sorter records the normal token usage in its
existing usage pipeline and Benchmark Center records the provider call timing.

### Encoded-image cache

Product Sorter uses overlapping batches so the boundary photo can preserve
same-product continuity. It can also retry the same batch with another provider.
Without a cache, those repeated photos are decoded and JPEG-encoded again.

`PRODUCT_SORTER_IMAGE_CACHE_ENTRIES=24` keeps a bounded in-memory LRU cache keyed
by file path, size, and modification time. Set it to `0` to disable the cache.
The original photos are never modified.

## Offline behavior

When Ollama is present in `AI_PROVIDERS`, Product Sorter does not block a batch on
the public-internet preflight. A local-only run therefore continues without
Wi-Fi. If Ollama fails and the configured chain then falls back to a cloud
provider, that provider can still report its own connectivity error normally.

## Troubleshooting

### Ollama is not reachable

Start the service and verify the configured URL:

```bash
ollama serve
ollama list
```

### Model is missing

```bash
ollama pull gemma4
```

Then use **Detect vision models** again.

### Installed model is text-only

Product Sorter rejects a model that explicitly reports capabilities without
`vision`. Select a vision model from the detected list.

### Local inference is too slow

Use Benchmark Center on a controlled sample and compare model size,
quantization, batch size, and hardware utilization. Avoid choosing a large model
only because it is more capable; throughput and VRAM/RAM pressure matter for a
long product shoot.
