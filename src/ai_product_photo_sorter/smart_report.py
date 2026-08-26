"""Optional operation-wide Markdown report with deterministic facts and AI advice.

The report is intentionally one file per sorting operation. Programmatic facts are
calculated locally from Product Sorter's own results; an optional final text-only
AI call turns those facts into a concise executive analysis and recommendations.
The AI never supplies the numeric tables, so a failed narrative call cannot make
the core catalog run fail or corrupt the report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from model_catalog import default_model
from professional import VERSION, record_usage
from providers import configured_rest_providers

REPORT_ENV = "PRODUCT_SORTER_MD_REPORT"
REPORT_NAME = "SMART_REPORT.md"
REPORT_TEMP_NAME = "SMART_REPORT.md.tmp"
_TRUE = {"1", "true", "yes", "on"}


def report_enabled() -> bool:
    return os.getenv(REPORT_ENV, "").strip().lower() in _TRUE


def _fmt_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TiB"


def _safe_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _usage_facts(output: Path) -> list[dict[str, Any]]:
    db_path = output / "progress.sqlite3"
    if not db_path.is_file():
        return []
    try:
        db = sqlite3.connect(db_path)
        rows = db.execute(
            """SELECT provider, model, COUNT(*), COALESCE(SUM(input_tokens),0),
                      COALESCE(SUM(output_tokens),0), COALESCE(SUM(estimated_cost),0)
               FROM api_usage GROUP BY provider, model ORDER BY provider, model"""
        ).fetchall()
        db.close()
        return [
            {
                "provider": row[0] or "",
                "model": row[1] or "",
                "calls": int(row[2] or 0),
                "input_tokens": int(row[3] or 0),
                "output_tokens": int(row[4] or 0),
                "estimated_cost": float(row[5] or 0),
            }
            for row in rows
        ]
    except (OSError, sqlite3.Error):
        return []


def _source_bytes(items: list[dict[str, Any]]) -> int:
    total = 0
    seen: set[Path] = set()
    for item in items:
        path = Path(item.get("path", ""))
        try:
            identity = path.resolve()
            if identity in seen:
                continue
            seen.add(identity)
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _collect_facts(
    items: list[dict[str, Any]], output: Path, confidence_threshold: float
) -> dict[str, Any]:
    rows = _read_csv(output / "classification_report.csv")
    status_rows = _read_csv(output / "processing_status.csv")

    categories: Counter[str] = Counter()
    views: Counter[str] = Counter()
    brands: Counter[str] = Counter()
    product_rows: dict[str, dict[str, Any]] = {}
    group_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "category": "",
            "brand": "",
            "model": "",
            "photos": 0,
            "views": Counter(),
            "confidences": [],
            "needs_review": False,
        }
    )
    confidences: list[float] = []
    review_rows: list[dict[str, str]] = []

    for row in rows:
        category = row.get("category", "other") or "other"
        view = row.get("view", "unknown") or "unknown"
        brand = row.get("brand", "").strip()
        group = row.get("product_group", "").strip() or "unassigned"
        status = row.get("status", "")
        try:
            conf = float(row.get("confidence", "0") or 0)
        except ValueError:
            conf = 0.0
        categories[category] += 1
        views[view] += 1
        if brand:
            brands[brand] += 1
        confidences.append(conf)
        acc = group_acc[group]
        acc["category"] = acc["category"] or category
        acc["brand"] = acc["brand"] or brand
        acc["model"] = acc["model"] or row.get("model", "").strip()
        acc["photos"] += 1
        acc["views"][view] += 1
        acc["confidences"].append(conf)
        acc["needs_review"] = acc["needs_review"] or status == "needs_review"
        if status == "needs_review":
            review_rows.append(row)

    for group, acc in group_acc.items():
        values = acc["confidences"] or [0.0]
        product_rows[group] = {
            "product_group": group,
            "category": acc["category"],
            "brand": acc["brand"],
            "model": acc["model"],
            "photos": acc["photos"],
            "views": ", ".join(
                f"{name}:{count}" for name, count in sorted(acc["views"].items())
            ),
            "avg_confidence": sum(values) / len(values),
            "min_confidence": min(values),
            "status": "needs_review" if acc["needs_review"] else "classified",
        }

    completed = sum(1 for row in status_rows if row.get("status") == "completed")
    pending = sum(1 for row in status_rows if row.get("status") != "completed")
    if not status_rows:
        completed = len(rows)
        pending = 0

    capture_values = []
    for item in items:
        taken = item.get("taken_at")
        if isinstance(taken, datetime):
            capture_values.append(taken)

    category_products: Counter[str] = Counter(
        row["category"] for row in product_rows.values() if row["category"]
    )
    missing_brand = sum(1 for row in product_rows.values() if not row["brand"])
    missing_model = sum(1 for row in product_rows.values() if not row["model"])
    single_photo = sum(1 for row in product_rows.values() if row["photos"] == 1)
    low_confidence = sum(
        1 for row in rows
        if float(row.get("confidence", "0") or 0) < confidence_threshold
    )
    other_count = categories.get("other", 0)
    average = sum(confidences) / len(confidences) if confidences else 0.0

    signals: list[str] = []
    if rows and review_rows:
        signals.append(
            f"{len(review_rows)} of {len(rows)} photos ({len(review_rows)/len(rows):.1%}) require review."
        )
    if low_confidence:
        signals.append(f"{low_confidence} photos are below the {confidence_threshold:.0%} confidence threshold.")
    if other_count:
        signals.append(f"{other_count} photos remain in the 'other' category.")
    if single_photo:
        signals.append(f"{single_photo} product groups contain only one photo.")
    if missing_brand:
        signals.append(f"{missing_brand} product groups have no detected brand.")
    if missing_model:
        signals.append(f"{missing_model} product groups have no detected model.")
    sparse_categories = sum(1 for count in category_products.values() if count == 1)
    if sparse_categories >= 3:
        signals.append(
            f"{sparse_categories} categories contain only one product group; review for near-synonym taxonomy fragmentation."
        )
    if not signals:
        signals.append("No major deterministic quality warning was detected from the current report.")

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": VERSION,
        "status": "complete" if pending == 0 else "partial",
        "photos": len(rows),
        "completed": completed,
        "pending": pending,
        "product_count": len(product_rows),
        "category_count": len(categories),
        "review_photo_count": len(review_rows),
        "source_bytes": _source_bytes(items),
        "output_mode": os.getenv("PRODUCT_SORTER_OUTPUT_MODE", "copy") or "copy",
        "confidence_threshold": confidence_threshold,
        "avg_confidence": average,
        "min_confidence": min(confidences) if confidences else 0.0,
        "max_confidence": max(confidences) if confidences else 0.0,
        "capture_start": min(capture_values).isoformat(sep=" ") if capture_values else "",
        "capture_end": max(capture_values).isoformat(sep=" ") if capture_values else "",
        "categories": categories,
        "category_products": category_products,
        "views": views,
        "brands": brands,
        "products": list(product_rows.values()),
        "reviews": review_rows,
        "signals": signals,
        "usage": _usage_facts(output),
    }


def _ai_prompt(facts: dict[str, Any], language: str) -> str:
    language_name = {"ar": "Arabic", "zh": "Chinese", "en": "English"}.get(language, "English")
    compact = {
        "operation_status": facts["status"],
        "photos": facts["photos"],
        "products": facts["product_count"],
        "categories": dict(facts["categories"].most_common()),
        "top_brands": dict(facts["brands"].most_common(20)),
        "views": dict(facts["views"].most_common()),
        "review_photos": facts["review_photo_count"],
        "confidence_threshold": facts["confidence_threshold"],
        "average_confidence": facts["avg_confidence"],
        "quality_signals": facts["signals"],
    }
    return f"""You are reviewing a completed product-photo sorting operation for a retail store.
Write in {language_name}. Use ONLY the supplied facts. Do not invent prices, stock
levels, brands, models, sales performance, or product facts that are not present.
Focus on catalog quality, taxonomy consistency, reshoot/review priorities, and
practical next actions for preparing an e-commerce catalog.

Facts:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Return JSON only with this exact shape:
{{
  "executive_summary": "2-4 concise sentences",
  "observations": ["fact-grounded observation", "..."],
  "recommendations": ["practical recommendation", "..."],
  "store_actions": ["next action for catalog/store workflow", "..."],
  "caveats": ["important limitation or review note", "..."]
}}
Keep each list to at most 8 useful items.
"""


def _parse_ai_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _gemini_ai(prompt: str) -> tuple[dict[str, Any], str, str, dict[str, int]] | None:
    keys = []
    for index in range(1, 5):
        value = os.getenv(f"GEMINI_API_KEY_{index}", "").strip()
        if value and value not in keys:
            keys.append(value)
    legacy = os.getenv("GEMINI_API_KEY", "").strip()
    if legacy and legacy not in keys:
        keys.append(legacy)
    if not keys:
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None
    model = os.getenv("GEMINI_MODEL", default_model("gemini") or "gemini-3.6-flash")
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.2
                ),
            )
            usage = getattr(response, "usage_metadata", None)
            tokens = {
                "input_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
                "output_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
            }
            return _parse_ai_json(response.text), "gemini", model, tokens
        except Exception:
            continue
    return None


def _rest_ai(prompt: str, provider_name: str) -> tuple[dict[str, Any], str, str, dict[str, int]] | None:
    pools = {pool.name: pool for pool in configured_rest_providers()}
    pool = pools.get(provider_name)
    if not pool:
        return None
    for client in pool.clients:
        try:
            raw = client.generate(prompt, [], lambda _path: b"")
            usage = client.last_usage or {}
            tokens = {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            }
            return _parse_ai_json(raw), provider_name, client.model, tokens
        except Exception:
            continue
    return None


def _generate_ai_sections(facts: dict[str, Any], language: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prompt = _ai_prompt(facts, language)
    requested = [
        value.strip().lower()
        for value in os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini")).split(",")
        if value.strip()
    ]
    for provider in requested:
        result = _gemini_ai(prompt) if provider == "gemini" else _rest_ai(prompt, provider)
        if result:
            sections, name, model, tokens = result
            return sections, {"provider": name, "model": model, **tokens}
    return None, None


def _record_report_usage(output: Path, usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    db_path = output / "progress.sqlite3"
    if not db_path.is_file():
        return
    try:
        db = sqlite3.connect(db_path)
        record_usage(
            db,
            str(usage.get("provider", "")),
            str(usage.get("model", "")),
            int(usage.get("input_tokens", 0) or 0),
            int(usage.get("output_tokens", 0) or 0),
        )
        db.close()
    except (OSError, sqlite3.Error):
        pass


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(_safe_cell(value) for value in row) + " |" for row in rows]
    return lines


def _labels(language: str) -> dict[str, str]:
    if language == "ar":
        return {
            "title": "تقرير Product Sorter الذكي",
            "summary": "الملخص التنفيذي",
            "snapshot": "ملخص العملية",
            "taxonomy": "التصنيفات المكتشفة",
            "inventory": "فهرس المنتجات",
            "review": "قائمة المراجعة",
            "coverage": "تغطية زوايا التصوير",
            "brands": "العلامات التجارية",
            "usage": "استخدام الـ API",
            "files": "معمارية ملفات العملية",
            "signals": "إشارات جودة البيانات",
            "ai": "تحليل ونصائح الذكاء الاصطناعي",
            "method": "المنهجية وحدود التقرير",
        }
    if language == "zh":
        return {
            "title": "Product Sorter 智能报告", "summary": "执行摘要", "snapshot": "任务概览",
            "taxonomy": "发现的分类", "inventory": "产品清单", "review": "待复核项目",
            "coverage": "拍摄视角覆盖", "brands": "品牌", "usage": "API 使用情况",
            "files": "任务文件结构", "signals": "数据质量信号", "ai": "AI 分析与建议",
            "method": "方法与限制",
        }
    return {
        "title": "Product Sorter Smart Report", "summary": "Executive summary", "snapshot": "Operation snapshot",
        "taxonomy": "Discovered taxonomy", "inventory": "Product inventory", "review": "Review queue",
        "coverage": "Photo-view coverage", "brands": "Brands", "usage": "API usage",
        "files": "Operation file architecture", "signals": "Data-quality signals", "ai": "AI analysis and recommendations",
        "method": "Method and limitations",
    }


def _render_report(facts: dict[str, Any], ai: dict[str, Any] | None, ai_usage: dict[str, Any] | None, language: str) -> str:
    L = _labels(language)
    lines = [f"# {L['title']}", "", f"> Product Sorter {facts['version']} · {facts['generated_at']} · status: **{facts['status']}**", ""]

    lines += [f"## {L['summary']}", ""]
    if ai and ai.get("executive_summary"):
        lines.append(str(ai["executive_summary"]).strip())
    else:
        lines.append(
            f"{facts['photos']} photos were organized into {facts['product_count']} product groups across "
            f"{facts['category_count']} categories. {facts['review_photo_count']} photos require review."
        )
    lines.append("")

    lines += [f"## {L['snapshot']}", ""]
    lines += _table(
        ["Metric", "Value"],
        [
            ["Operation status", facts["status"]],
            ["Photos classified", facts["photos"]],
            ["Completed / pending", f"{facts['completed']} / {facts['pending']}"],
            ["Product groups", facts["product_count"]],
            ["Categories", facts["category_count"]],
            ["Photos needing review", facts["review_photo_count"]],
            ["Selected source size", _fmt_bytes(facts["source_bytes"])],
            ["Output mode", facts["output_mode"]],
            ["Confidence threshold", f"{facts['confidence_threshold']:.0%}"],
            ["Average / min / max confidence", f"{facts['avg_confidence']:.1%} / {facts['min_confidence']:.1%} / {facts['max_confidence']:.1%}"],
            ["Capture window", f"{facts['capture_start']} → {facts['capture_end']}" if facts['capture_start'] else "unknown"],
        ],
    )
    lines.append("")

    lines += [f"## {L['taxonomy']}", ""]
    category_rows = []
    for name, photo_count in facts["categories"].most_common():
        category_rows.append([
            name, photo_count, facts["category_products"].get(name, 0),
            f"{photo_count / facts['photos']:.1%}" if facts["photos"] else "0%",
        ])
    lines += _table(["Category", "Photos", "Products", "Share"], category_rows or [["—", 0, 0, "0%"]])
    lines.append("")

    lines += [f"## {L['inventory']}", ""]
    inventory_rows = [
        [row["product_group"], row["category"], row["brand"] or "—", row["model"] or "—", row["photos"], row["views"], f"{row['avg_confidence']:.1%}", row["status"]]
        for row in facts["products"]
    ]
    lines += _table(["Product group", "Category", "Brand", "Model", "Photos", "Views", "Avg confidence", "Status"], inventory_rows or [["—", "—", "—", "—", 0, "—", "0%", "—"]])
    lines.append("")

    lines += [f"## {L['review']}", ""]
    review_rows = [
        [row.get("filename", ""), row.get("product_group", ""), row.get("category", ""), row.get("brand", "") or "—", row.get("model", "") or "—", row.get("view", ""), f"{float(row.get('confidence', '0') or 0):.1%}", row.get("reason", "")]
        for row in facts["reviews"]
    ]
    if review_rows:
        lines += _table(["File", "Product", "Category", "Brand", "Model", "View", "Confidence", "Reason"], review_rows)
    else:
        lines.append("No photos are currently marked for review.")
    lines.append("")

    lines += [f"## {L['coverage']}", ""]
    lines += _table(["View", "Photos"], [[name, count] for name, count in facts["views"].most_common()] or [["unknown", 0]])
    lines.append("")

    lines += [f"## {L['brands']}", ""]
    lines += _table(["Brand", "Detected photos"], [[name, count] for name, count in facts["brands"].most_common()] or [["No brand detected", 0]])
    lines.append("")

    lines += [f"## {L['signals']}", ""]
    lines += [f"- {signal}" for signal in facts["signals"]]
    lines.append("")

    lines += [f"## {L['usage']}", ""]
    usage_rows = [[row["provider"], row["model"], row["calls"], row["input_tokens"], row["output_tokens"], f"{row['estimated_cost']:.6f}"] for row in facts["usage"]]
    if ai_usage:
        usage_rows.append([ai_usage.get("provider", ""), ai_usage.get("model", ""), "1 (smart report)", ai_usage.get("input_tokens", 0), ai_usage.get("output_tokens", 0), "recorded in api_usage.csv"])
    lines += _table(["Provider", "Model", "Calls", "Input tokens", "Output tokens", "Estimated cost"], usage_rows or [["—", "—", 0, 0, 0, "0"]])
    lines.append("")

    lines += [f"## {L['files']}", "", "```text", f"{output_name(facts)}/", "├── <category>/Product_####_<brand_model>/", "├── Needs_Review/", "├── classification_report.csv", "├── category_registry.json", "├── processing_status.csv", "├── progress.sqlite3", "├── api_usage.csv", "├── error_report.csv", "├── run_history.log", f"└── {REPORT_NAME}", "```", ""]
    lines += _table(
        ["File", "Purpose"],
        [
            ["classification_report.csv", "Per-photo classification, product group, view, brand/model, confidence and review state"],
            ["category_registry.json", "AI-grown category registry for this operation"],
            ["processing_status.csv", "Completed/pending resume state"],
            ["progress.sqlite3", "Crash-safe cached batches and usage state"],
            ["api_usage.csv", "Provider/model token and estimated-cost log"],
            ["error_report.csv", "Failed-batch diagnostics"],
            ["run_history.log", "Human-readable operation events"],
            [REPORT_NAME, "This operation-wide summary"],
        ],
    )
    lines.append("")

    lines += [f"## {L['ai']}", ""]
    if ai:
        for key, heading in (("observations", "Observations"), ("recommendations", "Recommendations"), ("store_actions", "Store actions"), ("caveats", "Caveats")):
            values = ai.get(key, [])
            if values:
                lines += [f"### {heading}", ""] + [f"- {str(value).strip()}" for value in values] + [""]
    else:
        lines.append("AI narrative was unavailable. All deterministic tables above were still generated locally from Product Sorter's own operation data.")
        lines.append("")

    lines += [f"## {L['method']}", "", "- Numeric counts, categories, product groups, confidence values, file structure and review state are generated programmatically from Product Sorter outputs.", "- The AI section is advisory and receives a compact fact summary only; it is instructed not to invent product, stock, price or sales facts.", "- Source originals are not modified by generating this report.", "- This is one report for the complete operation; category and product details are represented as sections/tables instead of creating one Markdown file per folder.", ""]
    return "\n".join(lines)


def output_name(facts: dict[str, Any]) -> str:
    return "Sorted_Products"


def generate_smart_report(
    items: list[dict[str, Any]],
    output: Path,
    confidence_threshold: float,
    ai_generator: Callable[[dict[str, Any], str], tuple[dict[str, Any] | None, dict[str, Any] | None]] | None = None,
) -> Path:
    """Generate one operation-wide SMART_REPORT.md without risking the core run."""
    facts = _collect_facts(items, output, confidence_threshold)
    language = os.getenv("APP_LANGUAGE", "en").strip().lower()
    if language not in {"ar", "en", "zh"}:
        language = "en"
    generator = ai_generator or _generate_ai_sections
    ai_sections: dict[str, Any] | None = None
    ai_usage: dict[str, Any] | None = None
    try:
        ai_sections, ai_usage = generator(facts, language)
    except Exception:
        ai_sections, ai_usage = None, None
    _record_report_usage(output, ai_usage)
    text = _render_report(facts, ai_sections, ai_usage, language)
    path = output / REPORT_NAME
    temp = output / REPORT_TEMP_NAME
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
    return path


def apply_smart_report(module: Any) -> None:
    """Add CLI flag + final report generation without rewriting the stable engine."""
    base_parse_args = module.parse_args
    base_build_outputs = module.build_outputs

    def parse_args(env_file: Path) -> argparse.Namespace:
        original = list(sys.argv)
        explicit: bool | None = None
        remaining = [original[0]]
        for value in original[1:]:
            if value == "--md-report":
                explicit = True
            elif value == "--no-md-report":
                explicit = False
            else:
                remaining.append(value)
        sys.argv[:] = remaining
        try:
            try:
                args = base_parse_args(env_file)
            except SystemExit as exc:
                if exc.code == 0 and any(flag in original for flag in ("-h", "--help")):
                    print("\nSmart Markdown report:\n  --md-report       Generate SMART_REPORT.md after sorting (one extra text-only AI call)\n  --no-md-report    Disable it even if PRODUCT_SORTER_MD_REPORT is enabled")
                raise
        finally:
            sys.argv[:] = original
        enabled = report_enabled() if explicit is None else explicit
        os.environ[REPORT_ENV] = "true" if enabled else "false"
        setattr(args, "md_report", enabled)
        return args

    def build_outputs(items: list[dict[str, Any]], output: Path, confidence: float, dry_run: bool) -> None:
        base_build_outputs(items, output, confidence, dry_run)
        if dry_run or not report_enabled():
            return
        try:
            report = generate_smart_report(items, output, confidence)
            print(f"Smart report: {report}")
            if hasattr(module, "append_log"):
                module.append_log(output, "SMART_REPORT_WRITTEN", f"path={report.name}")
        except Exception as exc:
            # Report generation must never turn a successful photo-sort into a failed run.
            warning = f"Smart report could not be generated: {exc}"
            print(warning, file=sys.stderr)
            if hasattr(module, "append_log"):
                module.append_log(output, "SMART_REPORT_FAILED", str(exc))

    module.parse_args = parse_args
    module.build_outputs = build_outputs
    module.generate_smart_report = generate_smart_report
