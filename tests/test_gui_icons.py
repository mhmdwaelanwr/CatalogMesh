from ai_product_photo_sorter.gui_icons import (
    ACTION_ICON_KEYS,
    ICON_SEGMENTS,
    PROVIDERS,
    WORKSPACE_ICON_KEYS,
    WORKSPACE_ORDER_KEYS,
    _line_points,
    _workspace_icon_key,
)


def test_all_twelve_workspaces_have_icon_keys():
    expected = (
        "operation", "models", "results", "review", "sku", "exports",
        "storage", "automation", "reports", "benchmark", "environment", "about",
    )
    assert WORKSPACE_ORDER_KEYS == expected
    assert all(key in ICON_SEGMENTS for key in expected)


def test_legacy_workspace_aliases_resolve_without_changing_labels():
    assert _workspace_icon_key("Setup") == "operation"
    assert _workspace_icon_key("API") == "models"
    assert _workspace_icon_key("Results") == "results"
    assert _workspace_icon_key("SKU Match") == "sku"


def test_core_action_icons_are_defined():
    assert ACTION_ICON_KEYS == {
        "start": "start",
        "stop": "stop",
        "resume": "resume",
        "save": "save",
        "open": "open",
    }
    assert all(key in ICON_SEGMENTS for key in ACTION_ICON_KEYS.values())


def test_provider_marks_cover_remote_model_tabs():
    assert PROVIDERS == ("GEMINI", "OPENAI", "ANTHROPIC")


def test_line_rasterizer_includes_both_endpoints():
    points = tuple(_line_points(2, 3, 6, 3))
    assert points[0] == (2, 3)
    assert points[-1] == (6, 3)
    assert len(points) == 5
