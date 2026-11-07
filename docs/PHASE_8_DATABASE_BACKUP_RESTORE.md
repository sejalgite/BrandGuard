# BrandGuard — Database Backup, Restore & Reliability Procedures

This guide provides operational runbooks for backing up, verifying, and restoring the BrandGuard PostgreSQL database across development, staging, and containerized deployments.

---

## 1. Architecture & Detected Environment

- **Database Engine:** PostgreSQL 18.4 (x86_64)
- **Active Extensions:**
  - `vector` (v0.8.6) — pgvector embedding storage
  - `uuid-ossp` (v1.1) — UUID generation functions
  - `plpgsql` (v1.0) — Procedural language
- **Schema Management:** Alembic (current revision `0007_evaluation_intelligence`)
- **Total Tables:** 26 application tables (including `alembic_version`)
- **Backup Archive Format:** PostgreSQL Custom Format (`-Fc`, compressed via zlib)
- **Client Utilities Required:** `pg_dump`, `pg_restore`, and `psql`

---

## 2. Secure Credential Handling

Passwords are **never** passed via CLI flags or process arguments. Credentials are supplied via:
1. `DATABASE_URL` environment variable:
   ```bash
   export DATABASE_URL="postgresql://brandguard_user:your_secure_password@localhost:5432/brandguard"
   ```
2. Temporary, restricted-permission `PGPASSFILE` managed automatically by `backup_db.py` and `restore_db.py` in memory/temp storage and cleaned up immediately after execution.

### Manual PGPASSFILE Configuration (Optional)
**Linux/macOS:**
```bash
echo "localhost:5432:brandguard:brandguard_user:your_secure_password" > ~/.pgpass
chmod 0600 ~/.pgpass
export PGPASSFILE=~/.pgpass
```

**Windows (PowerShell):**
```powershell
$pgpass = "$env:APPDATA\postgresql\pgpass.conf"
New-Item -ItemType Directory -Force (Split-Path $pgpass)
"localhost:5432:brandguard:brandguard_user:your_secure_password" | Out-File -FilePath $pgpass -Encoding ascii
```

---

## 3. Database Backup Procedure

The script `backend/scripts/backup_db.py` creates a compressed, timestamped, pre-validated backup file.

### Basic Backup Command
```bash
python backend/scripts/backup_db.py
```
*Outputs to: `backend/backups/brandguard_backup_YYYYMMDD_HHMMSS.dump`*

### Custom Destination or Output Directory
```bash
# Specify explicit output filename
python backend/scripts/backup_db.py -o /var/backups/brandguard_daily.dump

# Specify destination directory
python backend/scripts/backup_db.py --output-dir /var/backups/brandguard
```

### Custom Database URL
```bash
python backend/scripts/backup_db.py --db-url "postgresql://brandguard_user:secret@db.internal:5432/brandguard"
```

### Flags Reference
| Flag | Description |
| :--- | :--- |
| `--db-url` | Target database connection URL (defaults to `DATABASE_URL` env var). |
| `-o, --output` | Explicit backup file destination. |
| `--output-dir` | Directory where timestamped backup file will be created. |
| `--force` | Overwrite target backup file if it already exists (off by default). |

---

## 4. Backup Verification Procedure

Every backup produced by `backup_db.py` is automatically verified upon creation. To manually inspect or verify an existing backup archive:

### Inspect Archive Table of Contents (TOC)
```bash
pg_restore -l backend/backups/brandguard_backup_20261107_170942.dump
```
Look for:
- `EXTENSION - vector`
- `EXTENSION - uuid-ossp`
- `TABLE public alembic_version`
- `TABLE public users`
- `TABLE public organizations`

### End-to-End Test Restore Against a Temporary Database
Run a verification restore against an ephemeral test database without touching the active database:
```bash
python backend/scripts/restore_db.py --file backend/backups/brandguard_backup_20261107_170942.dump --test-restore
```
**Output confirms:**
1. Temporary database `brandguard_test_restore_<pid>` created.
2. Backup restored cleanly.
3. `alembic_version` matches current migration head.
4. Total tables, user records, and pgvector extension verified.
5. Temporary test database dropped cleanly.

---

## 5. Database Restore Procedure

The restore script `backend/scripts/restore_db.py` restores a verified backup into the target database.

> [!CAUTION]
> Database restoration is a **destructive operation**. It modifies or overwrites database tables and cannot be undone. Always verify existing backups before proceeding.

### Interactive Restore (Prompts for confirmation)
```bash
python backend/scripts/restore_db.py --file backend/backups/brandguard_backup_20261107_170942.dump
```
*Prompts the operator to type `RESTORE` to proceed.*

### Non-Interactive / Scripted Restore
```bash
python backend/scripts/restore_db.py \
  --file backend/backups/brandguard_backup_20261107_170942.dump \
  --confirm
```

### Clean Restore (Drops objects before recreating them)
```bash
python backend/scripts/restore_db.py \
  --file backend/backups/brandguard_backup_20261107_170942.dump \
  --confirm \
  --clean
```

---

## 6. Separate Backup Requirements for Uploaded Files

> [!IMPORTANT]
> PostgreSQL database dumps store **only** relational metadata, embeddings, and database tables. They **DO NOT** store uploaded document files or asset binaries.

Uploaded physical files are stored in `backend/storage/` (configured via `STORAGE_PATH`):
- `backend/storage/documents/{organization_id}/`: Uploaded PDFs, DOCX, TXT files, and analyzed document versions.
- `backend/storage/assets/{organization_id}/`: Uploaded logo images, color palettes, and brand guidelines.

### Backing Up Storage Files
```bash
# Tar and compress storage folder
tar -czvf /var/backups/brandguard_storage_$(date +%Y%m%d_%H%M%S).tar.gz backend/storage/
```

### Restoring Storage Files
```bash
# Restore files into storage directory
tar -xzvf /var/backups/brandguard_storage_20261107_170942.tar.gz -C backend/
```

---

## 7. Operational Retention & Scheduling Recommendations

For a small staging or production deployment:

| Cadence | Retention | Destination | Storage Requirement |
| :--- | :--- | :--- | :--- |
| **Hourly (Active hours)** | 24 hours | Local dedicated disk volume (`/var/backups/hourly`) | ~25 MB / day |
| **Daily (Midnight UTC)** | 30 days | Decoupled storage volume or S3-compatible bucket | ~35 MB / month |
| **Weekly** | 90 days | Cold storage / encrypted archive | ~50 MB / quarter |

### Automated Cron Job (Linux / Docker Host Example)
```crontab
# Daily database backup at 02:00 UTC
0 2 * * * /usr/bin/python3 /app/scripts/backup_db.py --output-dir /var/backups/brandguard >> /var/log/brandguard_backup.log 2>&1

# Daily storage files backup at 02:30 UTC
30 2 * * * tar -czf /var/backups/brandguard/storage_$(date +\%Y\%m\%d).tar.gz /app/storage >> /var/log/brandguard_backup.log 2>&1
```

---

## 8. Known Limitations

1. **Active Database Connections During Restoration:** If application web workers hold active locks on tables during a restore without `--clean`, `pg_restore` may queue or time out. For major rollbacks, stop backend workers (`docker compose stop backend`) before restoring the database.
2. **Cluster Distributed Transactions:** `pg_dump` takes a consistent snapshot at the time the dump starts. Operations executed after the dump starts are not included.
3. **Database Version Compatibility:** Dumps created on PostgreSQL 18.x can be restored on PostgreSQL 18.x or newer; restoring an 18.x dump onto an older PostgreSQL version (e.g. 15.x or 16.x) is not supported by PostgreSQL.

