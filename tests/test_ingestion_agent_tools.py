import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.agent_tools import AgentTool, AgentToolRegistry, build_default_agent_registry
from ai_product_photo_sorter.ingestion import diff_snapshots, scan_image_folder


class IngestionAgentToolsTests(unittest.TestCase):
    def test_scan_and_diff_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            first.write_bytes(b"a")
            previous = scan_image_folder(root)

            second = root / "b.png"
            second.write_bytes(b"b")
            current = scan_image_folder(root)
            diff = diff_snapshots(previous, current)

            self.assertEqual([item.path for item in diff["added"]], [str(second.resolve())])
            self.assertEqual(diff["removed"], [])

    def test_default_agent_registry_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_agent_registry()
            names = [tool["name"] for tool in registry.manifest()]
            self.assertEqual(names, ["find_missing_assets", "scan_shoot"])
            self.assertTrue(all(not tool["mutates_external_state"] for tool in registry.manifest()))

            result = registry.call("scan_shoot", {"root": Path(directory)})
            self.assertEqual(result, [])

    def test_registry_refuses_external_mutation_tool(self):
        registry = AgentToolRegistry()
        registry.register(
            AgentTool(
                name="publish",
                description="test",
                mutates_external_state=True,
                requires_human_approval=True,
                handler=lambda: "should not run",
            )
        )

        with self.assertRaises(PermissionError):
            registry.call("publish", {})


if __name__ == "__main__":
    unittest.main()
