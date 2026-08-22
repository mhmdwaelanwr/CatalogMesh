# AI Product Photo Sorter

Cross-platform desktop and command-line tool that uses vision AI to group, order, and report product photos while preserving the original files.

> Current release: **3.1.0-rc1** (release candidate)

## Why it exists

Product shoots often produce a long sequence of front, back, side, and detail photos. This project analyzes that sequence, identifies photos of the same product, and builds an organized output catalog with review and progress reports.

## Highlights

- Shared Tkinter GUI and CLI engine.
- Gemini, OpenAI, and Anthropic support.
- One to four configured API keys per provider (up to 12 total).
- Automatic key rotation on quota/rate-limit errors and optional provider fallback.
- Secure prompt for an extra key when all configured keys are exhausted.
- Resume-safe SQLite progress, run history, backups, and graceful stopping.
- Progress bar, ETA, completed/pending/failed lists, and CSV reports.
- Internet connectivity and latency-quality checks before API batches.
- Arabic, English, and Chinese interface with device-language detection.
- Optional OS keyring storage for API credentials.
- Windows, Linux, and macOS launchers.

## Safety and privacy

- Source photos are never deleted, moved, or renamed.
- `.env`, databases, output folders, logs, and credentials are ignored by Git.
- Product images are sent to the provider selected by the user. Review that provider's privacy and billing terms before processing sensitive material.
- AI classifications can be wrong. Low-confidence results should be reviewed.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/mhmdwaelanwr/ai-product-photo-sorter.git
cd ai-product-photo-sorter
python -m venv .venv
```

Activate the environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install and configure:

```bash
python -m pip install -r requirements.txt
python set_data.py
```

Run the GUI or CLI:

```bash
python product_sorter_gui.py
python product_sorter.py
```

Platform launchers are also available: `start.bat`, `start.command`, and `start.sh`.

## API configuration

Copy `.env.example` to `.env`, or use `python set_data.py`. You may configure only one key or as many as four per provider:

```dotenv
AI_PROVIDERS=gemini,openai,anthropic
GEMINI_API_KEY_1=your_key
GEMINI_API_KEY_2=
OPENAI_API_KEY_1=your_key
ANTHROPIC_API_KEY_1=your_key
```

Providers are attempted in the listed order. Keys rotate only for quota and rate-limit failures; connectivity and invalid-request errors are handled separately.

## Outputs

- Organized product/category folders and `Needs_Review/`.
- `classification_report.csv` and `processing_status.csv`.
- Completed, pending, failed, usage, and run-history reports.
- `progress.sqlite3` for safe resume.

## Tests

```bash
python -m unittest discover -v
python -m py_compile *.py
```

The suite includes a synthetic image-to-report integration flow and key-rotation scenarios. Live checks are opt-in:

```bash
python live_api_smoke.py
python gui_smoke.py
```

See [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) for checks requiring real credentials, a graphical desktop, or a labeled product dataset.

## العربية

الأداة ترتب صور جلسات تصوير المنتجات، وتجمع صور الواجهة والخلفية والجوانب للمنتج نفسه، وتحفظ التقدم والتقارير. تدعم واجهة رسومية وطرفية وثلاثة مزودي ذكاء اصطناعي، ويمكن وضع من مفتاح واحد إلى أربعة مفاتيح لكل مزود. ابدأ بتشغيل `python set_data.py` لإعداد المشروع دون تعديل الملفات يدويًا.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report vulnerabilities according to [SECURITY.md](SECURITY.md). Never include API keys or private product images in an issue.

## License

MIT — see [LICENSE](LICENSE).
