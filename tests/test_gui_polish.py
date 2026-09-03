import unittest

from ai_product_photo_sorter.gui_polish import next_tab_index


class GuiPolishTests(unittest.TestCase):
    def test_workspace_navigation_wraps_forward_and_backward(self):
        self.assertEqual(next_tab_index(0, 5, 1), 1)
        self.assertEqual(next_tab_index(4, 5, 1), 0)
        self.assertEqual(next_tab_index(0, 5, -1), 4)

    def test_empty_workspace_collection_is_safe(self):
        self.assertEqual(next_tab_index(0, 0, 1), 0)


if __name__ == "__main__":
    unittest.main()
