"""
Tests for k8s_wizard_detect — Skaffold status and namespace mapping.

Pure unit tests: YAML files on disk → parsed dicts.
No kubectl / cluster / skaffold CLI required.
"""

from pathlib import Path
from unittest.mock import patch

from src.core.services.k8s_wizard_detect import skaffold_status, k8s_env_namespaces


# ═══════════════════════════════════════════════════════════════════
#  skaffold_status
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldStatus:
    def test_no_skaffold_files(self, tmp_path: Path):
        """Empty project → has_skaffold=False, configs=[]."""
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is False
        assert result["configs"] == []

    def test_detects_skaffold_yaml(self, tmp_path: Path):
        """skaffold.yaml present → detected with path."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\nkind: Config\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        assert len(result["configs"]) == 1
        assert result["configs"][0]["path"] == "skaffold.yaml"
        assert result["configs"][0]["api_version"] == "skaffold/v4beta6"

    def test_detects_skaffold_yml(self, tmp_path: Path):
        """skaffold.yml (without 'a') also detected."""
        (tmp_path / "skaffold.yml").write_text(
            "apiVersion: skaffold/v2beta29\nkind: Config\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        assert result["configs"][0]["path"] == "skaffold.yml"
        assert result["configs"][0]["api_version"] == "skaffold/v2beta29"

    def test_parses_profiles(self, tmp_path: Path):
        """Profiles section → profile names extracted."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\n"
            "kind: Config\n"
            "profiles:\n"
            "  - name: dev\n"
            "    deploy:\n"
            "      kubectl: {}\n"
            "  - name: prod\n"
            "    deploy:\n"
            "      kubectl: {}\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        profiles = result["configs"][0]["profiles"]
        assert profiles == ["dev", "prod"]

    def test_profiles_missing_name_skipped(self, tmp_path: Path):
        """Profile entries without a name key are skipped."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\n"
            "profiles:\n"
            "  - name: good\n"
            "  - deploy: {}\n"  # no name
            "  - name: also-good\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["configs"][0]["profiles"] == ["good", "also-good"]

    def test_no_profiles_section(self, tmp_path: Path):
        """Skaffold file without profiles → empty profiles list."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\nkind: Config\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["configs"][0]["profiles"] == []

    def test_malformed_yaml_still_detected(self, tmp_path: Path):
        """Unparseable skaffold.yaml → still detected with empty fields."""
        (tmp_path / "skaffold.yaml").write_text(
            "{{invalid yaml}}",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        assert len(result["configs"]) == 1
        assert result["configs"][0]["profiles"] == []
        assert result["configs"][0]["api_version"] == ""

    def test_non_dict_yaml_still_detected(self, tmp_path: Path):
        """Skaffold file that parses to a string → still detected, api_version=''."""
        (tmp_path / "skaffold.yaml").write_text(
            "just a plain string\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        assert result["configs"][0]["api_version"] == ""
        assert result["configs"][0]["profiles"] == []

    @patch("shutil.which", return_value="/usr/local/bin/skaffold")
    def test_cli_available_true(self, _mock, tmp_path: Path):
        """When skaffold CLI exists → available=True."""
        result = skaffold_status(tmp_path)
        assert result["available"] is True

    @patch("shutil.which", return_value=None)
    def test_cli_available_false(self, _mock, tmp_path: Path):
        """When skaffold CLI absent → available=False."""
        result = skaffold_status(tmp_path)
        assert result["available"] is False

    def test_both_yaml_and_yml_detected(self, tmp_path: Path):
        """Both skaffold.yaml and skaffold.yml → both detected."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\nkind: Config\n",
            encoding="utf-8",
        )
        (tmp_path / "skaffold.yml").write_text(
            "apiVersion: skaffold/v2beta29\nkind: Config\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        assert len(result["configs"]) == 2
        paths = [c["path"] for c in result["configs"]]
        assert "skaffold.yaml" in paths
        assert "skaffold.yml" in paths


# ═══════════════════════════════════════════════════════════════════
#  k8s_env_namespaces
# ═══════════════════════════════════════════════════════════════════


def _write_project_yml(tmp_path: Path, content: str) -> None:
    """Helper to create a project.yml in tmp_path."""
    (tmp_path / "project.yml").write_text(content, encoding="utf-8")


class TestK8sEnvNamespaces:
    def test_no_project_yml(self, tmp_path: Path):
        """No project.yml → empty environments list."""
        result = k8s_env_namespaces(tmp_path)
        assert result == {"environments": []}

    def test_project_with_no_environments(self, tmp_path: Path):
        """project.yml with no environments → empty list."""
        _write_project_yml(tmp_path, "name: myapp\n")
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"] == []

    def test_namespace_convention(self, tmp_path: Path):
        """Namespace follows 'project-name-envname' convention."""
        _write_project_yml(tmp_path, (
            "name: myapp\n"
            "environments:\n"
            "  - name: dev\n"
            "  - name: staging\n"
            "  - name: production\n"
        ))
        result = k8s_env_namespaces(tmp_path)
        envs = result["environments"]
        assert len(envs) == 3
        assert envs[0]["namespace"] == "myapp-dev"
        assert envs[1]["namespace"] == "myapp-staging"
        assert envs[2]["namespace"] == "myapp-production"

    def test_env_names_preserved(self, tmp_path: Path):
        """Environment names match what's in project.yml."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: qa\n"
        ))
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["name"] == "qa"

    def test_default_flag_propagated(self, tmp_path: Path):
        """The default flag from the environment is passed through."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
            "    default: true\n"
            "  - name: prod\n"
        ))
        result = k8s_env_namespaces(tmp_path)
        envs = result["environments"]
        assert envs[0]["default"] is True
        assert envs[1]["default"] is False

    def test_overlay_detected_k8s_overlays(self, tmp_path: Path):
        """k8s/overlays/{env} directory → has_overlay=True."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: staging\n"
        ))
        (tmp_path / "k8s" / "overlays" / "staging").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        env = result["environments"][0]
        assert env["has_overlay"] is True
        assert env["overlay_path"] == "k8s/overlays/staging"

    def test_overlay_detected_k8s_envs(self, tmp_path: Path):
        """k8s/envs/{env} directory → has_overlay=True."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
        ))
        (tmp_path / "k8s" / "envs" / "dev").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        env = result["environments"][0]
        assert env["has_overlay"] is True
        assert env["overlay_path"] == "k8s/envs/dev"

    def test_overlay_detected_kubernetes_overlays(self, tmp_path: Path):
        """kubernetes/overlays/{env} directory → has_overlay=True."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: prod\n"
        ))
        (tmp_path / "kubernetes" / "overlays" / "prod").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        env = result["environments"][0]
        assert env["has_overlay"] is True
        assert env["overlay_path"] == "kubernetes/overlays/prod"

    def test_overlay_detected_deploy_overlays(self, tmp_path: Path):
        """deploy/overlays/{env} directory → has_overlay=True."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: canary\n"
        ))
        (tmp_path / "deploy" / "overlays" / "canary").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        env = result["environments"][0]
        assert env["has_overlay"] is True
        assert env["overlay_path"] == "deploy/overlays/canary"

    def test_no_overlay_when_dir_missing(self, tmp_path: Path):
        """No overlay directories → has_overlay=False, empty path."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
        ))
        result = k8s_env_namespaces(tmp_path)
        env = result["environments"][0]
        assert env["has_overlay"] is False
        assert env["overlay_path"] == ""

    def test_values_file_detected(self, tmp_path: Path):
        """values-{env}.yaml → values_file set."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: staging\n"
        ))
        (tmp_path / "values-staging.yaml").write_text("key: val\n")
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["values_file"] == "values-staging.yaml"

    def test_values_file_dot_format(self, tmp_path: Path):
        """values.{env}.yaml → values_file set."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: prod\n"
        ))
        (tmp_path / "values.prod.yaml").write_text("key: val\n")
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["values_file"] == "values.prod.yaml"

    def test_values_file_in_helm_dir(self, tmp_path: Path):
        """helm/values-{env}.yaml → values_file set."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
        ))
        (tmp_path / "helm").mkdir()
        (tmp_path / "helm" / "values-dev.yaml").write_text("key: val\n")
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["values_file"] == "helm/values-dev.yaml"

    def test_values_file_in_charts_dir(self, tmp_path: Path):
        """charts/values-{env}.yaml → values_file set."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: qa\n"
        ))
        (tmp_path / "charts").mkdir()
        (tmp_path / "charts" / "values-qa.yaml").write_text("key: val\n")
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["values_file"] == "charts/values-qa.yaml"

    def test_no_values_file(self, tmp_path: Path):
        """No matching values file → empty string."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
        ))
        result = k8s_env_namespaces(tmp_path)
        assert result["environments"][0]["values_file"] == ""

    def test_overlay_priority_k8s_overlays_first(self, tmp_path: Path):
        """k8s/overlays/ is checked first (before k8s/envs/)."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
        ))
        (tmp_path / "k8s" / "overlays" / "dev").mkdir(parents=True)
        (tmp_path / "k8s" / "envs" / "dev").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        # k8s/overlays/ wins because it's checked first
        assert result["environments"][0]["overlay_path"] == "k8s/overlays/dev"

    def test_multi_env_with_mixed_overlays(self, tmp_path: Path):
        """Multiple envs: some with overlays, some without."""
        _write_project_yml(tmp_path, (
            "name: api\n"
            "environments:\n"
            "  - name: dev\n"
            "  - name: staging\n"
            "  - name: prod\n"
        ))
        (tmp_path / "k8s" / "overlays" / "staging").mkdir(parents=True)
        result = k8s_env_namespaces(tmp_path)
        envs = result["environments"]
        assert envs[0]["has_overlay"] is False  # dev — no overlay
        assert envs[1]["has_overlay"] is True   # staging — has overlay
        assert envs[2]["has_overlay"] is False  # prod — no overlay
