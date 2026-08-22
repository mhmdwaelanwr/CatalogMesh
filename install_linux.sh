#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/product-sorter-pro"
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$install_dir" "$apps_dir"
cp -a . "$install_dir/"
python3 -m venv "$install_dir/.venv"
"$install_dir/.venv/bin/pip" install -r "$install_dir/requirements.txt"
sed "s|@INSTALL_DIR@|$install_dir|g" product-sorter.desktop.in > "$apps_dir/product-sorter-pro.desktop"
chmod +x "$apps_dir/product-sorter-pro.desktop"
echo "Installed to $install_dir"
