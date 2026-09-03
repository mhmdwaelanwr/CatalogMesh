from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .ingestion import scan_image_folder
from .missing_assets import find_missing_assets


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    mutates_external_state: bool
    requires_human_approval: bool
    handler: Callable[..., object]


class AgentToolRegistry:
    """Small orchestration surface that can be adapted to MCP/agents later.

    The first registry intentionally exposes only local/read-only operations.
    External catalog writes must be added as separately gated tools rather than
    silently wrapping publishing functions.
    """

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError(f"invalid or duplicate agent tool: {tool.name!r}")
        self._tools[tool.name] = tool

    def manifest(self) -> list[dict[str, object]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "mutates_external_state": tool.mutates_external_state,
                "requires_human_approval": tool.requires_human_approval,
            }
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def call(self, name: str, arguments: Mapping[str, object]) -> object:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown agent tool: {name}")
        if tool.mutates_external_state:
            raise PermissionError(
                f"agent tool {name!r} mutates external state and cannot run through the read-only registry"
            )
        return tool.handler(**dict(arguments))


def build_default_agent_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        AgentTool(
            name="scan_shoot",
            description="Build a deterministic, non-destructive snapshot of local product-shoot images.",
            mutates_external_state=False,
            requires_human_approval=False,
            handler=scan_image_folder,
        )
    )
    registry.register(
        AgentTool(
            name="find_missing_assets",
            description="Find catalog SKUs that have no configured image reference.",
            mutates_external_state=False,
            requires_human_approval=False,
            handler=find_missing_assets,
        )
    )
    return registry
