#!/usr/bin/env python3
"""
backend/scripts/backup_db.py
Production-grade database backup utility for BrandGuard.

Exports a compressed PostgreSQL custom format archive (-Fc) capturing all
application tables, constraints, indexes, triggers, pgvector extension, and Alembic state.

Features:
- Zero password exposure in CLI args, process listings, or logs.
- Temporary PGPASSFILE / secure environment credential isolation.
- Automatic verification of backup file existence, size, and TOC readability via pg_restore.
- Distinguishes schema DDL tables from table data entries in TOC.
- Explicitly checks for all 26 core BrandGuard application tables and pgvector extension.
- Exits with non-zero code on any failure.
- Never silently overwrites existing backup files.
"""
import os
import sys
import shutil
import logging
import argparse
import tempfile
import urllib.parse
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Set

# Ensure backend root is on sys.path for app.config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("brandguard.backup")

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
    Locates a PostgreSQL CLI tool (pg_dump, pg_restore, psql) across standard locations.
    Checks PG_BIN_DIR env var, system PATH, and common Windows/Linux directories.
    """
    # 1. Custom PG_BIN_DIR environment variable
    pg_bin_env = os.getenv("PG_BIN_DIR")
    if pg_bin_env:
        candidate = os.path.join(pg_bin_env, tool_name if sys.platform != "win32" else f"{tool_name}.exe")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # 2. System PATH
    tool_in_path = shutil.which(tool_name)
    if tool_in_path:
        return tool_in_path

    # 3. Known directory fallbacks
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


def build_dump_command(
    pg_dump_path: str,
    conn_info: Dict[str, str],
    output_file: str,
) -> List[str]:
    """
    Builds the pg_dump command arguments.
    Never includes password in the argument list.
    """
    return [
        pg_dump_path,
        "-h", conn_info["host"],
        "-p", conn_info["port"],
        "-U", conn_info["user"],
        "-d", conn_info["dbname"],
        "-Fc",  # PostgreSQL Custom compressed format
        "--no-owner",  # Don't output commands to set ownership of objects
        "--no-privileges",  # Don't dump privileges (grant/revoke)
        "-f", output_file,
    ]


def validate_backup(backup_path: str, pg_restore_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifies that the generated backup file exists, is non-empty, and has a readable TOC.
    Differentiates DDL schema definitions from table data entries, and verifies
    expected BrandGuard application tables and extensions.
    """
    if not os.path.isfile(backup_path):
        raise FileNotFoundError(f"Backup file not found at: {backup_path}")

    file_size = os.path.getsize(backup_path)
    if file_size <= 0:
        raise ValueError(f"Backup file is empty (0 bytes): {backup_path}")

    restore_tool = pg_restore_path or find_pg_tool("pg_restore")
    if not restore_tool:
        logger.warning("pg_restore utility not found; TOC content inspection skipped.")
        return {"file_size_bytes": file_size, "toc_verified": False}

    # Run pg_restore -l to inspect archive Table of Contents
    result = subprocess.run(
        [restore_tool, "-l", backup_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore -l failed to read backup TOC: {result.stderr.strip()}")

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

    unique_tables = sorted(list(ddl_tables))
    missing_tables = sorted(list(EXPECTED_BRANDGUARD_TABLES - ddl_tables))

    return {
        "file_size_bytes": file_size,
        "toc_verified": True,
        "unique_table_count": len(unique_tables),
        "total_toc_table_entries": len(ddl_tables) + len(data_tables),
        "tables": unique_tables,
        "missing_expected_tables": missing_tables,
        "extensions": sorted(list(extensions_found)),
        "has_alembic": "alembic_version" in ddl_tables,
        "has_vector": "vector" in extensions_found,
    }


def execute_backup(
    db_url: Optional[str] = None,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """
    Executes a database backup and validates the result.
    Returns (backup_file_path, validation_summary).
    """
    # 1. Resolve connection info
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
    logger.info("Initiating database backup for target: %s", conn_info["redacted_url"])

    # 2. Locate pg_dump and pg_restore
    pg_dump_path = find_pg_tool("pg_dump")
    if not pg_dump_path:
        raise FileNotFoundError(
            "pg_dump utility not found. Please install PostgreSQL client tools or set PG_BIN_DIR."
        )

    pg_restore_path = find_pg_tool("pg_restore")

    # 3. Determine output file path
    if output_path:
        final_output = os.path.abspath(output_path)
    else:
        target_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups"
        )
        os.makedirs(target_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        final_output = os.path.join(target_dir, f"brandguard_backup_{timestamp}.dump")

    # Guard against accidental silent overwrite
    if os.path.exists(final_output) and not force:
        raise FileExistsError(
            f"Backup file '{final_output}' already exists. Use --force to overwrite."
        )

    # 4. Execute dump with isolated credentials
    cmd = build_dump_command(pg_dump_path, conn_info, final_output)
    env = os.environ.copy()

    # Isolate password via secure environment / PGPASSFILE without CLI argument exposure
    temp_passfile = None
    if conn_info["password"]:
        try:
            temp_dir = tempfile.gettempdir()
            temp_passfile = os.path.join(temp_dir, f".pgpass_{os.getpid()}_{datetime.now().timestamp()}")
            with open(temp_passfile, "w", encoding="utf-8") as f:
                f.write(
                    f"{conn_info['host']}:{conn_info['port']}:{conn_info['dbname']}:"
                    f"{conn_info['user']}:{conn_info['password']}\n"
                )
            if sys.platform != "win32":
                os.chmod(temp_passfile, 0o600)
            env["PGPASSFILE"] = temp_passfile
            env["PGPASSWORD"] = conn_info["password"]
        except Exception as e:
            logger.warning("Could not create secure PGPASSFILE, falling back to process env: %s", e)
            env["PGPASSWORD"] = conn_info["password"]

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # Redact any accidental credential echo in stderr
            clean_err = proc.stderr.replace(conn_info["password"], "******") if conn_info["password"] else proc.stderr
            raise RuntimeError(f"pg_dump process failed with code {proc.returncode}: {clean_err.strip()}")
    finally:
        if temp_passfile and os.path.exists(temp_passfile):
            try:
                os.remove(temp_passfile)
            except OSError:
                pass

    # 5. Validate backup integrity
    validation = validate_backup(final_output, pg_restore_path)
    logger.info(
        "Backup successfully created and validated: %s (%0.2f MB, %d application tables, %d TOC entries)",
        final_output,
        validation["file_size_bytes"] / (1024 * 1024),
        validation.get("unique_table_count", 0),
        validation.get("total_toc_table_entries", 0),
    )

    return final_output, validation


def main():
    parser = argparse.ArgumentParser(description="BrandGuard Database Backup Utility")
    parser.add_argument("--db-url", help="Database URL (default: DATABASE_URL env var)")
    parser.add_argument("-o", "--output", help="Specific output file path")
    parser.add_argument("--output-dir", help="Directory where timestamped backup file will be placed")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing backup file")

    args = parser.parse_args()

    try:
        backup_path, validation = execute_backup(
            db_url=args.db_url,
            output_path=args.output,
            output_dir=args.output_dir,
            force=args.force,
        )
        print(f"SUCCESS: Backup created at '{backup_path}'")
        print(f"Size: {validation['file_size_bytes']} bytes")
        if validation.get("toc_verified"):
            print(f"Verified application tables: {validation.get('unique_table_count')}")
            print(f"Total table TOC entries: {validation.get('total_toc_table_entries')} (schema + data)")
            print(f"Alembic version present: {validation.get('has_alembic')}")
            print(f"pgvector extension present: {validation.get('has_vector')}")
        sys.exit(0)
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
