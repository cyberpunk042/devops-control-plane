"""
Tests for k8s_wizard — state persistence (save/load/wipe).

These are pure unit tests using tmp_path for filesystem isolation.
No subprocess, no network.
"""

import json
from pathlib import Path

from src.core.services.k8s_wizard import (
    save_wizard_state,
    load_wizard_state,
    wipe_wizard_state,
)


# ═══════════════════════════════════════════════════════════════════
#  save_wizard_state + load_wizard_state
# ═══════════════════════════════════════════════════════════════════


class TestWizardStatePersistence:
    def _valid_state(self, **overrides):
        """Minimal valid state dict."""
        base = {
            "_services": [{"name": "api", "kind": "Deployment", "image": "app:1"}],
            "namespace": "default",
        }
        base.update(overrides)
        return base

    def test_save_load_round_trip(self, tmp_path: Path):
        """save → load round-trip preserves state integrity.

        The fundamental contract: what you save is what you get back.
        """
        state = self._valid_state()
        save_result = save_wizard_state(tmp_path, state)
        assert save_result["ok"] is True

        loaded = load_wizard_state(tmp_path)
        assert loaded["ok"] is True
        assert loaded["_services"][0]["name"] == "api"
        assert loaded["_services"][0]["image"] == "app:1"
        assert loaded["namespace"] == "default"

    def test_load_nonexistent_not_found(self, tmp_path: Path):
        """load on nonexistent file → {ok: False, reason: "not_found"}.

        No crash, no exception — just a clear signal that no saved
        state exists.
        """
        result = load_wizard_state(tmp_path)
        assert result["ok"] is False
        assert result["reason"] == "not_found"

    def test_load_corrupt_json_invalid(self, tmp_path: Path):
        """load on corrupt JSON → {ok: False, reason: "invalid"}.

        The file exists but is not valid JSON — perhaps manually edited
        or corrupted by a disk error.
        """
        state_dir = tmp_path / "k8s"
        state_dir.mkdir()
        (state_dir / ".wizard-state.json").write_text("{not valid json!!!", encoding="utf-8")

        result = load_wizard_state(tmp_path)
        assert result["ok"] is False
        assert result["reason"] == "invalid"

    def test_load_returns_state_merged_with_ok(self, tmp_path: Path):
        """load returns state fields merged with ok: True.

        The loaded dict has the state fields PLUS ok=True at the top level,
        not nested under a 'state' key.
        """
        state = self._valid_state(ingress="app.example.com", skaffold=True)
        save_wizard_state(tmp_path, state)

        loaded = load_wizard_state(tmp_path)
        assert loaded["ok"] is True
        # State fields are at top level, not nested
        assert loaded["ingress"] == "app.example.com"
        assert loaded["skaffold"] is True
        assert "_services" in loaded

    def test_save_creates_k8s_dir(self, tmp_path: Path):
        """save creates k8s/ dir if it doesn't exist.

        First-time wizard save on a project with no k8s/ directory
        should not crash — it creates the directory.
        """
        assert not (tmp_path / "k8s").exists()

        result = save_wizard_state(tmp_path, self._valid_state())
        assert result["ok"] is True
        assert (tmp_path / "k8s").is_dir()
        assert (tmp_path / "k8s" / ".wizard-state.json").is_file()

    def test_save_empty_state_error(self, tmp_path: Path):
        """save with empty state → error.

        A state with neither _services nor _infraDecisions has nothing
        meaningful to persist — saving it would create a useless file.
        """
        result = save_wizard_state(tmp_path, {})
        assert "error" in result

    def test_save_returns_correct_path(self, tmp_path: Path):
        """save returns {ok: True, path: "k8s/.wizard-state.json"}.

        The path is relative to project_root, not absolute.
        """
        result = save_wizard_state(tmp_path, self._valid_state())
        assert result["ok"] is True
        assert result["path"] == "k8s/.wizard-state.json"

    def test_wipe_removes_file(self, tmp_path: Path):
        """wipe removes the state file.

        After wipe, load should return not_found.
        """
        save_wizard_state(tmp_path, self._valid_state())
        assert (tmp_path / "k8s" / ".wizard-state.json").is_file()

        result = wipe_wizard_state(tmp_path)
        assert result["ok"] is True
        assert not (tmp_path / "k8s" / ".wizard-state.json").exists()

    def test_wipe_nonexistent_ok(self, tmp_path: Path):
        """wipe on nonexistent file → ok (no crash).

        Idempotent: wiping when nothing exists is not an error.
        """
        result = wipe_wizard_state(tmp_path)
        assert result["ok"] is True

    def test_sanitization_strips_transient_on_save(self, tmp_path: Path):
        """Sanitization strips transient fields on save.

        Transient fields like _appSvcCount, _infraSvcCount, _configMode,
        action are detection artifacts. They must NOT be persisted because
        they become stale and cause confusion on reload.
        """
        state = self._valid_state(
            _appSvcCount=3,
            _infraSvcCount=1,
            _configMode="multi",
            action="setup",
        )
        # Also add _compose to a service (should be stripped)
        state["_services"][0]["_compose"] = {"build": "."}

        save_wizard_state(tmp_path, state)
        loaded = load_wizard_state(tmp_path)

        assert loaded["ok"] is True
        assert "_appSvcCount" not in loaded
        assert "_infraSvcCount" not in loaded
        assert "_configMode" not in loaded
        assert "action" not in loaded
        assert "_compose" not in loaded["_services"][0]

    def test_core_fields_preserved_through_cycle(self, tmp_path: Path):
        """Core fields preserved through save/load cycle.

        All fields that the wizard frontend needs to rebuild the UI
        must survive the save→sanitize→persist→load cycle.
        """
        state = {
            "_services": [
                {
                    "name": "api",
                    "kind": "Deployment",
                    "image": "app:v2",
                    "port": 8080,
                    "replicas": 3,
                    "envVars": [{"key": "DB", "type": "secret"}],
                    "volumes": [{"name": "data", "type": "pvc-dynamic"}],
                },
            ],
            "_infraDecisions": [
                {"name": "postgres", "kind": "StatefulSet"},
            ],
            "namespace": "production",
            "ingress": "api.example.com",
            "skaffold": True,
            "output_dir": "manifests/prod",
            "mesh": {"provider": "istio"},
        }

        save_wizard_state(tmp_path, state)
        loaded = load_wizard_state(tmp_path)

        assert loaded["ok"] is True
        # Services
        svc = loaded["_services"][0]
        assert svc["name"] == "api"
        assert svc["kind"] == "Deployment"
        assert svc["image"] == "app:v2"
        assert svc["port"] == 8080
        assert svc["replicas"] == 3
        assert svc["envVars"][0]["key"] == "DB"
        assert svc["volumes"][0]["name"] == "data"
        # Infra
        assert loaded["_infraDecisions"][0]["name"] == "postgres"
        assert loaded["_infraDecisions"][0]["kind"] == "StatefulSet"
        # Top-level config
        assert loaded["namespace"] == "production"
        assert loaded["ingress"] == "api.example.com"
        assert loaded["skaffold"] is True
        assert loaded["output_dir"] == "manifests/prod"
        assert loaded["mesh"]["provider"] == "istio"
        # Metadata added by sanitize
        assert "_savedAt" in loaded
        assert loaded["_version"] == 1
