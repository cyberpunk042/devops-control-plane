"""
Tests for Skaffold — detection, generation, and wizard integration.

Pure unit tests: files on disk + function calls → dicts/YAML.
No skaffold CLI required.

Source modules:
  - k8s_wizard_detect.skaffold_status   (detection)
  - k8s_wizard_generate._generate_skaffold  (generation)
  - wizard_setup.setup_k8s  (wizard flow with skaffold=True)
"""

import textwrap
from pathlib import Path
from unittest.mock import patch

import yaml

from src.core.services.k8s_wizard_detect import skaffold_status
from src.core.services.k8s_wizard_generate import _generate_skaffold


# ═══════════════════════════════════════════════════════════════════
#  1. DETECTION — skaffold_status
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldDetection:
    """skaffold_status finds configs, parses profiles, checks CLI."""

    # --- file detection ---

    def test_no_files(self, tmp_path: Path):
        """No skaffold files → has_skaffold=False."""
        r = skaffold_status(tmp_path)
        assert r["has_skaffold"] is False
        assert r["configs"] == []

    def test_skaffold_yaml(self, tmp_path: Path):
        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\nkind: Config\n")
        r = skaffold_status(tmp_path)
        assert r["has_skaffold"] is True
        assert len(r["configs"]) == 1

    def test_skaffold_yml(self, tmp_path: Path):
        (tmp_path / "skaffold.yml").write_text("apiVersion: skaffold/v4beta11\nkind: Config\n")
        assert skaffold_status(tmp_path)["has_skaffold"] is True

    def test_both_yaml_and_yml(self, tmp_path: Path):
        """Both variants present → both detected."""
        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\nkind: Config\n")
        (tmp_path / "skaffold.yml").write_text("apiVersion: skaffold/v2beta29\nkind: Config\n")
        r = skaffold_status(tmp_path)
        assert len(r["configs"]) == 2

    # --- version parsing ---

    def test_api_version_parsed(self, tmp_path: Path):
        """apiVersion extracted from config."""
        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\nkind: Config\n")
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["api_version"] == "skaffold/v4beta11"

    def test_api_version_missing(self, tmp_path: Path):
        """YAML without apiVersion → empty string."""
        (tmp_path / "skaffold.yaml").write_text("kind: Config\n")
        cfg = skaffold_status(tmp_path)["configs"][0]
        assert cfg["api_version"] == ""

    # --- profile parsing ---

    def test_profiles_extracted(self, tmp_path: Path):
        """profiles[].name extracted."""
        (tmp_path / "skaffold.yaml").write_text(textwrap.dedent("""\
            apiVersion: skaffold/v4beta11
            kind: Config
            profiles:
              - name: dev
              - name: staging
              - name: production
        """))
        profiles = skaffold_status(tmp_path)["configs"][0]["profiles"]
        assert profiles == ["dev", "staging", "production"]

    def test_profiles_without_name_skipped(self, tmp_path: Path):
        """Profile entries missing name are skipped."""
        (tmp_path / "skaffold.yaml").write_text(textwrap.dedent("""\
            apiVersion: skaffold/v4beta11
            profiles:
              - name: dev
              - {}
              - name: prod
        """))
        profiles = skaffold_status(tmp_path)["configs"][0]["profiles"]
        assert profiles == ["dev", "prod"]

    def test_no_profiles_section(self, tmp_path: Path):
        """No profiles key → empty list."""
        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\nkind: Config\n")
        assert skaffold_status(tmp_path)["configs"][0]["profiles"] == []

    def test_profiles_not_a_list(self, tmp_path: Path):
        """profiles is not a list → empty list."""
        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4beta11\nprofiles: invalid\n")
        assert skaffold_status(tmp_path)["configs"][0]["profiles"] == []

    # --- malformed YAML ---

    def test_malformed_yaml_still_detected(self, tmp_path: Path):
        """Unparseable YAML → config detected but fields empty."""
        (tmp_path / "skaffold.yaml").write_text("{{bad yaml}}")
        r = skaffold_status(tmp_path)
        assert r["has_skaffold"] is True
        assert len(r["configs"]) == 1

    def test_non_dict_yaml(self, tmp_path: Path):
        """YAML that parses to a non-dict → still detected."""
        (tmp_path / "skaffold.yaml").write_text("- item1\n- item2\n")
        r = skaffold_status(tmp_path)
        assert r["has_skaffold"] is True

    # --- CLI availability ---

    @patch("shutil.which", return_value="/usr/local/bin/skaffold")
    def test_cli_available(self, mock_which, tmp_path: Path):
        assert skaffold_status(tmp_path)["available"] is True

    @patch("shutil.which", return_value=None)
    def test_cli_unavailable(self, mock_which, tmp_path: Path):
        assert skaffold_status(tmp_path)["available"] is False


# ═══════════════════════════════════════════════════════════════════
#  2. GENERATION — _generate_skaffold
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldGeneration:
    """_generate_skaffold builds skaffold.yaml from wizard state."""

    def test_disabled_returns_none(self):
        """skaffold=False → None."""
        assert _generate_skaffold({"skaffold": False}, []) is None

    def test_absent_returns_none(self):
        """No skaffold key → None."""
        assert _generate_skaffold({}, []) is None

    def test_enabled_returns_file_dict(self):
        """skaffold=True → file dict with path, content, reason."""
        result = _generate_skaffold({"skaffold": True}, [])
        assert result is not None
        assert result["path"] == "skaffold.yaml"
        assert "content" in result
        assert "reason" in result

    def test_valid_yaml_output(self):
        """Generated content is valid YAML."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert isinstance(parsed, dict)

    def test_api_version(self):
        """Generated has correct apiVersion."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert parsed["apiVersion"].startswith("skaffold/")

    def test_kind_config(self):
        """Generated has kind: Config."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert parsed["kind"] == "Config"

    def test_deploy_section(self):
        """Generated has a deploy section."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert "deploy" in parsed

    def test_manifests_section(self):
        """Generated has a manifests section."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert "manifests" in parsed

    # --- build artifacts ---

    def test_build_artifacts_from_services(self):
        """Services with images → build artifacts."""
        data = {
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "myapp", "kind": "Deployment"},
            ],
        }
        result = _generate_skaffold(data, [])
        parsed = yaml.safe_load(result["content"])
        assert "build" in parsed
        assert len(parsed["build"]["artifacts"]) == 1
        assert parsed["build"]["artifacts"][0]["image"] == "myapp"

    def test_multiple_services_multiple_artifacts(self):
        """Multiple services → multiple build artifacts."""
        data = {
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "api-img", "kind": "Deployment"},
                {"name": "worker", "image": "worker-img", "kind": "Deployment"},
            ],
        }
        result = _generate_skaffold(data, [])
        parsed = yaml.safe_load(result["content"])
        images = [a["image"] for a in parsed["build"]["artifacts"]]
        assert "api-img" in images
        assert "worker-img" in images

    def test_skip_kind_excluded(self):
        """Services with kind=Skip are excluded from artifacts."""
        data = {
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "myapp", "kind": "Deployment"},
                {"name": "db", "image": "postgres:16", "kind": "Skip"},
            ],
        }
        result = _generate_skaffold(data, [])
        parsed = yaml.safe_load(result["content"])
        if "build" in parsed:
            images = [a["image"] for a in parsed["build"]["artifacts"]]
            assert "postgres:16" not in images

    def test_no_image_excluded(self):
        """Services without image are excluded from artifacts."""
        data = {
            "skaffold": True,
            "_services": [{"name": "api", "image": "", "kind": "Deployment"}],
        }
        result = _generate_skaffold(data, [])
        parsed = yaml.safe_load(result["content"])
        if "build" in parsed:
            assert len(parsed["build"]["artifacts"]) == 0

    def test_no_services_no_build_section(self):
        """No services → no build section."""
        result = _generate_skaffold({"skaffold": True, "_services": []}, [])
        parsed = yaml.safe_load(result["content"])
        # Either no build key, or build with empty artifacts
        if "build" in parsed:
            assert len(parsed["build"].get("artifacts", [])) == 0

    # --- manifest paths ---

    def test_manifest_paths_from_generated_files(self):
        """Generated files → their paths in manifests.rawYaml."""
        generated = [
            {"path": "k8s/deployment.yaml", "content": "..."},
            {"path": "k8s/service.yaml", "content": "..."},
        ]
        result = _generate_skaffold({"skaffold": True}, generated)
        parsed = yaml.safe_load(result["content"])
        paths = parsed["manifests"]["rawYaml"]
        assert "k8s/deployment.yaml" in paths
        assert "k8s/service.yaml" in paths

    def test_non_yaml_files_excluded(self):
        """Non-YAML generated files excluded from manifests."""
        generated = [
            {"path": "k8s/deploy.yaml", "content": "..."},
            {"path": "README.md", "content": "..."},
        ]
        result = _generate_skaffold({"skaffold": True}, generated)
        parsed = yaml.safe_load(result["content"])
        paths = parsed["manifests"]["rawYaml"]
        assert "README.md" not in paths

    def test_fallback_glob_when_no_files(self):
        """No generated files → glob pattern as fallback."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        paths = parsed["manifests"]["rawYaml"]
        assert any("*" in p for p in paths), f"Expected glob fallback, got {paths}"

    def test_custom_output_dir(self):
        """Custom output_dir → reflected in manifest glob."""
        result = _generate_skaffold({"skaffold": True, "output_dir": "deploy/k8s"}, [])
        parsed = yaml.safe_load(result["content"])
        paths = parsed["manifests"]["rawYaml"]
        assert any("deploy/k8s" in p for p in paths)

    # --- metadata ---

    def test_metadata_name_from_first_service(self):
        """Metadata name comes from first service."""
        data = {
            "skaffold": True,
            "_services": [{"name": "my-api", "image": "x", "kind": "Deployment"}],
        }
        result = _generate_skaffold(data, [])
        parsed = yaml.safe_load(result["content"])
        assert parsed["metadata"]["name"] == "my-api"

    def test_metadata_name_default(self):
        """No services → metadata name defaults to 'app'."""
        result = _generate_skaffold({"skaffold": True}, [])
        parsed = yaml.safe_load(result["content"])
        assert parsed["metadata"]["name"] == "app"

    def test_overwrite_false(self):
        """Generated file defaults to overwrite=False."""
        result = _generate_skaffold({"skaffold": True}, [])
        assert result["overwrite"] is False


# ═══════════════════════════════════════════════════════════════════
#  3. WIZARD INTEGRATION — setup_k8s with skaffold=True
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldWizardIntegration:
    """setup_k8s with skaffold checkbox → generates skaffold.yaml.

    0.3.9: Round-trip — wizard state → disk → skaffold_status detection.
    """

    def _minimal_wizard_data(self, **overrides) -> dict:
        """Minimal valid wizard data for K8s setup.

        Uses the correct _services list shape that wizard_state_to_resources expects.
        """
        data = {
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:latest",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 1,
                },
            ],
            "output_dir": "k8s",
            "skaffold": True,
            "overwrite": True,
        }
        data.update(overrides)
        return data

    def test_skaffold_file_created(self, tmp_path: Path):
        """setup_k8s with skaffold=True → skaffold.yaml in files_created."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, self._minimal_wizard_data())
        assert result["ok"] is True
        assert any("skaffold" in f for f in result.get("files_created", []))

    def test_skaffold_yaml_on_disk(self, tmp_path: Path):
        """skaffold.yaml written to project root."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        skaffold_path = tmp_path / "skaffold.yaml"
        assert skaffold_path.is_file()

    def test_skaffold_yaml_valid(self, tmp_path: Path):
        """Generated skaffold.yaml is valid YAML."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        parsed = yaml.safe_load((tmp_path / "skaffold.yaml").read_text())
        assert isinstance(parsed, dict)
        assert parsed["apiVersion"] == "skaffold/v4beta11"

    def test_skaffold_references_manifests(self, tmp_path: Path):
        """skaffold.yaml references the generated K8s manifests."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        parsed = yaml.safe_load((tmp_path / "skaffold.yaml").read_text())
        paths = parsed.get("manifests", {}).get("rawYaml", [])
        assert len(paths) > 0, "skaffold should reference at least one manifest"

    def test_skaffold_false_no_file(self, tmp_path: Path):
        """setup_k8s with skaffold=False → no skaffold.yaml."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data(skaffold=False))
        assert not (tmp_path / "skaffold.yaml").is_file()

    def test_skaffold_detectable_after_setup(self, tmp_path: Path):
        """After setup_k8s, skaffold_status detects the generated config."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        r = skaffold_status(tmp_path)
        assert r["has_skaffold"] is True
        assert len(r["configs"]) >= 1

    def test_skaffold_build_artifact_matches_service(self, tmp_path: Path):
        """Build artifact image matches wizard service image."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        parsed = yaml.safe_load((tmp_path / "skaffold.yaml").read_text())
        assert "build" in parsed
        images = [a["image"] for a in parsed["build"]["artifacts"]]
        assert "myapp:latest" in images

    # ── 0.3.9 NEW: Round-trip detection of generated sections ───

    def test_profiles_detected_after_setup(self, tmp_path: Path):
        """Profiles in generated config → detected by skaffold_status.

        0.3.9: Round-trip — environments → profiles → detection.
        """
        from src.core.services.wizard_setup import setup_k8s
        data = self._minimal_wizard_data(
            environments=["dev-from-local", "dev"],
        )
        setup_k8s(tmp_path, data)
        r = skaffold_status(tmp_path)
        cfg = r["configs"][0]
        assert isinstance(cfg["profiles"], list)
        assert "dev-from-local" in cfg["profiles"]
        assert "dev" in cfg["profiles"]

    def test_port_forward_detected_after_setup(self, tmp_path: Path):
        """Port-forward in generated config → detected by skaffold_status.

        0.3.9: portForward is inside profiles (dev-from-local), not top-level.
        Detection should find it if present at top level. For profile-level
        portForward, we verify the generated YAML structure is correct.
        """
        from src.core.services.wizard_setup import setup_k8s
        data = self._minimal_wizard_data(
            environments=["dev-from-local"],
        )
        setup_k8s(tmp_path, data)

        # Verify portForward exists in the dev-from-local profile
        parsed = yaml.safe_load((tmp_path / "skaffold.yaml").read_text())
        dev_local = next(
            (p for p in parsed.get("profiles", []) if p["name"] == "dev-from-local"),
            None,
        )
        assert dev_local is not None, "dev-from-local profile should exist"
        assert "portForward" in dev_local, "dev-from-local should have portForward"
        assert len(dev_local["portForward"]) > 0

    def test_deploy_strategy_detected_after_setup(self, tmp_path: Path):
        """Deploy strategy in generated config → detected by skaffold_status.

        0.3.9: Default wizard generates kubectl deployer.
        """
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        r = skaffold_status(tmp_path)
        cfg = r["configs"][0]
        assert cfg["deploy_strategy"] == "kubectl"

    def test_tag_policy_detected_after_setup(self, tmp_path: Path):
        """Tag policy in generated config → detected by skaffold_status.

        0.3.9: Default wizard uses gitCommit tag policy.
        """
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, self._minimal_wizard_data())
        r = skaffold_status(tmp_path)
        cfg = r["configs"][0]
        assert cfg["tag_policy"] == "gitCommit"

