"""
Integration tests for K8s + Skaffold chain (1.8).

Tests how K8s wizard state (services, namespace, manifests) wires
into Skaffold config generation via _generate_skaffold().
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.k8s_wizard_generate import _generate_skaffold

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _gen(data: dict, generated_files: list[dict] | None = None) -> dict:
    """Call _generate_skaffold and return content + parsed YAML."""
    if generated_files is None:
        generated_files = [
            {"path": "k8s/deployment.yaml", "content": "---"},
            {"path": "k8s/service.yaml", "content": "---"},
        ]
    # Ensure skaffold is enabled unless explicitly disabled
    if "skaffold" not in data:
        data["skaffold"] = True
    result = _generate_skaffold(data, generated_files)
    if result is None:
        return {"result": None, "content": "", "parsed": None}
    content = result["content"]
    parsed = yaml.safe_load(content)
    return {"content": content, "parsed": parsed, "result": result}


def _svc(name: str = "api", image: str = "myapp:latest", **kw) -> dict:
    """Build a service dict for _services."""
    base = {"name": name, "image": image, "kind": "Deployment"}
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════
#  1.8 — K8s + Skaffold
# ═══════════════════════════════════════════════════════════════════


class TestK8sManifestsInSkaffold:
    """K8s manifests → Skaffold manifests section."""

    def test_manifests_in_raw_yaml(self):
        """K8s manifests → rawYaml in Skaffold."""
        files = [
            {"path": "k8s/deployment.yaml", "content": "---"},
            {"path": "k8s/service.yaml", "content": "---"},
        ]
        out = _gen({"_services": [_svc()]}, files)
        raw = out["parsed"]["manifests"]["rawYaml"]
        assert "k8s/deployment.yaml" in raw
        assert "k8s/service.yaml" in raw

    def test_manifest_paths_from_generated_files(self):
        """Generated K8s manifest paths → Skaffold manifests.rawYaml."""
        files = [
            {"path": "k8s/ns.yaml", "content": "---"},
            {"path": "k8s/deploy.yaml", "content": "---"},
            {"path": "k8s/svc.yaml", "content": "---"},
        ]
        out = _gen({"_services": [_svc()]}, files)
        raw = out["parsed"]["manifests"]["rawYaml"]
        assert len(raw) == 3

    def test_non_yaml_files_excluded(self):
        """Non-YAML files not in manifests."""
        files = [
            {"path": "k8s/deploy.yaml", "content": "---"},
            {"path": "README.md", "content": "hello"},
            {"path": "k8s/notes.txt", "content": "notes"},
        ]
        out = _gen({"_services": [_svc()]}, files)
        raw = out["parsed"]["manifests"]["rawYaml"]
        assert len(raw) == 1
        assert "k8s/deploy.yaml" in raw

    def test_glob_fallback_when_no_yaml_files(self):
        """No YAML generated files → fallback to k8s/*.yaml glob."""
        out = _gen({"_services": [_svc()], "output_dir": "k8s"}, [])
        raw = out["parsed"]["manifests"]["rawYaml"]
        assert "k8s/*.yaml" in raw


class TestK8sServicesInSkaffold:
    """K8s services → Skaffold build artifacts."""

    def test_service_becomes_artifact(self):
        """K8s service with image → Skaffold build artifact."""
        out = _gen({"_services": [_svc("api", "myapp:latest")]})
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["image"] == "myapp:latest"

    def test_multiple_services_multiple_artifacts(self):
        """Multiple K8s services → multiple Skaffold artifacts."""
        out = _gen({"_services": [
            _svc("api", "myapp-api:latest"),
            _svc("web", "myapp-web:latest"),
            _svc("worker", "myapp-worker:latest"),
        ]})
        artifacts = out["parsed"]["build"]["artifacts"]
        images = [a["image"] for a in artifacts]
        assert len(images) == 3
        assert "myapp-api:latest" in images
        assert "myapp-web:latest" in images
        assert "myapp-worker:latest" in images

    def test_skip_service_excluded(self):
        """Skip-kind service → not in artifacts."""
        out = _gen({"_services": [
            _svc("api", "myapp:latest"),
            _svc("skip-me", "skip:latest", kind="Skip"),
        ]})
        artifacts = out["parsed"]["build"]["artifacts"]
        images = [a["image"] for a in artifacts]
        assert "myapp:latest" in images
        assert "skip:latest" not in images

    def test_service_without_image_excluded(self):
        """Service without image → not in artifacts."""
        out = _gen({"_services": [
            _svc("api", "myapp:latest"),
            {"name": "noimg", "kind": "Deployment", "image": ""},
        ]})
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 1

    def test_dockerfile_override(self):
        """Dockerfile field flows → artifact docker.dockerfile."""
        out = _gen({"_services": [
            _svc("api", "myapp:latest", dockerfile="Dockerfile.prod"),
        ]})
        art = out["parsed"]["build"]["artifacts"][0]
        assert art["docker"]["dockerfile"] == "Dockerfile.prod"

    def test_build_args_flow(self):
        """Build args → artifact docker.buildArgs."""
        out = _gen({"_services": [
            _svc("api", "myapp:latest", buildArgs={"NODE_ENV": "production"}),
        ]})
        art = out["parsed"]["build"]["artifacts"][0]
        assert art["docker"]["buildArgs"] == {"NODE_ENV": "production"}

    def test_build_target_flows(self):
        """Build target → artifact docker.target."""
        out = _gen({"_services": [
            _svc("api", "myapp:latest", buildTarget="runtime"),
        ]})
        art = out["parsed"]["build"]["artifacts"][0]
        assert art["docker"]["target"] == "runtime"


class TestK8sNamespaceInSkaffold:
    """K8s namespace → Skaffold deploy config."""

    def test_namespace_in_default_namespace(self):
        """K8s namespace → Skaffold deploy.kubectl.defaultNamespace."""
        out = _gen({"_services": [_svc()], "namespace": "prod"})
        kubectl = out["parsed"]["deploy"]["kubectl"]
        assert kubectl["defaultNamespace"] == "prod"

    def test_namespace_in_global_flags(self):
        """K8s namespace → --namespace in flags.global."""
        out = _gen({"_services": [_svc()], "namespace": "prod"})
        flags = out["parsed"]["deploy"]["kubectl"]["flags"]["global"]
        assert "--namespace" in flags
        assert "prod" in flags

    def test_no_namespace_no_flags(self):
        """No namespace → no defaultNamespace or namespace flag."""
        out = _gen({"_services": [_svc()]})
        kubectl = out["parsed"]["deploy"]["kubectl"]
        assert "defaultNamespace" not in kubectl
        assert "flags" not in kubectl or "global" not in kubectl.get("flags", {})


class TestSkaffoldControl:
    """Skaffold enable/disable and config options."""

    def test_disabled_returns_none(self):
        """skaffold=False → returns None."""
        out = _gen({"skaffold": False, "_services": [_svc()]})
        assert out["result"] is None

    def test_no_services_no_build(self):
        """No services with images → no build section."""
        out = _gen({"_services": []})
        assert "build" not in out["parsed"]

    def test_tag_policy_git_commit(self):
        """tagPolicy=gitCommit → build.tagPolicy.gitCommit."""
        out = _gen({"_services": [_svc()], "tagPolicy": "gitCommit"})
        tp = out["parsed"]["build"]["tagPolicy"]
        assert "gitCommit" in tp

    def test_tag_policy_sha256(self):
        """tagPolicy=sha256 → build.tagPolicy.sha256."""
        out = _gen({"_services": [_svc()], "tagPolicy": "sha256"})
        tp = out["parsed"]["build"]["tagPolicy"]
        assert "sha256" in tp

    def test_valid_yaml(self):
        """Generated Skaffold YAML is valid."""
        out = _gen({"_services": [_svc()]})
        assert out["parsed"] is not None
        assert out["parsed"]["apiVersion"] == "skaffold/v4beta11"
        assert out["parsed"]["kind"] == "Config"


class TestDeployStrategies:
    """Different deploy strategies wire correctly."""

    def test_kubectl_strategy(self):
        """deployStrategy=kubectl → deploy.kubectl present."""
        out = _gen({"_services": [_svc()], "deployStrategy": "kubectl"})
        assert "kubectl" in out["parsed"]["deploy"]

    def test_helm_strategy(self):
        """deployStrategy=helm → deploy.helm.releases present."""
        out = _gen({"_services": [_svc()], "deployStrategy": "helm"})
        assert "helm" in out["parsed"]["deploy"]
        assert "releases" in out["parsed"]["deploy"]["helm"]

    def test_kustomize_strategy(self):
        """deployStrategy=kustomize → manifests.kustomize.paths present."""
        out = _gen({"_services": [_svc()], "deployStrategy": "kustomize"})
        assert "kustomize" in out["parsed"]["manifests"]
        assert "paths" in out["parsed"]["manifests"]["kustomize"]
