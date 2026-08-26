import unittest
from unittest.mock import patch

from i18n import detect_language, set_language, tr


class LanguageTests(unittest.TestCase):
    @patch.dict("os.environ", {"LANG": "zh_CN.UTF-8"}, clear=True)
    def test_detects_chinese_device_language(self):
        self.assertEqual(detect_language(), "zh")

    @patch.dict("os.environ", {"LANG": "ar_EG.UTF-8"}, clear=True)
    def test_detects_arabic_device_language(self):
        self.assertEqual(detect_language(), "ar")

    def test_chinese_translation_is_available(self):
        set_language("zh")
        self.assertIn("图片", tr("all_photos"))
        set_language("en")


if __name__ == "__main__":
    unittest.main()
