# Production verification checklist

## Verified automatically

- Unit and synthetic end-to-end tests.
- CLI/core identity, Python compilation, shell syntax, wheel build.
- Database migrations, locking, failure and usage reports.
- Archive integrity and secret-pattern scan.

## Requires a desktop machine

**v3.1.0 status: completed by the maintainer on real desktop devices.**

Run `python -m scripts.smoke.gui_smoke` and visually check Arabic, English and Chinese layouts,
file pickers, scaling and the Start/Stop/Resume buttons for future releases.

## Requires the owner's API keys

**v3.1.0 status:** Gemini completed a live two-image verification. OpenAI and Anthropic remain
covered by automated integration/compatibility tests; successful paid live samples require funded API accounts.

Run `python -m scripts.smoke.live_api_smoke` to validate configured credentials without uploading
product images. Run `python -m scripts.smoke.live_provider_sample_smoke` for a two-image non-sensitive
vision sample when funded credentials are available.

## Requires a labelled real dataset

Copy `examples/ground_truth.example.csv`, label at least 50 front/back product photos,
then run with `--ground-truth`. Review `quality_score.txt`, `Needs_Review`, and
false product merges before production use.
