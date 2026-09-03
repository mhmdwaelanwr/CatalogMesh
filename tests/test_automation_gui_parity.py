import unittest

from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.automation_gui import (
    REMOTE_MUTATION_COMMANDS,
    _wheel_units,
    build_argv,
    command_names,
    cli_preview,
)


class _WheelEvent:
    def __init__(self, *, delta=0, num=None):
        self.delta = delta
        self.num = num


class AutomationGuiParityTests(unittest.TestCase):
    def test_gui_command_catalog_matches_cli_subcommands_exactly(self):
        parser = build_parser()
        subcommands = set()
        for action in parser._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                subcommands.update(choices)
        self.assertEqual(set(command_names()), subcommands)

    def test_remote_mutation_commands_are_explicitly_guarded(self):
        expected = {
            "execute-shopify-stage",
            "execute-shopify-publish",
            "execute-shopify-rollback",
            "execute-akeneo-products",
            "execute-akeneo-rollback",
            "execute-odoo-products",
        }
        self.assertEqual(REMOTE_MUTATION_COMMANDS, expected)
        self.assertTrue(expected.issubset(set(command_names())))

    def test_build_argv_handles_paths_flags_and_repeated_options(self):
        argv = build_argv(
            "missing-assets",
            {
                "catalog": "catalog.csv",
                "sku_column": "SKU",
                "asset_columns": "front, back",
            },
        )
        self.assertEqual(
            argv,
            [
                "missing-assets",
                "catalog.csv",
                "--sku-column",
                "SKU",
                "--asset-column",
                "front",
                "--asset-column",
                "back",
            ],
        )

    def test_build_argv_boolean_flag_represents_flag_presence(self):
        self.assertEqual(
            build_argv("scan", {"root": "photos", "no_recursive": True}),
            ["scan", "photos", "--no-recursive"],
        )
        self.assertEqual(
            build_argv("scan", {"root": "photos", "no_recursive": False}),
            ["scan", "photos"],
        )

    def test_preview_uses_public_automation_entrypoint(self):
        self.assertEqual(
            cli_preview(["scan", "My Photos"]),
            "product-sorter-automation scan 'My Photos'",
        )

    def test_scroll_wheel_normalizes_windows_macos_and_linux_events(self):
        self.assertLess(_wheel_units(_WheelEvent(delta=120)), 0)
        self.assertGreater(_wheel_units(_WheelEvent(delta=-120)), 0)
        self.assertEqual(_wheel_units(_WheelEvent(num=4)), -3)
        self.assertEqual(_wheel_units(_WheelEvent(num=5)), 3)
        self.assertEqual(_wheel_units(_WheelEvent()), 0)


if __name__ == "__main__":
    unittest.main()
