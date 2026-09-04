import argparse
import unittest

from ai_product_photo_sorter import rclone_storage, storage_cli
from ai_product_photo_sorter.automation_gui import command_names
from ai_product_photo_sorter.capabilities import (
    STORAGE_CAPABILITIES,
    storage_automation_commands,
    storage_backend_callables,
    storage_cli_commands,
)


def _subcommands(parser: argparse.ArgumentParser) -> set[str]:
    commands: set[str] = set()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            commands.update(choices)
    return commands


class CapabilityParityTests(unittest.TestCase):
    def test_storage_registry_matches_first_class_cli_and_automation_aliases(self):
        self.assertEqual(_subcommands(storage_cli.build_parser()), set(storage_cli_commands()))
        self.assertTrue(storage_automation_commands().issubset(set(command_names())))

    def test_storage_registry_points_to_real_shared_backend_capabilities(self):
        for name in storage_backend_callables():
            self.assertTrue(callable(getattr(rclone_storage, name, None)), name)
        self.assertTrue(all(item.gui_surface == "Storage Center" for item in STORAGE_CAPABILITIES))
        self.assertTrue(all(not item.visual_only for item in STORAGE_CAPABILITIES))


if __name__ == "__main__":
    unittest.main()
