"""Small dependency-free Arabic/English/Chinese translation layer."""

from __future__ import annotations

import locale
import os


LANGUAGES = {"ar": "العربية", "en": "English", "zh": "中文"}
_language = "en"

TEXT = {
    "detected": {
        "ar": "تم اكتشاف لغة الجهاز: {name}. هل تريد الاستمرار بها؟ [Y/n]: ",
        "en": "Detected device language: {name}. Continue in this language? [Y/n]: ",
        "zh": "检测到设备语言：{name}。是否使用此语言继续？[Y/n]：",
    },
    "choose_language": {"ar": "اختر اللغة", "en": "Choose language", "zh": "选择语言"},
    "invalid": {"ar": "اختيار غير صحيح، حاول مرة أخرى.", "en": "Invalid choice. Try again.", "zh": "选择无效，请重试。"},
    "required": {"ar": "هذا الحقل مطلوب، حاول مرة أخرى.", "en": "This field is required. Try again.", "zh": "此项为必填项，请重试。"},
    "setup_title": {"ar": "إعداد Product Sorter", "en": "Product Sorter Setup", "zh": "Product Sorter 设置"},
    "keys_private": {"ar": "لن تظهر مفاتيح API أثناء كتابتها أو بعد الحفظ.", "en": "API keys stay hidden while typing and after saving.", "zh": "API 密钥在输入和保存后都不会显示。"},
    "api_key": {"ar": "مفتاح Gemini رقم {index}", "en": "Gemini API key {index}", "zh": "Gemini API 密钥 {index}"},
    "optional": {"ar": "اختياري", "en": "optional", "zh": "可选"},
    "keep_existing": {"ar": "Enter للاحتفاظ بالموجود", "en": "Enter to keep existing", "zh": "按 Enter 保留现有值"},
    "first_key_required": {"ar": "المفتاح الأول مطلوب.", "en": "The first API key is required.", "zh": "第一个 API 密钥为必填项。"},
    "source_path": {"ar": "مسار مجلد صور المنتجات", "en": "Product photos folder", "zh": "产品图片文件夹路径"},
    "output_path": {"ar": "مسار مجلد النتائج", "en": "Output folder", "zh": "输出文件夹路径"},
    "prices_path": {"ar": "مسار As3ar.xlsx (اختياري)", "en": "As3ar.xlsx path (optional)", "zh": "As3ar.xlsx 路径（可选）"},
    "model": {"ar": "اسم موديل Gemini", "en": "Gemini model name", "zh": "Gemini 模型名称"},
    "batch_size": {"ar": "عدد الصور في الدفعة من 3 إلى 8", "en": "Batch size from 3 to 8", "zh": "每批图片数（3 到 8）"},
    "confidence": {"ar": "حد الثقة من 0 إلى 1", "en": "Confidence threshold from 0 to 1", "zh": "置信度阈值（0 到 1）"},
    "retries": {"ar": "عدد محاولات إعادة الاتصال", "en": "Retry count", "zh": "重试次数"},
    "photo_limit": {"ar": "عدد صور العينة (فارغ للكل)", "en": "Sample photo count (blank for all)", "zh": "样本图片数量（留空表示全部）"},
    "existing_env": {"ar": "تم العثور على ملف .env موجود:", "en": "Existing .env file found:", "zh": "发现现有 .env 文件："},
    "edit_env": {"ar": "تعديل الإعدادات الحالية", "en": "Edit current settings", "zh": "编辑当前设置"},
    "run_existing": {"ar": "تشغيل بالإعدادات الحالية", "en": "Run with current settings", "zh": "使用当前设置运行"},
    "new_env": {"ar": "بدء إعداد جديد", "en": "Start new setup", "zh": "开始新设置"},
    "exit": {"ar": "خروج", "en": "Exit", "zh": "退出"},
    "save_only": {"ar": "حفظ .env فقط", "en": "Save .env only", "zh": "仅保存 .env"},
    "save_run": {"ar": "حفظ .env وتشغيل الآن", "en": "Save .env and run now", "zh": "保存 .env 并立即运行"},
    "cancel": {"ar": "إلغاء بدون حفظ", "en": "Cancel without saving", "zh": "取消且不保存"},
    "what_next": {"ar": "ماذا تريد أن تفعل؟", "en": "What would you like to do?", "zh": "您想做什么？"},
    "saved": {"ar": "تم حفظ الإعدادات بأمان في: {path}", "en": "Settings saved securely to: {path}", "zh": "设置已安全保存到：{path}"},
    "number_range": {"ar": "أدخل رقمًا من {minimum} إلى {maximum}.", "en": "Enter a number from {minimum} to {maximum}.", "zh": "请输入 {minimum} 到 {maximum} 之间的数字。"},
    "choose_numbers": {"ar": "اختر {choices}: ", "en": "Choose {choices}: ", "zh": "请选择 {choices}："},
    "cancelled": {"ar": "تم الإلغاء ولم يتغير ملف .env.", "en": "Cancelled; .env was not changed.", "zh": "已取消；.env 未更改。"},
    "run_later": {"ar": "شغّل لاحقًا بالأمر: python product_sorter.py", "en": "Run later with: python product_sorter.py", "zh": "稍后运行：python product_sorter.py"},
    "bad_photo_limit": {"ar": "عدد العينة غير صحيح؛ سيتم تركه فارغًا.", "en": "Invalid sample count; it will be left blank.", "zh": "样本数量无效；将留空。"},
    "running": {"ar": "يتم الآن تشغيل Product Sorter...", "en": "Starting Product Sorter...", "zh": "正在启动 Product Sorter..."},
    "all_photos": {"ar": "معالجة كل الصور", "en": "Process all photos", "zh": "处理所有图片"},
    "quick_sample": {"ar": "معالجة عينة سريعة ({count} صورة)", "en": "Process a quick sample ({count} photos)", "zh": "处理快速样本（{count} 张）"},
    "custom_count": {"ar": "إدخال عدد مخصص", "en": "Enter a custom count", "zh": "输入自定义数量"},
    "total_photos": {"ar": "إجمالي الصور الموجودة: {count}", "en": "Total photos found: {count}", "zh": "找到的图片总数：{count}"},
    "how_many": {"ar": "عاوز تعالج كام صورة؟ من 1 إلى {total}: ", "en": "How many photos? 1 to {total}: ", "zh": "要处理多少张图片？1 到 {total}："},
    "continue_previous": {"ar": "استكمال العملية السابقة", "en": "Continue previous operation", "zh": "继续上次操作"},
    "new_operation": {"ar": "بدء عملية جديدة في مجلد جديد", "en": "Start a new operation in a new folder", "zh": "在新文件夹中开始新操作"},
    "previous_status": {"ar": "عملية سابقة: تم {done}/{total}، متبقي {left}.", "en": "Previous operation: {done}/{total} processed; {left} remaining.", "zh": "上次操作：已处理 {done}/{total}，剩余 {left}。"},
    "requirements_ok": {"ar": "كل المكتبات المطلوبة مثبتة.", "en": "All required libraries are installed.", "zh": "所有必需库均已安装。"},
    "missing_libs": {"ar": "المكتبات التالية غير موجودة:", "en": "The following libraries are missing:", "zh": "缺少以下库："},
    "install_now": {"ar": "تحميل وتثبيت المكتبات الآن", "en": "Download and install now", "zh": "立即下载并安装"},
    "installing": {"ar": "جاري تثبيت المكتبات المطلوبة...", "en": "Installing required libraries...", "zh": "正在安装所需库..."},
    "install_success": {"ar": "تم تثبيت المكتبات بنجاح.", "en": "Libraries installed successfully.", "zh": "所需库安装成功。"},
    "install_failed": {"ar": "فشل تثبيت المكتبات؛ راجع رسائل pip.", "en": "Library installation failed; review the pip messages.", "zh": "库安装失败；请查看 pip 消息。"},
    "restart_next": {"ar": "سيُعاد تشغيل السكربت للخطوة التالية...", "en": "Restarting the script for the next step...", "zh": "正在重启脚本并进入下一步..."},
    "quota_all": {"ar": "انتهت حصة جميع مفاتيح Gemini.", "en": "All Gemini API keys have exhausted their quota.", "zh": "所有 Gemini API 密钥的配额均已用尽。"},
    "enter_new_key": {"ar": "أدخل مفتاحًا جديدًا أو Enter للتوقف: ", "en": "Enter a new API key or press Enter to stop: ", "zh": "输入新的 API 密钥，或按 Enter 停止："},
    "new_key_ok": {"ar": "تم قبول المفتاح الجديد؛ إعادة الدفعة الحالية.", "en": "New API key accepted; retrying the current batch.", "zh": "新 API 密钥已接受；正在重试当前批次。"},
    "switch_key": {"ar": "انتهت حصة المفتاح؛ التحويل إلى {current}/{total}.", "en": "Key quota exhausted; switching to {current}/{total}.", "zh": "密钥配额已用尽；切换到 {current}/{total}。"},
    "found_photos": {"ar": "تم العثور على {count} صورة JPG بالترتيب الزمني.", "en": "Found {count} JPG photos in chronological order.", "zh": "按时间顺序找到 {count} 张 JPG 图片。"},
    "selected_photos": {"ar": "تم اختيار {selected} من {total} صورة.", "en": "Selected {selected} of {total} photos.", "zh": "已选择 {selected}/{total} 张图片。"},
    "internet": {"ar": "الإنترنت: {quality} ({ms} ms)", "en": "Internet: {quality} ({ms} ms)", "zh": "网络：{quality}（{ms} ms）"},
    "excellent": {"ar": "ممتاز", "en": "excellent", "zh": "优秀"},
    "good": {"ar": "جيد", "en": "good", "zh": "良好"},
    "fair": {"ar": "متوسط", "en": "fair", "zh": "一般"},
    "weak": {"ar": "ضعيف", "en": "weak", "zh": "较弱"},
    "disconnected": {"ar": "غير متصل", "en": "offline", "zh": "离线"},
    "offline": {"ar": "لا يوجد اتصال بالإنترنت.", "en": "Internet connection is unavailable.", "zh": "网络连接不可用。"},
    "retry_or_quit": {"ar": "Enter لإعادة الفحص أو Q للخروج: ", "en": "Press Enter to retry or Q to quit: ", "zh": "按 Enter 重试，或输入 Q 退出："},
    "progress_remaining": {"ar": "متبقي {count} صورة", "en": "{count} photos left", "zh": "剩余 {count} 张"},
    "progress_eta": {"ar": "الوقت المتوقع {eta}", "en": "ETA {eta}", "zh": "预计剩余 {eta}"},
    "calculating": {"ar": "جارٍ الحساب", "en": "calculating", "zh": "正在计算"},
}


def detect_language() -> str:
    explicit = os.getenv("APP_LANGUAGE", "").lower().strip()
    if explicit in LANGUAGES:
        return explicit
    candidates = [os.getenv("LC_ALL", ""), os.getenv("LC_MESSAGES", ""), os.getenv("LANG", "")]
    try:
        candidates.append(locale.getlocale()[0] or "")
    except Exception:
        pass
    value = " ".join(candidates).lower()
    if "zh" in value:
        return "zh"
    if "ar" in value:
        return "ar"
    return "en"


def set_language(language: str) -> None:
    global _language
    _language = language if language in LANGUAGES else "en"


def get_language() -> str:
    return _language


def tr(key: str, **values: object) -> str:
    item = TEXT.get(key, {})
    template = item.get(_language) or item.get("en") or key
    return template.format(**values)


def confirm_language() -> str:
    detected = detect_language()
    set_language(detected)
    try:
        answer = input(tr("detected", name=LANGUAGES[detected])).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer in {"", "y", "yes", "نعم", "是"}:
        return detected
    print(f"\n{tr('choose_language')}:\n[1] العربية\n[2] English\n[3] 中文")
    while True:
        try:
            choice = input("1 / 2 / 3: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "2"
        if choice in {"1", "2", "3"}:
            selected = {"1": "ar", "2": "en", "3": "zh"}[choice]
            set_language(selected)
            return selected
        print(tr("invalid"))
