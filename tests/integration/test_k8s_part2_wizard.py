"""
Integration tests — K8s domain Part 2: Wizard state, translator, wizard generate.

TDD: requirements for the wizard state machine that drives the Configure step.
This is the hardest part — translate user choices into K8s resources.

Covers:
  - State persistence (load/save/wipe)
  - State sanitization
  - Wizard state → resource translation (services, env, volumes, PVCs, ConfigMaps, Secrets)
  - Wizard generate (resources → YAML files)
  - Pod builder (probes, volumes, env vars, mesh annotations)
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ═══════════════════════════════════════════════════════════════════
#  1. STATE PERSISTENCE — save/load/wipe wizard state
# ═══════════════════════════════════════════════════════════════════


class TestWizardStatePersistence:
    """Wizard state must survive across sessions via JSON file."""

    def test_save_and_load(self, tmp_path: Path):
        from src.core.services.k8s_wizard import save_wizard_state, load_wizard_state
        state = {
            "namespace": "prod",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2},
            ],
        }
        save_result = save_wizard_state(tmp_path, state)
        assert save_result["ok"] is True

        load_result = load_wizard_state(tmp_path)
        assert load_result["ok"] is True
        assert load_result["namespace"] == "prod"
        assert len(load_result["_services"]) == 1

    def test_load_nonexistent(self, tmp_path: Path):
        from src.core.services.k8s_wizard import load_wizard_state
        r = load_wizard_state(tmp_path)
        assert r["ok"] is False
        assert r["reason"] == "not_found"

    def test_wipe(self, tmp_path: Path):
        from src.core.services.k8s_wizard import save_wizard_state, wipe_wizard_state, load_wizard_state
        save_wizard_state(tmp_path, {"namespace": "test"})
        wipe_wizard_state(tmp_path)
        r = load_wizard_state(tmp_path)
        assert r["ok"] is False

    def test_save_creates_k8s_dir(self, tmp_path: Path):
        """save must create k8s/ dir if it doesn't exist."""
        from src.core.services.k8s_wizard import save_wizard_state
        save_wizard_state(tmp_path, {"namespace": "test", "_services": [{"name": "x"}]})
        assert (tmp_path / "k8s").is_dir()

    def test_load_corrupt_json(self, tmp_path: Path):
        """Corrupt state file → graceful error, not crash."""
        from src.core.services.k8s_wizard import load_wizard_state
        k = tmp_path / "k8s"; k.mkdir()
        (k / ".wizard-state.json").write_text("{broken json")
        r = load_wizard_state(tmp_path)
        assert r["ok"] is False
        assert r["reason"] == "invalid"


class TestWizardStateSanitization:
    """_sanitize_state must strip transient/detection fields."""

    def test_strips_transient_fields(self, tmp_path: Path):
        from src.core.services.k8s_wizard import save_wizard_state, load_wizard_state
        state = {
            "namespace": "prod",
            "_services": [{"name": "api"}],
            # Transient fields that should NOT be persisted
            "action": "save",
            "_appServices": ["api"],
            "_infraServices": [],
            "_classifiedModules": [],
        }
        save_wizard_state(tmp_path, state)
        loaded = load_wizard_state(tmp_path)
        assert "action" not in loaded
        assert "_appServices" not in loaded
        assert "_infraServices" not in loaded
        assert "_classifiedModules" not in loaded

    def test_preserves_core_fields(self, tmp_path: Path):
        from src.core.services.k8s_wizard import save_wizard_state, load_wizard_state
        state = {
            "namespace": "prod",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [{"name": "DB_HOST", "value": "db"}],
                    "volumes": [{"name": "data", "mountPath": "/data", "type": "emptyDir"}],
                },
            ],
            "ingress": "api.example.com",
            "skaffold": True,
        }
        save_wizard_state(tmp_path, state)
        loaded = load_wizard_state(tmp_path)
        assert loaded["namespace"] == "prod"
        assert loaded["_services"][0]["name"] == "api"
        assert loaded["_services"][0]["replicas"] == 2
        assert loaded.get("ingress") == "api.example.com"


# ═══════════════════════════════════════════════════════════════════
#  2. STATE TRANSLATOR — wizard state → K8s resources
# ═══════════════════════════════════════════════════════════════════


class TestWizardStateTranslator:
    """wizard_state_to_resources must convert user choices into resource list."""

    def test_single_service_produces_deployment_and_service(self):
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Deployment" in kinds
        assert "Service" in kinds

    def test_multiple_services(self):
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2, "envVars": [], "volumes": []},
                {"name": "web", "image": "web:v1", "port": 3000, "replicas": 1, "envVars": [], "volumes": []},
                {"name": "worker", "image": "worker:v1", "port": 9000, "replicas": 3, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        deployments = [r for r in resources if r["kind"] == "Deployment"]
        services = [r for r in resources if r["kind"] == "Service"]
        assert len(deployments) == 3
        assert len(services) == 3

    def test_env_vars_produce_configmap(self):
        """Service with plain env vars → ConfigMap resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_HOST", "value": "db.local", "type": "hardcoded"},
                        {"key": "LOG_LEVEL", "value": "info", "type": "hardcoded"},
                    ],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "ConfigMap" in kinds

    def test_secret_env_vars_produce_secret(self):
        """Service with secret env vars → Secret resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_PASSWORD", "value": "secret123", "type": "secret"},
                    ],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Secret" in kinds

    def test_pvc_volumes_produce_pvc_resources(self):
        """Service with PVC volumes → PersistentVolumeClaim resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [
                        {
                            "name": "pgdata",
                            "mountPath": "/var/lib/postgresql/data",
                            "type": "pvc-dynamic",
                            "size": "10Gi",
                            "storageClass": "standard",
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "PersistentVolumeClaim" in kinds

    def test_namespace_resource_created(self):
        """Non-default namespace → Namespace resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "production",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Namespace" in kinds

    def test_default_namespace_no_namespace_resource(self):
        """namespace='default' → no Namespace resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Namespace" not in kinds

    def test_ingress_resource_created(self):
        """ingress host set → Ingress resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "ingress": "api.example.com",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Ingress" in kinds

    def test_no_ingress_without_host(self):
        """ingress empty → no Ingress resource."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "ingress": "",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Ingress" not in kinds

    def test_all_resources_have_namespace(self):
        """Every resource must have namespace field set."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "staging",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        for r in resources:
            assert r.get("namespace") == "staging", f"{r['kind']} missing namespace"


# ═══════════════════════════════════════════════════════════════════
#  3. POD BUILDER — low-level pod template construction
# ═══════════════════════════════════════════════════════════════════


class TestPodBuilder:
    """Pod builder must produce correct container specs."""

    def test_build_probe_http(self):
        from src.core.services.k8s_pod_builder import _build_probe
        probe = _build_probe({"type": "http", "path": "/health", "port": 8080})
        assert probe["httpGet"]["path"] == "/health"
        assert probe["httpGet"]["port"] == 8080

    def test_build_probe_tcp(self):
        from src.core.services.k8s_pod_builder import _build_probe
        probe = _build_probe({"type": "tcp", "port": 5432})
        assert probe["tcpSocket"]["port"] == 5432

    def test_build_probe_exec(self):
        from src.core.services.k8s_pod_builder import _build_probe
        probe = _build_probe({"type": "exec", "command": "pg_isready"})
        # exec wraps the command in ["sh", "-c", cmd]
        assert probe["exec"]["command"][0] == "sh"

    def test_build_env_vars_plain(self):
        from src.core.services.k8s_pod_builder import _build_env_vars
        env = [{"name": "FOO", "value": "bar", "type": "plain"}]
        result = _build_env_vars(env, svc_name="svc")
        # Should produce a list of K8s env entries
        assert any(e.get("name") == "FOO" for e in result)

    def test_build_wizard_volume_emptydir(self):
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {"name": "cache", "mountPath": "/cache", "type": "emptyDir"}
        volume, mount = _build_wizard_volume(vol, 0, "svc")
        assert volume["name"] == "cache"
        assert "emptyDir" in volume
        assert mount["mountPath"] == "/cache"

    def test_build_wizard_volume_pvc(self):
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {"name": "data", "mountPath": "/data", "type": "pvc-dynamic", "claimName": "data-pvc"}
        volume, mount = _build_wizard_volume(vol, 0, "svc")
        assert "persistentVolumeClaim" in volume
        assert mount["mountPath"] == "/data"

    def test_build_pod_template(self):
        """Full pod template from service config."""
        from src.core.services.k8s_generate import _build_pod_template
        spec = {
            "image": "api:v1",
            "port": 8080,
            "replicas": 2,
            "env": [{"name": "DB_HOST", "value": "db"}],
            "volumes": [{"name": "cache", "emptyDir": {}}],
            "volumeMounts": [{"name": "cache", "mountPath": "/cache"}],
        }
        template = _build_pod_template("api", spec)
        assert "spec" in template
        containers = template["spec"]["containers"]
        assert len(containers) >= 1
        assert containers[0]["image"] == "api:v1"

    def test_mesh_annotations(self):
        """Service mesh → annotations added."""
        from src.core.services.k8s_pod_builder import _build_mesh_annotations
        annotations = _build_mesh_annotations({"provider": "istio", "port": 8080, "enabled": True})
        assert len(annotations) > 0

    def test_api_version_for_kind(self):
        from src.core.services.k8s_pod_builder import _api_version_for_kind
        assert _api_version_for_kind("Deployment") == "apps/v1"
        assert _api_version_for_kind("Service") == "v1"
        assert _api_version_for_kind("Ingress") == "networking.k8s.io/v1"
        assert _api_version_for_kind("ConfigMap") == "v1"
        assert _api_version_for_kind("Secret") == "v1"
        assert _api_version_for_kind("PersistentVolumeClaim") == "v1"


# ═══════════════════════════════════════════════════════════════════
#  4. WIZARD GENERATE — resources → YAML files on disk
# ═══════════════════════════════════════════════════════════════════


class TestWizardGenerate:
    """generate_k8s_wizard must produce YAML files from resource list."""

    def test_basic_generation(self, tmp_path: Path):
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True
        assert len(result["files"]) >= 2  # Deployment + Service at minimum

    def test_generated_files_are_valid_yaml(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        for f in result["files"]:
            content = f.get("content", "")
            doc = yaml.safe_load(content)
            assert doc is not None
            assert "kind" in doc
            assert "apiVersion" in doc

    def test_multi_service_generation(self, tmp_path: Path):
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "prod",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2, "envVars": [], "volumes": []},
                {"name": "web", "image": "web:v1", "port": 3000, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True
        # At least 2 Deployments + 2 Services + 1 Namespace
        assert len(result["files"]) >= 5

    def test_with_env_vars_generates_configmap(self, tmp_path: Path):
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_HOST", "value": "db.local", "type": "hardcoded"},
                    ],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        file_contents = " ".join(f.get("content", "") for f in result["files"])
        assert "ConfigMap" in file_contents

    def test_skaffold_generation(self, tmp_path: Path):
        """skaffold=True → skaffold.yaml generated."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard, _generate_skaffold

        state = {
            "namespace": "default",
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)

        skaffold = _generate_skaffold(state, result["files"])
        assert skaffold is not None
        assert "apiVersion" in skaffold.get("content", "") or "apiVersion" in str(skaffold)


# ═══════════════════════════════════════════════════════════════════
#  5. FULL WIZARD ROUND-TRIP
# ═══════════════════════════════════════════════════════════════════


class TestWizardRoundTrip:
    """Save state → translate → generate → detect → validate: all consistent."""

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_full_round_trip(self, _m, tmp_path: Path):
        from src.core.services.k8s_wizard import (
            save_wizard_state, load_wizard_state,
            wizard_state_to_resources,
        )
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard
        from src.core.services.k8s_detect import k8s_status
        from src.core.services.k8s_validate import validate_manifests

        # 1. Save wizard state
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2, "envVars": [], "volumes": []},
            ],
        }
        save_wizard_state(tmp_path, state)

        # 2. Load and translate
        loaded = load_wizard_state(tmp_path)
        assert loaded["ok"] is True
        resources = wizard_state_to_resources(loaded)

        # 3. Generate YAML files
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True

        # 4. Write files to disk
        for f in result["files"]:
            fp = tmp_path / f["path"]
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f["content"])

        # 5. Detect — must find the generated resources
        status = k8s_status(tmp_path)
        assert status["has_k8s"] is True
        assert status["total_resources"] >= 2

        # 6. Validate — generated manifests must pass
        v = validate_manifests(tmp_path)
        assert v["ok"] is True
        assert v["errors"] == 0
