"""
Event Sourcing — FULL integration tests.

Tests BOTH sides of the system:
  1. MEDIATOR SIDE: index cycle computes all nodes → events in store
  2. ROUTE SIDE: user operations emit events → chains form

Exercises every chain type, every domain, every subtype from
the event sourcing design spec.

No Flask app needed — route operations are simulated by appending
events directly to the store (same code path as @tracked decorator).
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import pytest

from src.core.services.events.models import Event
from src.core.services.events.store import EventStore

ROOT = Path(__file__).parent.parent


# ══════════════════════════════════════════════════════════════════════
#  TEST SETUP — real mediator cycle + simulated route operations
# ══════════════════════════════════════════════════════════════════════


def _build_full_system():
    """Run a real mediator cycle AND simulate all route operations.

    Route operations are simulated by appending Events directly to the
    store — this is the EXACT same thing the @tracked decorator does.
    The events have the same structure, same fields, same correlation.
    """
    from src.core.services.mediator.core import QueryMediator
    from src.core.services.mediator.tree import DataTree
    from src.core.services.mediator.registrations import register_all
    from src.core.services.events.correlation import set_correlation, clear_correlation

    tree = DataTree()
    mediator = QueryMediator(tree, ROOT)
    register_all(mediator)

    try:
        from src.core.services.mediator.persistence import hydrate_cache
        hydrate_cache(mediator, ROOT)
    except Exception:
        pass

    store = mediator._event_store
    cycle_id = f"cycle-test-{int(time.time())}"

    # ── MEDIATOR SIDE: run full cycle ──────────────────────────
    store.append(Event(
        id="", ts=time.time(), type="index.cycle.started",
        correlation_id=cycle_id, source="watcher",
        summary="Full test cycle",
    ))

    set_correlation(cycle_id)
    for path in sorted(mediator.tree.all_paths()):
        if path.startswith("timeline."):
            continue
        try:
            mediator.get(path, force=True)
        except Exception:
            pass
    clear_correlation()

    store.append(Event(
        id="", ts=time.time(), type="index.cycle.completed",
        correlation_id=cycle_id, source="watcher",
        summary="Full test cycle completed",
    ))

    # ── ROUTE SIDE: simulate all user operations ──────────────
    # Each operation appends events to the store with proper
    # correlation IDs, forming chains. This is what @tracked does.
    _emit_all_route_operations(store)

    # Resolve timeline.data
    result = mediator.get("timeline.data", force=True)
    data = result["data"]

    return {
        "store": store,
        "mediator": mediator,
        "cycle_id": cycle_id,
        "entries": data["entries"],
        "chains": data["chains"],
        "facets": data["facets"],
        "calendar": data["calendar"],
        "by_adapter": data["facets"].get("by_adapter", {}),
    }


def _emit_all_route_operations(store: EventStore) -> None:
    """Emit events for every route operation domain.

    Each chain is a group of events sharing a correlation_id.
    This exercises the same code path as the @tracked decorator.
    """
    t = time.time()

    # All chain definitions: (correlation_id, events)
    # Each event: (type, summary)
    _CHAINS = {
        # Vault session
        "vault-session:test": [
            ("vault.unlocked", "Vault unlocked"),
            ("vault.key.added", "Added API_KEY"),
            ("vault.key.updated", "Updated DB_HOST"),
            ("vault.key.deleted", "Deleted OLD_KEY"),
            ("vault.key.moved", "Moved SECRET to section"),
            ("vault.section.renamed", "Renamed section"),
            ("vault.synced", "Synced to GitHub"),
            ("vault.exported", "Exported vault"),
            ("vault.imported", "Imported vault"),
            ("vault.env.activated", "Activated staging"),
            ("vault.env.created", "Created production env"),
            ("vault.auto_locked", "Auto-lock triggered"),
            ("vault.locked", "Vault locked"),
        ],
        # Content
        "content-batch:test": [
            ("content.encrypted", "Encrypted credentials.pdf"),
            ("content.decrypted", "Decrypted design.psd"),
            ("content.uploaded", "Uploaded hero.png"),
            ("content.deleted", "Deleted old-logo.png"),
            ("content.folder.created", "Created assets folder"),
            ("content.saved", "Saved README.md"),
            ("content.renamed", "Renamed file"),
            ("content.moved", "Moved to archive"),
            ("content.optimized", "Optimized hero.png 2MB→340KB"),
            ("content.enc_key.set", "Set encryption key"),
        ],
        # Pages pipeline
        "pages-pipeline:test": [
            ("pages.segment.built", "Built docs segment"),
            ("pages.all.built", "Built all segments"),
            ("pages.merged", "Merged segments"),
            ("pages.deployed", "Deployed to gh-pages"),
            ("pages.initialized", "Pages initialized"),
            ("pages.segment.created", "Created docs segment"),
            ("pages.segment.updated", "Updated segment config"),
            ("pages.segment.deleted", "Deleted old segment"),
            ("pages.preview.started", "Preview started"),
            ("pages.preview.stopped", "Preview stopped"),
        ],
        # Docker pipeline
        "docker-pipeline:test": [
            ("docker.built", "Built api image"),
            ("docker.started", "Compose services up"),
            ("docker.stopped", "Compose services down"),
            ("docker.restarted", "Services restarted"),
            ("docker.pruned", "Pruned unused"),
            ("docker.pulled", "Pulled node:20"),
            ("docker.executed", "Exec in container"),
            ("docker.container.removed", "Removed old container"),
            ("docker.image.removed", "Removed old image"),
        ],
        # K8s deploy
        "k8s-deploy:test": [
            ("k8s.applied", "Applied manifests"),
            ("k8s.deleted", "Deleted old pod"),
            ("k8s.scaled", "Scaled to 3 replicas"),
            ("k8s.helm.installed", "Installed nginx chart"),
            ("k8s.helm.upgraded", "Upgraded release"),
            ("k8s.helm.templated", "Rendered templates"),
            ("k8s.manifests.generated", "Generated manifests"),
        ],
        # Terraform
        "tf-pipeline:test": [
            ("terraform.planned", "Plan: 3 to add"),
            ("terraform.initialized", "Terraform init"),
            ("terraform.applied", "Applied plan"),
            ("terraform.destroyed", "Destroyed resources"),
            ("terraform.validated", "Config valid"),
            ("terraform.formatted", "Formatted HCL"),
            ("terraform.workspace.switched", "Switched to staging"),
        ],
        # Backup
        "backup:test": [
            ("backup.created", "Created backup archive"),
            ("backup.restored", "Restored from archive"),
            ("backup.imported", "Imported backup"),
            ("backup.deleted", "Deleted old backup"),
            ("backup.encrypted", "Encrypted archive"),
            ("backup.decrypted", "Decrypted archive"),
            ("backup.uploaded", "Uploaded to GitHub Release"),
        ],
        # Git flow
        "git-flow:test": [
            ("git.committed", "Committed: feat: add vault"),
            ("git.pushed", "Pushed to origin/main"),
            ("git.pulled", "Pulled from origin"),
            ("git.stashed", "Stashed changes"),
            ("git.stash.popped", "Popped stash"),
            ("git.remote.added", "Added upstream remote"),
            ("git.remote.removed", "Removed old remote"),
        ],
        # CI
        "ci:test": [
            ("ci.workflow.dispatched", "Dispatched deploy workflow"),
            ("ci.workflow.generated", "Generated CI workflow"),
        ],
        # Quality
        "quality:test": [
            ("quality.validated", "Quality check passed"),
            ("quality.linted", "Linted with ruff"),
            ("quality.formatted", "Formatted with black"),
        ],
        # Testing
        "testing:test": [
            ("testing.ran", "Pytest: 42 passed"),
            ("testing.coverage", "Coverage: 85%"),
        ],
        # Security
        "security-scan:test": [
            ("security.scanned", "Trivy: 2 CVEs"),
            ("security.finding.dismissed", "Dismissed CVE-2024-1234"),
            ("security.finding.undismissed", "Undismissed CVE-2024-1234"),
        ],
        # Secrets
        "secrets-push:test": [
            ("secrets.key.generated", "Generated AES key"),
            ("secrets.environment.created", "Created staging env"),
            ("secrets.secret.set", "Set DB_URL"),
            ("secrets.secret.deleted", "Deleted OLD_KEY"),
            ("secrets.pushed", "Pushed to staging"),
        ],
        # Tools
        "install:docker:test": [
            ("tools.installed", "Installed Docker 24.0"),
            ("tools.updated", "Updated Node 18→20"),
            ("tools.removed", "Removed old tool"),
            ("tools.plan.cached", "Cached install plan"),
        ],
        # Plans
        "plan:deploy:test": [
            ("plan.created", "Created deploy pipeline"),
            ("plan.executed", "Started execution"),
            ("plan.step.completed", "Step 1: build done"),
            ("plan.step.completed", "Step 2: test done"),
            ("plan.completed", "Plan completed"),
        ],
        # Scripts
        "script:test": [
            ("script.executed", "Ran analyze-deps.sh"),
            ("script.executed", "Ran seed-database.sh"),
        ],
        # Traces
        "trace:demo:test": [
            ("trace.started", "Started trace: demo"),
            ("trace.stopped", "Stopped: 45s recorded"),
            ("trace.shared", "Pushed to ledger"),
            ("trace.deleted", "Trace deleted"),
        ],
        # CDP Test
        "test-suite:login:test": [
            ("cdp_test.suite.created", "Created login-flow suite"),
            ("cdp_test.recording.started", "Recording session"),
            ("cdp_test.recording.stopped", "12 steps captured"),
            ("cdp_test.replay.started", "Replay started"),
            ("cdp_test.replay.completed", "12/12 passed"),
        ],
        # Changelog
        "changelog:v1.2:test": [
            ("changelog.entry.added", "Added: feat vault"),
            ("changelog.entry.edited", "Edited entry"),
            ("changelog.entry.deleted", "Deleted entry"),
            ("changelog.bootstrapped", "Bootstrapped from git"),
            ("changelog.released", "Released v1.2.0"),
        ],
        # Artifacts
        "artifact:api:test": [
            ("artifact.target.created", "Created api-server target"),
            ("artifact.target.updated", "Updated config"),
            ("artifact.target.deleted", "Deleted old target"),
            ("artifact.built", "Built api-server"),
            ("artifact.published", "Published to ghcr.io"),
        ],
        # Wizard
        "wizard:test": [
            ("wizard.detected", "14 stacks found"),
            ("wizard.integration.setup", "Setup git"),
            ("wizard.integration.setup", "Setup CI"),
            ("wizard.integration.setup", "Setup DNS"),
            ("wizard.config.saved", "project.yml saved"),
            ("wizard.completed", "Wizard complete"),
        ],
        # Server
        "server:test": [
            ("server.started", "Server started on :8000"),
            ("server.restarted", "Server restarted"),
            ("server.factory_reset", ".state/ cleared"),
            ("server.settings.changed", "Dev mode toggled"),
        ],
        # Notifications
        "notification:test": [
            ("notification.dismissed", "Dismissed CVE warning"),
            ("notification.deleted", "Deleted stale alert"),
        ],
        # Environment
        "env:test": [
            ("env.activated", "Activated staging"),
            ("env.created", "Created production"),
        ],
    }

    for corr_id, events in _CHAINS.items():
        for i, (event_type, summary) in enumerate(events):
            store.append(Event(
                id="", ts=t + i * 0.001,
                type=event_type,
                correlation_id=corr_id,
                source="route",
                path=event_type,
                status="ok",
                duration_ms=10,
                summary=summary,
                origin="user",
                actor="user",
            ))
        t += 1


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sys():
    return _build_full_system()

@pytest.fixture(scope="module")
def store(sys):
    return sys["store"]

@pytest.fixture(scope="module")
def entries(sys):
    return sys["entries"]

@pytest.fixture(scope="module")
def chains(sys):
    return sys["chains"]

@pytest.fixture(scope="module")
def by_adapter(sys):
    return sys["by_adapter"]

@pytest.fixture(scope="module")
def cycle_id(sys):
    return sys["cycle_id"]


# ── Helpers ───────────────────────────────────────────────────────────

def _chains_by_prefix(chains, prefix):
    return [c for c in chains if c["chain_id"].startswith(prefix)]


# ══════════════════════════════════════════════════════════════════════
#  1. ALL CHAIN TYPES EXIST
# ══════════════════════════════════════════════════════════════════════


class TestAllChainTypes:
    """Every chain type from the design spec must exist."""

    @pytest.mark.parametrize("prefix,min_members", [
        ("cycle-test-", 40),
        ("vault-session:", 3),
        ("content-batch:", 3),
        ("pages-pipeline:", 3),
        ("docker-pipeline:", 3),
        ("k8s-deploy:", 3),
        ("tf-pipeline:", 3),
        ("backup:", 3),
        ("git-flow:", 2),
        ("ci:", 2),
        ("quality:", 2),
        ("testing:", 2),
        ("security-scan:", 2),
        ("secrets-push:", 2),
        ("install:", 2),
        ("plan:", 2),
        ("script:", 2),
        ("trace:", 2),
        ("test-suite:", 2),
        ("changelog:", 2),
        ("artifact:", 2),
        ("wizard:", 2),
        ("server:", 2),
        ("notification:", 2),
        ("env:", 2),
    ])
    def test_chain_exists_with_members(self, chains, prefix, min_members):
        matching = _chains_by_prefix(chains, prefix)
        assert matching, f"No chain with prefix '{prefix}'"
        biggest = max(matching, key=lambda c: c["entry_count"])
        assert biggest["entry_count"] >= min_members, \
            f"Chain {prefix}* has {biggest['entry_count']} members, need >= {min_members}"

    def test_git_branch_chain(self, chains):
        git = _chains_by_prefix(chains, "git:")
        assert git, "No git branch chain"
        biggest = max(git, key=lambda c: c["entry_count"])
        assert biggest["entry_count"] > 100

    def test_chat_thread_chains(self, chains):
        chat = [c for c in chains if "chat" in c.get("sources", [])]
        assert chat, "No chat thread chains"


# ══════════════════════════════════════════════════════════════════════
#  2. ALL DOMAIN ADAPTERS EXIST
# ══════════════════════════════════════════════════════════════════════


class TestAllDomains:
    """Every domain from the design spec must appear in by_adapter."""

    @pytest.mark.parametrize("domain", [
        # From mediator computations
        "docker", "k8s", "terraform", "dns", "docs", "pages",
        "git", "env", "packages", "quality", "security", "testing",
        "audit", "posture", "index", "github", "tools", "status",
        "mediator",
        # From external adapters
        "git_log", "chat",
        # From route operations
        "vault", "content", "backup", "ci",
        "plan", "script", "trace", "cdp_test",
        "changelog", "artifact", "wizard", "server",
        "notification", "secrets",
    ])
    def test_domain_exists(self, by_adapter, domain):
        assert domain in by_adapter, f"Domain '{domain}' missing"


# ══════════════════════════════════════════════════════════════════════
#  3. DOMAIN SUBTYPES — every event type appears as a subtype
# ══════════════════════════════════════════════════════════════════════


class TestVaultSubtypes:
    @pytest.mark.parametrize("sub", [
        "unlocked", "locked", "key.added", "key.updated", "key.deleted",
        "key.moved", "section.renamed", "synced", "exported", "imported",
        "env.activated", "env.created", "auto_locked",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("vault", {}), f"vault missing '{sub}'"


class TestContentSubtypes:
    @pytest.mark.parametrize("sub", [
        "encrypted", "decrypted", "uploaded", "deleted",
        "folder.created", "saved", "renamed", "moved",
        "optimized", "enc_key.set",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("content", {}), f"content missing '{sub}'"


class TestPagesSubtypes:
    @pytest.mark.parametrize("sub", [
        "segment.built", "all.built", "merged", "deployed",
        "initialized", "segment.created", "segment.updated",
        "segment.deleted", "preview.started", "preview.stopped",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("pages", {}), f"pages missing '{sub}'"


class TestDockerSubtypes:
    @pytest.mark.parametrize("sub", [
        "built", "started", "stopped", "restarted",
        "pruned", "pulled", "executed",
        "container.removed", "image.removed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("docker", {}), f"docker missing '{sub}'"


class TestK8sSubtypes:
    @pytest.mark.parametrize("sub", [
        "applied", "deleted", "scaled",
        "helm.installed", "helm.upgraded", "helm.templated",
        "manifests.generated",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("k8s", {}), f"k8s missing '{sub}'"


class TestTerraformSubtypes:
    @pytest.mark.parametrize("sub", [
        "planned", "initialized", "applied", "destroyed",
        "validated", "formatted", "workspace.switched",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("terraform", {}), f"terraform missing '{sub}'"


class TestBackupSubtypes:
    @pytest.mark.parametrize("sub", [
        "created", "restored", "imported", "deleted",
        "encrypted", "decrypted", "uploaded",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("backup", {}), f"backup missing '{sub}'"


class TestGitOpSubtypes:
    @pytest.mark.parametrize("sub", [
        "committed", "pushed", "pulled",
        "stashed", "stash.popped",
        "remote.added", "remote.removed",
    ])
    def test_subtype(self, by_adapter, sub):
        # git ops go under "git" domain
        assert sub in by_adapter.get("git", {}), f"git missing '{sub}'"


class TestCISubtypes:
    @pytest.mark.parametrize("sub", [
        "workflow.dispatched", "workflow.generated",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("ci", {}), f"ci missing '{sub}'"


class TestQualitySubtypes:
    @pytest.mark.parametrize("sub", [
        "validated", "linted", "formatted",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("quality", {}), f"quality missing '{sub}'"


class TestTestingSubtypes:
    @pytest.mark.parametrize("sub", [
        "ran", "coverage",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("testing", {}), f"testing missing '{sub}'"


class TestSecuritySubtypes:
    @pytest.mark.parametrize("sub", [
        "scanned", "finding.dismissed", "finding.undismissed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("security", {}), f"security missing '{sub}'"


class TestSecretsSubtypes:
    @pytest.mark.parametrize("sub", [
        "key.generated", "environment.created",
        "secret.set", "secret.deleted", "pushed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("secrets", {}), f"secrets missing '{sub}'"


class TestToolsSubtypes:
    @pytest.mark.parametrize("sub", [
        "installed", "updated", "removed", "plan.cached",
    ])
    def test_subtype(self, by_adapter, sub):
        # tools ops from route go under "tools" domain
        assert sub in by_adapter.get("tools", {}), f"tools missing '{sub}'"


class TestPlanSubtypes:
    @pytest.mark.parametrize("sub", [
        "created", "executed", "step.completed", "completed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("plan", {}), f"plan missing '{sub}'"


class TestScriptSubtypes:
    def test_executed(self, by_adapter):
        assert "executed" in by_adapter.get("script", {}), "script missing 'executed'"


class TestTraceSubtypes:
    @pytest.mark.parametrize("sub", [
        "started", "stopped", "shared", "deleted",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("trace", {}), f"trace missing '{sub}'"


class TestCdpTestSubtypes:
    @pytest.mark.parametrize("sub", [
        "suite.created", "recording.started", "recording.stopped",
        "replay.started", "replay.completed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("cdp_test", {}), f"cdp_test missing '{sub}'"


class TestChangelogSubtypes:
    @pytest.mark.parametrize("sub", [
        "entry.added", "entry.edited", "entry.deleted",
        "bootstrapped", "released",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("changelog", {}), f"changelog missing '{sub}'"


class TestArtifactSubtypes:
    @pytest.mark.parametrize("sub", [
        "target.created", "target.updated", "target.deleted",
        "built", "published",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("artifact", {}), f"artifact missing '{sub}'"


class TestWizardSubtypes:
    @pytest.mark.parametrize("sub", [
        "detected", "integration.setup", "config.saved", "completed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("wizard", {}), f"wizard missing '{sub}'"


class TestServerSubtypes:
    @pytest.mark.parametrize("sub", [
        "started", "restarted", "factory_reset", "settings.changed",
    ])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("server", {}), f"server missing '{sub}'"


class TestNotificationSubtypes:
    @pytest.mark.parametrize("sub", ["dismissed", "deleted"])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("notification", {}), \
            f"notification missing '{sub}'"


class TestEnvSubtypes:
    @pytest.mark.parametrize("sub", ["activated", "created"])
    def test_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("env", {}), f"env missing '{sub}'"


# Mediator aggregate subtypes (from index cycle)
class TestMediatorSubtypes:
    @pytest.mark.parametrize("sub", [
        "index:scan", "index:delta", "index:files", "index:dirs",
        "index:paths", "index:classify",
        "docker", "k8s", "terraform", "dns", "docs", "pages",
        "git status", "github", "ci scan", "packages", "env",
        "security scan", "testing scan", "quality",
        "scores", "structure", "deps", "clients", "L1",
        "L1:deep", "L2:risks", "L2:repo", "L2:quality", "L2:structure",
        "scores:enriched",
        "toolchain", "platform", "project",
        "pulls", "runs", "workflows",
        "tools", "builders", "scripts",
        "runtime", "status",
    ])
    def test_mediator_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"


# ══════════════════════════════════════════════════════════════════════
#  4. CHAIN INTEGRITY
# ══════════════════════════════════════════════════════════════════════


class TestChainIntegrity:

    def test_every_chain_has_2_plus(self, chains):
        for c in chains:
            assert c["entry_count"] >= 2, \
                f"Chain {c['chain_id']} has {c['entry_count']} members"

    def test_every_chain_has_origin(self, chains):
        for c in chains:
            roles = {m.get("chain_role", "") for m in c.get("members", [])}
            assert "origin" in roles, f"Chain {c['chain_id']} has no origin"

    def test_no_duplicate_ids(self, entries):
        ids = [e["id"] for e in entries]
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        assert not dupes, f"Duplicate IDs: {dupes[:5]}"


# ══════════════════════════════════════════════════════════════════════
#  5. ENTRY FIELDS
# ══════════════════════════════════════════════════════════════════════


class TestEntryFields:

    def test_every_entry_has_id(self, entries):
        for e in entries:
            assert e.get("id")

    def test_every_entry_has_ts(self, entries):
        for e in entries:
            assert e.get("ts", 0) > 0

    def test_every_entry_has_source(self, entries):
        for e in entries:
            assert e.get("source")

    def test_every_entry_has_summary(self, entries):
        for e in entries:
            assert e.get("summary"), f"Entry {e['id']} missing summary"

    def test_every_entry_has_adapter(self, entries):
        for e in entries:
            assert e.get("adapter"), f"Entry {e['id']} missing adapter"


# ══════════════════════════════════════════════════════════════════════
#  6. SUPPRESSION
# ══════════════════════════════════════════════════════════════════════


class TestSuppression:

    def test_no_timeline_leak(self, entries):
        for e in entries:
            ref = e.get("ref", "")
            assert not ref.startswith("timeline."), f"Leaked: {ref}"

    def test_no_detect_leak(self, entries):
        for e in entries:
            ref = e.get("ref", "")
            assert not ref.startswith("detect."), f"Leaked: {ref}"


# ══════════════════════════════════════════════════════════════════════
#  7. COMPLETENESS
# ══════════════════════════════════════════════════════════════════════


class TestCompleteness:

    def test_total_entries_substantial(self, entries):
        assert len(entries) >= 200, f"Only {len(entries)} entries"

    def test_total_chains_substantial(self, chains):
        assert len(chains) >= 25, f"Only {len(chains)} chains"

    def test_total_domains_substantial(self, by_adapter):
        assert len(by_adapter) >= 25, f"Only {len(by_adapter)} domains"

    def test_event_store_has_events(self, store):
        assert store.count() >= 100, f"Only {store.count()} events in store"
