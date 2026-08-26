#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n1)"
if [[ -z "$version" ]]; then
  echo "Unable to determine version from pyproject.toml" >&2
  exit 1
fi

deb_work="$(mktemp -d)"
trap 'rm -rf "$deb_work"' EXIT
root="$deb_work/product-sorter-pro_${version}_all"
mkdir -p "$root/DEBIAN" "$root/opt/product-sorter-pro" "$root/usr/bin" "$root/usr/share/applications" "$root/usr/share/icons/hicolor/256x256/apps"
cp -a . "$root/opt/product-sorter-pro/"
find "$root/opt/product-sorter-pro" -type d \( -name .git -o -name __pycache__ -o -name .build-venv -o -name build -o -name dist \) -prune -exec rm -rf {} +
find "$root/opt/product-sorter-pro" -type f \( -name .env -o -name '*.pyc' \) -delete
cat > "$root/DEBIAN/control" <<EOF
Package: product-sorter-pro
Version: $version
Architecture: all
Depends: python3 (>= 3.10), python3-venv, python3-tk
Maintainer: Mohamed Anwar
Homepage: https://github.com/mhmdwaelanwr/ai-product-photo-sorter
Description: Multilingual AI product photo sorter
EOF
cat > "$root/usr/bin/product-sorter-pro" <<'EOF'
#!/bin/sh
exec /opt/product-sorter-pro/start.sh --gui
EOF
chmod +x "$root/usr/bin/product-sorter-pro"
sed "s|@INSTALL_DIR@|/opt/product-sorter-pro|g" packaging/linux/product-sorter.desktop.in > "$root/usr/share/applications/product-sorter-pro.desktop"
cp assets/branding/product-sorter-256.png "$root/usr/share/icons/hicolor/256x256/apps/product-sorter-pro.png"
mkdir -p dist
dpkg-deb --build "$root" "dist/product-sorter-pro_${version}_all.deb"
