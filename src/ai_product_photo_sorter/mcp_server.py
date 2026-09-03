from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog_exports import generate_exports
from .ingestion import scan_image_folder
from .missing_assets import find_missing_assets, find_missing_local_images
from .sku_matching import generate_candidates, load_catalog_rows


def _catalog_fields(path: str) -> list[dict[str, Any]]:
    return [dict(row.get("fields", {})) for row in load_catalog_rows(Path(path))]


def build_server():
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("MCP support is optional. Install with: pip install 'ai-product-photo-sorter[mcp]'") from exc

    server = MCPServer("Product Sorter")

    @server.tool()
    def scan_shoot(root: str, recursive: bool = True) -> list[dict[str, object]]:
        """Scan local product-shoot images without modifying source files."""
        return [item.to_dict() for item in scan_image_folder(root, recursive=recursive)]

    @server.tool()
    def show_missing_skus(catalog: str, sku_column: str = "sku", asset_columns: list[str] | None = None) -> list[dict[str, object]]:
        """Find catalog SKUs that have no configured image reference."""
        kwargs: dict[str, Any] = {"sku_column": sku_column}
        if asset_columns:
            kwargs["asset_columns"] = tuple(asset_columns)
        return [item.to_dict() for item in find_missing_assets(_catalog_fields(catalog), **kwargs)]

    @server.tool()
    def show_missing_local_skus(catalog: str, shoot: str, sku_column: str = "sku") -> list[dict[str, object]]:
        """Find SKUs without a conservative exact-stem image candidate in a shoot folder."""
        images = scan_image_folder(shoot)
        return [item.to_dict() for item in find_missing_local_images(_catalog_fields(catalog), [asset.path for asset in images], sku_column=sku_column)]

    @server.tool()
    def propose_matches(approved_groups: str, catalog: str, evidence_json: str | None = None, output_dir: str | None = None, top_k: int = 5) -> dict[str, object]:
        """Generate ranked SKU candidates. Never auto-confirms a candidate."""
        manifest, path = generate_candidates(Path(approved_groups), Path(catalog), evidence_json=Path(evidence_json) if evidence_json else None, output_dir=Path(output_dir) if output_dir else None, top_k=top_k)
        return {"manifest": str(path), "summary": manifest.get("summary", {}), "automatic_confirmation": False, "human_confirmation_required": True}

    @server.tool()
    def prepare_shopify_draft(match_manifest: str, output_dir: str | None = None) -> dict[str, object]:
        """Prepare offline Shopify draft files from fully human-confirmed matches only."""
        summary, path = generate_exports(Path(match_manifest), output_dir=Path(output_dir) if output_dir else None, profile="shopify")
        return {"manifest": str(path), "summary": summary, "publish_performed": False, "network_calls_performed": 0, "human_publish_approval_required": True}

    return server


def main() -> int:
    server = build_server()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
