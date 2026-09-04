"""Capability contracts used to keep CatalogMesh GUI and CLI in parity.

The registry deliberately describes real backend/workflow capabilities rather than
pure presentation details.  CI uses it to fail when a capability loses either its
CLI or desktop surface.  Visual-only helpers such as opening a file picker or the
About page are explicitly marked and are not required to grow artificial CLI
commands.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    cli_command: str
    automation_command: str
    gui_surface: str
    backend_callable: str
    visual_only: bool = False


@dataclass(frozen=True)
class WorkflowCapability:
    id: str
    workspace: str
    cli_surface: str
    gui_method: str
    core_cli_flags: tuple[str, ...] = ()
    automation_commands: tuple[str, ...] = ()
    visual_only: bool = False


STORAGE_CAPABILITIES = (
    Capability("storage.version", "version", "storage-version", "Storage Center", "rclone_version"),
    Capability("storage.remotes", "remotes", "storage-remotes", "Storage Center", "list_remotes"),
    Capability("storage.test", "test", "storage-test", "Storage Center", "test_remote"),
    Capability("storage.dry_run", "dry-run", "storage-dry-run", "Storage Center", "stream_transfer"),
    Capability("storage.copy", "copy", "storage-copy", "Storage Center", "stream_transfer"),
    Capability("storage.sync", "sync", "storage-sync", "Storage Center", "stream_transfer"),
)


# Primary desktop workflow.  The order is intentional and mirrors the sidebar.
WORKFLOW_CAPABILITIES = (
    WorkflowCapability(
        "operation.sort",
        "Operation setup",
        "catalogmesh",
        "start",
        core_cli_flags=("--source", "--output"),
    ),
    WorkflowCapability(
        "models.configure",
        "Models & API keys",
        "catalogmesh-setup",
        "refresh_models",
    ),
    WorkflowCapability(
        "results.activity",
        "Results & activity",
        "catalogmesh",
        "refresh_tables",
        core_cli_flags=("--source", "--output"),
    ),
    WorkflowCapability(
        "review.manage",
        "Review",
        "catalogmesh / catalogmesh-automation",
        "reload_review",
        core_cli_flags=(
            "--review-init",
            "--review-summary",
            "--review-apply",
            "--review-export-approved",
        ),
        automation_commands=(
            "review-init",
            "review-summary",
            "review-apply",
            "review-export-approved",
        ),
    ),
    WorkflowCapability(
        "sku.match",
        "SKU Match",
        "catalogmesh / catalogmesh-automation",
        "generate_sku_candidates",
        core_cli_flags=("--sku-match", "--sku-confirm", "--sku-clear"),
        automation_commands=("sku-generate", "sku-confirm", "sku-clear"),
    ),
    WorkflowCapability(
        "exports.generate",
        "Exports",
        "catalogmesh / catalogmesh-automation",
        "generate_catalog_exports",
        core_cli_flags=("--export-catalog",),
        automation_commands=("export-catalog",),
    ),
    WorkflowCapability(
        "storage.manage",
        "Storage",
        "catalogmesh-storage / catalogmesh-automation",
        "start_rclone_transfer",
        automation_commands=tuple(item.automation_command for item in STORAGE_CAPABILITIES),
    ),
    WorkflowCapability(
        "automation.run",
        "Automation",
        "catalogmesh-automation",
        "run_automation_command",
    ),
    WorkflowCapability(
        "reports.generate_and_view",
        "Reports",
        "catalogmesh --md-report",
        "refresh_reports",
        core_cli_flags=("--md-report",),
    ),
    WorkflowCapability(
        "benchmark.run",
        "Benchmark",
        "catalogmesh --benchmark",
        "start_benchmark",
        core_cli_flags=("--benchmark",),
    ),
    WorkflowCapability(
        "environment.configure",
        "Environment",
        "catalogmesh-setup",
        "save_environment",
    ),
    WorkflowCapability(
        "about.display",
        "About",
        "n/a",
        "copy_contact",
        visual_only=True,
    ),
)


# Important real capabilities nested inside the Benchmark/Environment workflow.
# They still require both a callable desktop path and a CLI path even though they
# do not own a top-level sidebar page.
INTERNAL_CAPABILITIES = (
    WorkflowCapability(
        "local_ai.ollama_models",
        "Models & API keys",
        "catalogmesh / catalogmesh-setup",
        "refresh_ollama_models",
    ),
    WorkflowCapability(
        "local_evidence.generate",
        "Benchmark",
        "catalogmesh --local-evidence",
        "run_local_evidence",
        core_cli_flags=("--local-evidence",),
    ),
    WorkflowCapability(
        "calibration.prepare_ground_truth",
        "Benchmark",
        "catalogmesh --prepare-ground-truth",
        "prepare_ground_truth_labels",
        core_cli_flags=("--prepare-ground-truth",),
    ),
    WorkflowCapability(
        "calibration.run",
        "Benchmark",
        "catalogmesh --calibrate-hybrid",
        "calibrate_hybrid_thresholds",
        core_cli_flags=("--calibrate-hybrid",),
    ),
    WorkflowCapability(
        "hybrid_routing.simulate",
        "Benchmark",
        "catalogmesh --simulate-hybrid-routing",
        "simulate_hybrid_routing",
        core_cli_flags=("--simulate-hybrid-routing",),
    ),
)


ALL_REAL_CAPABILITIES = WORKFLOW_CAPABILITIES + INTERNAL_CAPABILITIES


def storage_cli_commands() -> frozenset[str]:
    return frozenset(item.cli_command for item in STORAGE_CAPABILITIES)


def storage_automation_commands() -> frozenset[str]:
    return frozenset(item.automation_command for item in STORAGE_CAPABILITIES)


def storage_backend_callables() -> frozenset[str]:
    return frozenset(item.backend_callable for item in STORAGE_CAPABILITIES)


def required_automation_commands() -> frozenset[str]:
    return frozenset(
        command
        for capability in ALL_REAL_CAPABILITIES
        for command in capability.automation_commands
    )


def required_core_cli_flags() -> frozenset[str]:
    return frozenset(
        flag
        for capability in ALL_REAL_CAPABILITIES
        for flag in capability.core_cli_flags
    )
