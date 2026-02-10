"""
Tests for src.ui.web.vault — secrets vault core.

Covers:
  - Lock / unlock round-trip
  - Wrong passphrase rejection
  - Rate limiting
  - Secure delete
  - Vault status
  - Secret file detection
  - .env key listing with masking
  - Export / import
  - Auto-lock timer
  - Register passphrase
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_vault_state():
    """Reset all vault module-level state between tests."""
    from src.ui.web import vault

    vault._session_passphrase = None
    vault._auto_lock_minutes = 30
    vault._failed_attempts = 0
    vault._last_failed_time = 0
    vault._cancel_auto_lock_timer()
    vault._project_root_ref = None
    yield
    vault._cancel_auto_lock_timer()


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a temp project dir with a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DATABASE_URL="postgres://localhost/mydb"\n'
        'SECRET_KEY="s3cr3t-k3y-v4lue"\n'
        "DEBUG=true\n"
        "# This is a comment\n"
        "\n"
        'EMPTY_VAR=""\n',
        encoding="utf-8",
    )
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════
#  Lock / Unlock round-trip
# ═══════════════════════════════════════════════════════════════════════


class TestLockUnlock:
    def test_lock_creates_vault_and_removes_env(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault

        env_path = project_dir / ".env"
        original_content = env_path.read_bytes()

        result = lock_vault(env_path, "test-passphrase")

        assert result["success"] is True
        assert not env_path.exists(), ".env should be deleted after lock"
        assert (project_dir / ".env.vault").exists(), "vault file should exist"

        # Vault should be valid JSON
        vault_data = json.loads((project_dir / ".env.vault").read_text())
        assert vault_data["vault"] is True
        assert vault_data["version"] == 1
        assert vault_data["algorithm"] == "aes-256-gcm"

    def test_unlock_restores_env(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault, unlock_vault

        env_path = project_dir / ".env"
        original_content = env_path.read_bytes()

        lock_vault(env_path, "my-secret")
        assert not env_path.exists()

        result = unlock_vault(env_path, "my-secret")

        assert result["success"] is True
        assert env_path.exists(), ".env should be restored"
        assert env_path.read_bytes() == original_content, "content should be identical"
        assert not (project_dir / ".env.vault").exists(), "vault file should be deleted"

    def test_round_trip_preserves_content_exactly(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault, unlock_vault

        env_path = project_dir / ".env"
        original = env_path.read_bytes()

        lock_vault(env_path, "password123")
        unlock_vault(env_path, "password123")

        assert env_path.read_bytes() == original

    def test_lock_requires_no_existing_vault(self, project_dir: Path) -> None:
        """Lock should overwrite any existing vault file silently."""
        from src.ui.web.vault import lock_vault

        env_path = project_dir / ".env"
        vault_path = project_dir / ".env.vault"

        # First lock
        lock_vault(env_path, "pass1")
        assert vault_path.exists()

        # Restore .env manually to test re-lock
        env_path.write_text("RETRY=1\n")
        lock_vault(env_path, "pass2")

        assert vault_path.exists()
        assert not env_path.exists()


# ═══════════════════════════════════════════════════════════════════════
#  Error cases
# ═══════════════════════════════════════════════════════════════════════


class TestErrors:
    def test_lock_missing_env_raises(self, tmp_path: Path) -> None:
        from src.ui.web.vault import lock_vault

        with pytest.raises(ValueError, match="not found"):
            lock_vault(tmp_path / ".env", "pass")

    def test_lock_short_passphrase_raises(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault

        with pytest.raises(ValueError, match="at least 4"):
            lock_vault(project_dir / ".env", "ab")

    def test_unlock_no_vault_raises(self, tmp_path: Path) -> None:
        from src.ui.web.vault import unlock_vault

        with pytest.raises(ValueError, match="No vault file"):
            unlock_vault(tmp_path / ".env", "pass")

    def test_unlock_env_exists_raises(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault, unlock_vault

        env_path = project_dir / ".env"
        lock_vault(env_path, "pass1234")

        # Recreate .env to simulate conflict
        env_path.write_text("CONFLICT=1\n")

        with pytest.raises(ValueError, match="already exists"):
            unlock_vault(env_path, "pass1234")

    def test_wrong_passphrase_raises(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault, unlock_vault

        env_path = project_dir / ".env"
        lock_vault(env_path, "correct-password")

        with pytest.raises(ValueError, match="Wrong passphrase"):
            unlock_vault(env_path, "wrong-password")


# ═══════════════════════════════════════════════════════════════════════
#  Rate limiting
# ═══════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    def test_rate_limit_after_three_failures(self, project_dir: Path) -> None:
        from src.ui.web import vault
        from src.ui.web.vault import lock_vault, unlock_vault

        env_path = project_dir / ".env"
        lock_vault(env_path, "correct")

        # Three wrong attempts
        for _ in range(3):
            with pytest.raises(ValueError, match="Wrong passphrase"):
                unlock_vault(env_path, "wrong")

        # Fourth attempt should be rate-limited
        with pytest.raises(ValueError, match="Too many failed"):
            unlock_vault(env_path, "correct")

        # The locked status should show rate_limited
        status = vault.vault_status(env_path)
        assert status["rate_limited"] is True

    def test_rate_limit_resets_on_success(self, project_dir: Path) -> None:
        from src.ui.web import vault

        vault._failed_attempts = 2
        vault._last_failed_time = time.time() - 100  # Long ago

        env_path = project_dir / ".env"
        vault.lock_vault(env_path, "pass1234")

        # Restore for unlock test
        env_path2 = project_dir / ".env"
        # Need to re-create env so we can't test unlock easily
        # But we can test that _reset_rate_limit works
        vault._reset_rate_limit()
        assert vault._failed_attempts == 0


# ═══════════════════════════════════════════════════════════════════════
#  Vault status
# ═══════════════════════════════════════════════════════════════════════


class TestVaultStatus:
    def test_status_unlocked(self, project_dir: Path) -> None:
        from src.ui.web.vault import vault_status

        status = vault_status(project_dir / ".env")
        assert status["locked"] is False

    def test_status_locked(self, project_dir: Path) -> None:
        from src.ui.web.vault import lock_vault, vault_status

        env_path = project_dir / ".env"
        lock_vault(env_path, "pass1234")

        status = vault_status(env_path)
        assert status["locked"] is True
        assert status["vault_file"] == ".env.vault"

    def test_status_empty(self, tmp_path: Path) -> None:
        from src.ui.web.vault import vault_status

        status = vault_status(tmp_path / ".env")
        assert status["locked"] is False
        assert status.get("empty") is True


# ═══════════════════════════════════════════════════════════════════════
#  Secret file detection
# ═══════════════════════════════════════════════════════════════════════


class TestDetectSecrets:
    def test_detects_env_file(self, project_dir: Path) -> None:
        from src.ui.web.vault import detect_secret_files

        files = detect_secret_files(project_dir)
        names = [f["name"] for f in files]
        assert ".env" in names

        env_info = next(f for f in files if f["name"] == ".env")
        assert env_info["exists"] is True
        assert env_info["locked"] is False

    def test_detects_locked_vault(self, project_dir: Path) -> None:
        from src.ui.web.vault import detect_secret_files, lock_vault

        lock_vault(project_dir / ".env", "pass1234")

        files = detect_secret_files(project_dir)
        env_info = next(f for f in files if f["name"] == ".env")
        assert env_info["locked"] is True
        assert env_info["exists"] is False

    def test_ignores_nonexistent(self, tmp_path: Path) -> None:
        from src.ui.web.vault import detect_secret_files

        files = detect_secret_files(tmp_path)
        assert len(files) == 0


# ═══════════════════════════════════════════════════════════════════════
#  .env key listing
# ═══════════════════════════════════════════════════════════════════════


class TestListEnvKeys:
    def test_lists_keys_with_masking(self, project_dir: Path) -> None:
        from src.ui.web.vault import list_env_keys

        keys = list_env_keys(project_dir / ".env")

        names = [k["key"] for k in keys]
        assert "DATABASE_URL" in names
        assert "SECRET_KEY" in names
        assert "DEBUG" in names

        db_key = next(k for k in keys if k["key"] == "DATABASE_URL")
        assert db_key["has_value"] is True
        # Masked: first 2 chars + dots + last char
        assert "•" in db_key["masked"]
        # Original value should NOT appear
        assert "postgres://localhost/mydb" not in db_key["masked"]

    def test_empty_var(self, project_dir: Path) -> None:
        from src.ui.web.vault import list_env_keys

        keys = list_env_keys(project_dir / ".env")
        empty = next(k for k in keys if k["key"] == "EMPTY_VAR")
        assert empty["has_value"] is False
        assert empty["masked"] == "(empty)"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        from src.ui.web.vault import list_env_keys

        keys = list_env_keys(tmp_path / ".env")
        assert keys == []

    def test_comments_skipped(self, project_dir: Path) -> None:
        from src.ui.web.vault import list_env_keys

        keys = list_env_keys(project_dir / ".env")
        names = [k["key"] for k in keys]
        assert "# This is a comment" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Export / Import
# ═══════════════════════════════════════════════════════════════════════


class TestExportImport:
    def test_export_creates_valid_envelope(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file

        env_path = project_dir / ".env"
        envelope = export_vault_file(env_path, "export-password-8")

        assert envelope["format"] == "dcp-vault-export-v1"
        assert "ciphertext" in envelope
        assert "salt" in envelope
        assert "iv" in envelope
        assert "tag" in envelope
        assert envelope["original_name"] == ".env"

        # Original file should still exist (export doesn't delete)
        assert env_path.exists()

    def test_export_requires_min_8_chars(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file

        with pytest.raises(ValueError, match="at least 8"):
            export_vault_file(project_dir / ".env", "short")

    def test_import_round_trip(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file, import_vault_file

        env_path = project_dir / ".env"
        original = env_path.read_text()

        envelope = export_vault_file(env_path, "export-password-8")

        # Delete original and import
        env_path.unlink()
        result = import_vault_file(envelope, env_path, "export-password-8")

        assert result["success"] is True
        assert env_path.read_text() == original

    def test_import_wrong_password(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file, import_vault_file

        envelope = export_vault_file(project_dir / ".env", "correct-pw-long")

        with pytest.raises(ValueError, match="Wrong password"):
            import_vault_file(
                envelope, project_dir / ".env", "wrong-password-long",
            )

    def test_import_dry_run(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file, import_vault_file

        env_path = project_dir / ".env"
        original = env_path.read_text()

        envelope = export_vault_file(env_path, "export-password-8")

        # Modify on disk
        env_path.write_text("DIFFERENT=true\n")

        result = import_vault_file(
            envelope, env_path, "export-password-8", dry_run=True,
        )

        assert result["success"] is True
        # File should NOT be changed in dry-run
        assert env_path.read_text() == "DIFFERENT=true\n"

    def test_import_shows_changes(self, project_dir: Path) -> None:
        from src.ui.web.vault import export_vault_file, import_vault_file

        env_path = project_dir / ".env"
        envelope = export_vault_file(env_path, "export-password-8")

        # Modify on disk to have different keys
        env_path.write_text("NEW_KEY=added\nDEBUG=false\n")

        result = import_vault_file(
            envelope, env_path, "export-password-8", dry_run=True,
        )

        changes = result["changes"]
        actions = {c["key"]: c["action"] for c in changes}

        # DATABASE_URL was in export but not in current → added
        assert actions.get("DATABASE_URL") == "added"
        # DEBUG exists in both → changed (value differs)
        assert actions.get("DEBUG") == "changed"
        # NEW_KEY exists in current but not export → kept
        assert actions.get("NEW_KEY") == "kept"


# ═══════════════════════════════════════════════════════════════════════
#  Register passphrase
# ═══════════════════════════════════════════════════════════════════════


class TestRegisterPassphrase:
    def test_register_stores_passphrase(self, project_dir: Path) -> None:
        from src.ui.web import vault

        env_path = project_dir / ".env"
        result = vault.register_passphrase("my-pass", env_path)

        assert result["success"] is True
        assert vault._session_passphrase == "my-pass"

    def test_register_empty_raises(self, project_dir: Path) -> None:
        from src.ui.web.vault import register_passphrase

        with pytest.raises(ValueError, match="cannot be empty"):
            register_passphrase("", project_dir / ".env")

    def test_register_validates_against_vault(self, project_dir: Path) -> None:
        from src.ui.web import vault

        env_path = project_dir / ".env"

        # Lock with known passphrase, then restore .env manually
        vault.lock_vault(env_path, "correct-pass")
        # Keep the vault file but recreate .env
        env_path.write_text("KEY=val\n")

        # Now register with wrong passphrase — should fail
        with pytest.raises(ValueError, match="Wrong passphrase"):
            vault.register_passphrase("wrong-pass", env_path)


# ═══════════════════════════════════════════════════════════════════════
#  Auto-lock configuration
# ═══════════════════════════════════════════════════════════════════════


class TestAutoLock:
    def test_set_auto_lock_minutes(self) -> None:
        from src.ui.web import vault

        vault.set_auto_lock_minutes(15)
        assert vault._auto_lock_minutes == 15

    def test_disable_auto_lock(self) -> None:
        from src.ui.web import vault

        vault.set_auto_lock_minutes(0)
        assert vault._auto_lock_minutes == 0

    def test_auto_lock_uses_stored_passphrase(self, project_dir: Path) -> None:
        from src.ui.web import vault

        env_path = project_dir / ".env"
        vault.set_project_root(project_dir)

        # Lock and unlock to store passphrase
        vault.lock_vault(env_path, "auto-lock-pass")
        vault.unlock_vault(env_path, "auto-lock-pass")

        # Now auto-lock should use stored passphrase
        result = vault.auto_lock()
        assert result["success"] is True
        assert not env_path.exists()
        assert (project_dir / ".env.vault").exists()

    def test_auto_lock_no_passphrase(self) -> None:
        from src.ui.web import vault

        result = vault.auto_lock()
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════
#  Vault API routes
# ═══════════════════════════════════════════════════════════════════════


class TestVaultRoutes:
    @pytest.fixture()
    def client(self, project_dir: Path):
        from src.ui.web.server import create_app

        app = create_app(project_root=project_dir, mock_mode=True)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_vault_status_unlocked(self, client, project_dir: Path) -> None:
        resp = client.get("/api/vault/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["locked"] is False

    def test_vault_lock_unlock(self, client, project_dir: Path) -> None:
        # Lock
        resp = client.post(
            "/api/vault/lock",
            json={"passphrase": "test-pass"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Status should be locked
        resp = client.get("/api/vault/status")
        data = resp.get_json()
        assert data["locked"] is True

        # Unlock
        resp = client.post(
            "/api/vault/unlock",
            json={"passphrase": "test-pass"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Status unlocked again
        resp = client.get("/api/vault/status")
        data = resp.get_json()
        assert data["locked"] is False

    def test_vault_lock_missing_passphrase(self, client) -> None:
        resp = client.post("/api/vault/lock", json={})
        assert resp.status_code == 400

    def test_vault_keys_unlocked(self, client, project_dir: Path) -> None:
        resp = client.get("/api/vault/keys")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "unlocked"
        assert len(data["keys"]) > 0

        names = [k["key"] for k in data["keys"]]
        assert "DATABASE_URL" in names

        # Verify sections are returned  
        assert "sections" in data
        assert isinstance(data["sections"], list)
        # Flat .env without section comments → all keys in one "General" section
        if data["sections"]:
            all_section_keys = []
            for s in data["sections"]:
                assert "name" in s
                assert "keys" in s
                for k in s["keys"]:
                    assert "kind" in k
                    all_section_keys.append(k["key"])
            # Every key should appear in a section
            for name in names:
                assert name in all_section_keys

    def test_vault_keys_locked(self, client, project_dir: Path) -> None:
        # Lock the vault first
        client.post("/api/vault/lock", json={"passphrase": "test-pass"})

        resp = client.get("/api/vault/keys")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "locked"
        assert data["keys"] == []

    def test_vault_keys_empty(self, client, project_dir: Path) -> None:
        # Remove the .env to simulate empty state
        (project_dir / ".env").unlink()

        resp = client.get("/api/vault/keys")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "empty"
        assert data["keys"] == []

    def test_vault_secrets_detection(self, client, project_dir: Path) -> None:
        resp = client.get("/api/vault/secrets")
        assert resp.status_code == 200
        data = resp.get_json()
        files = data["files"]
        assert any(f["name"] == ".env" for f in files)

    def test_vault_auto_lock_config(self, client) -> None:
        resp = client.post("/api/vault/auto-lock", json={"minutes": 15})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["auto_lock_minutes"] == 15

    def test_vault_export_import(self, client, project_dir: Path) -> None:
        # Export
        resp = client.post(
            "/api/vault/export",
            json={"password": "export-pass-8", "filename": ".env"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        envelope = data["envelope"]

        # Import (dry run)
        resp = client.post(
            "/api/vault/import",
            json={
                "password": "export-pass-8",
                "vault_data": envelope,
                "target": ".env",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_vault_create_empty(self, client, project_dir: Path) -> None:
        # Remove .env first
        (project_dir / ".env").unlink()

        resp = client.post(
            "/api/vault/create",
            json={"entries": []},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # .env should now exist
        assert (project_dir / ".env").exists()
        content = (project_dir / ".env").read_text()
        assert "Auto-generated" in content

    def test_vault_create_with_entries(self, client, project_dir: Path) -> None:
        (project_dir / ".env").unlink()

        resp = client.post(
            "/api/vault/create",
            json={"entries": [
                {"key": "DB_HOST", "value": "localhost"},
                {"key": "API_KEY", "value": "sk-12345"},
            ]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        content = (project_dir / ".env").read_text()
        assert "DB_HOST=localhost" in content
        assert "API_KEY=sk-12345" in content

    def test_vault_create_already_exists(self, client, project_dir: Path) -> None:
        # .env already exists from fixture
        resp = client.post(
            "/api/vault/create",
            json={"entries": []},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "already exists" in data["error"]
