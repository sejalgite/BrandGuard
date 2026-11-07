"""
backend/scripts/schema_compare.py
Development-only verification utility — NOT integrated into application startup or deployment.

Compares schema objects (extensions, indexes, constraints, triggers, trigger functions)
between the active brandguard database and a fresh restore from the latest backup archive.
Performs a read-only inspection of the active database; creates and drops a temporary
database for the comparison restore. Safe to run at any time against a live database.

Usage (development / CI verification only):
    python backend/scripts/schema_compare.py

Requirements:
    - PostgreSQL 18 client utilities (pg_restore, psql, createdb, dropdb)
    - At least one .dump archive in backend/backups/
    - DATABASE_URL or PGPASSWORD environment variable for the brandguard_user role

Expected Output:
    Extensions, indexes (count + HNSW), constraints, triggers, and trigger functions
    compared with MATCH / MISMATCH / MISSING indicators.
    Final line: RESULT: ALL SCHEMA OBJECTS MATCH — OK
"""
import subprocess
import sys
import os
import uuid

PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"
PG_RESTORE = r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe"
CREATEDB = r"C:\Program Files\PostgreSQL\18\bin\createdb.exe"
DROPDB = r"C:\Program Files\PostgreSQL\18\bin\dropdb.exe"
HOST = "127.0.0.1"
PORT = "5435"
USER = "brandguard_user"
ACTIVE_DB = "brandguard"

# Find latest backup
BACKUPS_DIR = r"c:\Brandguard\backend\backups"
backups = sorted(
    [f for f in os.listdir(BACKUPS_DIR) if f.endswith(".dump")],
    reverse=True
)
if not backups:
    print("ERROR: No backup files found.")
    sys.exit(1)
BACKUP_FILE = os.path.join(BACKUPS_DIR, backups[0])
print(f"Using backup: {BACKUP_FILE}")

TEMP_DB = f"brandguard_schema_check_{os.getpid()}"
print(f"Temp DB: {TEMP_DB}")

env = os.environ.copy()
env["PGPASSWORD"] = "brandguard_password"

def psql(db, sql, label=""):
    result = subprocess.run(
        [PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", db,
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        print(f"  PSQL ERROR [{label}]: {result.stderr.strip()}")
        return []
    return [line for line in result.stdout.strip().splitlines() if line.strip()]

def run(cmd, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"  CMD ERROR [{label}]: {result.stderr.strip()[:300]}")
    return result.returncode == 0

try:
    # Create temp DB
    print(f"\n--- Creating temp DB: {TEMP_DB} ---")
    if not run([CREATEDB, "-h", HOST, "-p", PORT, "-U", USER, TEMP_DB], "createdb"):
        sys.exit(1)

    # Restore into temp DB
    print(f"--- Restoring backup into {TEMP_DB} ---")
    result = subprocess.run(
        [PG_RESTORE, "-h", HOST, "-p", PORT, "-U", USER,
         "-d", TEMP_DB, "--no-owner", "--no-acl", BACKUP_FILE],
        capture_output=True, text=True, env=env
    )
    # pg_restore exits 1 on warnings; check stderr
    if result.returncode > 1:
        print(f"  RESTORE ERROR: {result.stderr[:500]}")
        sys.exit(1)
    elif result.returncode == 1:
        print(f"  Restore completed with warnings (exit 1 — normal): {result.stderr[:200]}")
    else:
        print("  Restore completed successfully.")

    all_ok = True

    # ---- EXTENSIONS ----
    print("\n========== EXTENSIONS ==========")
    ext_sql = "SELECT extname, extversion FROM pg_extension ORDER BY extname;"
    active_exts = psql(ACTIVE_DB, ext_sql, "active exts")
    temp_exts = psql(TEMP_DB, ext_sql, "temp exts")
    print(f"{'Extension':<20} {'Active':>10} {'Restored':>10} {'Match':>8}")
    print("-" * 55)
    all_ext_names = sorted(set([r.split('|')[0] for r in active_exts + temp_exts]))
    active_ext_map = {r.split('|')[0]: r.split('|')[1] for r in active_exts}
    temp_ext_map = {r.split('|')[0]: r.split('|')[1] for r in temp_exts}
    for name in all_ext_names:
        av = active_ext_map.get(name, "MISSING")
        tv = temp_ext_map.get(name, "MISSING")
        match = "OK" if av == tv else "MISMATCH"
        if match != "OK":
            all_ok = False
        print(f"{name:<20} {av:>10} {tv:>10} {match:>8}")

    # ---- INDEXES ----
    print("\n========== INDEXES ==========")
    idx_sql = """SELECT tablename, indexname, indexdef 
                 FROM pg_indexes 
                 WHERE schemaname = 'public' 
                 ORDER BY tablename, indexname;"""
    active_idxs = psql(ACTIVE_DB, idx_sql, "active idx")
    temp_idxs = psql(TEMP_DB, idx_sql, "temp idx")
    active_idx_map = {}
    temp_idx_map = {}
    for r in active_idxs:
        parts = r.split('|', 2)
        if len(parts) >= 3:
            active_idx_map[parts[1]] = (parts[0], parts[2])
    for r in temp_idxs:
        parts = r.split('|', 2)
        if len(parts) >= 3:
            temp_idx_map[parts[1]] = (parts[0], parts[2])
    
    all_idx_names = sorted(set(list(active_idx_map.keys()) + list(temp_idx_map.keys())))
    hnsw_indexes = []
    idx_mismatches = []
    missing_in_temp = []
    missing_in_active = []
    
    for idx_name in all_idx_names:
        in_active = idx_name in active_idx_map
        in_temp = idx_name in temp_idx_map
        if in_active and in_temp:
            adef = active_idx_map[idx_name][1]
            tdef = temp_idx_map[idx_name][1]
            if 'hnsw' in adef.lower():
                hnsw_indexes.append(idx_name)
            if adef != tdef:
                idx_mismatches.append((idx_name, adef, tdef))
                all_ok = False
        elif in_active and not in_temp:
            missing_in_temp.append(idx_name)
            all_ok = False
        elif in_temp and not in_active:
            missing_in_active.append(idx_name)
            all_ok = False
    
    print(f"  Active DB index count:   {len(active_idx_map)}")
    print(f"  Restored DB index count: {len(temp_idx_map)}")
    print(f"  HNSW indexes found:      {len(hnsw_indexes)}")
    if hnsw_indexes:
        for h in hnsw_indexes:
            print(f"    - {h}: {active_idx_map[h][1][:80]}...")
    if idx_mismatches:
        print(f"  MISMATCHES ({len(idx_mismatches)}):")
        for name, adef, tdef in idx_mismatches:
            print(f"    {name}:\n      active:   {adef}\n      restored: {tdef}")
    if missing_in_temp:
        print(f"  MISSING IN RESTORED: {missing_in_temp}")
    if missing_in_active:
        print(f"  MISSING IN ACTIVE:   {missing_in_active}")
    if not idx_mismatches and not missing_in_temp and not missing_in_active:
        print("  All indexes match.")

    # ---- CONSTRAINTS ----
    print("\n========== CONSTRAINTS ==========")
    con_sql = """SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
                        COALESCE(kcu.column_name, '') as col,
                        COALESCE(ccu.table_name, '') as ref_table,
                        COALESCE(ccu.column_name, '') as ref_col
                 FROM information_schema.table_constraints tc
                 LEFT JOIN information_schema.key_column_usage kcu
                   ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                 LEFT JOIN information_schema.constraint_column_usage ccu
                   ON tc.constraint_name = ccu.constraint_name
                   AND tc.table_schema = ccu.table_schema
                 WHERE tc.table_schema = 'public'
                 ORDER BY tc.table_name, tc.constraint_name, kcu.column_name;"""
    active_cons = set(psql(ACTIVE_DB, con_sql, "active cons"))
    temp_cons = set(psql(TEMP_DB, con_sql, "temp cons"))
    
    only_active = active_cons - temp_cons
    only_temp = temp_cons - active_cons
    print(f"  Active constraint rows:   {len(active_cons)}")
    print(f"  Restored constraint rows: {len(temp_cons)}")
    if only_active:
        print(f"  ONLY IN ACTIVE ({len(only_active)}):")
        for c in sorted(only_active)[:10]:
            print(f"    {c}")
        all_ok = False
    if only_temp:
        print(f"  ONLY IN RESTORED ({len(only_temp)}):")
        for c in sorted(only_temp)[:10]:
            print(f"    {c}")
        all_ok = False
    if not only_active and not only_temp:
        print("  All constraints match.")

    # ---- TRIGGERS ----
    print("\n========== TRIGGERS ==========")
    trig_sql = """SELECT trigger_name, event_manipulation, event_object_table, action_timing
                  FROM information_schema.triggers
                  WHERE trigger_schema = 'public'
                  ORDER BY trigger_name, event_manipulation;"""
    active_trigs = psql(ACTIVE_DB, trig_sql, "active trigs")
    temp_trigs = psql(TEMP_DB, trig_sql, "temp trigs")
    
    active_trig_set = set(active_trigs)
    temp_trig_set = set(temp_trigs)
    only_a = active_trig_set - temp_trig_set
    only_t = temp_trig_set - active_trig_set
    print(f"  Active trigger rows:   {len(active_trigs)}")
    print(f"  Restored trigger rows: {len(temp_trigs)}")
    for t in active_trigs:
        print(f"    ACTIVE: {t}")
    if only_a:
        print(f"  ONLY IN ACTIVE: {only_a}")
        all_ok = False
    if only_t:
        print(f"  ONLY IN RESTORED: {only_t}")
        all_ok = False
    if not only_a and not only_t:
        print("  All triggers match.")

    # ---- TRIGGER FUNCTIONS ----
    print("\n========== TRIGGER FUNCTIONS ==========")
    tfunc_sql = """SELECT p.proname, pg_get_functiondef(p.oid) as definition
                   FROM pg_proc p
                   JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'public'
                   AND p.prokind = 'f'
                   ORDER BY p.proname;"""
    active_funcs = psql(ACTIVE_DB, tfunc_sql, "active funcs")
    temp_funcs = psql(TEMP_DB, tfunc_sql, "temp funcs")
    
    # Just get function names
    afunc_names = [r.split('|')[0] for r in active_funcs]
    tfunc_names = [r.split('|')[0] for r in temp_funcs]
    
    print(f"  Active functions:   {afunc_names}")
    print(f"  Restored functions: {tfunc_names}")
    
    if set(afunc_names) == set(tfunc_names):
        print("  All trigger functions match.")
    else:
        only_af = set(afunc_names) - set(tfunc_names)
        only_tf = set(tfunc_names) - set(afunc_names)
        if only_af:
            print(f"  ONLY IN ACTIVE: {only_af}")
        if only_tf:
            print(f"  ONLY IN RESTORED: {only_tf}")
        all_ok = False

    # ---- SUMMARY ----
    print("\n========== SUMMARY ==========")
    if all_ok:
        print("  RESULT: ALL SCHEMA OBJECTS MATCH — OK")
    else:
        print("  RESULT: SCHEMA MISMATCHES DETECTED — REVIEW ABOVE")

finally:
    # Drop temp DB
    print(f"\n--- Dropping temp DB: {TEMP_DB} ---")
    run([DROPDB, "-h", HOST, "-p", PORT, "-U", USER, "--if-exists", TEMP_DB], "dropdb")
    print("Done.")
