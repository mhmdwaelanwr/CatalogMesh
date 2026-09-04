# Frozen configuration persistence

CatalogMesh keeps packaged resources and user configuration on separate filesystem roots.

- PyInstaller resources continue to resolve from the runtime bundle (`sys._MEIPASS`) when present.
- An existing `.env` beside the executable opts into portable configuration mode.
- Otherwise frozen builds use a stable per-user configuration location:
  - Windows: `%LOCALAPPDATA%\CatalogMesh\.env` (falling back to `%APPDATA%` and then the user's local AppData path)
  - macOS: `~/Library/Application Support/CatalogMesh/.env`
  - Linux: `$XDG_CONFIG_HOME/CatalogMesh/.env`, or `~/.config/CatalogMesh/.env`
- Source checkouts and installed-wheel compatibility behavior remain unchanged.

The configuration writer creates a missing per-user parent directory before saving. Credentials keep the existing `.env` file permissions and OS-keyring handling.

This change does not alter release, tag, version, publishing, connector, SKU-review, or rclone safety boundaries.
