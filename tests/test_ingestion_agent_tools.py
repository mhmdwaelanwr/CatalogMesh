from dataclasses import replace

import pytest

from ai_product_photo_sorter.agent_tools import AgentTool, AgentToolRegistry, build_default_agent_registry
from ai_product_photo_sorter.ingestion import diff_snapshots, scan_image_folder


def test_scan_and_diff_snapshots(tmp_path):
    first = tmp_path / "a.jpg"
    first.write_bytes(b"a")
    previous = scan_image_folder(tmp_path)

    second = tmp_path / "b.png"
    second.write_bytes(b"b")
    current = scan_image_folder(tmp_path)
    diff = diff_snapshots(previous, current)

    assert [item.path for item in diff["added"]] == [str(second.resolve())]
    assert diff["removed"] == []


def test_default_agent_registry_is_read_only(tmp_path):
    registry = build_default_agent_registry()
    names = [tool["name"] for tool in registry.manifest()]
    assert names == ["find_missing_assets", "scan_shoot"]
    assert all(not tool["mutates_external_state"] for tool in registry.manifest())

    result = registry.call("scan_shoot", {"root": tmp_path})
    assert result == []


def test_registry_refuses_external_mutation_tool():
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

    with pytest.raises(PermissionError):
        registry.call("publish", {})
