import unittest

from ai_product_photo_sorter.gui_workflow import (
    WORKSPACE_USAGE_ORDER,
    workspace_usage_order,
)


class GuiWorkflowTests(unittest.TestCase):
    def test_usage_order_matches_daily_catalog_flow(self):
        records = [
            ("setup", "Operation setup"),
            ("models", "Models & API keys"),
            ("results", "Results & activity"),
            ("benchmark", "Benchmark"),
            ("environment", "Environment"),
            ("reports", "Reports"),
            ("about", "About"),
            ("review", "Review"),
            ("sku", "SKU Match"),
            ("exports", "Exports"),
            ("automation", "Automation"),
        ]
        ordered_ids = workspace_usage_order(records)
        labels = {tab_id: label for tab_id, label in records}
        self.assertEqual(
            tuple(labels[tab_id] for tab_id in ordered_ids),
            WORKSPACE_USAGE_ORDER,
        )

    def test_unknown_future_tabs_are_preserved_at_end(self):
        records = [
            ("setup", "Operation setup"),
            ("future", "Future Lab"),
            ("about", "About"),
        ]
        self.assertEqual(
            workspace_usage_order(records),
            ("setup", "about", "future"),
        )


if __name__ == "__main__":
    unittest.main()
