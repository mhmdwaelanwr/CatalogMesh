import os
import unittest
from unittest.mock import patch

# Import the GUI feature catalogs so the runtime validator sees the same catalog
# set that the desktop facade loads in production.
from ai_product_photo_sorter import (
    automation_gui,
    benchmark_gui,
    catalog_exports_gui,
    environment_gui,
    hybrid_gui,
    hybrid_routing_gui,
    local_evidence_gui,
    ollama_gui,
    performance_gui,
    report_gui,
    review_center_gui,
    rclone_gui,
    sku_matching_gui,
    threshold_calibration_gui,
)
from ai_product_photo_sorter.branding import APP_NAME, APP_TAGLINE
from ai_product_photo_sorter.gui_i18n_runtime import (
    TranslationIndex,
    collect_translation_triplets,
    validate_loaded_catalogs,
)


class GuiI18nRuntimeTests(unittest.TestCase):
    def test_all_loaded_gui_catalogs_have_three_language_parity(self):
        self.assertEqual(validate_loaded_catalogs(), ())

    def test_runtime_index_translates_legacy_hardcoded_literals(self):
        index = TranslationIndex(collect_translation_triplets())
        with patch.dict(os.environ, {"PRODUCT_SORTER_ARABIC_SHAPING": "0"}):
            self.assertEqual(index.translate("Browse…", "ar"), "استعراض…")
            self.assertEqual(index.translate("Source and output are required", "ar"), "مجلد الصور ومجلد النتائج مطلوبان")
        self.assertEqual(index.translate("Browse…", "zh"), "浏览…")
        self.assertEqual(index.translate("Unknown technical detail", "zh"), "Unknown technical detail")

    def test_template_translation_preserves_runtime_provider_value(self):
        index = TranslationIndex(collect_translation_triplets())
        self.assertEqual(
            index.translate("Enter at least one GEMINI API key first.", "zh"),
            "请先至少输入一个 GEMINI API 密钥。",
        )
        with patch.dict(os.environ, {"PRODUCT_SORTER_ARABIC_SHAPING": "0"}):
            self.assertEqual(
                index.translate("All OPENAI keys are exhausted. Enter a new key to continue:", "ar"),
                "انتهت كل مفاتيح OPENAI. أدخل مفتاحًا جديدًا للمتابعة:",
            )

    def test_storage_catalog_participates_in_global_translation_index(self):
        index = TranslationIndex(collect_translation_triplets())
        self.assertEqual(index.translate("Cloud Storage · rclone", "zh"), "云存储 · rclone")
        with patch.dict(os.environ, {"PRODUCT_SORTER_ARABIC_SHAPING": "0"}):
            self.assertEqual(index.translate("Cloud Storage · rclone", "ar"), "التخزين السحابي · rclone")

    def test_catalogmesh_brand_has_all_supported_taglines(self):
        self.assertEqual(APP_NAME, "CatalogMesh")
        self.assertEqual(set(APP_TAGLINE), {"en", "ar", "zh"})
        self.assertTrue(all(APP_TAGLINE.values()))


if __name__ == "__main__":
    unittest.main()
