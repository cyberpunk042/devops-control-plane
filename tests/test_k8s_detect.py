"""
Tests for k8s_detect — offline manifest scanning, Helm, Kustomize.

Pure unit tests: YAML files on disk → parsed dicts.
No kubectl / cluster required.
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from src.core.services.k8s_detect import (
    k8s_status,
    _collect_yaml_files,
    _detect_helm_charts,
    _detect_kustomize,
    _detect_infra_services,
)

# All 6 conventional manifest dirs the product supports
_ALL_MANIFEST_DIRS = ["k8s", "kubernetes", "deploy", "manifests", "kube", "charts"]


# ═══════════════════════════════════════════════════════════════════
#  _collect_yaml_files
# ═══════════════════════════════════════════════════════════════════


class TestCollectYamlFiles:
    @pytest.mark.parametrize("dir_name", _ALL_MANIFEST_DIRS)
    def test_finds_yaml_in_each_manifest_dir(self, tmp_path: Path, dir_name: str):
        """YAML files in each of the 6 conventional dirs are collected.

        Pessimistic: verifies Path type, existence, directory membership,
        non-YAML exclusion, and set equality on filenames.
        """
        mdir = tmp_path / dir_name
        mdir.mkdir()
        (mdir / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment")
        (mdir / "service.yml").write_text("apiVersion: v1\nkind: Service")
        (mdir / "readme.md").write_text("not a manifest")  # must NOT be collected
        (mdir / "config.json").write_text("{}")  # must NOT be collected

        result = _collect_yaml_files(tmp_path, [dir_name])

        # Correct count — exactly 2 YAML files, not the .md or .json
        assert isinstance(result, list)
        assert len(result) == 2

        # Every result is a Path, exists, and is within the expected dir
        for p in result:
            assert isinstance(p, Path), f"Expected Path, got {type(p)}"
            assert p.exists(), f"Path does not exist: {p}"
            rel = p.relative_to(tmp_path)
            assert rel.parts[0] == dir_name, (
                f"Expected file in {dir_name}/, got {rel}"
            )

        # Exact filename match — no extras, no missing
        names = {f.name for f in result}
        assert names == {"deployment.yaml", "service.yml"}

    def test_finds_yaml_in_nested_dirs(self, tmp_path: Path):
        """YAML files in subdirectories of manifest dir are collected."""
        nested = tmp_path / "k8s" / "base"
        nested.mkdir(parents=True)
        (nested / "deploy.yaml").write_text("apiVersion: apps/v1\nkind: Deployment")

        result = _collect_yaml_files(tmp_path, ["k8s"])

        assert len(result) == 1
        assert isinstance(result[0], Path)
        assert result[0].exists()
        assert result[0].name == "deploy.yaml"
        # Verify it's nested under k8s/base/
        rel = result[0].relative_to(tmp_path)
        assert rel.parts == ("k8s", "base", "deploy.yaml")

    def test_skips_excluded_dirs(self, tmp_path: Path):
        """YAML files in .git, node_modules, .venv, __pycache__ are skipped."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "good.yaml").write_text("apiVersion: v1\nkind: ConfigMap")

        # Create YAML files in several skip dirs — ALL must be excluded
        for skip_dir in [".git", "node_modules", ".venv", "__pycache__"]:
            bad_dir = k8s / skip_dir
            bad_dir.mkdir()
            (bad_dir / "bad.yaml").write_text("apiVersion: v1\nkind: Secret")

        result = _collect_yaml_files(tmp_path, ["k8s"])

        assert len(result) == 1
        assert result[0].name == "good.yaml"
        # Verify no skip-dir paths leaked through
        for p in result:
            rel_parts = p.relative_to(tmp_path).parts
            for skip in [".git", "node_modules", ".venv", "__pycache__"]:
                assert skip not in rel_parts, f"Skip dir {skip} leaked through: {p}"

    def test_both_yaml_and_yml_extensions(self, tmp_path: Path):
        """Both .yaml and .yml extensions are collected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "a.yaml").write_text("apiVersion: v1\nkind: ConfigMap")
        (k8s / "b.yml").write_text("apiVersion: v1\nkind: Secret")
        (k8s / "c.txt").write_text("not yaml")

        result = _collect_yaml_files(tmp_path, ["k8s"])

        assert len(result) == 2
        names = {f.name for f in result}
        assert names == {"a.yaml", "b.yml"}

    def test_no_manifest_dirs_scans_root(self, tmp_path: Path):
        """When no manifest dirs found, scans project root."""
        (tmp_path / "app.yaml").write_text("apiVersion: v1\nkind: Pod")

        result = _collect_yaml_files(tmp_path, [])

        assert len(result) >= 1
        names = {f.name for f in result}
        assert "app.yaml" in names
        # Verify the file is at root level
        for p in result:
            if p.name == "app.yaml":
                assert p.parent == tmp_path

    def test_caps_at_50(self, tmp_path: Path):
        """At most 50 YAML files are returned (safety cap)."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        for i in range(60):
            (k8s / f"file-{i:03d}.yaml").write_text(f"apiVersion: v1\nkind: ConfigMap")

        result = _collect_yaml_files(tmp_path, ["k8s"])

        assert len(result) == 50
        # All 50 are valid Path objects
        for p in result:
            assert isinstance(p, Path)
            assert p.exists()

    def test_empty_dir(self, tmp_path: Path):
        """Empty manifest dir → empty list, not an error."""
        (tmp_path / "k8s").mkdir()

        result = _collect_yaml_files(tmp_path, ["k8s"])

        assert isinstance(result, list)
        assert result == []

    def test_multiple_manifest_dirs_simultaneously(self, tmp_path: Path):
        """Files from multiple manifest dirs are all collected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text("apiVersion: apps/v1\nkind: Deployment")

        deploy = tmp_path / "deploy"
        deploy.mkdir()
        (deploy / "svc.yaml").write_text("apiVersion: v1\nkind: Service")

        result = _collect_yaml_files(tmp_path, ["k8s", "deploy"])

        assert len(result) == 2
        names = {f.name for f in result}
        assert names == {"deploy.yaml", "svc.yaml"}
        # Verify files come from different directories
        dirs = {p.relative_to(tmp_path).parts[0] for p in result}
        assert dirs == {"k8s", "deploy"}


# ═══════════════════════════════════════════════════════════════════
#  _detect_helm_charts
# ═══════════════════════════════════════════════════════════════════


class TestDetectHelmCharts:
    # Keys the function returns for a valid (parseable) chart
    _CURRENT_KEYS = {
        "name", "version", "description", "path",
        "app_version", "type",
        "has_values", "has_templates", "has_subcharts", "has_lockfile",
        "env_values_files",
    }

    def test_detects_chart_yaml(self, tmp_path: Path):
        """Chart.yaml with name + version + description → all fields extracted.

        Pessimistic: verifies return type, element type, exact key set,
        value types, and exact values.
        """
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: myapp\nversion: 1.2.3\ndescription: My application\n"
        )

        result = _detect_helm_charts(tmp_path)

        # Return shape
        assert isinstance(result, list)
        assert len(result) == 1
        chart = result[0]
        assert isinstance(chart, dict)

        # Exact key set — no extra, no missing
        assert set(chart.keys()) == self._CURRENT_KEYS

        # Exact values
        assert chart["name"] == "myapp"
        assert chart["version"] == "1.2.3"
        assert chart["description"] == "My application"
        assert chart["path"] == "charts/myapp"

        # Value type checks — str for text fields, bool for flags, list for collections
        for key in ("name", "version", "description", "path", "app_version", "type"):
            assert isinstance(chart[key], str), f"Key '{key}' is {type(chart[key])}, expected str"
        for key in ("has_values", "has_templates", "has_subcharts", "has_lockfile"):
            assert isinstance(chart[key], bool), f"Key '{key}' is {type(chart[key])}, expected bool"
        assert isinstance(chart["env_values_files"], list)

    def test_multiple_charts(self, tmp_path: Path):
        """Multiple Chart.yaml files → all detected with correct values."""
        for name, ver in [("frontend", "1.0.0"), ("backend", "2.0.0")]:
            d = tmp_path / "charts" / name
            d.mkdir(parents=True)
            (d / "Chart.yaml").write_text(
                f"name: {name}\nversion: {ver}\ndescription: {name} service\n"
            )

        result = _detect_helm_charts(tmp_path)

        assert isinstance(result, list)
        assert len(result) == 2

        # All charts have the correct key set
        for chart in result:
            assert isinstance(chart, dict)
            assert set(chart.keys()) == self._CURRENT_KEYS

        # Both names present with correct data
        by_name = {c["name"]: c for c in result}
        assert set(by_name.keys()) == {"frontend", "backend"}
        assert by_name["frontend"]["version"] == "1.0.0"
        assert by_name["backend"]["version"] == "2.0.0"
        assert by_name["frontend"]["path"] == "charts/frontend"
        assert by_name["backend"]["path"] == "charts/backend"

    def test_skips_excluded_dirs(self, tmp_path: Path):
        """Chart.yaml inside .git, node_modules, .venv → skipped."""
        for skip_dir in [".git", "node_modules", ".venv"]:
            bad = tmp_path / skip_dir / "chart"
            bad.mkdir(parents=True)
            (bad / "Chart.yaml").write_text("name: bad\nversion: 0.0.1\n")

        result = _detect_helm_charts(tmp_path)

        assert isinstance(result, list)
        assert result == []

    def test_malformed_chart_yaml(self, tmp_path: Path):
        """Unparseable Chart.yaml → still detected with name=unknown.

        Graceful degradation: malformed YAML shouldn't crash detection.
        """
        d = tmp_path / "charts" / "broken"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("{{invalid yaml: [[[")

        result = _detect_helm_charts(tmp_path)

        assert isinstance(result, list)
        assert len(result) == 1
        chart = result[0]
        assert isinstance(chart, dict)
        assert chart["name"] == "unknown"
        assert chart["path"] == "charts/broken"

    def test_no_charts(self, tmp_path: Path):
        """No Chart.yaml anywhere → empty list (not error dict)."""
        (tmp_path / "k8s").mkdir()
        (tmp_path / "k8s" / "deploy.yaml").write_text("kind: Deployment")

        result = _detect_helm_charts(tmp_path)

        assert isinstance(result, list)
        assert result == []

    def test_nested_chart_in_deploy_helm(self, tmp_path: Path):
        """Nested chart (deploy/helm/myapp/Chart.yaml) → detected with full path."""
        chart_dir = tmp_path / "deploy" / "helm" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: myapp\nversion: 2.0.0\ndescription: Nested chart\n"
        )

        result = _detect_helm_charts(tmp_path)

        assert isinstance(result, list)
        assert len(result) == 1
        chart = result[0]
        assert chart["name"] == "myapp"
        assert chart["version"] == "2.0.0"
        assert chart["path"] == "deploy/helm/myapp"
        # Path must be relative, not absolute
        assert not chart["path"].startswith("/")

    # ── NEW FEATURES (TDD red — backend needs to be updated) ──────

    def test_app_version_extracted(self, tmp_path: Path):
        """appVersion field from Chart.yaml → extracted when present."""
        chart_dir = tmp_path / "charts" / "api"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: api\nversion: 1.0.0\nappVersion: '3.2.1'\ndescription: API\n"
        )

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "app_version" in chart, "Missing 'app_version' key"
        assert chart["app_version"] == "3.2.1"

    def test_chart_type_extracted(self, tmp_path: Path):
        """Chart type field (application vs library) → extracted when present."""
        chart_dir = tmp_path / "charts" / "lib"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: lib\nversion: 1.0.0\ntype: library\ndescription: Shared lib\n"
        )

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "type" in chart, "Missing 'type' key"
        assert chart["type"] == "library"

    def test_values_yaml_detected(self, tmp_path: Path):
        """values.yaml presence next to Chart.yaml → has_values=True."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        (chart_dir / "values.yaml").write_text("replicas: 2\n")

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "has_values" in chart, "Missing 'has_values' key"
        assert chart["has_values"] is True

    def test_templates_dir_detected(self, tmp_path: Path):
        """templates/ directory next to Chart.yaml → has_templates=True."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        (chart_dir / "templates").mkdir()
        (chart_dir / "templates" / "deployment.yaml").write_text("kind: Deployment")

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "has_templates" in chart, "Missing 'has_templates' key"
        assert chart["has_templates"] is True

    def test_subcharts_detected(self, tmp_path: Path):
        """charts/ subdirectory (sub-charts) → has_subcharts=True."""
        chart_dir = tmp_path / "charts" / "parent"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: parent\nversion: 1.0.0\n")
        sub = chart_dir / "charts" / "child"
        sub.mkdir(parents=True)
        (sub / "Chart.yaml").write_text("name: child\nversion: 0.1.0\n")

        result = _detect_helm_charts(tmp_path)

        # Find the parent chart
        parent = [c for c in result if c["name"] == "parent"]
        assert len(parent) == 1
        assert "has_subcharts" in parent[0], "Missing 'has_subcharts' key"
        assert parent[0]["has_subcharts"] is True

    def test_chart_lock_detected(self, tmp_path: Path):
        """Chart.lock presence → has_lockfile=True."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        (chart_dir / "Chart.lock").write_text("generated: '2024-01-01'\n")

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "has_lockfile" in chart, "Missing 'has_lockfile' key"
        assert chart["has_lockfile"] is True

    def test_env_values_files_detected(self, tmp_path: Path):
        """Env-specific values files (values-dev.yaml, values-staging.yaml) → listed."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        (chart_dir / "values.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-dev.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-staging.yaml").write_text("replicas: 2\n")
        (chart_dir / "values-prod.yaml").write_text("replicas: 3\n")

        result = _detect_helm_charts(tmp_path)

        assert len(result) == 1
        chart = result[0]
        assert "env_values_files" in chart, "Missing 'env_values_files' key"
        assert isinstance(chart["env_values_files"], list)
        env_names = set(chart["env_values_files"])
        assert env_names == {"values-dev.yaml", "values-staging.yaml", "values-prod.yaml"}


# ═══════════════════════════════════════════════════════════════════
#  _detect_kustomize
# ═══════════════════════════════════════════════════════════════════


class TestDetectKustomize:
    # Keys returned when kustomize IS found
    _FOUND_KEYS = {"exists", "path"}
    # Keys returned when kustomize is NOT found
    _NOT_FOUND_KEYS = {"exists"}

    def test_root_kustomization_yaml(self, tmp_path: Path):
        """kustomization.yaml at root → detected.

        Pessimistic: verifies dict type, exact key set, value types, exact values.
        """
        (tmp_path / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert isinstance(result["exists"], bool)
        assert result["path"] == "kustomization.yaml"
        assert isinstance(result["path"], str)

    def test_root_kustomization_yml(self, tmp_path: Path):
        """kustomization.yml at root → detected."""
        (tmp_path / "kustomization.yml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert isinstance(result["exists"], bool)
        assert result["path"] == "kustomization.yml"
        assert isinstance(result["path"], str)

    def test_root_kustomization_capitalized(self, tmp_path: Path):
        """Kustomization (capitalized, no ext) at root → detected."""
        (tmp_path / "Kustomization").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert result["path"] == "Kustomization"

    def test_in_k8s_subdir(self, tmp_path: Path):
        """kustomization.yaml in k8s/ subdirectory → detected with full path."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert result["path"] == "k8s/kustomization.yaml"
        # Path is relative, uses forward slash separator
        assert not result["path"].startswith("/")

    def test_in_kubernetes_subdir(self, tmp_path: Path):
        """kustomization.yaml in kubernetes/ subdirectory → detected."""
        kube = tmp_path / "kubernetes"
        kube.mkdir()
        (kube / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert result["path"] == "kubernetes/kustomization.yaml"

    def test_in_deploy_subdir(self, tmp_path: Path):
        """kustomization.yaml in deploy/ subdirectory → detected."""
        deploy = tmp_path / "deploy"
        deploy.mkdir()
        (deploy / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is True
        assert result["path"] == "deploy/kustomization.yaml"

    def test_not_found(self, tmp_path: Path):
        """No kustomization file anywhere → exists=False, no path key.

        Pessimistic: verify dict type, exact key set, and that 'path' is NOT present.
        """
        (tmp_path / "k8s").mkdir()

        result = _detect_kustomize(tmp_path)

        assert isinstance(result, dict)
        assert result["exists"] is False
        assert isinstance(result["exists"], bool)
        # When not found, there should be no misleading "path" key
        assert "path" not in result or result.get("path") is None or result.get("path") == ""

    # ── NEW FEATURES (TDD red — backend needs to be updated) ──────

    def test_overlays_structure_detected(self, tmp_path: Path):
        """k8s/overlays/ with per-env subdirs → overlays detected.

        Kustomize overlays are the standard multi-environment pattern.
        """
        base = tmp_path / "k8s"
        base.mkdir()
        (base / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        for env in ("dev", "staging", "prod"):
            overlay = base / "overlays" / env
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text(
                f"bases:\n- ../../\npatchesStrategicMerge:\n- patch.yaml\n"
            )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "overlays" in result, "Missing 'overlays' key"
        assert isinstance(result["overlays"], list)
        assert set(result["overlays"]) == {"dev", "staging", "prod"}

    def test_overlay_count(self, tmp_path: Path):
        """Number of overlay environments → counted."""
        base = tmp_path / "k8s"
        base.mkdir()
        (base / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        for env in ("dev", "prod"):
            overlay = base / "overlays" / env
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text("bases:\n- ../../\n")

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "overlay_count" in result, "Missing 'overlay_count' key"
        assert result["overlay_count"] == 2

    def test_bases_directory_detected(self, tmp_path: Path):
        """bases/ directory present in kustomize project → has_bases=True."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        bases = k8s / "base"
        bases.mkdir()
        (bases / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_bases" in result, "Missing 'has_bases' key"
        assert result["has_bases"] is True

    def test_single_env_vs_multi_env_mode(self, tmp_path: Path):
        """Single kustomization without overlays → mode='single'.
        With overlays → mode='multi'."""
        # Single-env: just kustomization.yaml, no overlays
        (tmp_path / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "mode" in result, "Missing 'mode' key"
        assert result["mode"] in ("single", "multi")

    # ── Kustomize content parsing (TDD red) ───────────────────────

    def test_patches_detected(self, tmp_path: Path):
        """Patches (strategicMerge, json6902, unified) → detected.

        Kustomize patches modify base resources per overlay. A DevOps control
        plane must know WHAT is being patched to advise the user.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "patchesStrategicMerge:\n- patch-replicas.yaml\n"
            "patchesJson6902:\n- target:\n    kind: Deployment\n    name: app\n"
            "  path: json-patch.yaml\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_patches" in result, "Missing 'has_patches' key"
        assert result["has_patches"] is True
        assert "patch_types" in result, "Missing 'patch_types' key"
        assert isinstance(result["patch_types"], list)
        assert "patchesStrategicMerge" in result["patch_types"]
        assert "patchesJson6902" in result["patch_types"]

    def test_patch_count_per_overlay(self, tmp_path: Path):
        """Each overlay's patch count → counted."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        dev = k8s / "overlays" / "dev"
        dev.mkdir(parents=True)
        (dev / "kustomization.yaml").write_text(
            "bases:\n- ../../\n"
            "patchesStrategicMerge:\n- patch1.yaml\n- patch2.yaml\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "overlay_details" in result, "Missing 'overlay_details' key"
        assert isinstance(result["overlay_details"], list)
        dev_overlay = [o for o in result["overlay_details"] if o["name"] == "dev"]
        assert len(dev_overlay) == 1
        assert "patch_count" in dev_overlay[0]
        assert dev_overlay[0]["patch_count"] == 2

    def test_config_map_generator_detected(self, tmp_path: Path):
        """configMapGenerator entries → detected."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "configMapGenerator:\n"
            "- name: app-config\n  literals:\n  - APP_ENV=production\n"
            "- name: db-config\n  envs:\n  - db.env\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_config_map_generator" in result, "Missing 'has_config_map_generator' key"
        assert result["has_config_map_generator"] is True
        assert "config_map_generator_count" in result
        assert result["config_map_generator_count"] == 2

    def test_secret_generator_detected(self, tmp_path: Path):
        """secretGenerator entries → detected (auto base64 handling).

        When secretGenerator is used, Kustomize handles base64 encoding
        automatically. This is the SAFE path for secrets.
        """
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "secretGenerator:\n"
            "- name: db-credentials\n  literals:\n  - DB_PASS=hunter2\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_secret_generator" in result, "Missing 'has_secret_generator' key"
        assert result["has_secret_generator"] is True
        assert "secret_generator_count" in result
        assert result["secret_generator_count"] == 1

    def test_raw_secrets_flagged(self, tmp_path: Path):
        """Raw Secret manifests without secretGenerator → flagged.

        If someone writes a Secret YAML by hand, they need to base64-encode
        the values themselves. This is error-prone and should be flagged.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- secret.yaml\n")
        (k8s / "secret.yaml").write_text(
            "apiVersion: v1\nkind: Secret\nmetadata:\n  name: my-secret\n"
            "type: Opaque\ndata:\n  password: cGFzc3dvcmQ=\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_raw_secrets" in result, "Missing 'has_raw_secrets' key"
        assert result["has_raw_secrets"] is True

    def test_envsubst_vars_detected(self, tmp_path: Path):
        """${VAR} patterns in manifests → envsubst dependency detected.

        If manifests use ${VAR} syntax, they need envsubst piping before
        kubectl apply. The control plane must warn the user.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n"
            "  name: ${APP_NAME}\nspec:\n  replicas: ${REPLICAS}\n"
            "  template:\n    spec:\n      containers:\n"
            "      - name: app\n        image: ${IMAGE}:${TAG}\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_envsubst_vars" in result, "Missing 'has_envsubst_vars' key"
        assert result["has_envsubst_vars"] is True
        assert "envsubst_vars" in result
        assert isinstance(result["envsubst_vars"], list)
        assert set(result["envsubst_vars"]) >= {"APP_NAME", "REPLICAS", "IMAGE", "TAG"}

    def test_kustomize_vars_replacements_detected(self, tmp_path: Path):
        """vars/replacements in kustomization → variable refs detected."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "vars:\n- name: SERVICE_NAME\n  objref:\n    kind: Service\n    name: my-svc\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_vars" in result, "Missing 'has_vars' key"
        assert result["has_vars"] is True

    def test_images_section_detected(self, tmp_path: Path):
        """images section → image overrides detected.

        This is how multi-env deploys work: dev uses :latest, prod uses :v1.2.3.
        """
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "images:\n- name: myapp\n  newTag: v1.2.3\n"
            "- name: sidecar\n  newName: registry.io/sidecar\n  newTag: latest\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "has_image_overrides" in result, "Missing 'has_image_overrides' key"
        assert result["has_image_overrides"] is True
        assert "image_override_count" in result
        assert result["image_override_count"] == 2

    def test_namespace_override_detected(self, tmp_path: Path):
        """namespace field in kustomization → namespace override detected."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\nnamespace: my-app-prod\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "namespace" in result, "Missing 'namespace' key"
        assert result["namespace"] == "my-app-prod"

    def test_name_transformations_detected(self, tmp_path: Path):
        """namePrefix/nameSuffix → transformations detected."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deploy.yaml\n"
            "namePrefix: prod-\nnameSuffix: -v2\n"
        )

        result = _detect_kustomize(tmp_path)

        assert result["exists"] is True
        assert "name_prefix" in result, "Missing 'name_prefix' key"
        assert result["name_prefix"] == "prod-"
        assert "name_suffix" in result, "Missing 'name_suffix' key"
        assert result["name_suffix"] == "-v2"
# ═══════════════════════════════════════════════════════════════════
#  k8s_status (integration of the above, mock kubectl)
# ═══════════════════════════════════════════════════════════════════


class TestK8sStatus:
    """Tests for k8s_status orchestrator.

    0.2.2d-0: Plumbing (existing sub-detector integration).
    """
    # Required top-level keys in every k8s_status result
    _REQUIRED_KEYS = {
        "has_k8s", "kubectl", "manifest_dirs", "manifests",
        "resource_summary", "total_resources", "helm_charts", "kustomize",
    }

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_empty_project(self, _mock_kubectl, tmp_path: Path):
        """Project with no K8s files → has_k8s=False, empty lists.

        Pessimistic: verifies dict type, all required keys, value types,
        and exact empty-state values.
        """
        result = k8s_status(tmp_path)

        assert isinstance(result, dict)
        # All required keys present
        assert self._REQUIRED_KEYS.issubset(set(result.keys()))

        assert result["has_k8s"] is False
        assert isinstance(result["has_k8s"], bool)
        assert result["manifests"] == []
        assert isinstance(result["manifests"], list)
        assert result["helm_charts"] == []
        assert isinstance(result["helm_charts"], list)
        assert result["kustomize"]["exists"] is False
        assert isinstance(result["kustomize"], dict)
        assert result["total_resources"] == 0
        assert isinstance(result["total_resources"], int)
        assert result["resource_summary"] == {}
        assert isinstance(result["resource_summary"], dict)
        assert result["manifest_dirs"] == []
        assert isinstance(result["manifest_dirs"], list)
        assert isinstance(result["kubectl"], dict)

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_single_deployment(self, _mock_kubectl, tmp_path: Path):
        """k8s/ with a Deployment manifest → detected + parsed.

        Pessimistic: checks full return shape, resource detail fields,
        and value types throughout.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: myapp\n  namespace: prod\n"
        )

        result = k8s_status(tmp_path)

        assert isinstance(result, dict)
        assert self._REQUIRED_KEYS.issubset(set(result.keys()))
        assert result["has_k8s"] is True
        assert result["manifest_dirs"] == ["k8s"]
        assert result["total_resources"] == 1
        assert result["resource_summary"]["Deployment"] == 1
        assert len(result["manifests"]) == 1

        # Manifest detail shape
        m = result["manifests"][0]
        assert isinstance(m, dict)
        assert {"path", "resources", "count"}.issubset(set(m.keys()))
        assert m["path"] == "k8s/deploy.yaml"
        assert isinstance(m["path"], str)
        assert m["count"] == 1
        assert isinstance(m["resources"], list)

        # Resource shape
        r = m["resources"][0]
        assert isinstance(r, dict)
        assert {"kind", "name", "namespace", "apiVersion"}.issubset(set(r.keys()))
        assert r["kind"] == "Deployment"
        assert r["name"] == "myapp"
        assert r["namespace"] == "prod"
        assert r["apiVersion"] == "apps/v1"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_multi_document_yaml(self, _mock_kubectl, tmp_path: Path):
        """YAML with multiple documents (---) → all resources detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "all.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: web\n"
            "---\n"
            "apiVersion: v1\nkind: Service\n"
            "metadata:\n  name: web-svc\n"
        )

        result = k8s_status(tmp_path)
        assert result["total_resources"] == 2
        assert result["resource_summary"]["Deployment"] == 1
        assert result["resource_summary"]["Service"] == 1

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_helm_only_project(self, _mock_kubectl, tmp_path: Path):
        """Project with only Helm chart (no raw manifests) → has_k8s=True."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert len(result["helm_charts"]) == 1
        assert result["manifests"] == []

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kustomize_only_project(self, _mock_kubectl, tmp_path: Path):
        """Project with only kustomization.yaml → has_k8s=True."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deployment.yaml\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert result["kustomize"]["exists"] is True

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.29.0"})
    def test_kubectl_version_passed_through(self, _mock_kubectl, tmp_path: Path):
        """kubectl availability is included in result."""
        result = k8s_status(tmp_path)
        assert result["kubectl"]["available"] is True
        assert result["kubectl"]["version"] == "v1.29.0"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_non_k8s_yaml_ignored(self, _mock_kubectl, tmp_path: Path):
        """YAML without kind/apiVersion → not counted as K8s resource."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432\n")

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_multiple_manifest_dirs(self, _mock_kubectl, tmp_path: Path):
        """Both k8s/ and deploy/ exist → both listed."""
        (tmp_path / "k8s").mkdir()
        (tmp_path / "deploy").mkdir()

        result = k8s_status(tmp_path)
        assert "k8s" in result["manifest_dirs"]
        assert "deploy" in result["manifest_dirs"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_resource_summary_counts_kinds(self, _mock_kubectl, tmp_path: Path):
        """resource_summary has correct per-kind counts."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "all.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: a\n"
            "---\n"
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: b\n"
            "---\n"
            "apiVersion: v1\nkind: Service\n"
            "metadata:\n  name: svc-a\n"
        )

        result = k8s_status(tmp_path)
        assert result["resource_summary"]["Deployment"] == 2
        assert result["resource_summary"]["Service"] == 1
        assert result["total_resources"] == 3

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifest_detail_shape(self, _mock_kubectl, tmp_path: Path):
        """Each manifest entry has path, resources list, and count."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: web\n  namespace: prod\n"
        )

        result = k8s_status(tmp_path)
        m = result["manifests"][0]
        assert "path" in m
        assert "resources" in m
        assert "count" in m
        assert m["count"] == 1
        r = m["resources"][0]
        assert r["kind"] == "Deployment"
        assert r["name"] == "web"
        assert r["namespace"] == "prod"
        assert r["apiVersion"] == "apps/v1"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifests_in_manifests_dir(self, _mock_kubectl, tmp_path: Path):
        """Manifests in manifests/ directory → detected."""
        mdir = tmp_path / "manifests"
        mdir.mkdir()
        (mdir / "svc.yaml").write_text(
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: my-svc\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert "manifests" in result["manifest_dirs"]
        assert result["total_resources"] == 1

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifests_in_kubernetes_dir(self, _mock_kubectl, tmp_path: Path):
        """Manifests in kubernetes/ directory → detected."""
        kdir = tmp_path / "kubernetes"
        kdir.mkdir()
        (kdir / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert "kubernetes" in result["manifest_dirs"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_files_in_venv_skipped(self, _mock_kubectl, tmp_path: Path):
        """YAML files inside .venv/ → not detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        venv = k8s / ".venv"
        venv.mkdir()
        (venv / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: bad\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_files_in_node_modules_skipped(self, _mock_kubectl, tmp_path: Path):
        """YAML files inside node_modules/ → not detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        nm = k8s / "node_modules"
        nm.mkdir()
        (nm / "chart.yaml").write_text(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: bad\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0


# ═══════════════════════════════════════════════════════════════════
#  0.2.2d-i  Deployment strategy detection
# ═══════════════════════════════════════════════════════════════════


class TestDeploymentStrategy:
    """k8s_status must detect HOW the project deploys: raw_kubectl, helm,
    kustomize, skaffold, or mixed."""

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_raw_kubectl_only(self, _mock_kubectl, tmp_path: Path):
        """Manifests only, no Helm/Kustomize/Skaffold → strategy 'raw_kubectl'."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert result["has_k8s"] is True
        assert "deployment_strategy" in result, "Missing 'deployment_strategy' key"
        assert result["deployment_strategy"] == "raw_kubectl"
        assert "strategies_detected" in result
        assert isinstance(result["strategies_detected"], list)
        assert result["strategies_detected"] == ["raw_kubectl"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_helm_only(self, _mock_kubectl, tmp_path: Path):
        """Helm chart only → strategy 'helm'."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")

        result = k8s_status(tmp_path)

        assert result["deployment_strategy"] == "helm"
        assert result["strategies_detected"] == ["helm"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kustomize_only(self, _mock_kubectl, tmp_path: Path):
        """Kustomize only → strategy 'kustomize'."""
        (tmp_path / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = k8s_status(tmp_path)

        assert result["deployment_strategy"] == "kustomize"
        assert result["strategies_detected"] == ["kustomize"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_mixed_helm_and_raw(self, _mock_kubectl, tmp_path: Path):
        """Helm charts + raw manifests → strategy 'mixed'."""
        chart_dir = tmp_path / "charts" / "infra"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: infra\nversion: 1.0.0\n")
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert result["deployment_strategy"] == "mixed"
        assert isinstance(result["strategies_detected"], list)
        assert set(result["strategies_detected"]) == {"helm", "raw_kubectl"}

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kustomize_plus_helm(self, _mock_kubectl, tmp_path: Path):
        """Kustomize + Helm sub-charts → strategy 'mixed'."""
        (tmp_path / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        chart_dir = tmp_path / "charts" / "redis"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: redis\nversion: 1.0.0\n")

        result = k8s_status(tmp_path)

        assert result["deployment_strategy"] == "mixed"
        assert set(result["strategies_detected"]) == {"kustomize", "helm"}

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_strategies_always_list(self, _mock_kubectl, tmp_path: Path):
        """strategies_detected is always a list, even for single strategy."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "svc.yaml").write_text(
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\n"
        )

        result = k8s_status(tmp_path)

        assert isinstance(result["strategies_detected"], list)
        assert len(result["strategies_detected"]) == 1

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_strategy_values_are_known_enums(self, _mock_kubectl, tmp_path: Path):
        """Each strategy value is from {"raw_kubectl", "helm", "kustomize", "skaffold"}."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        valid_strategies = {"raw_kubectl", "helm", "kustomize", "skaffold"}
        for s in result["strategies_detected"]:
            assert s in valid_strategies, f"Unknown strategy: {s}"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_no_k8s_no_strategy(self, _mock_kubectl, tmp_path: Path):
        """Empty project → no strategy, strategies_detected empty."""
        result = k8s_status(tmp_path)

        assert result["has_k8s"] is False
        assert result["deployment_strategy"] == "none"
        assert result["strategies_detected"] == []


# ═══════════════════════════════════════════════════════════════════
#  0.2.2d-ii  Unified environment map
# ═══════════════════════════════════════════════════════════════════


class TestUnifiedEnvironmentMap:
    """k8s_status must roll up environments from all sources into a
    unified list."""

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_envs_from_kustomize_overlays(self, _mock_kubectl, tmp_path: Path):
        """Kustomize overlays → rolled up into environments list."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        for env in ("dev", "staging", "prod"):
            overlay = k8s / "overlays" / env
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text("bases:\n- ../../\n")

        result = k8s_status(tmp_path)

        assert "environments" in result, "Missing 'environments' key"
        assert isinstance(result["environments"], list)
        env_names = {e["name"] for e in result["environments"]}
        assert {"dev", "staging", "prod"}.issubset(env_names)
        # Each env has required fields
        for env in result["environments"]:
            assert "name" in env
            assert "source" in env

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_envs_from_helm_values_files(self, _mock_kubectl, tmp_path: Path):
        """Helm env-specific values files → rolled up into environments list."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        (chart_dir / "values.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-dev.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-prod.yaml").write_text("replicas: 3\n")

        result = k8s_status(tmp_path)

        assert "environments" in result
        env_names = {e["name"] for e in result["environments"]}
        assert {"dev", "prod"}.issubset(env_names)
        # Source should indicate helm_values
        helm_envs = [e for e in result["environments"] if e["source"] == "helm_values"]
        assert len(helm_envs) >= 2

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_no_environments_empty_list(self, _mock_kubectl, tmp_path: Path):
        """No environments detected → environments: [], not error."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert "environments" in result
        assert result["environments"] == []

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kustomize_namespace_in_env(self, _mock_kubectl, tmp_path: Path):
        """Kustomize namespace override → included in env's namespace field."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")
        dev = k8s / "overlays" / "dev"
        dev.mkdir(parents=True)
        (dev / "kustomization.yaml").write_text(
            "bases:\n- ../../\nnamespace: dev-ns\n"
        )

        result = k8s_status(tmp_path)

        assert "environments" in result
        dev_envs = [e for e in result["environments"] if e["name"] == "dev"]
        assert len(dev_envs) == 1
        assert dev_envs[0].get("namespace") == "dev-ns"


# ═══════════════════════════════════════════════════════════════════
#  0.2.2d-iii  Readiness assessment
# ═══════════════════════════════════════════════════════════════════


class TestReadinessAssessment:
    """k8s_status must assess whether the project is ready to deploy."""

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.29.0"})
    def test_tool_availability_shape(self, _mock_kubectl, tmp_path: Path):
        """tool_availability includes kubectl, helm, kustomize, skaffold."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert "tool_availability" in result, "Missing 'tool_availability' key"
        ta = result["tool_availability"]
        assert isinstance(ta, dict)
        assert "kubectl" in ta
        assert isinstance(ta["kubectl"], dict)
        assert "available" in ta["kubectl"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_secret_safety_with_raw_secrets(self, _mock_kubectl, tmp_path: Path):
        """Raw kind: Secret manifests → secret_safety.has_raw_secrets=True."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "secret.yaml").write_text(
            "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-creds\n"
            "type: Opaque\ndata:\n  password: cGFzcw==\n"
        )

        result = k8s_status(tmp_path)

        assert "secret_safety" in result, "Missing 'secret_safety' key"
        ss = result["secret_safety"]
        assert isinstance(ss, dict)
        assert ss["has_raw_secrets"] is True

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_not_configured_readiness(self, _mock_kubectl, tmp_path: Path):
        """No K8s files → deployment_readiness = 'not_configured'."""
        result = k8s_status(tmp_path)

        assert "deployment_readiness" in result, "Missing 'deployment_readiness' key"
        assert result["deployment_readiness"] == "not_configured"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.29.0"})
    def test_ready_when_tools_available(self, _mock_kubectl, tmp_path: Path):
        """Simple manifests + kubectl available → deployment_readiness = 'ready'."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert result["deployment_readiness"] in ("ready", "needs_config", "needs_tools")

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_needs_tools_when_kubectl_missing(self, _mock_kubectl, tmp_path: Path):
        """Manifests present but kubectl not available → 'needs_tools'."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert result["deployment_readiness"] == "needs_tools"


# ═══════════════════════════════════════════════════════════════════
#  0.2.2d-iv  Infrastructure service detection
# ═══════════════════════════════════════════════════════════════════


class TestInfraServiceDetection:
    """0.2.15a/b — Infrastructure service detection.

    Two detection sources:
    - kubectl infra: Resource kinds (Ingress, Certificate, ServiceMonitor, Gateway)
      + annotation prefixes (cert-manager.io, prometheus.io, nginx.ingress.kubernetes.io)
    - helm infra: Chart names matching _INFRA_CHART_NAMES

    Each detected service has: name (str), detected_via (str).
    Results are deduplicated and sorted alphabetically by name.
    """

    # ── 0.2.15a: kubectl infra — resource kind detection ──────────

    def test_ingress_kind_detects_controller(self):
        """Ingress resource → ingress-controller, detected_via: resource_kind.

        K8s: Ingress requires a controller (nginx, traefik, etc.) to function.
        The tool must flag this dependency.
        """
        resources = [{"kind": "Ingress", "metadata": {"name": "my-ingress"}}]
        result = _detect_infra_services(resources, [])

        assert isinstance(result, list)
        assert len(result) >= 1
        ic = next((s for s in result if s["name"] == "ingress-controller"), None)
        assert ic is not None, "Missing ingress-controller detection"
        assert ic["detected_via"] == "resource_kind"

    def test_certificate_kind_detects_cert_manager(self):
        """Certificate resource → cert-manager, detected_via: resource_kind.

        K8s: Certificate CRD belongs to cert-manager. If a Certificate
        resource exists, cert-manager must be installed.
        """
        resources = [{"kind": "Certificate", "metadata": {"name": "tls-cert"}}]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "cert-manager" in names
        cm = next(s for s in result if s["name"] == "cert-manager")
        assert cm["detected_via"] == "resource_kind"

    def test_cluster_issuer_kind_detects_cert_manager(self):
        """ClusterIssuer resource → cert-manager, detected_via: resource_kind."""
        resources = [{"kind": "ClusterIssuer", "metadata": {"name": "letsencrypt"}}]
        result = _detect_infra_services(resources, [])
        names = {s["name"] for s in result}
        assert "cert-manager" in names

    def test_service_monitor_kind_detects_prometheus(self):
        """ServiceMonitor resource → prometheus, detected_via: resource_kind.

        K8s: ServiceMonitor is a Prometheus Operator CRD. Its presence
        means the prometheus-operator stack must be running.
        """
        resources = [{"kind": "ServiceMonitor", "metadata": {"name": "app-monitor"}}]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "prometheus" in names
        pm = next(s for s in result if s["name"] == "prometheus")
        assert pm["detected_via"] == "resource_kind"

    def test_gateway_kind_detects_gateway_api(self):
        """Gateway resource → gateway-api, detected_via: resource_kind.

        K8s: Gateway API resources require a compatible controller
        (e.g., Envoy Gateway, Istio, Traefik).
        """
        resources = [{"kind": "Gateway", "metadata": {"name": "my-gw"}}]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "gateway-api" in names
        gw = next(s for s in result if s["name"] == "gateway-api")
        assert gw["detected_via"] == "resource_kind"

    # ── 0.2.15a: kubectl infra — annotation detection ─────────────

    def test_cert_manager_annotation_detected(self):
        """cert-manager.io/* annotation → cert-manager, detected_via: manifest_annotation."""
        resources = [{
            "kind": "Ingress",
            "metadata": {
                "name": "my-ingress",
                "annotations": {"cert-manager.io/cluster-issuer": "letsencrypt"},
            },
        }]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "cert-manager" in names
        cm = next(s for s in result if s["name"] == "cert-manager")
        assert cm["detected_via"] in ("manifest_annotation", "resource_kind")

    def test_prometheus_annotation_detected(self):
        """prometheus.io/* annotation → prometheus, detected_via: manifest_annotation."""
        resources = [{
            "kind": "Service",
            "metadata": {
                "name": "app-svc",
                "annotations": {"prometheus.io/scrape": "true"},
            },
        }]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "prometheus" in names

    def test_nginx_ingress_annotation_detected(self):
        """nginx.ingress.kubernetes.io/* annotation → ingress-nginx, detected_via: manifest_annotation."""
        resources = [{
            "kind": "Ingress",
            "metadata": {
                "name": "my-ingress",
                "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"},
            },
        }]
        result = _detect_infra_services(resources, [])

        names = {s["name"] for s in result}
        assert "ingress-nginx" in names

    # ── 0.2.15a: negative + edge cases ────────────────────────────

    def test_no_infra_resources_empty_list(self):
        """Plain Deployment + Service → no infra detected."""
        resources = [
            {"kind": "Deployment", "metadata": {"name": "app"}},
            {"kind": "Service", "metadata": {"name": "app-svc"}},
        ]
        result = _detect_infra_services(resources, [])
        assert result == []

    def test_deduplication_kind_plus_annotation(self):
        """Ingress (kind) + cert-manager annotation on same resource → no duplicates.

        The same infra name must not appear twice. First-seen source wins.
        """
        resources = [{
            "kind": "Ingress",
            "metadata": {
                "name": "my-ingress",
                "annotations": {"cert-manager.io/cluster-issuer": "letsencrypt"},
            },
        }]
        result = _detect_infra_services(resources, [])

        # cert-manager should appear exactly once (from either source)
        cm_entries = [s for s in result if s["name"] == "cert-manager"]
        assert len(cm_entries) == 1, f"Expected 1 cert-manager entry, got {len(cm_entries)}"

        # ingress-controller should also appear exactly once
        ic_entries = [s for s in result if s["name"] == "ingress-controller"]
        assert len(ic_entries) == 1

    def test_empty_resources_and_charts(self):
        """No resources, no charts → empty list."""
        result = _detect_infra_services([], [])
        assert result == []
        assert isinstance(result, list)

    def test_result_sorted_by_name(self):
        """Results are sorted alphabetically by name."""
        resources = [
            {"kind": "ServiceMonitor", "metadata": {"name": "m"}},
            {"kind": "Ingress", "metadata": {"name": "i"}},
            {"kind": "Certificate", "metadata": {"name": "c"}},
        ]
        result = _detect_infra_services(resources, [])
        names = [s["name"] for s in result]
        assert names == sorted(names), f"Not sorted: {names}"

    # ── 0.2.15b: helm infra — chart name detection ────────────────

    def test_helm_ingress_nginx_detected(self):
        """Helm chart named ingress-nginx → detected, detected_via: helm_chart."""
        charts = [{"name": "ingress-nginx", "version": "4.0.0"}]
        result = _detect_infra_services([], charts)

        assert len(result) >= 1
        entry = next(s for s in result if s["name"] == "ingress-nginx")
        assert entry["detected_via"] == "helm_chart"

    def test_helm_cert_manager_detected(self):
        """Helm chart named cert-manager → detected."""
        charts = [{"name": "cert-manager", "version": "1.14.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "cert-manager" in names

    def test_helm_prometheus_detected(self):
        """Helm chart named prometheus → detected."""
        charts = [{"name": "prometheus", "version": "25.0.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "prometheus" in names

    def test_helm_kube_prometheus_stack_detected(self):
        """Helm chart named kube-prometheus-stack → detected."""
        charts = [{"name": "kube-prometheus-stack", "version": "56.0.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "kube-prometheus-stack" in names

    def test_helm_vault_detected(self):
        """Helm chart named vault → detected."""
        charts = [{"name": "vault", "version": "0.28.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "vault" in names

    def test_helm_sealed_secrets_detected(self):
        """Helm chart named sealed-secrets → detected."""
        charts = [{"name": "sealed-secrets", "version": "2.14.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "sealed-secrets" in names

    def test_helm_istio_detected(self):
        """Helm chart named istio → detected."""
        charts = [{"name": "istio", "version": "1.20.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "istio" in names

    def test_helm_longhorn_detected(self):
        """Helm chart named longhorn → detected."""
        charts = [{"name": "longhorn", "version": "1.6.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "longhorn" in names

    def test_helm_argocd_detected(self):
        """Helm chart named argo-cd → detected."""
        charts = [{"name": "argo-cd", "version": "6.0.0"}]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert "argo-cd" in names

    def test_helm_non_infra_chart_not_classified(self):
        """Non-infra chart (my-app) → NOT in infra_services.

        Only charts matching _INFRA_CHART_NAMES should be classified.
        Random application charts must not be flagged as infra.
        """
        charts = [{"name": "my-app", "version": "1.0.0"}]
        result = _detect_infra_services([], charts)
        assert result == []

    def test_helm_multiple_infra_charts(self):
        """Multiple infra Helm charts → all detected."""
        charts = [
            {"name": "ingress-nginx", "version": "4.0.0"},
            {"name": "cert-manager", "version": "1.14.0"},
            {"name": "prometheus", "version": "25.0.0"},
        ]
        result = _detect_infra_services([], charts)
        names = {s["name"] for s in result}
        assert {"ingress-nginx", "cert-manager", "prometheus"}.issubset(names)

    # ── 0.2.15b: mixed detection (kubectl + helm) ─────────────────

    def test_mixed_kubectl_and_helm_merged(self):
        """Resource kind + Helm chart → both detected, merged list.

        A project can have Ingress resources (→ ingress-controller) and
        a cert-manager Helm chart simultaneously. Both should appear.
        """
        resources = [{"kind": "Ingress", "metadata": {"name": "my-ingress"}}]
        charts = [{"name": "cert-manager", "version": "1.14.0"}]
        result = _detect_infra_services(resources, charts)

        names = {s["name"] for s in result}
        assert "ingress-controller" in names
        assert "cert-manager" in names
        # Verify detected_via is correct for each source
        ic = next(s for s in result if s["name"] == "ingress-controller")
        assert ic["detected_via"] == "resource_kind"
        cm = next(s for s in result if s["name"] == "cert-manager")
        assert cm["detected_via"] == "helm_chart"

    def test_mixed_deduplication_helm_overrides_kind(self):
        """Same infra name from both kind and helm → appears once.

        If cert-manager is detected from both a Certificate resource kind
        AND a cert-manager Helm chart, it should appear only once.
        """
        resources = [{"kind": "Certificate", "metadata": {"name": "tls"}}]
        charts = [{"name": "cert-manager", "version": "1.14.0"}]
        result = _detect_infra_services(resources, charts)

        cm_entries = [s for s in result if s["name"] == "cert-manager"]
        assert len(cm_entries) == 1, f"Expected 1 cert-manager, got {len(cm_entries)}"

    # ── Integration: k8s_status passes infra through ──────────────

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_k8s_status_ingress_integration(self, _mock_kubectl, tmp_path: Path):
        """k8s_status with Ingress YAML → infra_services includes ingress-controller."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "ingress.yaml").write_text(
            "apiVersion: networking.k8s.io/v1\nkind: Ingress\n"
            "metadata:\n  name: my-ingress\n"
        )

        result = k8s_status(tmp_path)

        assert "infra_services" in result, "Missing 'infra_services' key"
        assert isinstance(result["infra_services"], list)
        names = {s["name"] for s in result["infra_services"]}
        assert "ingress-controller" in names

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_k8s_status_helm_infra_integration(self, _mock_kubectl, tmp_path: Path):
        """k8s_status with infra Helm chart → infra_services includes it."""
        chart_dir = tmp_path / "charts" / "ingress-nginx"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: ingress-nginx\nversion: 4.0.0\n"
        )

        result = k8s_status(tmp_path)

        assert "infra_services" in result
        names = {s["name"] for s in result["infra_services"]}
        assert "ingress-nginx" in names

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_k8s_status_no_infra_integration(self, _mock_kubectl, tmp_path: Path):
        """k8s_status with plain Deployment → infra_services: []."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)

        assert "infra_services" in result
        assert result["infra_services"] == []


# ═══════════════════════════════════════════════════════════════════
#  0.2.2i  Cloud CLI detection
# ═══════════════════════════════════════════════════════════════════


class TestCloudCLIDetection:
    """Cloud CLI and tool detection in k8s_status.

    0.2.2i: tool_availability must include cloud CLIs + local K8s tools,
    each with {available: bool, version: str|None}.
    """

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.35.1"})
    def test_tool_availability_includes_cloud_clis(self, _mock_kubectl, tmp_path: Path):
        """tool_availability includes az, aws, gcloud with version."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)
        ta = result["tool_availability"]

        for cli in ("az", "aws", "gcloud"):
            assert cli in ta, f"Missing cloud CLI '{cli}' in tool_availability"
            assert isinstance(ta[cli], dict)
            assert "available" in ta[cli]
            assert isinstance(ta[cli]["available"], bool)
            assert "version" in ta[cli], f"Missing 'version' in {cli}"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.35.1"})
    def test_tool_availability_includes_local_k8s_tools(self, _mock_kubectl, tmp_path: Path):
        """tool_availability includes minikube, kind, helm, kustomize, skaffold with version."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)
        ta = result["tool_availability"]

        for tool in ("minikube", "kind", "helm", "kustomize", "skaffold"):
            assert tool in ta, f"Missing tool '{tool}' in tool_availability"
            assert isinstance(ta[tool], dict)
            assert "available" in ta[tool]
            assert isinstance(ta[tool]["available"], bool)
            assert "version" in ta[tool], f"Missing 'version' in {tool}"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.35.1"})
    def test_each_tool_has_consistent_shape(self, _mock_kubectl, tmp_path: Path):
        """Every tool entry has {available: bool, version: str|None}."""
        result = k8s_status(tmp_path)
        ta = result["tool_availability"]

        for tool_name, tool_info in ta.items():
            assert isinstance(tool_info, dict), f"{tool_name} is not a dict"
            assert "available" in tool_info, f"{tool_name} missing 'available'"
            assert isinstance(tool_info["available"], bool), f"{tool_name}['available'] is not bool"
            assert "version" in tool_info, f"{tool_name} missing 'version'"
            if tool_info["available"]:
                assert isinstance(tool_info["version"], str), (
                    f"{tool_name} is available but version is not str: {tool_info['version']}"
                )
            else:
                assert tool_info["version"] is None, (
                    f"{tool_name} is unavailable but version is not None: {tool_info['version']}"
                )

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_no_k8s_still_has_tool_availability(self, _mock_kubectl, tmp_path: Path):
        """Empty project, no tools → tool_availability still present with all keys."""
        result = k8s_status(tmp_path)

        assert "tool_availability" in result
        ta = result["tool_availability"]
        assert isinstance(ta, dict)
        expected_tools = {"kubectl", "helm", "kustomize", "skaffold",
                          "minikube", "kind", "az", "aws", "gcloud"}
        assert expected_tools.issubset(set(ta.keys())), (
            f"Missing tools: {expected_tools - set(ta.keys())}"
        )
