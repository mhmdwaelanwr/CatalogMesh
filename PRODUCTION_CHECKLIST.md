# Production verification checklist

## Verified automatically

- Unit and synthetic end-to-end tests.
- CLI/core identity, Python compilation, shell syntax, wheel build.
- Database migrations, locking, failure and usage reports.
- Archive integrity and secret-pattern scan.

## Requires a desktop machine

Run `python gui_smoke.py` and visually check Arabic, English and Chinese layouts,
file pickers, scaling and the Start/Stop/Resume buttons.

## Requires the owner's API keys

Run `python live_api_smoke.py`. It validates credentials without uploading
product images. Then process a two-image non-sensitive sample for each enabled
provider to confirm vision/model access and billing permissions.

## Requires a labelled real dataset

Copy `ground_truth.example.csv`, label at least 50 front/back product photos,
then run with `--ground-truth`. Review `quality_score.txt`, `Needs_Review`, and
false product merges before production use.
