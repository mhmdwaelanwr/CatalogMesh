import unittest

from ai_product_photo_sorter.arabic_ui import (
    arabic_visual_fix_enabled,
    contains_arabic,
    prepare_arabic_catalog,
    shape_arabic_for_tk,
)


class ArabicUiTests(unittest.TestCase):
    def test_detects_arabic_script(self):
        self.assertTrue(contains_arabic("منظم صور المنتجات"))
        self.assertFalse(contains_arabic("Product Sorter Pro"))

    def test_forced_shaping_changes_arabic_visual_order(self):
        logical = "منظم صور المنتجات"
        rendered = shape_arabic_for_tk(logical, force=True)
        self.assertNotEqual(rendered, logical)
        self.assertTrue(rendered)

    def test_mixed_latin_token_is_preserved(self):
        rendered = shape_arabic_for_tk("مطابقة SKU / الكتالوج", force=True)
        self.assertIn("SKU", rendered)

    def test_format_fields_survive_pre_shaping(self):
        rendered = shape_arabic_for_tk("تمت معالجة {count} من {total} صورة", force=True)
        self.assertIn("{count}", rendered)
        self.assertIn("{total}", rendered)
        self.assertIn("17", rendered.format(count=17, total=20))

    def test_disabled_shaping_is_identity(self):
        logical = "إنشاء تقرير Markdown ذكي شامل"
        self.assertEqual(shape_arabic_for_tk(logical, force=False), logical)

    def test_catalog_preparation_handles_nested_values(self):
        catalog = {
            "en": {"title": "Title"},
            "ar": {
                "title": "مركز المراجعة",
                "pair": ("فتح النتائج", "تقرير Markdown"),
            },
        }
        self.assertTrue(prepare_arabic_catalog(catalog, force=True))
        self.assertNotEqual(catalog["ar"]["title"], "مركز المراجعة")
        self.assertIn("Markdown", catalog["ar"]["pair"][1])

    def test_platform_default_is_linux_only_without_override(self):
        self.assertTrue(arabic_visual_fix_enabled(platform="linux"))
        self.assertFalse(arabic_visual_fix_enabled(platform="win32"))
        self.assertFalse(arabic_visual_fix_enabled(platform="darwin"))
        self.assertTrue(arabic_visual_fix_enabled(platform="win32", env_value="1"))
        self.assertFalse(arabic_visual_fix_enabled(platform="linux", env_value="0"))


if __name__ == "__main__":
    unittest.main()
