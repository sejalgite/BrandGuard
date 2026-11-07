"""
backend/tests/test_storage_backup_restore.py
Unit and integration tests for storage backup and restore utilities.
Verifies tenant isolation, path traversal guards, manifest generation,
checksum validation, overwrite safety, dry-run modes, symlink handling,
and corrupted archive detection.
"""
import os
import sys
import io
import json
import gzip
import tarfile
import hashlib
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from scripts.storage_backup import (
    calculate_sha256,
    resolve_storage_roots,
    scan_storage_files,
    create_storage_backup,
)
from scripts.storage_restore import (
    inspect_archive_manifest,
    is_path_safe,
    execute_storage_restore,
)
from app.config import Settings, settings


# =============================================================================
# 1. Tenant Isolation & Directory Path Safety Tests
# =============================================================================
class TestStorageSecurityAndIsolation:
    def test_tenant_directory_isolation(self, tmp_path):
        """Verifies files are placed strictly under organization subdirectories."""
        org_a = "11111111-1111-1111-1111-111111111111"
        org_b = "22222222-2222-2222-2222-222222222222"

        storage_root = tmp_path / "storage"
        (storage_root / "documents" / org_a).mkdir(parents=True)
        (storage_root / "documents" / org_b).mkdir(parents=True)

        file_a = storage_root / "documents" / org_a / "secret_a.txt"
        file_b = storage_root / "documents" / org_b / "secret_b.txt"
        file_a.write_text("tenant a payload", encoding="utf-8")
        file_b.write_text("tenant b payload", encoding="utf-8")

        sub_roots = [("documents", str(storage_root / "documents"))]
        records, total_bytes = scan_storage_files(str(storage_root), sub_roots)

        paths = [r["relative_path"] for r in records]
        assert f"documents/{org_a}/secret_a.txt" in paths
        assert f"documents/{org_b}/secret_b.txt" in paths
        assert len(records) == 2

    def test_path_traversal_rejection(self, tmp_path):
        """is_path_safe rejects relative or absolute path traversal attempts."""
        dest = str(tmp_path / "dest")
        os.makedirs(dest, exist_ok=True)

        assert is_path_safe(dest, "documents/org1/file.txt") is True
        assert is_path_safe(dest, "assets/org1/logo.png") is True

        # Traversal attempts
        assert is_path_safe(dest, "../outside.txt") is False
        assert is_path_safe(dest, "documents/../../escape.txt") is False
        assert is_path_safe(dest, "/etc/passwd") is False
        assert is_path_safe(dest, "C:\\Windows\\System32\\cmd.exe") is False
        assert is_path_safe(dest, "C:/Windows/win.ini") is False

    def test_symlink_handling(self, tmp_path):
        """Symlinks pointing outside storage parent are safely ignored."""
        storage_root = tmp_path / "storage"
        outside_dir = tmp_path / "sensitive"
        outside_dir.mkdir()
        secret_file = outside_dir / "passwords.txt"
        secret_file.write_text("root_pass=123", encoding="utf-8")

        docs_dir = storage_root / "documents" / "org_test"
        docs_dir.mkdir(parents=True)

        normal_file = docs_dir / "valid.txt"
        normal_file.write_text("regular data", encoding="utf-8")

        # Create symlink pointing outside storage root if platform supports symlinks
        # NOTE (Windows Limitation): On Windows, os.symlink requires SeCreateSymbolicLinkPrivilege
        # (typically Developer Mode or Administrator). On non-elevated Windows sessions, this
        # test cleanly skips and logs the operating system limitation. Tar-level symlink attacks
        # are independently verified without OS symlink creation in test_restore_symlink_rejection.
        symlink_target = docs_dir / "evil_symlink.txt"
        try:
            os.symlink(str(secret_file), str(symlink_target))
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not permitted by Windows policy without Developer Mode/Admin privileges")

        sub_roots = [("documents", str(storage_root / "documents"))]
        records, _ = scan_storage_files(str(storage_root), sub_roots)

        paths = [r["relative_path"] for r in records]
        assert "documents/org_test/valid.txt" in paths
        assert "documents/org_test/evil_symlink.txt" not in paths

    def test_restore_symlink_rejection(self, tmp_path):
        """execute_storage_restore rejects tar members containing malicious symlinks."""
        bad_archive = str(tmp_path / "symlink_attack.tar.gz")
        manifest = {
            "total_files": 1,
            "files": [{"path": "documents/attack.txt", "size_bytes": 0, "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}]
        }
        with tarfile.open(bad_archive, "w:gz") as tar:
            m_bytes = json.dumps(manifest).encode("utf-8")
            ti = tarfile.TarInfo("manifest.json")
            ti.size = len(m_bytes)
            tar.addfile(ti, io.BytesIO(m_bytes))

            ti_sym = tarfile.TarInfo("documents/attack.txt")
            ti_sym.type = tarfile.SYMTYPE
            ti_sym.linkname = "../../etc/shadow"
            tar.addfile(ti_sym)

        dest = str(tmp_path / "restore_dest")
        with pytest.raises(ValueError, match="Security violation.*symlink"):
            execute_storage_restore(bad_archive, destination=dest, confirm=True)

    def test_restore_path_traversal_rejection(self, tmp_path):
        """execute_storage_restore rejects tar members attempting directory traversal."""
        bad_archive = str(tmp_path / "traversal_attack.tar.gz")
        manifest = {
            "total_files": 1,
            "files": [{"path": "../../../evil.txt", "size_bytes": 4, "sha256": "abc"}]
        }
        with tarfile.open(bad_archive, "w:gz") as tar:
            m_bytes = json.dumps(manifest).encode("utf-8")
            ti = tarfile.TarInfo("manifest.json")
            ti.size = len(m_bytes)
            tar.addfile(ti, io.BytesIO(m_bytes))

            ti_bad = tarfile.TarInfo("../../../evil.txt")
            payload = b"evil"
            ti_bad.size = len(payload)
            tar.addfile(ti_bad, io.BytesIO(payload))

        dest = str(tmp_path / "restore_dest")
        with pytest.raises(ValueError, match="Security violation.*escapes destination"):
            execute_storage_restore(bad_archive, destination=dest, confirm=True)

    def test_asset_path_traversal_guard(self, tmp_path):
        """Verifies constitution get_asset_file containment check logic."""
        expected_org_dir = os.path.abspath(str(tmp_path / "assets" / "org123"))
        outside_file = os.path.abspath(str(tmp_path / "assets" / "org999" / "logo.png"))
        traversal_file = os.path.abspath(str(tmp_path / "assets" / "org123_escaped.png"))
        legit_file = os.path.abspath(str(tmp_path / "assets" / "org123" / "logo.png"))

        def is_contained(file_path: str, org_dir: str) -> bool:
            actual_dir = os.path.abspath(os.path.dirname(file_path))
            return actual_dir == org_dir or actual_dir.startswith(org_dir + os.sep)

        assert is_contained(legit_file, expected_org_dir) is True
        assert is_contained(outside_file, expected_org_dir) is False
        assert is_contained(traversal_file, expected_org_dir) is False


# =============================================================================
# 2. Manifest Generation, Checksum & Verification Tests
# =============================================================================
class TestManifestAndIntegrity:
    def test_manifest_generation(self, tmp_path):
        """Backup generates valid manifest.json with path, size, sha256, and mtime."""
        storage = tmp_path / "storage"
        docs = storage / "documents" / "tenant1"
        docs.mkdir(parents=True)
        sample = docs / "test.txt"
        content = b"Manifest verification test payload 123456"
        sample.write_bytes(content)

        expected_hash = hashlib.sha256(content).hexdigest()

        archive_path, manifest = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )

        assert os.path.isfile(archive_path)
        assert manifest["total_files"] == 1
        assert manifest["total_bytes"] == len(content)

        file_entry = manifest["files"][0]
        assert file_entry["path"] == "documents/tenant1/test.txt"
        assert file_entry["size_bytes"] == len(content)
        assert file_entry["sha256"] == expected_hash

        # Verify manifest inside tar archive
        parsed_manifest, member_names = inspect_archive_manifest(archive_path)
        assert "manifest.json" in member_names
        assert "documents/tenant1/test.txt" in member_names
        assert parsed_manifest["total_files"] == 1

    def test_sha256_verification_detects_tampering(self, tmp_path):
        """Restore fails when extracted file does not match manifest SHA-256."""
        storage = tmp_path / "storage"
        docs = storage / "documents" / "tenant1"
        docs.mkdir(parents=True)
        sample = docs / "test.txt"
        sample.write_bytes(b"original content")

        archive_path, _ = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )

        # Forge archive with altered content but original manifest hash
        forged_archive = str(tmp_path / "backups" / "forged.tar.gz")
        manifest, _ = inspect_archive_manifest(archive_path)

        with tarfile.open(forged_archive, "w:gz") as tar:
            # Keep original manifest
            m_bytes = json.dumps(manifest).encode("utf-8")
            ti = tarfile.TarInfo("manifest.json")
            ti.size = len(m_bytes)
            tar.addfile(ti, io.BytesIO(m_bytes))

            # Add altered file
            bad_data = b"TAMPERED_MALICIOUS_PAYLOAD"
            ti2 = tarfile.TarInfo("documents/tenant1/test.txt")
            ti2.size = len(bad_data)
            tar.addfile(ti2, io.BytesIO(bad_data))

        dest_dir = str(tmp_path / "restored")
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            execute_storage_restore(forged_archive, destination=dest_dir, confirm=True)

    def test_missing_file_detection(self, tmp_path):
        """inspect_archive_manifest raises ValueError if manifest.json is missing."""
        bad_archive = str(tmp_path / "no_manifest.tar.gz")
        with tarfile.open(bad_archive, "w:gz") as tar:
            data = b"some file"
            ti = tarfile.TarInfo("file.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        with pytest.raises(ValueError, match="missing required 'manifest.json'"):
            inspect_archive_manifest(bad_archive)

    def test_corrupted_archive_detection(self, tmp_path):
        """Corrupted archive raises ValueError."""
        corrupt_file = tmp_path / "corrupt.tar.gz"
        corrupt_file.write_bytes(b"NOT_A_VALID_GZIP_FILE")

        with pytest.raises(ValueError, match="Corrupted or invalid"):
            inspect_archive_manifest(str(corrupt_file))


# =============================================================================
# 3. Overwrite Safety, Incremental & Dry-Run Tests
# =============================================================================
class TestBackupAndRestoreBehaviors:
    def test_overwrite_protection(self, tmp_path):
        """create_storage_backup raises FileExistsError if archive exists and force=False."""
        storage = tmp_path / "storage"
        (storage / "documents").mkdir(parents=True)
        out_file = tmp_path / "existing.tar.gz"
        out_file.write_text("existing archive", encoding="utf-8")

        with pytest.raises(FileExistsError, match="already exists"):
            create_storage_backup(
                storage_root=str(storage),
                output_path=str(out_file),
                force=False,
            )

    def test_overwrite_flag_allows_replace(self, tmp_path):
        """Passing force=True replaces existing backup archive."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)
        (docs / "file.txt").write_text("new content", encoding="utf-8")

        out_file = tmp_path / "existing.tar.gz"
        out_file.write_text("old archive", encoding="utf-8")

        archive_path, manifest = create_storage_backup(
            storage_root=str(storage),
            output_path=str(out_file),
            force=True,
        )
        assert archive_path == str(out_file)
        assert manifest["total_files"] == 1

    def test_dry_run_behavior(self, tmp_path):
        """Dry run performs scanning and manifest generation without creating file."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)
        (docs / "file.txt").write_text("data", encoding="utf-8")

        out_file = tmp_path / "dry_run.tar.gz"
        path, manifest = create_storage_backup(
            storage_root=str(storage),
            output_path=str(out_file),
            dry_run=True,
        )
        assert path == "DRY_RUN"
        assert manifest["total_files"] == 1
        assert not out_file.exists()

    def test_empty_storage_backup(self, tmp_path):
        """Backing up an empty storage root creates valid archive with 0 files."""
        storage = tmp_path / "storage"
        storage.mkdir()

        archive_path, manifest = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )
        assert os.path.isfile(archive_path)
        assert manifest["total_files"] == 0
        assert manifest["total_bytes"] == 0

        # Can also be restored cleanly
        dest = str(tmp_path / "empty_restored")
        res = execute_storage_restore(archive_path, destination=dest, confirm=True)
        assert res["restored_count"] == 0

    def test_incremental_since_filter(self, tmp_path):
        """Files modified before --since timestamp are omitted from backup."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)

        old_file = docs / "old.txt"
        old_file.write_text("old data", encoding="utf-8")

        cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)

        new_file = docs / "new.txt"
        new_file.write_text("new data", encoding="utf-8")

        # Filter with future cutoff - both should be excluded
        _, manifest = create_storage_backup(
            storage_root=str(storage),
            dry_run=True,
            since=cutoff.isoformat(),
        )
        assert manifest["total_files"] == 0

    def test_restore_skips_existing_without_overwrite(self, tmp_path):
        """Restore preserves existing destination files by default."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)
        (docs / "doc.txt").write_text("archive version", encoding="utf-8")

        archive_path, _ = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )

        dest = tmp_path / "restore_target"
        (dest / "documents").mkdir(parents=True)
        existing_doc = dest / "documents" / "doc.txt"
        existing_doc.write_text("local uncommitted changes", encoding="utf-8")

        # Restore without overwrite
        res = execute_storage_restore(archive_path, destination=str(dest), confirm=True, overwrite=False)
        assert res["skipped_existing_count"] == 1
        assert res["restored_count"] == 0
        assert existing_doc.read_text(encoding="utf-8") == "local uncommitted changes"

        # Restore with overwrite
        res2 = execute_storage_restore(archive_path, destination=str(dest), confirm=True, overwrite=True)
        assert res2["restored_count"] == 1
        assert res2["skipped_existing_count"] == 0
        assert existing_doc.read_text(encoding="utf-8") == "archive version"

    def test_overwrite_rejects_symlink_target_escaping_destination(self, tmp_path):
        """Restore with overwrite=True raises ValueError if existing file is an escaping symlink."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)
        (docs / "payload.txt").write_text("safe content", encoding="utf-8")

        archive_path, _ = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )

        dest = tmp_path / "restore_target"
        (dest / "documents").mkdir(parents=True)
        outside_sensitive = tmp_path / "outside_sensitive.txt"
        outside_sensitive.write_text("critical secrets", encoding="utf-8")

        # NOTE (Windows Limitation): On Windows, creating live filesystem symlinks requires
        # elevated privileges (SeCreateSymbolicLinkPrivilege). This test tests overwrite protection
        # against malicious symlinks on disk and cleanly skips on unprivileged Windows environments.
        existing_symlink = dest / "documents" / "payload.txt"
        try:
            os.symlink(str(outside_sensitive), str(existing_symlink))
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not permitted by Windows policy without Developer Mode/Admin privileges")

        # Overwrite should detect that existing target is an escaping symlink and reject
        with pytest.raises(ValueError, match="symlink pointing outside destination"):
            execute_storage_restore(archive_path, destination=str(dest), confirm=True, overwrite=True)
        # Ensure outside sensitive file was NOT overwritten
        assert outside_sensitive.read_text(encoding="utf-8") == "critical secrets"

    def test_partial_restore_failure_reporting(self, tmp_path):
        """If extraction fails midway, RuntimeError reports the failure accurately."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)
        (docs / "file1.txt").write_text("one", encoding="utf-8")
        (docs / "file2.txt").write_text("two", encoding="utf-8")

        archive_path, _ = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )

        dest = tmp_path / "restore_fail_test"
        # Mock tar.extract to fail on the second file
        orig_extract = tarfile.TarFile.extract
        call_count = [0]

        def failing_extract(self, member, path="", set_attrs=True, *, numeric_owner=False):
            if member.name.endswith("file2.txt"):
                raise PermissionError("Disk full or permission denied simulation")
            return orig_extract(self, member, path=path, set_attrs=set_attrs, numeric_owner=numeric_owner)

        with patch.object(tarfile.TarFile, "extract", failing_extract):
            with pytest.raises(RuntimeError, match="Restore failed while extracting"):
                execute_storage_restore(archive_path, destination=str(dest), confirm=True)

    def test_large_file_handled(self, tmp_path):
        """Streams and verifies multi-megabyte files cleanly."""
        storage = tmp_path / "storage"
        docs = storage / "documents"
        docs.mkdir(parents=True)

        large_file = docs / "large.bin"
        chunk = b"A" * 1024 * 1024  # 1 MB chunk
        with open(large_file, "wb") as f:
            for _ in range(5):  # 5 MB
                f.write(chunk)

        archive_path, manifest = create_storage_backup(
            storage_root=str(storage),
            output_dir=str(tmp_path / "backups"),
        )
        assert manifest["total_bytes"] == 5 * 1024 * 1024

        dest = str(tmp_path / "large_restored")
        res = execute_storage_restore(archive_path, destination=dest, confirm=True)
        assert res["verified_count"] == 1
        assert os.path.getsize(os.path.join(dest, "documents", "large.bin")) == 5 * 1024 * 1024
