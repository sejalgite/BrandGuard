#!/usr/bin/env python3
"""
backend/scripts/storage_backup.py
Production-grade filesystem backup utility for BrandGuard uploaded documents and brand assets.

Features:
- Backs up both 'documents' and 'assets' storage hierarchies preserving organization directory structure.
- Generates an embedded, cryptographically verified manifest.json containing relative paths,
  file sizes, SHA-256 checksums, and modification timestamps.
- Zero paid dependencies: uses standard Python hashlib, tarfile, and gzip.
- Symlink containment: refuses to follow or bundle symlinks targeting files outside the storage root.
- Clean exclusion: ignores temporary probes (.readiness_probe_*), __pycache__, and hidden metadata.
- Incremental support: optionally backs up only files modified since a given ISO-8601 timestamp.
- Safety & Overwrite protection: rejects accidental overwrite of existing backup archives unless --force is passed.
- Dry-run capability: inspects and displays candidate files and manifest metrics without writing an archive.
"""
import os
import sys
import json
import gzip
import tarfile
import hashlib
import logging
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("brandguard.storage_backup")

EXCLUDED_FILENAMES: Set[str] = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

EXCLUDED_DIRNAMES: Set[str] = {
    "__pycache__",
    ".pytest_cache",
    ".git",
}


def calculate_sha256(file_path: str, chunk_size: int = 65536) -> str:
    """Computes SHA-256 hexadecimal digest of a file using chunked streaming."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_storage_roots(explicit_root: Optional[str] = None) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Resolves the base storage parent directory and the list of active sub-roots to archive.
    Returns (storage_parent_dir, [(sub_folder_name, sub_folder_abs_path), ...]).
    Sub-folders typically include 'documents' and 'assets'.
    """
    if explicit_root:
        base_dir = os.path.abspath(explicit_root)
        sub_roots = []
        for name in ["documents", "assets"]:
            target = os.path.join(base_dir, name)
            if os.path.isdir(target):
                sub_roots.append((name, target))
        if not sub_roots:
            # If the explicit root doesn't contain documents/assets subdirs, treat explicit root itself as unified
            sub_roots.append((".", base_dir))
        return base_dir, sub_roots

    try:
        from app.config import settings
        storage_parent = os.path.abspath(settings.STORAGE_ROOT)
        sub_roots = []
        for name, path in [("documents", settings.DOCUMENTS_STORAGE_PATH), ("assets", settings.ASSETS_STORAGE_PATH)]:
            abs_p = os.path.abspath(path)
            if os.path.isdir(abs_p):
                sub_roots.append((name, abs_p))
            else:
                # Ensure directory exists even if empty
                os.makedirs(abs_p, exist_ok=True)
                sub_roots.append((name, abs_p))
        return storage_parent, sub_roots
    except Exception as e:
        logger.warning("Could not load app.config settings (%s); falling back to default filesystem layout", e)
        fallback_parent = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage"))
        sub_roots = [
            ("documents", os.path.join(fallback_parent, "documents")),
            ("assets", os.path.join(fallback_parent, "assets")),
        ]
        return fallback_parent, sub_roots


def scan_storage_files(
    storage_parent: str,
    sub_roots: List[Tuple[str, str]],
    since_timestamp: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Scans storage sub-roots, verifies symlink security, computes checksums,
    and returns (file_metadata_list, total_bytes).
    """
    file_records: List[Dict[str, Any]] = []
    total_bytes = 0
    storage_parent_norm = os.path.abspath(storage_parent)

    for prefix, root_path in sub_roots:
        root_path_abs = os.path.abspath(root_path)
        if not os.path.exists(root_path_abs):
            continue

        for dirpath, dirnames, filenames in os.walk(root_path_abs, followlinks=False):
            # Prune excluded directories
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRNAMES]

            for fname in sorted(filenames):
                # Filter exclusions
                if fname in EXCLUDED_FILENAMES:
                    continue
                if fname.startswith(".readiness_probe_"):
                    continue
                if fname.endswith(".pyc") or fname.endswith(".tmp"):
                    continue

                full_path = os.path.join(dirpath, fname)

                # Symlink safety check: refuse symlinks resolving outside the storage parent
                if os.path.islink(full_path):
                    real_target = os.path.realpath(full_path)
                    if not (real_target == storage_parent_norm or real_target.startswith(storage_parent_norm + os.sep)):
                        logger.warning("Skipping symlink outside storage root: %s -> %s", full_path, real_target)
                        continue

                try:
                    stat_res = os.stat(full_path)
                except OSError as e:
                    logger.warning("Cannot stat file %s: %s", full_path, e)
                    continue

                mtime = datetime.fromtimestamp(stat_res.st_mtime, timezone.utc)

                # Incremental filter
                if since_timestamp and mtime <= since_timestamp:
                    continue

                # Relative path from storage_parent (e.g. 'documents/{org_id}/file.pdf')
                rel_path = os.path.relpath(full_path, storage_parent_norm).replace("\\", "/")

                sha256_hash = calculate_sha256(full_path)
                file_size = stat_res.st_size
                total_bytes += file_size

                file_records.append({
                    "relative_path": rel_path,
                    "absolute_source_path": full_path,
                    "size_bytes": file_size,
                    "sha256": sha256_hash,
                    "modified_at": mtime.isoformat(),
                })

    return file_records, total_bytes


def create_storage_backup(
    storage_root: Optional[str] = None,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    since: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Executes a persistent file storage backup.
    Returns (archive_path, manifest_dict).
    """
    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            raise ValueError(f"Invalid --since timestamp '{since}'. Use ISO-8601 format (e.g., 2026-11-07T00:00:00Z): {e}")

    storage_parent, sub_roots = resolve_storage_roots(storage_root)
    logger.info("Storage root resolved: %s (scanning sub-roots: %s)", storage_parent, [r[0] for r in sub_roots])

    files_to_backup, total_bytes = scan_storage_files(storage_parent, sub_roots, since_timestamp=since_dt)

    manifest: Dict[str, Any] = {
        "manifest_version": "1.0",
        "backup_type": "storage_files",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "storage_parent": storage_parent,
        "sub_roots": [r[0] for r in sub_roots],
        "since_filter": since_dt.isoformat() if since_dt else None,
        "total_files": len(files_to_backup),
        "total_bytes": total_bytes,
        "files": [
            {
                "path": item["relative_path"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
                "modified_at": item["modified_at"],
            }
            for item in files_to_backup
        ]
    }

    if dry_run:
        logger.info("[DRY-RUN] Manifest generated: %d files, %.2f KB total", len(files_to_backup), total_bytes / 1024)
        for item in files_to_backup:
            logger.info("  [DRY-RUN] %s (%d bytes, sha256=%s...)", item["relative_path"], item["size_bytes"], item["sha256"][:12])
        return "DRY_RUN", manifest

    # Determine destination archive path
    if output_path:
        final_output = os.path.abspath(output_path)
    else:
        target_dir = output_dir or os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage_backups"
        ))
        os.makedirs(target_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        final_output = os.path.join(target_dir, f"brandguard_storage_{ts}.tar.gz")

    # Safety: do not place backup inside live storage parent!
    storage_parent_norm = os.path.abspath(storage_parent)
    final_output_norm = os.path.abspath(final_output)
    if final_output_norm == storage_parent_norm or final_output_norm.startswith(storage_parent_norm + os.sep):
        raise ValueError(
            f"Security violation: Backup destination '{final_output}' must NOT reside inside live storage root '{storage_parent}'."
        )

    # Overwrite protection
    if os.path.exists(final_output) and not force:
        raise FileExistsError(
            f"Backup archive '{final_output}' already exists. Pass --force to overwrite."
        )

    os.makedirs(os.path.dirname(final_output), exist_ok=True)

    # Write archive
    temp_archive = f"{final_output}.tmp_{os.getpid()}"
    try:
        with tarfile.open(temp_archive, "w:gz") as tar:
            # 1. Add manifest.json as the first entry
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            ti = tarfile.TarInfo(name="manifest.json")
            ti.size = len(manifest_bytes)
            ti.mtime = int(datetime.now(timezone.utc).timestamp())
            ti.mode = 0o644
            import io
            tar.addfile(ti, io.BytesIO(manifest_bytes))

            # 2. Add each storage file under its relative path
            for rec in files_to_backup:
                tar.add(
                    rec["absolute_source_path"],
                    arcname=rec["relative_path"],
                    recursive=False,
                )

        # Atomic rename
        if os.path.exists(final_output):
            os.remove(final_output)
        os.rename(temp_archive, final_output)
        logger.info(
            "Storage backup completed: %s (%d files, %.2f KB, archive size: %.2f KB)",
            final_output,
            len(files_to_backup),
            total_bytes / 1024,
            os.path.getsize(final_output) / 1024,
        )
    finally:
        if os.path.exists(temp_archive):
            try:
                os.remove(temp_archive)
            except OSError:
                pass

    return final_output, manifest


def main():
    parser = argparse.ArgumentParser(description="BrandGuard Persistent File Storage Backup Utility")
    parser.add_argument("--storage-root", help="Explicit storage root (default: app.config settings.STORAGE_ROOT)")
    parser.add_argument("-o", "--output", help="Explicit output archive path (.tar.gz)")
    parser.add_argument("--output-dir", help="Directory where timestamped archive will be placed")
    parser.add_argument("--since", help="Incremental backup filter: only files modified since ISO-8601 timestamp")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing archive")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and list candidate files without creating archive")

    args = parser.parse_args()

    try:
        archive_path, manifest = create_storage_backup(
            storage_root=args.storage_root,
            output_path=args.output,
            output_dir=args.output_dir,
            force=args.force,
            dry_run=args.dry_run,
            since=args.since,
        )
        if args.dry_run:
            print("=" * 60)
            print("STORAGE BACKUP [DRY-RUN] SUMMARY:")
            print(f"Total Files: {manifest['total_files']}")
            print(f"Total Bytes: {manifest['total_bytes']} ({manifest['total_bytes']/1024:.2f} KB)")
            print("=" * 60)
        else:
            print(f"SUCCESS: Storage backup archive created at '{archive_path}'")
            print(f"Files bundled: {manifest['total_files']}")
            print(f"Raw data size: {manifest['total_bytes']} bytes ({manifest['total_bytes']/1024:.2f} KB)")
        sys.exit(0)
    except Exception as exc:
        logger.error("Storage backup failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

