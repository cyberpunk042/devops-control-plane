"""
Integration tests for DNS + CI/CD chain (1.13).

Tests that DNS/CDN configuration wires into GitHub Actions
post-deploy workflow generation via generate_deploy_post_steps().

Spec grounding:
    TECHNOLOGY_SPEC §DNS/CDN = "Records, SSL status → Generate configs → Update, purge, renew"
    PROJECT_SCOPE §4.6 Facilitate = "Generate DNS records, BIND zone files"
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.generators.github_workflow import generate_deploy_post_steps

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _gen(domains: list[str] | None = None, **kw) -> dict:
    """Build a deploy_config and generate post-deploy workflow."""
    config = {}
    if domains:
        config["domains"] = domains
    config.update(kw)
    return generate_deploy_post_steps(config)


def _parse(result) -> dict:
    """Parse the GeneratedFile content as YAML."""
    assert result is not None, "generate_deploy_post_steps returned None"
    data = result.model_dump()
    return yaml.safe_load(data["content"])


def _step_names(result) -> list[str]:
    """Extract step names from the post-deploy job."""
    wf = _parse(result)
    job = wf["jobs"]["post_deploy"]
    return [s.get("name", "") for s in job["steps"]]


# ═══════════════════════════════════════════════════════════════════
#  DNS verification step
# ═══════════════════════════════════════════════════════════════════


class TestDnsVerificationStep:
    """DNS verification runs after deploy."""

    def test_dns_verify_step_present(self):
        """DNS verify step present in workflow."""
        result = _gen(domains=["example.com"])
        names = _step_names(result)
        assert any("dns" in n.lower() or "verify" in n.lower() for n in names)

    def test_uses_dig(self):
        """DNS step uses dig to check domain resolution."""
        result = _gen(domains=["example.com"])
        wf = _parse(result)
        steps = wf["jobs"]["post_deploy"]["steps"]
        dns_steps = [s for s in steps if "dns" in s.get("name", "").lower()
                     or "verify" in s.get("name", "").lower()]
        assert len(dns_steps) >= 1
        run_cmd = dns_steps[0].get("run", "")
        assert "dig" in run_cmd

    def test_multiple_domains(self):
        """Multiple domains verified."""
        result = _gen(domains=["example.com", "api.example.com", "www.example.com"])
        wf = _parse(result)
        steps = wf["jobs"]["post_deploy"]["steps"]
        dns_steps = [s for s in steps if "dns" in s.get("name", "").lower()
                     or "verify" in s.get("name", "").lower()]
        run_cmd = dns_steps[0].get("run", "")
        assert "example.com" in run_cmd
        assert "api.example.com" in run_cmd
        assert "www.example.com" in run_cmd

    def test_no_domains_no_dns_step(self):
        """No domains → no DNS verification step."""
        result = _gen(cdn_provider="cloudflare")
        names = _step_names(result)
        assert not any("dns" in n.lower() and "verify" in n.lower() for n in names)


# ═══════════════════════════════════════════════════════════════════
#  CDN cache purge step
# ═══════════════════════════════════════════════════════════════════


class TestCdnCachePurgeStep:
    """CDN cache purge runs after deploy."""

    def test_cloudflare_purge(self):
        """Cloudflare → purge step with Cloudflare API/CLI."""
        result = _gen(cdn_provider="cloudflare")
        wf = _parse(result)
        steps = wf["jobs"]["post_deploy"]["steps"]
        purge_steps = [s for s in steps if "purge" in s.get("name", "").lower()
                       or "cache" in s.get("name", "").lower()
                       or "cdn" in s.get("name", "").lower()]
        assert len(purge_steps) >= 1
        run_cmd = purge_steps[0].get("run", "")
        assert "cloudflare" in run_cmd.lower() or "curl" in run_cmd.lower()

    def test_cloudfront_purge(self):
        """CloudFront → aws cloudfront create-invalidation."""
        result = _gen(cdn_provider="cloudfront")
        wf = _parse(result)
        steps = wf["jobs"]["post_deploy"]["steps"]
        purge_steps = [s for s in steps if "purge" in s.get("name", "").lower()
                       or "cache" in s.get("name", "").lower()
                       or "cdn" in s.get("name", "").lower()]
        assert len(purge_steps) >= 1
        run_cmd = purge_steps[0].get("run", "")
        assert "cloudfront" in run_cmd.lower()
        assert "create-invalidation" in run_cmd

    def test_netlify_purge(self):
        """Netlify → purge via netlify CLI."""
        result = _gen(cdn_provider="netlify")
        wf = _parse(result)
        steps = wf["jobs"]["post_deploy"]["steps"]
        purge_steps = [s for s in steps if "purge" in s.get("name", "").lower()
                       or "cache" in s.get("name", "").lower()
                       or "cdn" in s.get("name", "").lower()]
        assert len(purge_steps) >= 1

    def test_cdn_credentials_via_secrets(self):
        """CDN provider credentials via GHA secrets."""
        result = _gen(cdn_provider="cloudflare")
        wf = _parse(result)
        job = wf["jobs"]["post_deploy"]
        env = job.get("env", {})
        # Cloudflare needs API token
        has_secret = any("secrets." in str(v) for v in env.values())
        assert has_secret, f"No secrets found in env: {env}"

    def test_no_cdn_no_purge_step(self):
        """No CDN provider → no purge step."""
        result = _gen(domains=["example.com"])
        names = _step_names(result)
        assert not any("purge" in n.lower() or "cache" in n.lower() for n in names)


# ═══════════════════════════════════════════════════════════════════
#  Workflow structure
# ═══════════════════════════════════════════════════════════════════


class TestWorkflowStructure:
    """Generated workflow has correct structure."""

    def test_workflow_file_path(self):
        """Produces .github/workflows/post-deploy.yml."""
        result = _gen(domains=["example.com"])
        data = result.model_dump()
        assert data["path"] == ".github/workflows/post-deploy.yml"

    def test_valid_yaml(self):
        """Generated content is valid YAML."""
        result = _gen(domains=["example.com"], cdn_provider="cloudflare")
        data = result.model_dump()
        parsed = yaml.safe_load(data["content"])
        assert isinstance(parsed, dict)
        assert "jobs" in parsed

    def test_generated_file_model(self):
        """Returns GeneratedFile with path, content, reason."""
        result = _gen(domains=["example.com"])
        data = result.model_dump()
        assert "path" in data
        assert "content" in data
        assert "reason" in data

    def test_project_name_in_workflow(self):
        """project_name flows into workflow name."""
        result = _gen(domains=["example.com"], project_name="myapp")
        wf = _parse(result)
        assert "myapp" in wf["name"]

    def test_both_dns_and_cdn_steps(self):
        """Both DNS verify and CDN purge present when both configured."""
        result = _gen(domains=["example.com"], cdn_provider="cloudflare")
        names = _step_names(result)
        has_dns = any("dns" in n.lower() or "verify" in n.lower() for n in names)
        has_cdn = any("purge" in n.lower() or "cache" in n.lower()
                      or "cdn" in n.lower() for n in names)
        assert has_dns
        assert has_cdn
