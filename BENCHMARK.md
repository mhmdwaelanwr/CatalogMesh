# Benchmark Center

Product Sorter's Benchmark Center measures the **real sorting pipeline** instead of a synthetic timer. It is designed to make provider/model comparisons reproducible without inventing performance numbers.

## What it measures

Each benchmark run records:

- selected and completed photo counts;
- selected dataset size;
- total wall-clock time;
- average seconds per completed photo;
- throughput in photos per second;
- logical provider calls and failed provider calls;
- provider/model timing;
- image compression/encoding time and encoded payload size;
- input/output token usage when the provider exposes it;
- estimated cost using the existing Product Sorter cost configuration;
- peak process memory when the operating system exposes it;
- CPU/platform/Python details and an NVIDIA GPU snapshot when `nvidia-smi` is available;
- optional ground-truth accuracy when `--ground-truth` is supplied.

No extra AI request is made to create a benchmark report.

## CLI

Use the existing CLI with `--benchmark`:

```bash
product-sorter \
  --source ./Products \
  --output ./Sorted_Products \
  --limit 100 \
  --benchmark
```

An optional label can identify the experiment:

```bash
product-sorter \
  --source ./Products \
  --output ./Sorted_Products \
  --limit 100 \
  --benchmark \
  --benchmark-label "gemini-flash-100"
```

For a quality benchmark, provide the same ground-truth CSV supported by normal Product Sorter runs:

```bash
product-sorter \
  --source ./Products \
  --output ./Sorted_Products \
  --limit 100 \
  --ground-truth ./expected.csv \
  --benchmark
```

## GUI

The desktop app includes a **Benchmark** tab.

1. Configure the normal workspace, provider priority, model, and API keys.
2. Open **Benchmark**.
3. Choose the benchmark photo count.
4. Select **Start benchmark**.
5. Open the generated report from **Open latest report**.

The Benchmark tab deliberately reuses the production configuration so the measured code path is the same one used by real sorting operations.

## Isolation

Benchmark mode automatically writes to a fresh directory:

```text
<configured output>/
└── benchmarks/
    ├── history.jsonl
    ├── latest.txt
    └── run_YYYYMMDD_HHMMSS_microseconds/
        ├── BENCHMARK_REPORT.md
        ├── benchmark.json
        ├── progress.sqlite3
        ├── processing_status.csv
        ├── api_usage.csv
        └── normal Product Sorter result files
```

This matters because a normal Product Sorter output can contain cached batches. Reusing those cached responses would make a benchmark appear much faster without performing the provider work again.

## Comparing models correctly

Only compare two benchmark results when these conditions are held as constant as possible:

- same source images;
- same selected image count;
- same batch size;
- same Product Sorter version/commit;
- same machine for local models;
- comparable network conditions for cloud models;
- same confidence/ground-truth methodology;
- no unrelated heavy workload running in the background.

Cloud-provider results include network latency. A future local vision adapter can use the same benchmark infrastructure, but cloud and local results should be labeled separately.

## Interpreting request counts

`logical_provider_calls` counts calls made by Product Sorter's provider wrapper. A provider function may internally retry a request after a transient error or key rotation. Those retry delays are included in elapsed time, but internal attempts are not counted as separate logical provider calls.

Product Sorter intentionally overlaps neighboring batches by one image to preserve grouping context. For that reason, image encode calls and provider photo slots can be greater than the number of unique selected photos.

## Repository benchmark table

Do **not** add guessed or estimated numbers to the README. Publish a result here only after running the benchmark on a named dataset and recording the environment.

| Dataset | Provider / model | Photos | Dataset size | Hardware / network | Time | Avg / photo | Accuracy | Report |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| _No verified public benchmark published yet_ | — | — | — | — | — | — | — | — |

When a verified run is available, keep the generated `BENCHMARK_REPORT.md` or its machine-readable `benchmark.json` as the evidence for the published row.
