"""
backend/scripts/audit_backup_compare.py
Audits point-in-time snapshot integrity by comparing active database table counts
with table counts restored in an ephemeral temporary database.
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backup_db import find_pg_tool, parse_db_url, execute_backup
from scripts.restore_db import validate_backup_file


def run_table_by_table_audit():
    psql = find_pg_tool("psql")
    pg_restore = find_pg_tool("pg_restore")
    if not psql or not pg_restore:
        raise FileNotFoundError("psql and pg_restore are required for audit comparison.")

    from app.config import settings
    conn = parse_db_url(settings.DATABASE_URL)

    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = conn["password"]

    # 1. Take a fresh backup (with custom name, non-destructive)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    audit_dump = os.path.join(backup_dir, f"brandguard_audit_snapshot_{ts}.dump")

    print(f"1. Creating fresh snapshot: {audit_dump}")
    execute_backup(
        db_url=settings.DATABASE_URL,
        output_path=audit_dump,
        force=False,
    )

    # 2. Query all public table names and their row counts in active database AT THIS INSTANT
    tables_query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
    t_res = subprocess.run(
        [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", conn["dbname"], "-t", "-A", "-c", tables_query],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    tables = [t.strip() for t in t_res.stdout.splitlines() if t.strip()]

    print(f"2. Querying active database row counts for {len(tables)} tables...")
    active_counts = {}
    for t in tables:
        c_res = subprocess.run(
            [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", conn["dbname"], "-t", "-A", "-c", f"SELECT count(*) FROM {t};"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        active_counts[t] = int(c_res.stdout.strip() or 0)

    # 3. Create ephemeral temporary database
    temp_db = f"brandguard_audit_temp_{ts}"
    print(f"3. Provisioning temporary test database: {temp_db}...")
    subprocess.run(
        [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {temp_db};"],
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres", "-c", f"CREATE DATABASE {temp_db};"],
        env=env,
        check=True,
        capture_output=True,
    )

    try:
        # 4. Restore snapshot into temporary database
        print(f"4. Restoring snapshot into {temp_db}...")
        restore_cmd = [
            pg_restore,
            "-h", conn["host"],
            "-p", conn["port"],
            "-U", conn["user"],
            "-d", temp_db,
            "--no-owner",
            "--no-privileges",
            audit_dump,
        ]
        r_proc = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)
        if r_proc.returncode not in (0, 1):
            raise RuntimeError(f"Restore failed: {r_proc.stderr}")

        # 5. Query row counts in restored temporary database
        print(f"5. Querying restored database row counts for {len(tables)} tables...")
        restored_counts = {}
        for t in tables:
            c_res = subprocess.run(
                [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db, "-t", "-A", "-c", f"SELECT count(*) FROM {t};"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            restored_counts[t] = int(c_res.stdout.strip() or 0)

        # 6. Query Alembic revision
        al_res = subprocess.run(
            [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db, "-t", "-A", "-c", "SELECT version_num FROM alembic_version;"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        alembic_rev = al_res.stdout.strip()

        # 7. Query vector extension
        vec_res = subprocess.run(
            [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", temp_db, "-t", "-A", "-c", "SELECT extversion FROM pg_extension WHERE extname = 'vector';"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        vec_version = vec_res.stdout.strip()

        # Compile comparison
        comparison = []
        all_matched = True
        for t in tables:
            a_cnt = active_counts[t]
            r_cnt = restored_counts[t]
            matched = (a_cnt == r_cnt)
            if not matched:
                all_matched = False
            comparison.append({
                "table": t,
                "active_count": a_cnt,
                "restored_count": r_cnt,
                "match": matched,
            })

        print("\n" + "=" * 65)
        print(f"{'TABLE NAME':<26} | {'ACTIVE':<9} | {'RESTORED':<9} | {'STATUS'}")
        print("=" * 65)
        for row in comparison:
            status = "MATCH" if row["match"] else "MISMATCH"
            print(f"{row['table']:<26} | {row['active_count']:<9} | {row['restored_count']:<9} | {status}")
        print("=" * 65)
        print(f"All {len(tables)} tables matched: {all_matched}")
        print(f"Restored Alembic Revision: {alembic_rev}")
        print(f"Restored pgvector Version: {vec_version}")

        return {
            "all_matched": all_matched,
            "alembic_revision": alembic_rev,
            "vector_version": vec_version,
            "comparison": comparison,
            "audit_backup_file": audit_dump,
        }

    finally:
        # 8. Clean up ephemeral temporary database
        print(f"8. Cleaning up and dropping temporary test database: {temp_db}...")
        subprocess.run(
            [psql, "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {temp_db};"],
            env=env,
            check=True,
            capture_output=True,
        )
        print("Temporary test database dropped cleanly.")


if __name__ == "__main__":
    run_table_by_table_audit()

