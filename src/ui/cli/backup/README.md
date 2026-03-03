# CLI Domain: Backup — Archive Creation, Management & Discovery

> **1 file · 197 lines · 5 commands · Group: `controlplane backup`**
>
> **Exception note:** This domain has a single file under 200 lines,
> so the 450-line README minimum does not strictly apply. All required
> sections are still covered below.
>
> Creates, lists, previews, and deletes tar.gz backup archives stored in
> per-folder `.backup/` directories. Supports whole-archive encryption,
> `.enc` file decryption into archives, GitHub Release cross-referencing,
> and folder discovery.
>
> Core service: `core/services/backup/ops.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane backup                           │
│                                                                      │
│  folders ──► create FOLDER PATH... ──► list FOLDER ──► preview PATH  │
│  (discover)   (archive)                 (browse)       (inspect)     │
│                                                                      │
│                                             delete PATH              │
│                                             (remove)                 │
└──────────┬──────────────────────────────────────────────────────────-┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    core/services/backup/ops.py                      │
│                                                                      │
│  create_backup(root, folder, paths, ...)                             │
│    ├── collect files from paths                                      │
│    ├── optionally decrypt .enc files (COVAULT content)               │
│    ├── create tar.gz in FOLDER/.backup/                              │
│    ├── optionally encrypt entire archive                             │
│    └── return manifest (filename, size, stats)                       │
│                                                                      │
│  list_backups(root, folder, check_release=False)                     │
│    ├── scan FOLDER/.backup/ for .tar.gz / .tar.gz.enc               │
│    ├── optionally cross-ref with GitHub Release assets               │
│    └── return list with size, encrypted flag, git_tracked flag       │
│                                                                      │
│  preview_backup(root, path)                                          │
│    └── read tar.gz file tree without extracting                      │
│                                                                      │
│  delete_backup(root, path)                                           │
│    └── remove archive file from disk                                 │
│                                                                      │
│  list_folders(root)                                                  │
│    └── discover folders with content worth backing up                │
└──────────────────────────────────────────────────────────────────────┘
```

### Storage Layout

```
project/
├── docs/
│   ├── .backup/
│   │   ├── docs_20260301_143000_cli_export.tar.gz
│   │   └── docs_manual.tar.gz.enc            ← encrypted
│   ├── guides/
│   └── api/
└── content/
    ├── .backup/
    │   └── content_20260228_100000_cli_export.tar.gz
    └── media/
```

Each folder has its own `.backup/` subdirectory. Archives are named
with a timestamp and label by default, or with a custom name.

---

## Commands

### `controlplane backup create FOLDER PATH...`

Create a backup archive from selected paths within a folder.

```bash
# Archive docs/guides and docs/api into docs/.backup/
controlplane backup create docs docs/guides docs/api

# Archive entire content/ folder with encryption
controlplane backup create content content/ --encrypt

# Decrypt .enc files before archiving
controlplane backup create content content/ --decrypt-enc

# Custom archive name
controlplane backup create docs docs/ --name manual-snapshot

# JSON output
controlplane backup create docs docs/ --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `FOLDER` | argument | (required) | Target folder (archive stored in `FOLDER/.backup/`) |
| `PATH...` | argument(s) | (required) | Relative paths to include |
| `--label/-l` | string | `cli_export` | Label in the archive filename |
| `--decrypt-enc` | flag | off | Decrypt `.enc` files into the archive |
| `--encrypt` | flag | off | Encrypt the entire final archive |
| `--name` | string | (auto) | Custom archive name (overrides auto-generated) |
| `--json` | flag | off | JSON output |

**Output example:**

```
✅ Backup created: docs_20260301_143000_cli_export.tar.gz
   Path: /home/user/project/docs/.backup/docs_20260301_143000_cli_export.tar.gz
   Size: 245,768 bytes
   Files: 42
```

---

### `controlplane backup list FOLDER`

List all backup archives in a folder's `.backup/` directory.

```bash
controlplane backup list docs
controlplane backup list docs --check-release
controlplane backup list docs --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `FOLDER` | argument | (required) | Folder whose `.backup/` to scan |
| `--check-release` | flag | off | Cross-reference with GitHub Release assets |
| `--json` | flag | off | JSON output |

**Output example:**

```
📦 Backups in docs (3):
   docs_20260301_143000_cli_export.tar.gz  (240 KB)
   docs_20260228_120000_daily.tar.gz 📌  (180 KB)
   docs_encrypted.tar.gz.enc 🔒  (350 KB)
```

**Icons:** `🔒` = encrypted, `📌` = git-tracked

---

### `controlplane backup preview PATH`

Preview the file tree inside a backup archive without extracting it.

```bash
controlplane backup preview docs/.backup/docs_20260301_143000_cli_export.tar.gz
controlplane backup preview docs/.backup/docs_20260301_143000_cli_export.tar.gz --json
```

**Output example:**

```
📋 Archive: docs/.backup/docs_20260301_143000_cli_export.tar.gz
   Files: 42

   guides/getting-started.md                         [file  ]     5.2 KB
   guides/advanced.md                                [file  ]    12.8 KB
   api/reference.md                                  [file  ]     8.1 KB
   api/examples/                                     [dir   ]     0.0 KB
```

---

### `controlplane backup delete PATH`

Delete a backup archive from disk.

```bash
controlplane backup delete docs/.backup/docs_20260301_143000_cli_export.tar.gz
```

**Output:** `✅ Deleted: docs_20260301_143000_cli_export.tar.gz`

No `--json` flag on this command — it either succeeds or fails.

---

### `controlplane backup folders`

List scannable project folders (candidates for backup).

```bash
controlplane backup folders
controlplane backup folders --json
```

**Output example:**

```
📁 Folders (4):
   • docs
   • content
   • config
   • data
```

---

## File Map

```
cli/backup/
├── __init__.py    197 lines — group definition + all 5 commands +
│                              _resolve_project_root helper
└── README.md               — this file
```

**Total: 197 lines of Python in 1 file.**

All commands are in `__init__.py` because the domain is small enough
(5 thin commands) that splitting into sub-modules would add friction
without improving readability.

---

## Per-File Documentation

### `__init__.py` — Group + all commands (197 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from Click context; falls back to `find_project_file()` |
| `backup()` | Click group | Defines the `backup` group |
| `create(ctx, folder, paths, ...)` | Click command | Creates a tar.gz archive from selected paths with optional encryption |
| `list_backups_cmd(ctx, folder, ...)` | Click command (`list`) | Lists archives in `FOLDER/.backup/` with optional GitHub Release cross-ref |
| `preview(ctx, path, ...)` | Click command | Reads tar.gz file tree without extraction |
| `delete(ctx, path)` | Click command | Removes an archive file from disk |
| `folders(ctx, ...)` | Click command | Discovers project folders worth backing up |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `create_backup` | `backup.ops` | Create archive with manifest |
| `list_backups` | `backup.ops` | Scan `.backup/` directory |
| `preview_backup` | `backup.ops` | Read archive contents |
| `delete_backup` | `backup.ops` | Remove archive file |
| `list_folders` | `backup.ops` | Discover scannable folders |

---

## Dependency Graph

```
__init__.py
├── click                      ← click.group, click.command
├── core.config.loader         ← find_project_file (lazy, _resolve_project_root)
└── core.services.backup.ops   ← create_backup, list_backups, preview_backup,
                                  delete_backup, list_folders (all lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:451` | `from src.ui.cli.backup import backup` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/backup/ops.py` | `backup.ops` (same create/list/preview/delete) |
| Web routes | `routes/backup/archive.py` | `backup.ops` (archive operations) |
| Web routes | `routes/backup/restore.py` | `backup.ops` (restore operations) |
| Web routes | `routes/backup/tree.py` | `backup.ops` (folder tree view) |

---

## Design Decisions

### Why all commands are in __init__.py

Five thin commands (each 15–40 lines of logic) don't justify four
separate files. The single-file layout keeps the domain easy to scan
and avoids import ceremony between files.

### Why create takes FOLDER + PATH... (two-level addressing)

The `FOLDER` determines where the `.backup/` directory lives.
The `PATH...` arguments determine what goes into the archive.
This allows archiving a subset of a folder's contents while still
organizing archives by folder.

### Why --check-release is opt-in

Cross-referencing with GitHub Release requires `gh` CLI auth and
a network call. Making it a flag avoids the latency and auth
requirement for the common `list` use case.

### Why delete has no --json flag

Delete is destructive. If it succeeds, you get one line of
confirmation. If it fails, you get one line of error. There's
no structured data worth wrapping in JSON.
