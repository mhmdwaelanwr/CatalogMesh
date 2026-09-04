import unittest

from ai_product_photo_sorter.automation_gui import command_names
from ai_product_photo_sorter.capabilities import STORAGE_CAPABILITIES, storage_cli_commands


class CapabilityParityTests(unittest.TestCase):
    def test_storage_capabilities_are_exposed_by_canonical_cli_and_gui_parser(self):
        self.assertTrue(storage_cli_commands().issubset(set(command_names())))
        self.assertTrue(all(item.gui_surface == "Storage Center" for item in STORAGE_CAPABILITIES))
        self.assertTrue(all(not item.visual_only for item in STORAGE_CAPABILITIES))


if __name__ == "__main__":
    unittest.main()
