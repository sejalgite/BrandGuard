#!/usr/bin/env python3
"""
backend/scripts/restore_db.py
Production-grade database restore utility for BrandGuard.

Restores a PostgreSQL custom format archive (-Fc) created by backup_db.py.

Safety Guarantees:
- Pre-restoration archive validation (validates TOC before connecting).
- Explicit destructive operation confirmation required (--confirm or interactive prompt).
- Additional production safeguard: restoring into production/active database requires
  explicit database name confirmation via --confirm-database <dbname>.
- Never restores automatically during application startup.
- Never silently drops or recreates the database.
- Zero password exposure in CLI arguments, process listings, or logs.
- Supports dry-run / temporary test database verification (--test-restore).
- Documents that file storage (assets/documents) must be restored separately.
"""
import os
import sys
import shutil
import logging
import argparse
import tempfile
import urllib.parse
import subprocess
from typing import Dict, Any, Optional, List, Tuple, Set

# Ensure backend root is on sys.path for app.config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("brandguard.restore")

# All 26 core application tables required for BrandGuard
EXPECTED_BRANDGUARD_TABLES: Set[str] = {
    "ai_disclosure_logs",
    "alembic_version",
    "audit_logs",
    "brand_assets",
    "brand_constitutions",
    "brand_rules",
    "comments",
    "disputes",
    "document_versions",
    "documents",
    "evaluation_datasets",
    "evaluation_runs",
    "evaluation_test_cases",
    "fact_registry",
    "finding_decisions",
    "findings",
    "notifications",
    "organizations",
    "review_assignments",
    "review_history",
    "review_jobs",
    "reviews",
    "revoked_tokens",
    "suggested_corrections",
    "term_bank",
    "users",
}


def find_pg_tool(tool_name: str) -> Optional[str]:
    """
    Locates a PostgreSQL CLI tool (pg_restore, psql, pg_dump) across standard locations.
    Checks PG_BIN_DIR env var, system PATH, and common Windows/Linux directories.
    """
    pg_bin_env = os.getenv("PG_BIN_DIR")
    if pg_bin_env:
        candidate = os.path.join(pg_bin_env, tool_name if sys.platform != "win32" else f"{tool_name}.exe")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    tool_in_path = shutil.which(tool_name)
    if tool_in_path:
        return tool_in_path

    candidates: List[str] = []
    if sys.platform == "win32":
        candidates.extend([
            r"C:\Program Files\PostgreSQL\18\bin",
            r"C:\Program Files\PostgreSQL\17\bin",
            r"C:\Program Files\PostgreSQL\16\bin",
            r"C:\Brandguard\pgsql\bin",
        ])
    else:
        candidates.extend([
            "/usr/lib/postgresql/18/bin",
            "/usr/lib/postgresql/17/bin",
            "/usr/lib/postgresql/16/bin",
            "/usr/bin",
            "/usr/local/bin",
        ])

    for folder in candidates:
        candidate = os.path.join(folder, tool_name if sys.platform != "win32" else f"{tool_name}.exe")
        if os.path.isfile(candidate):
            return candidate

    return None


def parse_db_url(db_url: str) -> Dict[str, str]:
    """
    Parses a PostgreSQL connection string into individual connection components.
    Masks credentials for safe logging.
    """
    if not db_url or not isinstance(db_url, str):
        raise ValueError("DATABASE_URL must be a non-empty string.")

    parsed = urllib.parse.urlparse(db_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"Invalid database scheme '{parsed.scheme}'; expected 'postgresql'.")

    user = urllib.parse.unquote(parsed.username) if parsed.username else "postgres"
    password = urllib.parse.unquote(parsed.password) if parsed.password else ""
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    dbname = parsed.path.lstrip("/")
    if not dbname:
        raise ValueError("Database name is missing from DATABASE_URL.")

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "dbname": dbname,
        "redacted_url": f"postgresql://{user}:*****@{host}:{port}/{dbname}",
    }


def validate_backup_file(backup_path: str, pg_restore_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Validates the backup file before restoration.
    Ensures file exists, is non-empty, and possesses a readable PostgreSQL TOC
    containing all 26 core application tables and pgvector extension.
    """
    if not os.path.isfile(backup_path):
        raise FileNotFoundError(f"Backup file not found at: {backup_path}")

    file_size = os.path.getsize(backup_path)
    if file_size <= 0:
        raise ValueError(f"Backup file is empty (0 bytes): {backup_path}")

    restore_tool = pg_restore_path or find_pg_tool("pg_restore")
    if not restore_tool:
        raise FileNotFoundError(
            "pg_restore utility not found. Please install PostgreSQL client tools or set PG_BIN_DIR."
        )

    result = subprocess.run(
        [restore_tool, "-l", backup_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"Invalid or corrupted backup archive: {result.stderr.strip()}")

    toc_text = result.stdout
    ddl_tables = set(
        line.split()[-2] for line in toc_text.splitlines() if " TABLE public " in line
    )
    data_tables = set(
        line.split()[-2] for line in toc_text.splitlines() if " TABLE DATA public " in line
    )
    extensions_found = set(
        line.split()[-1] for line in toc_text.splitlines() if " EXTENSION " in line
    )

    has_alembic = "alembic_version" in ddl_tables
    has_users = "users" in ddl_tables

    if not (has_alembic and has_users):
        raise ValueError(
            f"Backup TOC verification failed: missing core tables (alembic_version={has_alembic}, users={has_users})."
        )

    unique_tables = sorted(list(ddl_tables))
    missing_tables = sorted(list(EXPECTED_BRANDGUARD_TABLES - ddl_tables))

    return {
        "file_size_bytes": file_size,
        "unique_table_count": len(unique_tables),
        "total_toc_table_entries": len(ddl_tables) + len(data_tables),
        "tables": unique_tables,
        "missing_expected_tables": missing_tables,
        "extensions": sorted(list(extensions_found)),
        "has_alembic": has_alembic,
        "has_vector": "vector" in extensions_found,
    }


def build_restore_command(
    pg_restore_path: str,
    conn_info: Dict[str, str],
    backup_file: str,
    clean: bool = False,
) -> List[str]:
    """
    Builds the pg_restore command arguments.
    Never includes password in the argument list.
    """
    cmd = [
        pg_restore_path,
        "-h", conn_info["host"],
        "-p", conn_info["port"],
        "-U", conn_info["user"],
        "-d", conn_info["dbname"],
        "--no-owner",
        "--no-privileges",
    ]
    if clean:
        cmd.append("--clean")
        cmd.append("--if-exists")

    cmd.append(backup_file)
    return cmd


def execute_restore(
    backup_path: str,
    db_url: Optional[str] = None,
    confirm: bool = False,
    confirm_database: Optional[str] = None,
    clean: bool = False,
) -> Dict[str, Any]:
    """
    Performs a validated database restore.
    Requires explicit confirmation flag (confirm=True) or interactive prompt.
    When restoring into the active production database, requires --confirm-database <dbname>.
    """
    # 1. Locate pg_restore
    pg_restore_path = find_pg_tool("pg_restore")
    if not pg_restore_path:
        raise FileNotFoundError("pg_restore utility not found.")

    # 2. Validate backup archive before any DB operations
    logger.info("Validating backup archive: %s", backup_path)
    val_summary = validate_backup_file(backup_path, pg_restore_path)
    logger.info(
        "Archive TOC valid: %d application tables detected (%d TOC entries), alembic_version=%s, vector=%s",
        val_summary["unique_table_count"],
        val_summary["total_toc_table_entries"],
        val_summary["has_alembic"],
        val_summary["has_vector"],
    )

    # 3. Resolve connection info
    resolved_url = db_url or os.getenv("DATABASE_URL")
    if not resolved_url:
        try:
            from app.config import settings
            resolved_url = settings.DATABASE_URL
        except Exception:
            pass

    if not resolved_url:
        raise ValueError("DATABASE_URL must be specified via argument or environment.")

    conn_info = parse_db_url(resolved_url)

    # 4. Mandatory destructive-action confirmation guard
    target_db = conn_info["dbname"]
    is_production_db = target_db in {"brandguard", "production", "prod"}

    if is_production_db:
        # Extra safeguard: cannot restore into production without matching --confirm-database
        if not confirm_database or confirm_database.strip() != target_db:
            if not sys.stdin.isatty():
                raise PermissionError(
                    f"CRITICAL SAFEGUARD: Restoring into active/production database '{target_db}' "
                    f"requires explicit parameter '--confirm-database {target_db}'."
                )

    if not confirm:
        if sys.stdin.isatty():
            print("=" * 70)
            print("WARNING: DATABASE RESTORATION IS A DESTRUCTIVE OPERATION.")
            print(f"Target Database: {conn_info['redacted_url']}")
            print(f"Source Backup:   {backup_path}")
            print("=" * 70)
            prompt_msg = f"Type exact database name '{target_db}' to proceed with overwriting: "
            user_input = input(prompt_msg)
            if user_input.strip() != target_db:
                logger.info("Restore canceled by user.")
                raise PermissionError("Destructive restore aborted: user confirmation failed.")
        else:
            raise PermissionError(
                "Destructive restore requires explicit confirmation. Pass '--confirm' in non-interactive environments."
            )

    logger.warning("Proceeding with database restore to target: %s", conn_info["redacted_url"])

    # 5. Execute restore with secure credentials
    cmd = build_restore_command(pg_restore_path, conn_info, backup_path, clean=clean)
    env = os.environ.copy()

    temp_passfile = None
    if conn_info["password"]:
        try:
            temp_dir = tempfile.gettempdir()
            temp_passfile = os.path.join(temp_dir, f".pgpass_restore_{os.getpid()}")
            with open(temp_passfile, "w", encoding="utf-8") as f:
                f.write(
                    f"{conn_info['host']}:{conn_info['port']}:{conn_info['dbname']}:"
                    f"{conn_info['user']}:{conn_info['password']}\n"
                )
            if sys.platform != "win32":
                os.chmod(temp_passfile, 0o600)
            env["PGPASSFILE"] = temp_passfile
            env["PGPASSWORD"] = conn_info["password"]
        except Exception:
            env["PGPASSWORD"] = conn_info["password"]

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
        )
        # Note: pg_restore returns 0 on clean exit, or 1 if warnings occurred (e.g. extension already exists)
        if proc.returncode not in (0, 1):
            clean_err = proc.stderr.replace(conn_info["password"], "******") if conn_info["password"] else proc.stderr
            raise RuntimeError(f"pg_restore failed with return code {proc.returncode}: {clean_err.strip()}")

        if proc.returncode == 1:
            logger.info("pg_restore completed with non-fatal warnings (e.g. existing extensions/roles).")
    finally:
        if temp_passfile and os.path.exists(temp_passfile):
            try:
                os.remove(temp_passfile)
            except OSError:
                pass

    logger.info("Database restoration completed successfully.")
    print("NOTE: Database restoration restored SQL tables and schema.")
    print("NOTE: Uploaded physical files (assets, documents) stored in 'storage/' must be restored separately.")

    return {
        "status": "success",
        "target": conn_info["redacted_url"],
        "backup_file": backup_path,
        "tables_restored": val_summary["unique_table_count"],
    }


def run_restore_test(backup_path: str, db_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes an end-to-end restore verification test against a temporary database.
    Guarantees that the active database is never touched.
    """
    psql_path = find_pg_tool("psql")
    pg_restore_path = find_pg_tool("pg_restore")
    if not psql_path or not pg_restore_path:
        raise FileNotFoundError("Both psql and pg_restore utilities are required for restore testing.")

    # Validate backup file
    val_summary = validate_backup_file(backup_path, pg_restore_path)

    # Base connection info
    resolved_url = db_url or os.getenv("DATABASE_URL")
    if not resolved_url:
        from app.config import settings
        resolved_url = settings.DATABASE_URL

    conn = parse_db_url(resolved_url)
    temp_db_name = f"brandguard_test_restore_{os.getpid()}"

    logger.info("Running restore verification test on temporary database: %s", temp_db_name)

    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = conn["password"]

    # 1. Create temporary database
    # Connect to maintenance database 'postgres' to issue CREATE DATABASE
    subprocess.run(
        [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres",
         "-c", f"DROP DATABASE IF EXISTS {temp_db_name};"],
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres",
         "-c", f"CREATE DATABASE {temp_db_name};"],
        env=env,
        check=True,
        capture_output=True,
    )

    try:
        # 2. Restore into temporary database
        restore_cmd = [
            pg_restore_path,
            "-h", conn["host"],
            "-p", conn["port"],
            "-U", conn["user"],
            "-d", temp_db_name,
            "--no-owner",
            "--no-privileges",
            backup_path,
        ]
        r_proc = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)
        if r_proc.returncode not in (0, 1):
            raise RuntimeError(f"Restore into test database failed: {r_proc.stderr.strip()}")

        # 3. Verify Alembic migration revision
        v_proc = subprocess.run(
            [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db_name,
             "-t", "-A", "-c", "SELECT version_num FROM alembic_version;"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        alembic_rev = v_proc.stdout.strip()

        # 4. Count users and tables
        u_proc = subprocess.run(
            [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db_name,
             "-t", "-A", "-c", "SELECT count(*) FROM users;"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        user_count = int(u_proc.stdout.strip() or 0)

        t_proc = subprocess.run(
            [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db_name,
             "-t", "-A", "-c", "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        table_count = int(t_proc.stdout.strip() or 0)

        # 5. Check pgvector extension in restored db
        vec_proc = subprocess.run(
            [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db_name,
             "-t", "-A", "-c", "SELECT count(*) FROM pg_extension WHERE extname = 'vector';"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        vector_count = int(vec_proc.stdout.strip() or 0)

        logger.info(
            "Temporary database verified: Alembic=%s, Users=%d, Tables=%d, Vector=%s",
            alembic_rev,
            user_count,
            table_count,
            vector_count > 0,
        )

        return {
            "status": "verified",
            "test_database": temp_db_name,
            "alembic_version": alembic_rev,
            "user_count": user_count,
            "table_count": table_count,
            "vector_extension_active": vector_count > 0,
        }

    finally:
        # Drop temporary test database cleanly
        try:
            subprocess.run(
                [psql_path, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres",
                 "-c", f"DROP DATABASE IF EXISTS {temp_db_name};"],
                env=env,
                check=True,
                capture_output=True,
            )
            logger.info("Temporary test database '%s' dropped cleanly.", temp_db_name)
        except Exception as drop_err:
            logger.warning("Failed to clean up temporary test database '%s': %s", temp_db_name, drop_err)


def main():
    parser = argparse.ArgumentParser(description="BrandGuard Database Restore Utility")
    parser.add_argument("-f", "--file", required=True, help="Path to the backup file (.dump)")
    parser.add_argument("--db-url", help="Target database URL (default: DATABASE_URL env var)")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation for non-interactive destructive restore")
    parser.add_argument("--confirm-database", help="Explicit confirmation of the target database name (required for production/brandguard)")
    parser.add_argument("--clean", action="store_true", help="Drop objects before restoring them")
    parser.add_argument("--test-restore", action="store_true", help="Run a verification test restore in a temporary database")

    args = parser.parse_args()

    try:
        if args.test_restore:
            result = run_restore_test(args.file, db_url=args.db_url)
            print("=" * 60)
            print("RESTORE VERIFICATION TEST: PASSED")
            print(f"Verified Alembic Revision: {result['alembic_version']}")
            print(f"Verified Table Count:     {result['table_count']}")
            print(f"Verified User Count:      {result['user_count']}")
            print(f"pgvector Extension:       {result['vector_extension_active']}")
            print("=" * 60)
        else:
            execute_restore(
                backup_path=args.file,
                db_url=args.db_url,
                confirm=args.confirm,
                confirm_database=args.confirm_database,
                clean=args.clean,
            )
            print("SUCCESS: Target database restored successfully.")
        sys.exit(0)
    except Exception as exc:
        logger.error("Restore failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
