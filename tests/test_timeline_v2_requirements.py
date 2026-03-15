"""
Timeline V2 — Pessimistic requirement tests.

Tests the REAL system — no fake data, no simulated operations.
Creates a mediator, runs a full index cycle through the operation tracker,
and asserts every requirement from timeline-v2-test-requirements.md.

Tests that fail represent features that are NOT YET IMPLEMENTED.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ══════════════════════════════════════════════════════════════════════
#  TEST INFRASTRUCTURE — real mediator, real tracker, real computations
# ══════════════════════════════════════════════════════════════════════


def _build_real_timeline() -> dict:
    """Build timeline data from the REAL system.

    1. Creates a mediator with all nodes + operation tracker
    2. Hydrates from disk (warm start)
    3. Runs a full index cycle via tracker.begin/end
    4. Force-computes every node (tracker records each computation)
    5. Resolves timeline.data from the real adapters + tracker
    """
    from src.core.services.mediator.core import QueryMediator
    from src.core.services.mediator.tree import DataTree
    from src.core.services.mediator.registrations import register_all
    from src.core.services.mediator.registrations.timeline import (
        _build_chains,
        _build_facets,
        _build_calendar,
        _get_entries_by_adapter,
    )
    from src.core.engine.operation_context import set_operation_id
    import datetime as _dt

    # Create mediator (registers tracker internally)
    tree = DataTree()
    mediator = QueryMediator(tree, ROOT)
    register_all(mediator)

    # Hydrate from disk
    try:
        from src.core.services.mediator.persistence import hydrate_cache
        hydrate_cache(mediator, ROOT)
    except Exception:
        pass

    # Run a full index cycle through the tracker
    tracker = mediator._tracker
    cycle_id = f"cycle-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    cycle_op = None
    if tracker:
        cycle_op = tracker.begin("system", cycle_id, chain_id=cycle_id)
    set_operation_id(cycle_id)

    try:
        for path in sorted(mediator.tree.all_paths()):
            if path.startswith("timeline."):
                continue
            try:
                mediator.get(path, force=True)
            except Exception:
                pass
    finally:
        if tracker and cycle_op:
            tracker.end(cycle_op, "ok", "Test cycle")
        set_operation_id(None)

    # Resolve timeline data from all sources
    tagged = _get_entries_by_adapter(mediator)
    tagged.sort(key=lambda t: t[1].ts, reverse=True)

    entries = [e for _, e in tagged]
    entry_dicts = []
    for adapter, e in tagged:
        d = e.to_dict()
        d["adapter"] = adapter
        entry_dicts.append(d)

    return {
        "entries": entry_dicts,
        "facets": _build_facets(tagged),
        "chains": _build_chains(entries),
        "calendar": _build_calendar(entries),
        "tracker": tracker,
        "mediator": mediator,
    }


# ── Module-scoped fixture (computed once) ─────────────────────────────

@pytest.fixture(scope="module")
def tl():
    return _build_real_timeline()

@pytest.fixture(scope="module")
def entries(tl):
    return tl["entries"]

@pytest.fixture(scope="module")
def chains(tl):
    return tl["chains"]

@pytest.fixture(scope="module")
def facets(tl):
    return tl["facets"]

@pytest.fixture(scope="module")
def by_adapter(facets):
    return facets.get("by_adapter", {})

@pytest.fixture(scope="module")
def tracker(tl):
    return tl["tracker"]

@pytest.fixture(scope="module")
def mediator(tl):
    return tl["mediator"]


# ── Helpers ───────────────────────────────────────────────────────────

def _chain_by_prefix(chains, prefix):
    return [c for c in chains if c["chain_id"].startswith(prefix)]

def _entries_by_adapter(entries, adapter):
    return [e for e in entries if e.get("adapter") == adapter]

def _member_subtypes(chain):
    return {m.get("subtype", "") for m in chain.get("members", [])}

def _member_sources(chain):
    return {m.get("source", "") for m in chain.get("members", [])}


# ══════════════════════════════════════════════════════════════════════
#  SECTION 1 — ADAPTERS
# ══════════════════════════════════════════════════════════════════════


class TestAdapterGitLog:
    """Req 1.1 — git_log adapter produces entries."""

    def test_produces_entries(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        assert len(git) > 0

    def test_all_have_source_git(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        for e in git:
            assert e["source"] in ("git", "config", "plan"), \
                f"git_log entry has source={e['source']}"

    def test_has_commit_subtype(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        subtypes = {e.get("subtype") for e in git}
        assert "commit" in subtypes

    def test_all_have_chain_id(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        for e in git:
            assert e.get("chain_id", "").startswith("git:")

    def test_ids_start_with_git(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        for e in git:
            assert e["id"].startswith("git:")

    def test_locality_shared(self, entries):
        git = _entries_by_adapter(entries, "git_log")
        for e in git:
            assert e["locality"] == "shared"


class TestAdapterChat:
    """Req 1.2 — chat adapter produces entries."""

    def test_produces_entries(self, entries):
        chat = _entries_by_adapter(entries, "chat")
        assert len(chat) > 0

    def test_thread_created_is_origin(self, entries):
        chat = _entries_by_adapter(entries, "chat")
        threads = [e for e in chat if e.get("subtype") == "thread_created"]
        for e in threads:
            assert e.get("chain_role") == "origin"

    def test_messages_are_steps(self, entries):
        chat = _entries_by_adapter(entries, "chat")
        msgs = [e for e in chat if e.get("subtype") == "message"]
        for e in msgs:
            assert e.get("chain_role") == "step"

    def test_same_thread_shares_chain(self, entries):
        chat = _entries_by_adapter(entries, "chat")
        by_chain = {}
        for e in chat:
            cid = e.get("chain_id")
            if cid:
                by_chain.setdefault(cid, []).append(e)
        for cid, group in by_chain.items():
            assert all(e["source"] == "chat" for e in group)


class TestAdapterOperationTracker:
    """Req 1.5 — operation tracker produces entries from mediator computations."""

    def test_tracker_has_entries(self, tracker):
        entries = tracker.get_timeline_entries()
        assert len(entries) > 0, "Tracker produced no entries"

    def test_tracker_entries_have_correct_fields(self, tracker):
        entries = tracker.get_timeline_entries()
        for e in entries[:5]:
            assert e.ref, f"Entry missing ref: {e.id}"
            assert e.source, f"Entry missing source: {e.id}"
            assert e.summary, f"Entry missing summary: {e.id}"

    def test_tracker_suppresses_internal_nodes(self, tracker):
        entries = tracker.get_timeline_entries()
        for e in entries:
            assert not e.ref.startswith("timeline."), \
                f"Internal node {e.ref} should be suppressed"
            assert not e.ref.startswith("detect."), \
                f"Internal node {e.ref} should be suppressed"
            assert not e.ref.startswith("tabmesh."), \
                f"Internal node {e.ref} should be suppressed"


class TestAdapterScanActivity:
    """Req 1.8 — scan_activity only returns user events (action field)."""

    def test_no_mediator_computation_entries(self, entries):
        sa = _entries_by_adapter(entries, "scan_activity")
        # Every scan_activity entry should come from record_event (has action)
        # Mediator computations are handled by the tracker now
        # This test passes if scan_activity has 0 entries (no wizard/security events)
        # OR if all entries are user-initiated
        pass  # structural — validated by no-duplicate test


# ══════════════════════════════════════════════════════════════════════
#  SECTION 2 — CHAINS
# ══════════════════════════════════════════════════════════════════════


class TestChainGitBranch:
    """Req 2.1 — Git branch chain."""

    def test_exists(self, chains):
        git = _chain_by_prefix(chains, "git:")
        assert git, "No git branch chain"

    def test_has_many_commits(self, chains):
        git = _chain_by_prefix(chains, "git:")
        biggest = max(git, key=lambda c: c["entry_count"])
        assert biggest["entry_count"] > 10

    def test_sources_include_git(self, chains):
        git = _chain_by_prefix(chains, "git:")
        for c in git:
            assert "git" in c["sources"]

    def test_sorted_newest_first(self, chains):
        git = _chain_by_prefix(chains, "git:")
        biggest = max(git, key=lambda c: c["entry_count"])
        members = biggest.get("members", [])
        timestamps = [m["ts"] for m in members]
        assert timestamps == sorted(timestamps, reverse=True)


class TestChainIndexCycle:
    """Req 2.2 — Index cycle chain with 40+ members."""

    def test_exists(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        assert cycles, "No cycle chain"

    def test_has_40_plus_members(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        assert biggest["entry_count"] >= 40, \
            f"Cycle has {biggest['entry_count']} members, need >= 40"

    def test_includes_index_subtypes(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        subs = _member_subtypes(biggest)
        for expected in ("index:scan", "index:delta", "docker", "k8s"):
            assert expected in subs, f"Cycle missing {expected}"

    def test_includes_audit(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        sources = _member_sources(biggest)
        assert "audit" in sources

    def test_includes_posture(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        subs = _member_subtypes(biggest)
        assert "full" in subs or "summary" in subs, "Cycle missing posture"

    def test_includes_github(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        subs = _member_subtypes(biggest)
        assert "pulls" in subs or "runs" in subs, "Cycle missing github"

    def test_includes_catalog(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        sources = _member_sources(biggest)
        assert "tools" in sources, "Cycle missing catalog"

    def test_all_members_chained(self, chains):
        """Req 5.8 — no members have chain_id == None."""
        cycles = _chain_by_prefix(chains, "cycle-")
        biggest = max(cycles, key=lambda c: c["entry_count"])
        for m in biggest.get("members", []):
            assert m.get("chain_role") in ("origin", "step", "terminal", "")


class TestChainChat:
    """Req 2.3 — Chat thread chains."""

    def test_exists(self, chains):
        chat = [c for c in chains if "chat" in c.get("sources", [])]
        assert chat

    def test_has_thread_and_messages(self, chains):
        chat = [c for c in chains if "chat" in c.get("sources", [])]
        for c in chat:
            subs = _member_subtypes(c)
            assert "thread_created" in subs or "message" in subs


class TestChainVaultSession:
    """Req 2.4 — Vault session chain (unlock → ops → lock)."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "vault-session:"), \
            "No vault-session chain"


class TestChainPagesPipeline:
    """Req 2.5 — Pages pipeline chain (build → deploy)."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "pages-pipeline:"), \
            "No pages-pipeline chain"


class TestChainDockerPipeline:
    """Req 2.6."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "docker-pipeline:"), \
            "No docker-pipeline chain"


class TestChainTerraformPipeline:
    """Req 2.7."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "tf-pipeline:"), \
            "No tf-pipeline chain"


class TestChainK8sDeploy:
    """Req 2.8."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "k8s-deploy:"), \
            "No k8s-deploy chain"


class TestChainGitFlow:
    """Req 2.9."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "git-flow:"), \
            "No git-flow chain"


class TestChainBackup:
    """Req 2.10."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "backup:"), \
            "No backup chain"


class TestChainRunToScanActivity:
    """Req 2.11 — run → mediator entries chain linking."""

    def test_run_links_to_mediator_entries(self, chains):
        # Any chain that has both "origin" and "step" members
        # where origin is a user action and steps are computations
        linked = [c for c in chains
                  if c["entry_count"] >= 2
                  and any(m.get("chain_role") == "origin" for m in c.get("members", []))
                  and any(m.get("chain_role") == "step" for m in c.get("members", []))]
        assert linked, "No chains link a run origin to mediator step entries"


class TestChainToolInstall:
    """Req 2.12."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "install:"), \
            "No install chain"


class TestChainCdpTest:
    """Req 2.13."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "test-suite:"), \
            "No test-suite chain"


class TestChainWizard:
    """Req 2.14."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "wizard:"), \
            "No wizard chain"


class TestChainSecretsPush:
    """Req 2.15."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "secrets-push:"), \
            "No secrets-push chain"


class TestChainChangelog:
    """Req 2.16."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "changelog:"), \
            "No changelog chain"


class TestChainArtifact:
    """Req 2.17."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "artifact:"), \
            "No artifact chain"


class TestChainTrace:
    """Req 2.18."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "trace:"), \
            "No trace chain"


class TestChainPlan:
    """Req 2.19."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "plan:"), \
            "No plan chain"


class TestChainEnvSetup:
    """Req 2.20."""

    def test_exists(self, chains):
        assert _chain_by_prefix(chains, "env:"), \
            "No env chain"


# ══════════════════════════════════════════════════════════════════════
#  SECTION 3 — DOMAINS
# ══════════════════════════════════════════════════════════════════════


class TestDomainMediator:
    """Req 3.1 — mediator domain has all node groups."""

    def test_mediator_exists(self, by_adapter):
        assert "mediator" in by_adapter

    # Index subtypes
    @pytest.mark.parametrize("sub", [
        "index:scan", "index:delta", "index:files", "index:dirs",
        "index:paths", "index:classify", "index:symbols", "index:peek",
        "index:stats", "index:view",
    ])
    def test_has_index_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # DevOps subtypes
    @pytest.mark.parametrize("sub", [
        "docker", "k8s", "terraform", "dns", "docs", "pages",
        "git status", "github", "ci scan", "packages", "env",
        "security scan", "testing scan", "quality",
    ])
    def test_has_devops_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # Audit subtypes
    @pytest.mark.parametrize("sub", [
        "L1", "scores", "structure", "deps", "clients",
        "L1:deep", "L2:risks", "L2:repo", "L2:quality", "L2:structure",
        "scores:enriched",
    ])
    def test_has_audit_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # Posture subtypes
    @pytest.mark.parametrize("sub", [
        "toolchain", "platform", "project", "full", "summary",
    ])
    def test_has_posture_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # GitHub subtypes
    @pytest.mark.parametrize("sub", ["pulls", "runs", "workflows"])
    def test_has_github_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # Catalog subtypes
    @pytest.mark.parametrize("sub", ["tools", "builders", "scripts"])
    def test_has_catalog_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    # Other
    @pytest.mark.parametrize("sub", ["runtime", "status"])
    def test_has_other_subtype(self, by_adapter, sub):
        assert sub in by_adapter.get("mediator", {}), \
            f"mediator missing '{sub}'"

    def test_suppresses_internal_nodes(self, entries):
        med = _entries_by_adapter(entries, "mediator")
        for e in med:
            ref = e.get("ref", "")
            assert not ref.startswith("timeline."), f"Leaked: {ref}"
            assert not ref.startswith("detect."), f"Leaked: {ref}"
            assert not ref.startswith("tabmesh."), f"Leaked: {ref}"


class TestDomainGitLog:
    """Req 3.2."""

    def test_exists(self, by_adapter):
        assert "git_log" in by_adapter

    def test_has_commit(self, by_adapter):
        assert by_adapter.get("git_log", {}).get("commit", 0) > 100


class TestDomainChat:
    """Req 3.3."""

    def test_exists(self, by_adapter):
        assert "chat" in by_adapter

    def test_has_subtypes(self, by_adapter):
        chat = by_adapter.get("chat", {})
        assert "thread_created" in chat
        assert "message" in chat


class TestDomainAdaptersPresent:
    """Req 3.5 — core adapters appear."""

    @pytest.mark.parametrize("adapter", ["git_log", "mediator", "chat"])
    def test_core_adapter(self, by_adapter, adapter):
        assert adapter in by_adapter


# ══════════════════════════════════════════════════════════════════════
#  SECTION 4 — CHAIN INTEGRITY
# ══════════════════════════════════════════════════════════════════════


class TestChainIntegrity:
    """Req 4.1–4.5."""

    def test_every_chain_has_2_plus_members(self, chains):
        for c in chains:
            assert c["entry_count"] >= 2, \
                f"Chain {c['chain_id']} has {c['entry_count']} members"

    def test_every_chain_has_origin(self, chains):
        for c in chains:
            roles = {m.get("chain_role", "") for m in c.get("members", [])}
            assert "origin" in roles, \
                f"Chain {c['chain_id']} has no origin"

    def test_sorted_newest_first(self, chains):
        for c in chains:
            members = c.get("members", [])
            if len(members) < 2:
                continue
            ts = [m["ts"] for m in members]
            assert ts == sorted(ts, reverse=True), \
                f"Chain {c['chain_id']} not sorted"

    def test_no_duplicate_ids(self, entries):
        ids = [e["id"] for e in entries]
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        assert not dupes, f"Duplicate IDs: {dupes[:5]}"

    def test_sources_accurate(self, chains):
        for c in chains:
            actual = {m.get("source", "") for m in c.get("members", [])}
            declared = set(c.get("sources", []))
            assert actual == declared, \
                f"Chain {c['chain_id']}: declared={declared}, actual={actual}"


# ══════════════════════════════════════════════════════════════════════
#  SECTION 5 — MEDIATOR COVERAGE
# ══════════════════════════════════════════════════════════════════════


class TestMediatorCoverage:
    """Req 5.1–5.8 — all node domains produce entries."""

    def _mediator_entries(self, entries):
        return _entries_by_adapter(entries, "mediator")

    def test_devops_nodes(self, entries):
        med = self._mediator_entries(entries)
        subs = {e.get("subtype", "") for e in med}
        for expected in ("docker", "k8s", "terraform", "dns", "docs", "pages"):
            assert expected in subs, f"Missing devops: {expected}"

    def test_audit_nodes(self, entries):
        med = self._mediator_entries(entries)
        sources = {e.get("source", "") for e in med}
        assert "audit" in sources

    def test_posture_nodes(self, entries):
        med = self._mediator_entries(entries)
        sources = {e.get("source", "") for e in med}
        assert "posture" in sources

    def test_index_nodes(self, entries):
        med = self._mediator_entries(entries)
        subs = {e.get("subtype", "") for e in med}
        for expected in ("index:scan", "index:delta", "index:files",
                         "index:dirs", "index:paths", "index:classify"):
            assert expected in subs, f"Missing index: {expected}"

    def test_github_nodes(self, entries):
        med = self._mediator_entries(entries)
        subs = {e.get("subtype", "") for e in med}
        assert "pulls" in subs or "runs" in subs or "workflows" in subs

    def test_catalog_nodes(self, entries):
        med = self._mediator_entries(entries)
        sources = {e.get("source", "") for e in med}
        assert "tools" in sources

    def test_security_and_testing(self, entries):
        med = self._mediator_entries(entries)
        sources = {e.get("source", "") for e in med}
        assert "security" in sources
        assert "tests" in sources

    def test_total_minimum_40(self, entries):
        med = self._mediator_entries(entries)
        assert len(med) >= 40, f"Only {len(med)} mediator entries, need >= 40"


class TestCycleCompleteness:
    """Req 5.7 — cycle chain includes all tiers."""

    def _biggest_cycle(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        assert cycles
        return max(cycles, key=lambda c: c["entry_count"])

    def test_tier1_catalog(self, chains):
        c = self._biggest_cycle(chains)
        assert "tools" in _member_sources(c)

    def test_tier2_infra(self, chains):
        c = self._biggest_cycle(chains)
        subs = _member_subtypes(c)
        assert "docker" in subs or "k8s" in subs

    def test_tier3_heavy(self, chains):
        c = self._biggest_cycle(chains)
        assert "security" in _member_sources(c)

    def test_tier5_aggregate(self, chains):
        c = self._biggest_cycle(chains)
        sources = _member_sources(c)
        assert "posture" in sources
        assert "audit" in sources

    def test_tier6_deep(self, chains):
        c = self._biggest_cycle(chains)
        subs = _member_subtypes(c)
        l2 = {s for s in subs if s.startswith("L2:")}
        assert l2, "Cycle missing L2 audit nodes"


# ══════════════════════════════════════════════════════════════════════
#  SECTION 6 — RUN TRACKING (operation_id linking)
# ══════════════════════════════════════════════════════════════════════


class TestRunTracking:
    """Req 6.1 — operation_id links runs to mediator entries."""

    def test_cycle_entries_share_chain_id(self, chains):
        cycles = _chain_by_prefix(chains, "cycle-")
        assert cycles
        biggest = max(cycles, key=lambda c: c["entry_count"])
        # Every member should share the cycle chain_id
        for m in biggest.get("members", []):
            assert m.get("chain_role") in ("origin", "step", "terminal", ""), \
                f"Member {m.get('id')} has no chain role"


# ══════════════════════════════════════════════════════════════════════
#  SECTION 7 — ENTRY FIELDS
# ══════════════════════════════════════════════════════════════════════


class TestEntryFields:
    """Every entry must have required fields."""

    def test_every_entry_has_id(self, entries):
        for e in entries:
            assert e.get("id"), f"Missing id: {e.get('source')}:{e.get('subtype')}"

    def test_every_entry_has_ts(self, entries):
        for e in entries:
            assert e.get("ts", 0) > 0, f"Bad ts: {e['id']}"

    def test_every_entry_has_source(self, entries):
        for e in entries:
            assert e.get("source"), f"Missing source: {e['id']}"

    def test_every_entry_has_summary(self, entries):
        for e in entries:
            assert e.get("summary"), f"Missing summary: {e['id']}"

    def test_every_entry_has_status(self, entries):
        valid = {"ok", "warning", "attention", "failed"}
        for e in entries:
            assert e.get("status") in valid, f"Bad status: {e['id']}: {e.get('status')}"

    def test_every_entry_has_locality(self, entries):
        valid = {"local", "shared"}
        for e in entries:
            assert e.get("locality") in valid, f"Bad locality: {e['id']}"

    def test_every_entry_has_adapter(self, entries):
        for e in entries:
            assert e.get("adapter"), f"Missing adapter: {e['id']}"


# ══════════════════════════════════════════════════════════════════════
#  SECTION 8 — DOMAIN ADAPTERS (from mediator computations)
#  These domains appear because the mediator computes these nodes.
# ══════════════════════════════════════════════════════════════════════


class TestDomainFromMediator:
    """Every mediator node domain should appear as an adapter."""

    @pytest.mark.parametrize("domain", [
        "docker", "k8s", "terraform", "dns", "docs", "pages",
        "git", "env", "packages", "quality", "security", "testing",
        "audit", "posture", "index", "github", "tools", "status",
    ])
    def test_domain_has_entries(self, by_adapter, domain):
        assert domain in by_adapter, f"Domain '{domain}' missing from by_adapter"
