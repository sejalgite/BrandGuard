"""
backend/tests/test_backup_restore.py
Unit and integration tests for database backup and restore scripts.
Verifies command construction, credential masking, error handling, validation,
table counting (DDL vs DATA), and safety guards against destructive operations.
"""
import os
import sys
import tempfile
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from scripts.backup_db import (
    parse_db_url,
    build_dump_command,
    validate_backup,
    execute_backup,
    find_pg_tool,
    EXPECTED_BRANDGUARD_TABLES,
)
from scripts.restore_db import (
    build_restore_command,
    validate_backup_file,
    execute_restore,
)


# =============================================================================
# 1. Database URL Parsing & Credential Redaction Tests
# =============================================================================
class TestDatabaseURLParsing:
    def test_parse_standard_url(self):
        url = "postgresql://brandguard_user:secret_pass123@localhost:5435/brandguard"
        conn = parse_db_url(url)
        assert conn["user"] == "brandguard_user"
        assert conn["password"] == "secret_pass123"
        assert conn["host"] == "localhost"
        assert conn["port"] == "5435"
        assert conn["dbname"] == "brandguard"
        assert "secret_pass123" not in conn["redacted_url"]
        assert "*****" in conn["redacted_url"]

    def test_parse_url_encoded_password(self):
        url = "postgresql://my_user:p%40ss%23word@db.host.internal:5432/my_db"
        conn = parse_db_url(url)
        assert conn["user"] == "my_user"
        assert conn["password"] == "p@ss#word"
        assert conn["host"] == "db.host.internal"
        assert conn["port"] == "5432"
        assert conn["dbname"] == "my_db"
        assert "p@ss#word" not in conn["redacted_url"]

    def test_parse_invalid_scheme(self):
        with pytest.raises(ValueError, match="Invalid database scheme"):
            parse_db_url("mysql://root:pass@localhost:3306/db")

        with pytest.raises(ValueError, match="Invalid database scheme"):
            parse_db_url("sqlite:///db.sqlite3")

    def test_parse_missing_dbname(self):
        with pytest.raises(ValueError, match="Database name is missing"):
            parse_db_url("postgresql://user:pass@localhost:5432/")

    def test_parse_empty_url(self):
        with pytest.raises(ValueError, match="must be a non-empty string"):
            parse_db_url("")


# =============================================================================
# 2. Backup Command Construction & Tool Discovery Tests
# =============================================================================
class TestBackupCommandConstruction:
    def test_dump_command_args_isolation(self):
        """Verifies pg_dump arguments and ensures password is NOT in the CLI arguments."""
        conn_info = {
            "user": "brandguard_user",
            "password": "SuperConfidentialPassword99!",
            "host": "127.0.0.1",
            "port": "5435",
            "dbname": "brandguard",
            "redacted_url": "postgresql://brandguard_user:*****@127.0.0.1:5435/brandguard",
        }
        cmd = build_dump_command("pg_dump", conn_info, "out.dump")

        assert cmd[0] == "pg_dump"
        assert "-h" in cmd and "127.0.0.1" in cmd
        assert "-p" in cmd and "5435" in cmd
        assert "-U" in cmd and "brandguard_user" in cmd
        assert "-d" in cmd and "brandguard" in cmd
        assert "-Fc" in cmd
        assert "--no-owner" in cmd
        assert "--no-privileges" in cmd
        assert "-f" in cmd and "out.dump" in cmd

        # Strict credential check: password must never appear in command line arguments
        assert "SuperConfidentialPassword99!" not in " ".join(cmd)

    def test_restore_command_args_isolation(self):
        """Verifies pg_restore arguments and ensures password is NOT in CLI arguments."""
        conn_info = {
            "user": "brandguard_user",
            "password": "SuperConfidentialPassword99!",
            "host": "127.0.0.1",
            "port": "5435",
            "dbname": "brandguard",
            "redacted_url": "postgresql://brandguard_user:*****@127.0.0.1:5435/brandguard",
        }
        cmd = build_restore_command("pg_restore", conn_info, "backup.dump", clean=True)

        assert cmd[0] == "pg_restore"
        assert "-h" in cmd and "127.0.0.1" in cmd
        assert "-p" in cmd and "5435" in cmd
        assert "-U" in cmd and "brandguard_user" in cmd
        assert "-d" in cmd and "brandguard" in cmd
        assert "--no-owner" in cmd
        assert "--no-privileges" in cmd
        assert "--clean" in cmd
        assert "--if-exists" in cmd
        assert "backup.dump" == cmd[-1]

        assert "SuperConfidentialPassword99!" not in " ".join(cmd)

    def test_find_pg_tool_with_custom_env(self, tmp_path, monkeypatch):
        fake_bin = tmp_path / "custom_pg_bin"
        fake_bin.mkdir()
        fake_tool = fake_bin / ("pg_dump.exe" if sys.platform == "win32" else "pg_dump")
        fake_tool.write_text("#!/bin/sh\necho 1", encoding="utf-8")
        if sys.platform != "win32":
            os.chmod(str(fake_tool), 0o755)

        monkeypatch.setenv("PG_BIN_DIR", str(fake_bin))
        found = find_pg_tool("pg_dump")
        assert found == str(fake_tool)


# =============================================================================
# 3. Validation & Safety Failure Handling Tests
# =============================================================================
class TestBackupValidationAndSafety:
    def test_missing_backup_utility_raises_error(self, monkeypatch):
        monkeypatch.setattr("scripts.backup_db.find_pg_tool", lambda tool: None)
        with pytest.raises(FileNotFoundError, match="pg_dump utility not found"):
            execute_backup(db_url="postgresql://user:pass@localhost:5432/db")

    def test_missing_database_url_raises_error(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with patch("app.config.settings", MagicMock(DATABASE_URL=None)):
            with pytest.raises(ValueError, match="DATABASE_URL must be specified"):
                execute_backup(db_url=None)

    def test_backup_collision_without_force_raises_error(self, tmp_path):
        existing_file = tmp_path / "brandguard_backup.dump"
        existing_file.write_text("existing data", encoding="utf-8")

        with patch("scripts.backup_db.find_pg_tool", return_value="pg_dump"):
            with pytest.raises(FileExistsError, match="already exists"):
                execute_backup(
                    db_url="postgresql://user:pass@localhost:5432/db",
                    output_path=str(existing_file),
                    force=False,
                )

    def test_validate_backup_empty_file_fails(self, tmp_path):
        empty_file = tmp_path / "empty.dump"
        empty_file.write_bytes(b"")

        with pytest.raises(ValueError, match="is empty"):
            validate_backup(str(empty_file))

    def test_validate_backup_missing_file_fails(self, tmp_path):
        non_existent = str(tmp_path / "does_not_exist.dump")
        with pytest.raises(FileNotFoundError, match="not found"):
            validate_backup(non_existent)

    def test_validate_backup_corrupted_toc_fails(self, tmp_path):
        corrupt_file = tmp_path / "corrupt.dump"
        corrupt_file.write_bytes(b"NOT_A_VALID_POSTGRES_DUMP_HEADER")

        mock_proc = MagicMock(returncode=1, stderr="pg_restore: error: did not find magic string in header")
        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="pg_restore -l failed to read backup TOC"):
                validate_backup(str(corrupt_file), pg_restore_path="pg_restore")

    def test_validate_backup_distinguishes_ddl_and_data_tables(self, tmp_path):
        """Verifies TOC parsing distinguishes DDL schema definitions and table data entries."""
        dump_file = tmp_path / "sample.dump"
        dump_file.write_bytes(b"dummy dump")

        sample_toc = (
            "1; 1259 1001 TABLE public users brandguard_user\n"
            "2; 0 1001 TABLE DATA public users brandguard_user\n"
            "3; 1259 1002 TABLE public alembic_version brandguard_user\n"
            "4; 0 1002 TABLE DATA public alembic_version brandguard_user\n"
            "5; 3079 1003 EXTENSION - vector\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=sample_toc)

        with patch("subprocess.run", return_value=mock_proc):
            val = validate_backup(str(dump_file), pg_restore_path="pg_restore")
            assert val["unique_table_count"] == 2
            assert val["total_toc_table_entries"] == 4
            assert val["has_alembic"] is True
            assert val["has_vector"] is True

    def test_credential_redaction_on_subprocess_failure(self):
        """Verifies that if pg_dump fails, the exception message masks the password."""
        mock_proc = MagicMock(
            returncode=2,
            stderr="FATAL: password authentication failed for user 'user' with secret_pass_12345"
        )
        with patch("scripts.backup_db.find_pg_tool", return_value="pg_dump"), \
             patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError) as exc_info:
                execute_backup(
                    db_url="postgresql://user:secret_pass_12345@localhost:5432/db",
                    output_path="test.dump",
                    force=True,
                )
            assert "secret_pass_12345" not in str(exc_info.value)
            assert "******" in str(exc_info.value)


# =============================================================================
# 4. Restore Confirmation & Safeguards Tests
# =============================================================================
class TestRestoreSafetyGuards:
    def test_restore_rejected_without_explicit_confirmation(self, tmp_path):
        valid_dump = tmp_path / "valid.dump"
        valid_dump.write_bytes(b"fake dump data")

        with patch("scripts.restore_db.validate_backup_file", return_value={"unique_table_count": 26, "total_toc_table_entries": 52, "has_alembic": True, "has_vector": True}), \
             patch("scripts.restore_db.find_pg_tool", return_value="pg_restore"), \
             patch("sys.stdin.isatty", return_value=False):
            with pytest.raises(PermissionError, match="Destructive restore requires explicit confirmation"):
                execute_restore(
                    backup_path=str(valid_dump),
                    db_url="postgresql://user:pass@localhost:5432/dev_test_db",
                    confirm=False,
                )

    def test_restore_production_safeguard_requires_confirm_database(self, tmp_path):
        """Restoring into production/brandguard database requires --confirm-database <dbname>."""
        valid_dump = tmp_path / "valid.dump"
        valid_dump.write_bytes(b"fake dump data")

        with patch("scripts.restore_db.validate_backup_file", return_value={"unique_table_count": 26, "total_toc_table_entries": 52, "has_alembic": True, "has_vector": True}), \
             patch("scripts.restore_db.find_pg_tool", return_value="pg_restore"), \
             patch("sys.stdin.isatty", return_value=False):
            # Attempt restore with --confirm but without --confirm-database brandguard
            with pytest.raises(PermissionError, match="CRITICAL SAFEGUARD"):
                execute_restore(
                    backup_path=str(valid_dump),
                    db_url="postgresql://user:pass@localhost:5432/brandguard",
                    confirm=True,
                    confirm_database=None,
                )

    def test_restore_fails_if_backup_missing_core_tables(self, tmp_path):
        dump_file = tmp_path / "partial.dump"
        dump_file.write_bytes(b"partial dump data")

        # Mock pg_restore -l returning TOC without alembic_version
        mock_toc = "1; 1259 1000 TABLE public some_table user\n"
        mock_proc = MagicMock(returncode=0, stdout=mock_toc)

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(ValueError, match="missing core tables"):
                validate_backup_file(str(dump_file), pg_restore_path="pg_restore")

    def test_restore_missing_utility_raises_error(self, tmp_path, monkeypatch):
        fake_file = tmp_path / "fake.dump"
        fake_file.write_bytes(b"data")
        monkeypatch.setattr("scripts.restore_db.find_pg_tool", lambda tool: None)

        with pytest.raises(FileNotFoundError, match="pg_restore utility not found"):
            execute_restore(backup_path=str(fake_file), db_url="postgresql://user:pass@localhost:5432/db", confirm=True)
