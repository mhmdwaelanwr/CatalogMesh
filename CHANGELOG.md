# Changelog

## 3.1.0-rc1
- عرض تقاطع الموديلات المتاحة لكل المفاتيح، واستكمال الدفعات المحفوظة عند تغيير الموديل، وإيقاف أخطاء 4xx فورًا.
- إضافة `provider_models.json` واكتشاف حي للموديلات المتاحة لكل مفتاح مع اختيارها من CLI وGUI.
- تحديث موديل Gemini الافتراضي إلى `gemini-3.6-flash` وقبول استجابة JSON كقائمة مباشرة أو كائن `items`.
- دعم 1–4 مفاتيح مستقلة لكل من Gemini وOpenAI وAnthropic.
- تدوير مفاتيح OpenAI وAnthropic عند الكوتا أو Rate Limit مثل Gemini.
- طلب مفتاح إضافي عند انتهاء جميع مفاتيح المزود في الوضع التفاعلي.
- واجهة GUI بتبويبات منفصلة للمفاتيح الـ12 مع توافق الإعدادات القديمة.

## 3.0.0-rc1

- Added graceful stop after the current batch.
- Added cross-platform file locking and output-folder opening.
- Added Windows `start.bat` and macOS `start.command` launchers.
- Added optional operating-system keyring storage for API secrets.
- Added schema-versioned SQLite migrations and token/cost usage reporting.
- Added `pyproject.toml`, PyInstaller build specification and release builder.
- Added GitHub Actions across Linux, Windows, macOS and Python 3.10/3.12.
- Added synthetic image-to-provider-to-report integration testing.
- Added opt-in live credential smoke testing without uploading product images.

## 2.1.0

- Split the shared processing implementation into `sorter_core.py`.
- Kept `product_sorter.py` as a compatible CLI entry point.
- Added `product_sorter_gui.py` with settings, API keys, start/stop/resume,
  live progress, ETA, logs, completed/pending/failed tables, and output opening.
- Added safe non-interactive engine mode for GUI subprocess control.
- Updated `start.sh` to let users choose GUI or CLI.

## 2.0.0

- Added Gemini, OpenAI and Anthropic provider configuration with fallback.
- Added API-key validation, request/cost estimates and configuration checks.
- Added single-instance output locking and automatic progress backups.
- Added persistent failure records, `error_report.csv`, and `--retry-failed`.
- Added ground-truth quality scoring with `--ground-truth expected.csv`.
- Added log rotation, version reporting, and beginner `start.sh` launcher.

## 1.0.0

- Initial multilingual product-photo sorter with progress, resume, `.env`,
  internet checks, API-key rotation, status lists and setup wizard.
# Unreleased

- Reworked progress rendering to keep one clean ANSI terminal line.
- Prevented captured GUI, CI, and redirected output from flooding logs with
  per-second progress snapshots.
