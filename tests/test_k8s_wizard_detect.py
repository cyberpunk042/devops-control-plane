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
    """Tests for skaffold_status.

    0.2.2e: Skaffold detection.
    """
    _REQUIRED_KEYS = {"available", "configs", "has_skaffold"}
    _CONFIG_KEYS = {
        "path", "profiles", "api_version",
        "has_port_forward", "build_strategy", "deploy_strategy",
        "required_configs", "tag_policy",
    }

    def test_no_skaffold_files(self, tmp_path: Path):
        """Empty project → has_skaffold=False, configs=[].

        Pessimistic: verifies dict type, all required keys, value types,
        and exact empty-state values.
        """
        result = skaffold_status(tmp_path)

        assert isinstance(result, dict)
        assert set(result.keys()) == self._REQUIRED_KEYS
        assert result["has_skaffold"] is False
        assert isinstance(result["has_skaffold"], bool)
        assert result["configs"] == []
        assert isinstance(result["configs"], list)
        assert isinstance(result["available"], bool)

    def test_detects_skaffold_yaml(self, tmp_path: Path):
        """skaffold.yaml present → detected with path, api_version, profiles.

        Pessimistic: verifies config entry shape, key set, value types.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta6\nkind: Config\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)

        assert isinstance(result, dict)
        assert set(result.keys()) == self._REQUIRED_KEYS
        assert result["has_skaffold"] is True
        assert len(result["configs"]) == 1

        cfg = result["configs"][0]
        assert isinstance(cfg, dict)
        assert set(cfg.keys()) == self._CONFIG_KEYS
        assert cfg["path"] == "skaffold.yaml"
        assert isinstance(cfg["path"], str)
        assert cfg["api_version"] == "skaffold/v4beta6"
        assert isinstance(cfg["api_version"], str)
        assert isinstance(cfg["profiles"], list)
        # 0.3.1 NEW fields — absent in minimal config → safe defaults
        assert cfg["has_port_forward"] is False
        assert isinstance(cfg["has_port_forward"], bool)
        assert cfg["build_strategy"] == ""
        assert isinstance(cfg["build_strategy"], str)
        assert cfg["deploy_strategy"] == ""
        assert isinstance(cfg["deploy_strategy"], str)
        assert cfg["required_configs"] == []
        assert isinstance(cfg["required_configs"], list)
        assert cfg["tag_policy"] == ""
        assert isinstance(cfg["tag_policy"], str)

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
        assert isinstance(profiles, list)
        assert profiles == ["dev", "prod"]
        assert all(isinstance(p, str) for p in profiles)

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
        cfg = result["configs"][0]
        assert cfg["profiles"] == []
        assert cfg["api_version"] == ""
        assert cfg["path"] == "skaffold.yaml"
        # 0.3.1 NEW: malformed → safe defaults for new fields
        assert cfg["has_port_forward"] is False
        assert cfg["build_strategy"] == ""
        assert cfg["deploy_strategy"] == ""
        assert cfg["required_configs"] == []
        assert cfg["tag_policy"] == ""

    def test_non_dict_yaml_still_detected(self, tmp_path: Path):
        """Skaffold file that parses to a string → still detected, api_version=''."""
        (tmp_path / "skaffold.yaml").write_text(
            "just a plain string\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        assert result["has_skaffold"] is True
        cfg = result["configs"][0]
        assert cfg["api_version"] == ""
        assert cfg["profiles"] == []
        # 0.3.1 NEW: non-dict YAML → safe defaults
        assert cfg["has_port_forward"] is False
        assert cfg["build_strategy"] == ""
        assert cfg["deploy_strategy"] == ""
        assert cfg["required_configs"] == []
        assert cfg["tag_policy"] == ""

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
        paths = {c["path"] for c in result["configs"]}
        assert paths == {"skaffold.yaml", "skaffold.yml"}

    # ── 0.3.1 NEW: portForward detection ─────────────────────────

    def test_port_forward_present(self, tmp_path: Path):
        """portForward array present → has_port_forward=True.

        0.3.1: Detect top-level portForward section.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "kind: Config\n"
            "portForward:\n"
            "  - resourceType: service\n"
            "    resourceName: api\n"
            "    port: 8080\n",
            encoding="utf-8",
        )
        result = skaffold_status(tmp_path)
        cfg = result["configs"][0]
        assert cfg["has_port_forward"] is True
        assert isinstance(cfg["has_port_forward"], bool)

    def test_port_forward_absent(self, tmp_path: Path):
        """No portForward section → has_port_forward=False."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\nkind: Config\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["has_port_forward"] is False

    # ── 0.3.1 NEW: build_strategy detection ──────────────────────

    def test_build_strategy_local(self, tmp_path: Path):
        """build.local present → build_strategy='local'.

        0.3.1: Skaffold v4beta11 — build.local is the default local build.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  local:\n"
            "    push: false\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["build_strategy"] == "local"
        assert isinstance(cfg["build_strategy"], str)

    def test_build_strategy_cluster(self, tmp_path: Path):
        """build.cluster present → build_strategy='cluster'.

        0.3.1: Skaffold v4beta11 — in-cluster build (Kaniko).
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  cluster:\n"
            "    namespace: build\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["build_strategy"] == "cluster"

    def test_build_strategy_google_cloud_build(self, tmp_path: Path):
        """build.googleCloudBuild → build_strategy='googleCloudBuild'.

        0.3.1: Skaffold v4beta11 — Google Cloud Build.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  googleCloudBuild:\n"
            "    projectId: my-project\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["build_strategy"] == "googleCloudBuild"

    def test_build_strategy_absent(self, tmp_path: Path):
        """No build section → build_strategy=''."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\nkind: Config\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["build_strategy"] == ""

    # ── 0.3.1 NEW: deploy_strategy detection ─────────────────────

    def test_deploy_strategy_kubectl(self, tmp_path: Path):
        """deploy.kubectl → deploy_strategy='kubectl'.

        0.3.1: Skaffold v4beta11 — raw kubectl deployer.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "deploy:\n"
            "  kubectl:\n"
            "    defaultNamespace: default\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["deploy_strategy"] == "kubectl"
        assert isinstance(cfg["deploy_strategy"], str)

    def test_deploy_strategy_helm(self, tmp_path: Path):
        """deploy.helm → deploy_strategy='helm'."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "deploy:\n"
            "  helm:\n"
            "    releases:\n"
            "      - name: app\n"
            "        chartPath: chart/\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["deploy_strategy"] == "helm"

    def test_deploy_strategy_kustomize(self, tmp_path: Path):
        """deploy.kustomize → deploy_strategy='kustomize'."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "deploy:\n"
            "  kustomize:\n"
            "    paths:\n"
            "      - k8s/base\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["deploy_strategy"] == "kustomize"

    def test_deploy_strategy_absent(self, tmp_path: Path):
        """No deploy section → deploy_strategy=''."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\nkind: Config\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["deploy_strategy"] == ""

    # ── 0.3.1 NEW: required_configs (multi-config) ──────────────

    def test_required_configs_present(self, tmp_path: Path):
        """requires section → required_configs list of paths.

        0.3.1: Skaffold v4beta11 — multi-module configs via requires.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "requires:\n"
            "  - path: ./module-a\n"
            "  - path: ./module-b\n"
            "    configs: [cfg-b]\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert isinstance(cfg["required_configs"], list)
        assert len(cfg["required_configs"]) == 2
        assert "./module-a" in cfg["required_configs"]
        assert "./module-b" in cfg["required_configs"]

    def test_required_configs_absent(self, tmp_path: Path):
        """No requires section → required_configs=[]."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\nkind: Config\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["required_configs"] == []

    # ── 0.3.1 NEW: tag_policy detection ──────────────────────────

    def test_tag_policy_git_commit(self, tmp_path: Path):
        """build.tagPolicy.gitCommit → tag_policy='gitCommit'.

        0.3.1: Skaffold v4beta11 — git-based tagging.
        """
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  tagPolicy:\n"
            "    gitCommit:\n"
            "      variant: Tags\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["tag_policy"] == "gitCommit"
        assert isinstance(cfg["tag_policy"], str)

    def test_tag_policy_sha256(self, tmp_path: Path):
        """build.tagPolicy.sha256 → tag_policy='sha256'."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  tagPolicy:\n"
            "    sha256: {}\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["tag_policy"] == "sha256"

    def test_tag_policy_absent(self, tmp_path: Path):
        """No tagPolicy → tag_policy=''."""
        (tmp_path / "skaffold.yaml").write_text(
            "apiVersion: skaffold/v4beta11\n"
            "build:\n"
            "  local:\n"
            "    push: false\n",
            encoding="utf-8",
        )
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["tag_policy"] == ""


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
