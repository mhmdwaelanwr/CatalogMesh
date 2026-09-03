from ai_product_photo_sorter.missing_assets import (
    find_missing_assets,
    find_missing_local_images,
    image_files_by_stem,
)


def test_find_missing_assets_requires_sku_and_empty_asset_columns():
    rows = [
        {"sku": "A-1", "image_url": "https://example.test/a.jpg"},
        {"sku": "B-2", "image_url": "  "},
        {"sku": "", "image_url": ""},
    ]

    result = find_missing_assets(rows, asset_columns=("image_url",))

    assert [item.sku for item in result] == ["B-2"]
    assert result[0].row_number == 3
    assert result[0].reason == "no_asset_reference"


def test_image_stems_and_local_missing_are_case_insensitive(tmp_path):
    a = tmp_path / "SKU-1.JPG"
    a.write_bytes(b"x")
    ignored = tmp_path / "notes.txt"
    ignored.write_text("x", encoding="utf-8")

    assert image_files_by_stem([a, ignored]) == {"sku-1"}

    rows = [{"sku": "sku-1"}, {"sku": "SKU-2"}]
    result = find_missing_local_images(rows, [a])
    assert [item.sku for item in result] == ["SKU-2"]
