# Hybrid visual embeddings — Shadow Mode

Product Sorter's hybrid visual-embedding layer is deliberately introduced as a **measurement-only Shadow Mode** before it is allowed to change production grouping.

The objective is to learn whether a lightweight local image-embedding model can confidently resolve obvious product boundaries so expensive Vision LLM calls can later be reserved for ambiguous cases.

## Safety contract

Shadow Mode does **not**:

- merge or split products;
- skip Gemini, OpenAI, Anthropic, or Ollama vision calls;
- change SQLite batch commits;
- change output folders or `classification_report.csv`;
- claim accuracy from agreement with another AI model.

It only creates additional evidence files after the normal sorter result is built.

## Optional runtime

The normal Product Sorter install stays lightweight. Install the ONNX-based image-embedding runtime only when you want to evaluate this feature:

```bash
python -m pip install "ai-product-photo-sorter[local-embeddings]"
```

The default model is:

```text
Qdrant/clip-ViT-B-32-vision
```

The first use of a model may require internet access to download its weights. Once cached, embedding inference is local. Set `HYBRID_EMBEDDING_CACHE_DIR` when you need an explicit model-cache location.

## CLI

Run a normal operation with shadow analysis:

```bash
product-sorter \
  --source ./Products \
  --output ./Sorted_Products \
  --hybrid-embeddings
```

Choose a model and conservative thresholds explicitly:

```bash
product-sorter \
  --source ./Products \
  --output ./Sorted_Products \
  --hybrid-embeddings \
  --hybrid-embedding-model Qdrant/clip-ViT-B-32-vision \
  --hybrid-same-threshold 0.90 \
  --hybrid-different-threshold 0.50
```

Performance tuning flags:

```text
--hybrid-embedding-batch-size N
--hybrid-embedding-parallel N
--hybrid-embedding-cache-dir PATH
```

These tune embedding execution only. They do not enable production routing.

## Desktop GUI

The Operation workspace contains **Hybrid visual embeddings · Shadow Lab**.

From there you can:

- enable/disable shadow analysis;
- select an image-embedding model;
- set same-product and different-product confidence thresholds;
- see whether the optional FastEmbed runtime is installed.

The same settings are persisted through the shared configuration path and the Environment Center.

## Decisions

For every adjacent photo boundary, cosine similarity is mapped to one of three diagnostic states:

```text
similarity >= same threshold       -> same_candidate
similarity <= different threshold  -> different_candidate
otherwise                          -> ambiguous
```

The default thresholds intentionally leave a broad ambiguous region:

```text
same >= 0.90
ambiguous = 0.50 .. 0.90
different <= 0.50
```

They are starting points for measurement, not universal production thresholds.

## Evidence files

A completed shadow run writes:

```text
hybrid_embedding_shadow.csv
hybrid_embedding_summary.json
```

The CSV records each adjacent boundary, similarity, embedding decision, final sorter relation, and optional ground-truth relation.

The JSON summary records:

- embedding model;
- embedding wall time and photos/second;
- confident coverage;
- ambiguous pair count;
- diagnostic agreement with the normal sorter;
- ground-truth confident boundary accuracy when labeled product groups are available.

Benchmark Center includes the same metrics in its JSON and Markdown reports.

## Ground truth for product boundaries

The existing ground-truth CSV remains backward compatible. Product Sorter's legacy scorer still uses the optional fields:

```text
filename,category,view,brand,model
```

To measure actual grouping-boundary accuracy for embeddings, add an optional `product_group` column:

```csv
filename,category,view,brand,model,product_group
IMG_0001.jpg,mouse,front,Logitech,M185,product_001
IMG_0002.jpg,mouse,back,Logitech,M185,product_001
IMG_0003.jpg,keyboard,front,Logitech,K120,product_002
```

Adjacent rows with the same `product_group` are labeled as the same product; a group change is a product boundary.

If `product_group` is absent, Shadow Mode reports only **agreement with sorter boundaries** and explicitly does not label it as accuracy.

## Benchmark gate before real hybrid routing

Production routing stays disabled until a representative labeled product-shoot dataset demonstrates acceptable results. At minimum, evaluate:

1. **confident coverage** — how many boundaries the embedding layer is willing to decide;
2. **ground-truth confident boundary accuracy** — how often those confident decisions are correct;
3. **embedding throughput** and memory footprint;
4. **end-to-end wall-time improvement** once routing is simulated;
5. **Vision LLM call reduction** and cloud-cost reduction;
6. failure cases across visually similar variants, packaging changes, reflections, and different camera order.

Thresholds should be selected from measured validation data rather than copied from one model or dataset.

## Intended next architecture

After the Shadow Mode gate is satisfied, the target path is:

```text
photos
  -> local visual embeddings
  -> confident same/different boundaries handled locally
  -> ambiguous boundaries enriched with OCR/barcode/catalog evidence
  -> Vision LLM resolves remaining ambiguity and semantic labels
  -> Review Center
  -> approved SKU/catalog export
```

That future routing phase must preserve deterministic SQLite commits, crash-safe resume, provider fallbacks, and Benchmark Center evidence.
