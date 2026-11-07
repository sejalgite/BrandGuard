# BrandGuard — Persistent File Storage, Backup & Recovery Runbook

This guide covers operational procedures for managing, backing up, and recovering BrandGuard's uploaded documents and brand visual assets.

---

## 1. Storage Architecture & Tenant Isolation

BrandGuard separates structured relational metadata (in PostgreSQL + pgvector) from physical binary files (on persistent storage).

### Hierarchy:
```
{STORAGE_ROOT}/
├── documents/
│   └── {organization_id}/
│       └── {version_uuid}_{filename}
└── assets/
    └── {organization_id}/
        └── {uuid_prefix}_{filename}
```

- **Configuration:** Controlled via `STORAGE_PATH` (default: `backend/storage/documents`).
- **Unified Root:** `STORAGE_ROOT` dynamically resolves to the parent storage root (`backend/storage`), provisioning `DOCUMENTS_STORAGE_PATH` and `ASSETS_STORAGE_PATH`.
- **Tenant Isolation:** Enforced both by API query scoping (`organization_id == current_user.organization_id`) and by filesystem containment verification (`os.path.abspath(dirname).startswith(expected_org_dir)` with trailing separator checks).
- **Path Traversal Guards:** All uploaded filenames are sanitized via `re.sub(r'[^a-zA-Z0-9_.-]', '_', basename)`. Both document and asset download endpoints strictly verify that requested files reside within the tenant's dedicated subdirectory.

---

## 2. File Backup Procedure (`storage_backup.py`)

The file backup utility creates a compressed `.tar.gz` archive capturing both `documents/` and `assets/` subtrees alongside an embedded `manifest.json`.

### Dry-Run / Preview:
```bash
python backend/scripts/storage_backup.py --dry-run
```

### Full Backup:
```bash
python backend/scripts/storage_backup.py
# Default output: backend/storage_backups/brandguard_storage_YYYYMMDD_HHMMSS.tar.gz
```

### Custom Destination or Output Directory:
```bash
python backend/scripts/storage_backup.py -o /var/backups/brandguard/storage_snapshot.tar.gz
python backend/scripts/storage_backup.py --output-dir /mnt/backups/brandguard
```

### Incremental Backup (Files modified after cutoff):
```bash
python backend/scripts/storage_backup.py --since 2026-11-01T00:00:00Z -o /var/backups/storage_diff.tar.gz
```

### Incremental Backup Limitations & Correctness:
> [!IMPORTANT]
> **Incremental archives are NOT stand-alone full backups.**
> - An incremental backup created with `--since` contains **only** files whose filesystem modification timestamp (`mtime`) is strictly newer than the cutoff timestamp.
> - **Restore Dependency:** Restoring an incremental backup alone will **not** restore the full storage state. You must restore the most recent full backup first, followed by each successive incremental archive in chronological order with `--overwrite`.
> - **Deleted & Renamed Files:** Incremental backups do not track file deletions or renames. If a file was deleted after the cutoff, the incremental archive does not delete that file on restore. A full baseline backup remains the authoritative ground truth.

### Safety Guarantees:
- **Refuses Overwriting:** Won't overwrite existing archives unless `--force` is provided.
- **Embedded Manifest:** Every archive embeds `manifest.json` with SHA-256 checksums, byte sizes, and timestamps for every file.
- **Symlink Protection:** Refuses to follow or bundle symlinks targeting files outside the storage parent directory.
- **Automatic Exclusion:** Omits transient probes (`.readiness_probe_*`), system metadata (`.DS_Store`, `Thumbs.db`), and bytecode caches (`__pycache__`).
- **Location Guard:** Rejects destinations located inside the live storage tree itself.

---

## 3. File Restoration Procedure (`storage_restore.py`)

The restoration utility extracts files from a `.tar.gz` backup archive with end-to-end checksum verification.

### Preview / Dry-Run:
```bash
python backend/scripts/storage_restore.py \
  --file backend/storage_backups/brandguard_storage_YYYYMMDD_HHMMSS.tar.gz \
  --destination /tmp/restore_preview \
  --dry-run
```

### Interactive Restore:
```bash
python backend/scripts/storage_restore.py \
  --file backend/storage_backups/brandguard_storage_YYYYMMDD_HHMMSS.tar.gz \
  --destination backend/storage
```
*(Prompts operator to type `RESTORE` before writing)*

### Scripted / Non-Interactive Restore:
```bash
python backend/scripts/storage_restore.py \
  --file backend/storage_backups/brandguard_storage_YYYYMMDD_HHMMSS.tar.gz \
  --destination backend/storage \
  --confirm
```

### Overwrite Policy & Existing File Safety:
- **Existing files remain untouched by default:** Any file that already exists at the destination target is skipped and logged unless `--overwrite` is explicitly specified.
- **Symlink Overwrite Guard:** Even when `--overwrite` is specified, if the existing target on disk is a symlink pointing outside the destination directory, restore immediately raises a `ValueError` security violation and halts.

### Partial Extraction & Failure Reporting:
- If extraction fails midway (e.g. disk full, permission denied), `storage_restore.py` immediately logs an error, records the exact count of files extracted prior to failure, and terminates with an exception. It **never** returns a successful return code or misleading summary on partial failures.
- Post-restore, every extracted file is checked against `manifest.json` for byte size and SHA-256 match. Checksum mismatches trigger a `RuntimeError`.

---

## 4. Coordinated Database & Storage Recovery

> [!WARNING]
> **Database backups and file storage backups are NOT an atomic single snapshot.**
> PostgreSQL `pg_dump` takes a snapshot of the database at its start time. Storage `tar.gz` takes a snapshot of the filesystem. If files are uploaded between the two operations, state drift can occur:
> - If database dump finishes, an upload arrives, and then storage backup runs: storage has files not present in the database.
> - If storage backup runs, an upload arrives, and then database dump runs: database references files not present in the storage archive.

### Recommended Production Strategy (Maintenance / Paused Window):
For 100% strict point-in-time consistency:
1. **Pause Ingestion / Maintenance Window:** Place application in read-only or pause new document/asset uploads (e.g. stop backend workers: `docker compose stop backend`).
2. **Execute Database Snapshot:**
   ```bash
   python backend/scripts/backup_db.py -o /backups/db_snapshot.dump
   ```
3. **Execute Storage Backup:**
   ```bash
   python backend/scripts/storage_backup.py -o /backups/storage_snapshot.tar.gz
   ```
4. **Resume Normal Traffic:** Restart backend workers.

### Recovery Sequence:
1. **Stop Application Backend:** Prevent incoming traffic from modifying state during restore.
2. **Restore Database First:**
   ```bash
   python backend/scripts/restore_db.py --file /backups/db_snapshot.dump --confirm --confirm-database brandguard --clean
   ```
3. **Restore Full Storage Baseline:**
   ```bash
   python backend/scripts/storage_restore.py --file /backups/storage_snapshot.tar.gz --destination backend/storage --confirm --overwrite
   ```
4. **Restore Any Subsequent Incremental Backups (Chronological Order):**
   ```bash
   python backend/scripts/storage_restore.py --file /backups/storage_incremental_1.tar.gz --destination backend/storage --confirm --overwrite
   ```
5. **Start Application Backend & Run Readiness Probe:**
   ```bash
   curl -s http://localhost:8000/api/v1/health/ready
   # Expected response: {"status":"ready","database":"connected","storage":"writable"}
   ```

---

## 5. Detecting Orphaned Records and Files

- **Orphan Files:** Files present on disk that have no corresponding row in `document_versions.file_path` or `brand_assets.file_path`.
- **Missing Files:** Database rows whose referenced `file_path` does not exist on disk.
- **Operational Audit Query:**
  ```sql
  -- Identify all active file paths expected on disk
  SELECT 'document' AS kind, file_path FROM document_versions WHERE file_path IS NOT NULL
  UNION ALL
  SELECT 'asset' AS kind, file_path FROM brand_assets WHERE file_path IS NOT NULL;
  ```
- **Policy:** **Never automatically delete orphan files.** Orphan files may represent uncommitted uploads or forensic evidence. Operators should audit file modification times against `audit_logs` before taking manual pruning actions.

---

## 6. Production Volume Mounts & Deployment Considerations

In Docker and containerized environments:
- Mount a persistent host directory or volume onto the path configured by `STORAGE_PATH` (e.g. `/app/storage`).
- **Never** store uploaded documents or brand assets in ephemeral container writable layers.
