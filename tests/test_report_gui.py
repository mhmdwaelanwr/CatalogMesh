import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_photo_sorter import report_gui


class ReportGuiSelectionTests(unittest.TestCase):
    def _app(self):
        app = SimpleNamespace(
            _report_refreshing=False,
            current_report_path=Path("/tmp/report.md"),
            report_tree=MagicMock(),
            report_paths={"report-0": Path("/tmp/report.md")},
            show_report=MagicMock(),
        )
        app.report_tree.selection.return_value = ("report-0",)
        return app

    def test_selecting_current_report_does_not_reload_it(self):
        app = self._app()
        path = report_gui._select_report_for_test(app)
        if path:
            app.show_report(path, select_tab=False)
        app.show_report.assert_not_called()

    def test_selection_is_ignored_while_tree_is_refreshing(self):
        app = self._app()
        app._report_refreshing = True
        app.current_report_path = None
        path = report_gui._select_report_for_test(app)
        if path:
            app.show_report(path, select_tab=False)
        app.show_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
