"""
Integration tests — K8s domain Part 1: Detection, Validation, Generation.

TDD: requirements for the finished K8s integration.
K8s is too large for one file — split into parts:
  Part 1: detect, validate, generate (this file)
  Part 2: wizard state, translator, wizard generate
  Part 3: cluster ops, helm, kubectl, scaling, events, logs
  Part 4: cross-integration (K8s ↔ Docker, K8s ↔ CI/CD)
"""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


_NO_KUBECTL = patch(
    "src.core.services.k8s_detect._kubectl_available",
    return_value={"available": False, "version": None},
)


# ═══════════════════════════════════════════════════════════════════
#  1. DETECTION — find all K8s resources in a project
# ═══════════════════════════════════════════════════════════════════


class TestK8sDetectManifests:
    """k8s_status must find YAML manifests, Helm charts, Kustomize."""

    # ── Manifest directory scanning ─────────────────────────────

    @_NO_KUBECTL
    def test_finds_manifests_in_k8s_dir(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "k8s"; k.mkdir()
        (k / "deploy.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: web
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: web
              template:
                metadata:
                  labels:
                    app: web
                spec:
                  containers:
                    - name: web
                      image: web:v1
        """))
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is True
        assert r["total_resources"] >= 1
        assert len(r["manifests"]) >= 1

    @_NO_KUBECTL
    def test_finds_manifests_in_kubernetes_dir(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "kubernetes"; k.mkdir()
        (k / "svc.yaml").write_text(textwrap.dedent("""\
            apiVersion: v1
            kind: Service
            metadata:
              name: web
            spec:
              ports:
                - port: 80
        """))
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is True

    @_NO_KUBECTL
    def test_finds_manifests_in_deploy_dir(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        d = tmp_path / "deploy"; d.mkdir()
        (d / "app.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: app
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: app
              template:
                metadata:
                  labels:
                    app: app
                spec:
                  containers:
                    - name: app
                      image: app:v1
        """))
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is True

    @_NO_KUBECTL
    def test_finds_manifests_in_manifests_dir(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        m = tmp_path / "manifests"; m.mkdir()
        (m / "deploy.yml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: x
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: x
              template:
                metadata:
                  labels:
                    app: x
                spec:
                  containers:
                    - name: x
                      image: x:v1
        """))
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is True

    @_NO_KUBECTL
    def test_skips_node_modules(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        nm = tmp_path / "node_modules" / "pkg"; nm.mkdir(parents=True)
        (nm / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\n")
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is False

    @_NO_KUBECTL
    def test_skips_venv(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        venv = tmp_path / ".venv" / "lib"; venv.mkdir(parents=True)
        (venv / "deploy.yaml").write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\n")
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is False

    @_NO_KUBECTL
    def test_empty_project(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        r = k8s_status(tmp_path)
        assert r["has_k8s"] is False
        assert r["total_resources"] == 0
        assert r["manifests"] == []

    # ── Multi-document YAML ─────────────────────────────────────

    @_NO_KUBECTL
    def test_multi_document_yaml(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "k8s"; k.mkdir()
        (k / "all.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: web
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: web
              template:
                metadata:
                  labels:
                    app: web
                spec:
                  containers:
                    - name: web
                      image: web:v1
            ---
            apiVersion: v1
            kind: Service
            metadata:
              name: web
            spec:
              ports:
                - port: 80
            ---
            apiVersion: v1
            kind: ConfigMap
            metadata:
              name: cfg
            data:
              key: value
        """))
        r = k8s_status(tmp_path)
        assert r["total_resources"] >= 3

    # ── Resource summary ────────────────────────────────────────

    @_NO_KUBECTL
    def test_resource_summary_counts_kinds(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "k8s"; k.mkdir()
        (k / "deploy.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: a
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: a
              template:
                metadata:
                  labels:
                    app: a
                spec:
                  containers:
                    - name: a
                      image: a:v1
        """))
        (k / "svc.yaml").write_text(textwrap.dedent("""\
            apiVersion: v1
            kind: Service
            metadata:
              name: a
            spec:
              ports:
                - port: 80
        """))
        r = k8s_status(tmp_path)
        assert "Deployment" in r["resource_summary"]
        assert "Service" in r["resource_summary"]

    # ── Manifest detail ─────────────────────────────────────────

    @_NO_KUBECTL
    def test_manifest_detail_has_path_and_resources(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "k8s"; k.mkdir()
        (k / "deploy.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: web
              namespace: prod
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: web
              template:
                metadata:
                  labels:
                    app: web
                spec:
                  containers:
                    - name: web
                      image: web:v1
        """))
        r = k8s_status(tmp_path)
        m = r["manifests"][0]
        assert "path" in m
        assert "resources" in m
        res = m["resources"][0]
        assert res["kind"] == "Deployment"
        assert res["name"] == "web"
        assert res["namespace"] == "prod"


class TestK8sDetectHelm:
    """Helm chart detection from Chart.yaml files."""

    @_NO_KUBECTL
    def test_finds_helm_chart(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        chart = tmp_path / "charts" / "myapp"; chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text(textwrap.dedent("""\
            apiVersion: v2
            name: myapp
            version: 1.0.0
            description: My application
        """))
        r = k8s_status(tmp_path)
        assert len(r["helm_charts"]) >= 1
        assert r["helm_charts"][0]["name"] == "myapp"
        assert r["helm_charts"][0]["version"] == "1.0.0"
        assert r["has_k8s"] is True

    @_NO_KUBECTL
    def test_finds_multiple_charts(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        for name in ("api", "web", "worker"):
            d = tmp_path / "charts" / name; d.mkdir(parents=True)
            (d / "Chart.yaml").write_text(f"apiVersion: v2\nname: {name}\nversion: 1.0.0\n")
        r = k8s_status(tmp_path)
        assert len(r["helm_charts"]) == 3

    @_NO_KUBECTL
    def test_helm_chart_in_node_modules_skipped(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        d = tmp_path / "node_modules" / "pkg"; d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("apiVersion: v2\nname: fake\nversion: 0.0.1\n")
        r = k8s_status(tmp_path)
        assert len(r["helm_charts"]) == 0

    @_NO_KUBECTL
    def test_invalid_chart_yaml(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        d = tmp_path / "mychart"; d.mkdir()
        (d / "Chart.yaml").write_text("{{broken yaml")
        r = k8s_status(tmp_path)
        # Should not crash; chart listed with unknown name
        assert len(r["helm_charts"]) >= 1
        assert r["helm_charts"][0]["name"] == "unknown"


class TestK8sDetectKustomize:
    """Kustomize detection from kustomization.yaml."""

    @_NO_KUBECTL
    def test_finds_kustomize_at_root(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        (tmp_path / "kustomization.yaml").write_text("resources:\n  - deploy.yaml\n")
        r = k8s_status(tmp_path)
        assert r["kustomize"]["exists"] is True

    @_NO_KUBECTL
    def test_finds_kustomize_yml_variant(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        (tmp_path / "kustomization.yml").write_text("resources:\n  - deploy.yaml\n")
        r = k8s_status(tmp_path)
        assert r["kustomize"]["exists"] is True

    @_NO_KUBECTL
    def test_finds_kustomize_in_k8s_dir(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        k = tmp_path / "k8s"; k.mkdir()
        (k / "kustomization.yaml").write_text("resources:\n  - deploy.yaml\n")
        r = k8s_status(tmp_path)
        assert r["kustomize"]["exists"] is True
        assert "k8s" in r["kustomize"]["path"]

    @_NO_KUBECTL
    def test_no_kustomize(self, _m, tmp_path: Path):
        from src.core.services.k8s_detect import k8s_status
        r = k8s_status(tmp_path)
        assert r["kustomize"]["exists"] is False


class TestK8sDetectKubectl:
    """kubectl availability detection."""

    def test_kubectl_available(self, tmp_path: Path):
        """When kubectl exists → available=True, version set."""
        from src.core.services.k8s_detect import k8s_status
        with patch("src.core.services.k8s_detect._kubectl_available",
                   return_value={"available": True, "version": "v1.28.0"}):
            r = k8s_status(tmp_path)
            assert r["kubectl"]["available"] is True
            assert r["kubectl"]["version"] == "v1.28.0"

    def test_kubectl_not_available(self, tmp_path: Path):
        """When kubectl missing → available=False."""
        from src.core.services.k8s_detect import k8s_status
        with patch("src.core.services.k8s_detect._kubectl_available",
                   return_value={"available": False, "version": None}):
            r = k8s_status(tmp_path)
            assert r["kubectl"]["available"] is False


# ═══════════════════════════════════════════════════════════════════
#  2. VALIDATION — structural + best-practice checks
# ═══════════════════════════════════════════════════════════════════


class TestK8sValidation:
    """validate_manifests must check structure and best practices."""

    # ── Valid manifests ─────────────────────────────────────────

    @_NO_KUBECTL
    def test_fully_valid_deployment(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "deploy.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: myapp
            spec:
              replicas: 2
              selector:
                matchLabels:
                  app: myapp
              strategy:
                type: RollingUpdate
              template:
                metadata:
                  labels:
                    app: myapp
                spec:
                  containers:
                    - name: app
                      image: myapp:v1.2.3
                      ports:
                        - containerPort: 8080
                      resources:
                        limits:
                          cpu: 500m
                          memory: 256Mi
                        requests:
                          cpu: 100m
                          memory: 128Mi
                      livenessProbe:
                        httpGet:
                          path: /health
                          port: 8080
                      readinessProbe:
                        httpGet:
                          path: /ready
                          port: 8080
                      securityContext:
                        runAsNonRoot: true
        """))
        r = validate_manifests(tmp_path)
        assert r["ok"] is True
        assert r["errors"] == 0

    @_NO_KUBECTL
    def test_empty_project_is_valid(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        r = validate_manifests(tmp_path)
        assert r["ok"] is True
        assert r["files_checked"] == 0

    # ── Structural errors ───────────────────────────────────────

    @_NO_KUBECTL
    def test_missing_metadata_name(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "bad.yaml").write_text("apiVersion: v1\nkind: ConfigMap\nmetadata: {}\ndata:\n  k: v\n")
        r = validate_manifests(tmp_path)
        assert r["errors"] > 0
        assert any("name" in i["message"].lower() for i in r["issues"] if i["severity"] == "error")

    @_NO_KUBECTL
    def test_deployment_missing_selector(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "bad.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: broken
            spec:
              replicas: 1
              template:
                metadata:
                  labels:
                    app: broken
                spec:
                  containers:
                    - name: app
                      image: broken:latest
        """))
        r = validate_manifests(tmp_path)
        assert any("selector" in i["message"].lower() for i in r["issues"] if i["severity"] == "error")

    @_NO_KUBECTL
    def test_deployment_no_containers(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "empty.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: empty
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: empty
              template:
                metadata:
                  labels:
                    app: empty
                spec:
                  containers: []
        """))
        r = validate_manifests(tmp_path)
        assert any("container" in i["message"].lower() for i in r["issues"] if i["severity"] == "error")

    # ── Best-practice warnings ──────────────────────────────────

    @_NO_KUBECTL
    def test_latest_tag_warning(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "latest.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: latest
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: latest
              template:
                metadata:
                  labels:
                    app: latest
                spec:
                  containers:
                    - name: app
                      image: myapp:latest
        """))
        r = validate_manifests(tmp_path)
        assert any("latest" in i["message"].lower() for i in r["issues"] if i["severity"] == "warning")

    @_NO_KUBECTL
    def test_no_resource_limits_warning(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "nolimits.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: nolimits
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: nolimits
              template:
                metadata:
                  labels:
                    app: nolimits
                spec:
                  containers:
                    - name: app
                      image: app:v1
        """))
        r = validate_manifests(tmp_path)
        assert any("resource" in i["message"].lower() or "limit" in i["message"].lower()
                    for i in r["issues"] if i["severity"] == "warning")

    @_NO_KUBECTL
    def test_implicit_latest_no_tag(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "notag.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: notag
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: notag
              template:
                metadata:
                  labels:
                    app: notag
                spec:
                  containers:
                    - name: app
                      image: myapp
        """))
        r = validate_manifests(tmp_path)
        assert any("latest" in i["message"].lower() for i in r["issues"] if i["severity"] == "warning")

    @_NO_KUBECTL
    def test_no_liveness_probe_info(self, _m, tmp_path: Path):
        """Missing liveness probe → info-level issue."""
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "noprobe.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: noprobe
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: noprobe
              template:
                metadata:
                  labels:
                    app: noprobe
                spec:
                  containers:
                    - name: app
                      image: app:v1
        """))
        r = validate_manifests(tmp_path)
        assert any("liveness" in i["message"].lower() for i in r["issues"] if i["severity"] == "info")

    @_NO_KUBECTL
    def test_no_security_context_info(self, _m, tmp_path: Path):
        """Missing securityContext → info-level issue."""
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "nosec.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: nosec
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: nosec
              template:
                metadata:
                  labels:
                    app: nosec
                spec:
                  containers:
                    - name: app
                      image: app:v1
        """))
        r = validate_manifests(tmp_path)
        assert any("securitycontext" in i["message"].lower() for i in r["issues"] if i["severity"] == "info")

    # ── Service validation ──────────────────────────────────────

    @_NO_KUBECTL
    def test_service_no_selector_warning(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "svc.yaml").write_text(textwrap.dedent("""\
            apiVersion: v1
            kind: Service
            metadata:
              name: headless
            spec:
              ports:
                - port: 80
        """))
        r = validate_manifests(tmp_path)
        assert any("selector" in i["message"].lower() for i in r["issues"] if i["severity"] == "warning")

    @_NO_KUBECTL
    def test_service_no_ports_warning(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "svc.yaml").write_text(textwrap.dedent("""\
            apiVersion: v1
            kind: Service
            metadata:
              name: noports
            spec:
              selector:
                app: test
        """))
        r = validate_manifests(tmp_path)
        assert any("port" in i["message"].lower() for i in r["issues"] if i["severity"] == "warning")

    # ── Unusual API version ─────────────────────────────────────

    @_NO_KUBECTL
    def test_unusual_api_version_warning(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "odd.yaml").write_text(textwrap.dedent("""\
            apiVersion: custom.io/v99alpha1
            kind: Widget
            metadata:
              name: odd
            spec:
              something: true
        """))
        r = validate_manifests(tmp_path)
        assert any("apiversion" in i["message"].lower() or "unusual" in i["message"].lower()
                    for i in r["issues"] if i["severity"] == "warning")

    # ── Error handling ──────────────────────────────────────────

    @_NO_KUBECTL
    def test_invalid_yaml_no_crash(self, _m, tmp_path: Path):
        from src.core.services.k8s_validate import validate_manifests
        k = tmp_path / "k8s"; k.mkdir()
        (k / "broken.yaml").write_text("{{not yaml at all")
        r = validate_manifests(tmp_path)
        assert "ok" in r  # must not crash


# ═══════════════════════════════════════════════════════════════════
#  3. GENERATION — produce K8s manifests from parameters
# ═══════════════════════════════════════════════════════════════════


class TestK8sGeneration:
    """generate_manifests must produce valid YAML for Deployment + Service."""

    def test_basic_generation(self, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", port=8080)
        assert r["ok"] is True
        assert len(r["files"]) >= 2  # Deployment + Service at minimum
        paths = [f["path"] for f in r["files"]]
        assert any("deployment" in p.lower() for p in paths)
        assert any("service" in p.lower() for p in paths)

    def test_deployment_content_valid_yaml(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", port=8080)
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        docs = list(yaml.safe_load_all(deploy_file["content"]))
        assert len(docs) >= 1
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["metadata"]["name"] == "myapp"

    def test_service_content_valid_yaml(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", port=8080)
        svc_file = next(f for f in r["files"] if "service" in f["path"].lower())
        docs = list(yaml.safe_load_all(svc_file["content"]))
        assert docs[0]["kind"] == "Service"
        assert docs[0]["spec"]["ports"][0]["port"] == 8080

    def test_custom_replicas(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", replicas=5)
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        assert doc["spec"]["replicas"] == 5

    def test_custom_service_type(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", service_type="LoadBalancer")
        svc_file = next(f for f in r["files"] if "service" in f["path"].lower())
        doc = yaml.safe_load(svc_file["content"])
        assert doc["spec"]["type"] == "LoadBalancer"

    def test_with_namespace(self, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", namespace="production")
        paths = [f["path"] for f in r["files"]]
        assert any("namespace" in p.lower() for p in paths)

    def test_with_ingress(self, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1", host="myapp.example.com")
        paths = [f["path"] for f in r["files"]]
        assert any("ingress" in p.lower() for p in paths)

    def test_no_ingress_without_host(self, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        paths = [f["path"] for f in r["files"]]
        assert not any("ingress" in p.lower() for p in paths)

    def test_default_image_uses_app_name(self, tmp_path: Path):
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp")
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        image = doc["spec"]["template"]["spec"]["containers"][0]["image"]
        assert "myapp" in image

    def test_generated_deployment_has_resource_limits(self, tmp_path: Path):
        """Generated deployments must include resource limits (best practice)."""
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "limits" in container["resources"]
        assert "requests" in container["resources"]

    def test_generated_deployment_has_probes(self, tmp_path: Path):
        """Generated deployments must include health probes."""
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert "readinessProbe" in container

    def test_generated_deployment_has_security_context(self, tmp_path: Path):
        """Generated deployments must set securityContext."""
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert "securityContext" in container

    def test_generated_deployment_has_rolling_update(self, tmp_path: Path):
        """Generated deployments must have RollingUpdate strategy."""
        import yaml
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        deploy_file = next(f for f in r["files"] if "deployment" in f["path"].lower())
        doc = yaml.safe_load(deploy_file["content"])
        assert doc["spec"]["strategy"]["type"] == "RollingUpdate"

    def test_files_go_under_k8s_dir(self, tmp_path: Path):
        """Generated files must be placed under k8s/ directory."""
        from src.core.services.k8s_generate import generate_manifests
        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        for f in r["files"]:
            assert f["path"].startswith("k8s/"), f"File {f['path']} not under k8s/"


# ═══════════════════════════════════════════════════════════════════
#  4. ROUND-TRIP — generate → detect → validate must be consistent
# ═══════════════════════════════════════════════════════════════════


class TestK8sRoundTrip:
    """Generated manifests must pass detection and validation."""

    @_NO_KUBECTL
    def test_generated_manifests_are_detected(self, _m, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        from src.core.services.k8s_detect import k8s_status

        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        for f in r["files"]:
            fp = tmp_path / f["path"]
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f["content"])

        status = k8s_status(tmp_path)
        assert status["has_k8s"] is True
        assert status["total_resources"] >= 2

    @_NO_KUBECTL
    def test_generated_manifests_pass_validation(self, _m, tmp_path: Path):
        from src.core.services.k8s_generate import generate_manifests
        from src.core.services.k8s_validate import validate_manifests

        r = generate_manifests(tmp_path, "myapp", image="myapp:v1")
        for f in r["files"]:
            fp = tmp_path / f["path"]
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f["content"])

        v = validate_manifests(tmp_path)
        assert v["ok"] is True
        assert v["errors"] == 0
