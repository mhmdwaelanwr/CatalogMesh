import argparse
import subprocess
import sys
import unittest

from ai_product_photo_sorter import config_cli, gui, rclone_storage, storage_cli
from ai_product_photo_sorter.automation_gui import command_names
from ai_product_photo_sorter.capabilities import (
    ALL_REAL_CAPABILITIES,
    STORAGE_CAPABILITIES,
    WORKFLOW_CAPABILITIES,
    required_automation_commands,
    required_config_commands,
    required_core_cli_flags,
    storage_automation_commands,
    storage_backend_callables,
    storage_cli_commands,
)


EXPECTED_WORKSPACES = (
    "Operation setup",
    "Models & API keys",
    "Results & activity",
    "Review",
    "SKU Match",
    "Exports",
    "Storage",
    "Automation",
    "Reports",
    "Benchmark",
    "Environment",
    "About",
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

    def test_primary_registry_covers_all_workspaces_in_required_order(self):
        self.assertEqual(
            tuple(capability.workspace for capability in WORKFLOW_CAPABILITIES),
            EXPECTED_WORKSPACES,
        )

    def test_every_real_capability_has_a_live_gui_method_and_cli_surface(self):
        for capability in ALL_REAL_CAPABILITIES:
            with self.subTest(capability=capability.id):
                self.assertTrue(
                    callable(getattr(gui.App, capability.gui_method, None)),
                    f"GUI method missing: {capability.gui_method}",
                )
                if not capability.visual_only:
                    self.assertTrue(capability.cli_surface)
                    self.assertNotEqual(capability.cli_surface, "n/a")

    def test_all_registered_automation_commands_are_rendered_by_automation_center(self):
        commands = set(command_names())
        self.assertTrue(required_automation_commands().issubset(commands))

    def test_environment_registry_matches_bounded_config_cli(self):
        commands = _subcommands(config_cli.build_parser())
        self.assertEqual(commands, set(required_config_commands()))

    def test_composed_core_cli_help_contains_registered_capability_flags(self):
        completed = subprocess.run(
            [sys.executable, "-m", "ai_product_photo_sorter.cli", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        for flag in sorted(required_core_cli_flags()):
            with self.subTest(flag=flag):
                self.assertIn(flag, completed.stdout)


if __name__ == "__main__":
    unittest.main()
