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
- Manual **Sync mirror** is available only as an explicit operation and requires the user to type the exact destination-specific confirmation phrase.
- A dry-run preview is available before a manual copy or sync.
- `.product_sorter.lock` and temporary `*.tmp` files are excluded from transfer.
- A credential-free local audit is appended to `.catalogmesh/storage-sync-audit.jsonl` inside the local output folder.

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

## Configuration

The feature uses the normal app settings for non-secret preferences:

```text
PRODUCT_SORTER_RCLONE_REMOTE
PRODUCT_SORTER_RCLONE_PATH
PRODUCT_SORTER_RCLONE_MODE
PRODUCT_SORTER_RCLONE_AUTO_COPY
PRODUCT_SORTER_RCLONE_BWLIMIT
PRODUCT_SORTER_RCLONE_TRANSFERS
PRODUCT_SORTER_RCLONE_CHECKERS
```

Optional executable/config-path overrides:

```text
PRODUCT_SORTER_RCLONE_BIN
PRODUCT_SORTER_RCLONE_CONFIG
```

`PRODUCT_SORTER_RCLONE_CONFIG` points rclone at an alternate config file but CatalogMesh does not parse that file. Do not put rclone passwords, tokens or OAuth secrets in CatalogMesh settings or approval artifacts.

## Intentionally not exposed through MCP

Storage transfer is a local desktop action and is not registered as an MCP tool. The existing MCP boundary remains focused on safe scan/audit/proposal operations and does not become a generic file-transfer or remote-mutation executor.
