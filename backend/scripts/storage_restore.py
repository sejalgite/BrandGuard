#!/usr/bin/env python3
"""
backend/scripts/storage_restore.py
Production-grade filesystem restore and verification utility for BrandGuard documents and brand assets.

Features:
- Restores a storage archive (.tar.gz) produced by storage_backup.py into an explicit target directory.
- Strict path traversal prevention: ensures every extracted member resolves strictly inside the destination root.
- Symlink attack protection: rejects tar members containing symlinks or hard links pointing outside destination.
- Cryptographic verification: verifies extracted file sizes and SHA-256 checksums against manifest.json.
- Safe overwrite policies: skips existing files by default unless --overwrite is explicitly passed.
- Safe dry-run mode: checks archive readability, verifies manifest entries, and reports potential actions without writing files.
- Mandatory confirmation guard: requires --confirm in non-interactive/automation scripts or interactive approval.
- Detailed post-restore audit report: counts restored, skipped, verified, and mismatched files.
"""
import os
import sys
import json
import gzip
import tarfile
import hashlib
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple, Set

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("brandguard.storage_restore")


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


def inspect_archive_manifest(archive_path: str) -> Tuple[Dict[str, Any], List[str]]:
    """
    Opens the archive and reads the embedded manifest.json.
    Returns (manifest_dict, list_of_tar_member_names).
    """
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    if os.path.getsize(archive_path) == 0:
        raise ValueError(f"Backup archive is empty (0 bytes): {archive_path}")

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            member_names = tar.getnames()
            if "manifest.json" not in member_names:
                raise ValueError("Archive is missing required 'manifest.json' header.")

            manifest_file = tar.extractfile("manifest.json")
            if not manifest_file:
                raise ValueError("Could not read 'manifest.json' from archive.")

            manifest = json.loads(manifest_file.read().decode("utf-8"))
            return manifest, member_names
    except tarfile.TarError as e:
        raise ValueError(f"Corrupted or invalid tar.gz archive: {e}")


def is_path_safe(destination_root: str, member_name: str) -> bool:
    """
    Verifies that the target path does not escape the destination directory.
    Resolves any symlinks present in parent directories to prevent symlink traversal.
    Rejects absolute paths and path traversal ('../').
    """
    dest_norm = os.path.realpath(os.path.abspath(destination_root))
    # Reject leading slashes or Windows drive letters
    if os.path.isabs(member_name) or (len(member_name) > 1 and member_name[1] == ":"):
        return False

    target_path = os.path.abspath(os.path.join(dest_norm, member_name))
    # Check logical path containment first
    if not (target_path == dest_norm or target_path.startswith(dest_norm + os.sep)):
        return False

    # Also verify real canonical path if the file or parent directory already exists
    # (to prevent symlink escape via pre-existing symlinks in the destination)
    check_dir = target_path
    while check_dir and check_dir != dest_norm:
        if os.path.exists(check_dir):
            real_check = os.path.realpath(check_dir)
            if not (real_check == dest_norm or real_check.startswith(dest_norm + os.sep)):
                return False
            break
        parent = os.path.dirname(check_dir)
        if parent == check_dir:
            break
        check_dir = parent

    return True


def execute_storage_restore(
    archive_path: str,
    destination: str,
    confirm: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
    create_destination: bool = True,
) -> Dict[str, Any]:
    """
    Restores and verifies files from archive_path into destination.
    """
    manifest, member_names = inspect_archive_manifest(archive_path)
    dest_abs = os.path.abspath(destination)

    logger.info("Validated archive manifest: %d files registered, created at %s", manifest.get("total_files", 0), manifest.get("created_at"))
    logger.info("Target destination: %s", dest_abs)

    if not os.path.exists(dest_abs):
        if create_destination:
            if not dry_run:
                os.makedirs(dest_abs, exist_ok=True)
        else:
            raise FileNotFoundError(f"Destination directory '{dest_abs}' does not exist.")

    # Guard confirmation
    if not dry_run and not confirm:
        if sys.stdin.isatty():
            print("=" * 70)
            print("WARNING: FILE RESTORATION MAY OVERWRITE OR MODIFY TARGET DIRECTORIES.")
            print(f"Archive:     {archive_path}")
            print(f"Destination: {dest_abs}")
            print(f"Files:       {manifest.get('total_files')}")
            print("=" * 70)
            val = input("Type 'RESTORE' to proceed: ")
            if val.strip() != "RESTORE":
                raise PermissionError("Restoration aborted: user confirmation failed.")
        else:
            raise PermissionError("Restoration requires explicit confirmation. Pass '--confirm' in non-interactive environments.")

    manifest_map = {f["path"]: f for f in manifest.get("files", [])}

    restored_files: List[str] = []
    skipped_existing: List[str] = []
    verified_files: List[str] = []
    checksum_mismatches: List[str] = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "manifest.json":
                continue

            # Security 1: Traversal check
            if not is_path_safe(dest_abs, member.name):
                raise ValueError(f"Security violation: Archive member '{member.name}' escapes destination root.")

            # Security 2: Symlink / hardlink check
            if member.issym() or member.islnk():
                link_target = member.linkname
                resolved_link = os.path.abspath(os.path.join(dest_abs, os.path.dirname(member.name), link_target))
                if not (resolved_link == dest_abs or resolved_link.startswith(dest_abs + os.sep)):
                    raise ValueError(f"Security violation: Archive member symlink '{member.name}' points outside destination: {link_target}")

            target_path = os.path.join(dest_abs, member.name)

            if member.isdir():
                if not dry_run and not os.path.exists(target_path):
                    os.makedirs(target_path, exist_ok=True)
                continue

            # Check if file already exists
            if os.path.exists(target_path):
                # Ensure the existing target path is not a symlink escaping destination before overwriting
                if os.path.islink(target_path):
                    real_existing = os.path.realpath(target_path)
                    if not (real_existing == dest_abs or real_existing.startswith(dest_abs + os.sep)):
                        raise ValueError(f"Security violation: Existing target '{member.name}' is a symlink pointing outside destination.")
                if not overwrite:
                    skipped_existing.append(member.name)
                    logger.info("Skipping existing file (pass --overwrite to replace): %s", member.name)
                    continue

            if dry_run:
                restored_files.append(member.name)
                continue

            # Extract member safely
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                tar.extract(member, path=dest_abs, set_attrs=False)
                restored_files.append(member.name)
            except Exception as extract_err:
                logger.error("Extraction error for member '%s': %s", member.name, extract_err)
                raise RuntimeError(
                    f"Restore failed while extracting '{member.name}': {extract_err}. "
                    f"Partially extracted {len(restored_files)} of {len(manifest_map)} files before failure."
                ) from extract_err

            # Cryptographic checksum verification against manifest
            manifest_info = manifest_map.get(member.name)
            if manifest_info:
                actual_sha = calculate_sha256(target_path)
                actual_size = os.path.getsize(target_path)

                if actual_sha == manifest_info["sha256"] and actual_size == manifest_info["size_bytes"]:
                    verified_files.append(member.name)
                else:
                    checksum_mismatches.append(member.name)
                    logger.error(
                        "Checksum/size mismatch for %s: expected sha256=%s size=%d; got sha256=%s size=%d",
                        member.name, manifest_info["sha256"], manifest_info["size_bytes"], actual_sha, actual_size
                    )
            else:
                logger.warning("Extracted file %s not found in manifest file index.", member.name)

    status_str = "dry_run" if dry_run else ("success" if not checksum_mismatches else "checksum_error")

    result = {
        "status": status_str,
        "archive": archive_path,
        "destination": dest_abs,
        "total_in_manifest": len(manifest_map),
        "restored_count": len(restored_files),
        "skipped_existing_count": len(skipped_existing),
        "verified_count": len(verified_files),
        "mismatch_count": len(checksum_mismatches),
        "mismatches": checksum_mismatches,
    }

    if checksum_mismatches:
        raise RuntimeError(f"Storage restoration detected {len(checksum_mismatches)} checksum mismatch(es)!")

    return result


def main():
    parser = argparse.ArgumentParser(description="BrandGuard Persistent File Storage Restore Utility")
    parser.add_argument("-f", "--file", required=True, help="Path to backup archive (.tar.gz)")
    parser.add_argument("-d", "--destination", required=True, help="Target restore directory")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation for non-interactive restore")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files in destination")
    parser.add_argument("--dry-run", action="store_true", help="Verify archive and preview restore without writing")
    parser.add_argument("--no-create", dest="create_dest", action="store_false", help="Fail if destination directory does not exist")

    args = parser.parse_args()

    try:
        summary = execute_storage_restore(
            archive_path=args.file,
            destination=args.destination,
            confirm=args.confirm,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            create_destination=args.create_dest,
        )
        print("=" * 60)
        if args.dry_run:
            print("STORAGE RESTORE [DRY-RUN] VERIFIED:")
            print(f"Files to restore:   {summary['restored_count']}")
            print(f"Files to skip:      {summary['skipped_existing_count']}")
        else:
            print("STORAGE RESTORE: SUCCESS")
            print(f"Files restored:     {summary['restored_count']}")
            print(f"Files verified SHA: {summary['verified_count']}")
            print(f"Files skipped:      {summary['skipped_existing_count']}")
        print(f"Target directory:   {summary['destination']}")
        print("=" * 60)
        sys.exit(0)
    except Exception as exc:
        logger.error("Restore failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

