import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "Windows Tk render regression test")
class WorkspaceRenderWindowsTests(unittest.TestCase):
    def test_scrollable_workspaces_keep_real_content_visible(self):
        import tkinter as tk

        from ai_product_photo_sorter.gui import App
        from ai_product_photo_sorter.gui_workflow import WORKSPACE_USAGE_ORDER

        root = tk.Tk()
        try:
            root.geometry("1240x860+0+0")
            app = App(root)
            root.update_idletasks()
            root.update()

            self.assertEqual(root.title(), "CatalogMesh")
            labels = tuple(
                str(app.main_tabs.tab(tab_id, "text"))
                for tab_id in app.main_tabs.tabs()
            )
            self.assertEqual(labels, WORKSPACE_USAGE_ORDER)
            self.assertTrue(hasattr(app, "rclone_page"))
            self.assertEqual(app.rclone_title.cget("text"), "Cloud Storage · rclone")

            self.assertEqual(set(app._workspace_scrolls), {"setup", "benchmark", "review"})
            cases = (
                (app.setup_page, app.workspace_label, "operation setup"),
                (app.benchmark_page, app.benchmark_title, "benchmark"),
                (app.review_page, app.review_title, "review"),
            )
            for page, marker, name in cases:
                with self.subTest(workspace=name):
                    app.main_tabs.select(page)
                    root.update_idletasks()
                    root.update()
                    self.assertTrue(marker.winfo_exists(), f"{name} marker was destroyed")
                    self.assertTrue(marker.winfo_ismapped(), f"{name} marker is not mapped")
                    self.assertGreater(marker.winfo_width(), 2, f"{name} marker has no width")
                    self.assertGreater(marker.winfo_height(), 2, f"{name} marker has no height")
                    info = next(
                        value
                        for value in app._workspace_scrolls.values()
                        if value["page"] is page
                    )
                    self.assertIs(info["content"], page)
                    self.assertIs(info["host"], page)

            # Exercise the final runtime i18n layer against the real integrated
            # App, not only the pure translation index.
            app.lang = "zh"
            app.apply_language()
            root.update_idletasks()
            expected_zh = tuple(app.ui_translate(label) for label in WORKSPACE_USAGE_ORDER)
            actual_zh = tuple(
                str(app.main_tabs.tab(tab_id, "text"))
                for tab_id in app.main_tabs.tabs()
            )
            self.assertEqual(actual_zh, expected_zh)
            self.assertEqual(app.rclone_title.cget("text"), "云存储 · rclone")
            self.assertEqual(app.workspace_nav_label.cget("text"), "工作区")
            self.assertEqual(root.title(), "CatalogMesh")

            app.lang = "ar"
            app.apply_language()
            root.update_idletasks()
            expected_ar = tuple(app.ui_translate(label) for label in WORKSPACE_USAGE_ORDER)
            actual_ar = tuple(
                str(app.main_tabs.tab(tab_id, "text"))
                for tab_id in app.main_tabs.tabs()
            )
            self.assertEqual(actual_ar, expected_ar)
            self.assertEqual(app.rclone_title.cget("text"), app.ui_translate("Cloud Storage · rclone"))
            self.assertEqual(root.title(), "CatalogMesh")
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
