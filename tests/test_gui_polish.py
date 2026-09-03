import unittest

from ai_product_photo_sorter.gui_polish import (
    SCROLLABLE_WORKSPACE_KEYS,
    next_tab_index,
    wheel_units,
)


class GuiPolishTests(unittest.TestCase):
    def test_workspace_navigation_wraps_forward_and_backward(self):
        self.assertEqual(next_tab_index(0, 5, 1), 1)
        self.assertEqual(next_tab_index(4, 5, 1), 0)
        self.assertEqual(next_tab_index(0, 5, -1), 4)

    def test_empty_workspace_collection_is_safe(self):
        self.assertEqual(next_tab_index(0, 0, 1), 0)

    def test_long_workspaces_are_explicitly_scrollable(self):
        self.assertEqual(
            SCROLLABLE_WORKSPACE_KEYS,
            ("setup", "benchmark", "review"),
        )

    def test_mousewheel_normalization_is_cross_platform(self):
        self.assertEqual(wheel_units(120), -1)
        self.assertEqual(wheel_units(-120), 1)
        self.assertEqual(wheel_units(480), -4)
        self.assertEqual(wheel_units(-480), 4)
        self.assertEqual(wheel_units(button=4), -3)
        self.assertEqual(wheel_units(button=5), 3)
        self.assertEqual(wheel_units(), 0)


if __name__ == "__main__":
    unittest.main()
