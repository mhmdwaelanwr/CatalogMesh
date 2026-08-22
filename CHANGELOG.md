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
- Redesigned the desktop GUI as a three-workspace dashboard with dark styling,
  operation controls, live status, result metrics, and improved activity views.
- Expanded the README with workflow, GUI, resume, model-selection, and
  troubleshooting guidance.
- Added instant persistent dark/light mode switching to the desktop GUI.
- Added a localized About workspace with version, developer, MIT license,
  profile links, and one-click contact copying.
- Added matching dark and light GUI previews to the README.
- Replaced design previews with 16 real application screenshots and added a
  structured, feature-by-feature visual walkthrough to the README.
- Promoted the high-resolution light operation workspace as the README hero image.
- Rebuilt the README with a project-style hero, status badges, navigation,
  capability matrix, safety guidance, and documented output structure.
- Removed the standalone Arabic README section while retaining multilingual app support.
