# CatalogMesh Storage Center — rclone

The v3.3 source build adds an optional **Storage** workspace backed by a locally installed `rclone` executable.

## Design

Catalog processing remains **local-first**:

1. photos are processed locally;
2. SQLite resume/checkpoint files and temporary work stay local;
3. a successful output folder can then be copied to a configured rclone remote.

This avoids putting crash-safe resume databases or temporary processing files directly on remote/cloud filesystems.

## Supported destinations

CatalogMesh does not implement storage-provider OAuth itself. It discovers remotes already configured in rclone with `rclone listremotes`, so any backend supported by the user's installed rclone can be selected, including common services such as Google Drive, OneDrive, Dropbox, S3-compatible storage, Backblaze B2, pCloud, MEGA, SFTP and WebDAV.

## Safety model

- CatalogMesh never reads or writes the rclone configuration file.
- Credentials remain owned by rclone.
- rclone is invoked with an argv list and `shell=False`.
- The rclone remote-control HTTP server is not started or exposed.
- Automatic post-run upload always uses **`rclone copy`**.
- Automatic upload never uses `sync`, so it does not delete destination-only files.
- Automatic CLI upload only starts after a real `RUN_COMPLETED` event and a fully completed `processing_status.csv`; help, dry-run, empty-input, early-exit and incomplete runs cannot arm it.
- The desktop owns its own cancellable auto-copy lifecycle, so its sorter subprocess does not trigger a duplicate terminal auto-copy.
- Manual **Sync mirror** is available only as an explicit operation and requires the exact destination-specific confirmation phrase `SYNC <full-target>`.
- A dry-run preview is available before a manual copy or sync.
- `.product_sorter.lock` and temporary `*.tmp` files are excluded from transfer.
- A credential-free local audit is appended to `.catalogmesh/storage-sync-audit.jsonl` inside the local output folder.
- An ambiguous/failed automatic transfer is not blindly retried in the same process.

## Storage workspace controls

The desktop Storage workspace provides:

- rclone installation/version detection;
- configured remote discovery;
- remote base-folder selection;
- read-only remote connectivity test;
- manual Copy;
- manually confirmed Sync mirror;
- dry-run preview;
- automatic Copy after a successful sorting run;
- bandwidth limiting;
- transfer/checker parallelism controls;
- live rclone output;
- transfer cancellation.

The final destination is built as:

```text
<remote>:<configured base folder>/<local output folder name>
```

For example:

```text
gdrive:CatalogMesh/Sorted_Products
```

Using the local output folder name as the final cloud directory reduces accidental collisions between separate catalog workspaces.

## First-class Storage CLI

The dedicated Storage Center and terminal use the same bounded `rclone_storage.py` backend. The primary v3.3 terminal entry point is `catalogmesh-storage`; `product-sorter-storage` remains the compatibility alias.

```bash
catalogmesh-storage version
catalogmesh-storage remotes
catalogmesh-storage test gdrive:CatalogMesh
catalogmesh-storage dry-run ./Sorted_Products gdrive:CatalogMesh --bwlimit 10M --transfers 4 --checkers 8
catalogmesh-storage copy ./Sorted_Products gdrive:CatalogMesh
catalogmesh-storage sync ./Sorted_Products gdrive:CatalogMesh --confirm "SYNC gdrive:CatalogMesh"
```

Human-readable output is the default and `--json` is optional where supported. CLI transfer output streams through the same backend used by the GUI and normal terminal interruption cancels the local rclone child process.

The older Automation CLI storage aliases are intentionally preserved for GUI/CLI parity with Automation Center:

```bash
catalogmesh-automation storage-version
catalogmesh-automation storage-remotes
catalogmesh-automation storage-test gdrive: --remote-path CatalogMesh
catalogmesh-automation storage-dry-run ./Sorted_Products gdrive: --remote-path CatalogMesh
catalogmesh-automation storage-copy ./Sorted_Products gdrive: --remote-path CatalogMesh
catalogmesh-automation storage-sync ./Sorted_Products gdrive: --remote-path CatalogMesh --confirm-sync "SYNC gdrive:CatalogMesh"
```

Sync confirmation is target-specific. A confirmation for only the remote root, such as `SYNC gdrive:`, is not accepted when the actual target is `gdrive:CatalogMesh`.

## Automatic post-sort copy

The same non-secret settings drive automatic copy from both desktop and terminal workflows:

```text
PRODUCT_SORTER_RCLONE_REMOTE
PRODUCT_SORTER_RCLONE_PATH
PRODUCT_SORTER_RCLONE_MODE
PRODUCT_SORTER_RCLONE_AUTO_COPY
PRODUCT_SORTER_RCLONE_BWLIMIT
PRODUCT_SORTER_RCLONE_TRANSFERS
PRODUCT_SORTER_RCLONE_CHECKERS
```

Even if `PRODUCT_SORTER_RCLONE_MODE=sync`, automatic post-run transfer is forced to **copy**. `sync` remains manual-only and always requires the exact full-target confirmation.

These settings are available through the desktop Storage/Environment surfaces and through the bounded `catalogmesh-config` / `product-sorter-config` CLI. The config CLI does not expose a generic environment executor and does not print secret values.

Optional executable/config-path overrides:

```text
PRODUCT_SORTER_RCLONE_BIN
PRODUCT_SORTER_RCLONE_CONFIG
```

`PRODUCT_SORTER_RCLONE_CONFIG` points rclone at an alternate config file but CatalogMesh does not parse that file. Do not put rclone passwords, tokens or OAuth secrets in CatalogMesh settings or approval artifacts.

## Intentionally not exposed through MCP

Storage transfer is a local desktop/terminal action and is not registered as an MCP tool. The existing MCP boundary remains focused on safe scan/audit/proposal operations and does not become a generic file-transfer or remote-mutation executor.
