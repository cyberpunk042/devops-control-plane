"""
Event Sourcing — Integration Tests.

Tests the REAL system end-to-end:
  1. Creates a mediator with event store
  2. Runs a full index cycle (mediator computes every node)
  3. Verifies every event has semantic types, rich summaries,
     result data, and proper chain linkage

No fake data. No simulation. Everything from real mediator computations.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ══════════════════════════════════════════════════════════════════════
#  INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════


def _run_full_cycle():
    from src.core.services.mediator.core import QueryMediator
    from src.core.services.mediator.tree import DataTree
    from src.core.services.mediator.registrations import register_all
    from src.core.services.events.correlation import set_correlation, clear_correlation
    from src.core.services.events.models import Event

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

    store.append(Event(
        id="", ts=time.time(), type="index.cycle.started",
        correlation_id=cycle_id, source="watcher",
        summary="Test cycle started",
    ))

    set_correlation(cycle_id)
    computed = []
    for path in sorted(mediator.tree.all_paths()):
        if path.startswith("timeline."):
            continue
        try:
            mediator.get(path, force=True)
            computed.append(path)
        except Exception:
            pass
    clear_correlation()

    store.append(Event(
        id="", ts=time.time(), type="index.cycle.completed",
        correlation_id=cycle_id, source="watcher",
        summary=f"Test cycle: {len(computed)} nodes",
    ))

    result = mediator.get("timeline.data", force=True)
    data = result["data"]

    return {
        "store": store,
        "mediator": mediator,
        "cycle_id": cycle_id,
        "computed": computed,
        "entries": data["entries"],
        "chains": data["chains"],
        "facets": data["facets"],
        "calendar": data["calendar"],
        "by_adapter": data["facets"].get("by_adapter", {}),
    }


@pytest.fixture(scope="module")
def system():
    return _run_full_cycle()

@pytest.fixture(scope="module")
def store(system):
    return system["store"]

@pytest.fixture(scope="module")
def entries(system):
    return system["entries"]

@pytest.fixture(scope="module")
def chains(system):
    return system["chains"]

@pytest.fixture(scope="module")
def by_adapter(system):
    return system["by_adapter"]

@pytest.fixture(scope="module")
def cycle_id(system):
    return system["cycle_id"]


def _chains_by_prefix(chains, prefix):
    return [c for c in chains if c["chain_id"].startswith(prefix)]


# ══════════════════════════════════════════════════════════════════════
#  1. EVENT STORE — events are recorded with semantic types
# ══════════════════════════════════════════════════════════════════════


class TestEventStoreBasics:

    def test_has_events(self, store):
        assert store.count() > 0

    def test_has_40_plus_events(self, store):
        assert store.count() >= 40

    def test_every_event_has_id(self, store):
        for e in store.all_events():
            assert e.id and e.id.startswith("evt-")

    def test_every_event_has_type(self, store):
        for e in store.all_events():
            assert e.type
            assert "." in e.type, f"Event type not dotted: {e.type}"

    def test_events_have_semantic_types(self, store, cycle_id):
        """Events should have types like docker.scanned, not mediator.computed."""
        events = store.query(correlation_id=cycle_id)
        types = {e.type for e in events}
        # Should have semantic types, not just mediator.computed
        non_generic = {t for t in types if not t.startswith("mediator.") and not t.startswith("index.cycle.")}
        assert len(non_generic) >= 20, \
            f"Only {len(non_generic)} semantic types, expected >= 20: {sorted(non_generic)}"

    def test_every_event_has_summary(self, store):
        for e in store.all_events():
            assert e.summary, f"Event {e.id} ({e.type}) missing summary"


class TestEventStoreCorrelation:

    def test_cycle_events_share_correlation(self, store, cycle_id):
        events = store.query(correlation_id=cycle_id)
        assert len(events) >= 40

    def test_cycle_has_lifecycle_events(self, store, cycle_id):
        events = store.query(correlation_id=cycle_id)
        types = {e.type for e in events}
        assert "index.cycle.started" in types
        assert "index.cycle.completed" in types


class TestEventRichData:
    """Events carry result summaries and detail."""

    def test_events_have_duration(self, store, cycle_id):
        events = store.query(correlation_id=cycle_id)
        computed = [e for e in events if not e.type.startswith("index.cycle.")]
        for e in computed:
            assert e.duration_ms >= 0

    def test_events_have_result_data(self, store, cycle_id):
        """Events should carry result summaries in detail."""
        events = store.query(correlation_id=cycle_id)
        with_result = [e for e in events
                       if e.detail.get("result") and not e.type.startswith("index.cycle.")]
        assert len(with_result) >= 10, \
            f"Only {len(with_result)} events with result data, expected >= 10"

    def test_summaries_are_descriptive(self, store, cycle_id):
        """Summaries should describe what was found, not just the path."""
        events = store.query(correlation_id=cycle_id)
        descriptive = 0
        for e in events:
            if e.type.startswith("index.cycle."):
                continue
            # A descriptive summary has more than just a path name
            if len(e.summary) > 10 and e.summary != e.path:
                descriptive += 1
        assert descriptive >= 15, \
            f"Only {descriptive} descriptive summaries, expected >= 15"


class TestEventPersistence:

    def test_jsonl_exists(self, store):
        files = list(store._events_dir.glob("*.jsonl"))
        assert files

    def test_jsonl_has_content(self, store):
        files = list(store._events_dir.glob("*.jsonl"))
        total = sum(len(f.read_text().strip().split("\n")) for f in files)
        assert total >= 40


# ══════════════════════════════════════════════════════════════════════
#  2. SEMANTIC EVENT TYPES — every domain produces typed events
# ══════════════════════════════════════════════════════════════════════


class TestSemanticEventTypes:
    """Every mediator domain produces events with semantic types."""

    def _cycle_types(self, store, cycle_id):
        events = store.query(correlation_id=cycle_id)
        return {e.type for e in events}

    # Index
    @pytest.mark.parametrize("event_type", [
        "index.scanned", "index.delta.computed",
        "index.classified",
    ])
    def test_index_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # DevOps
    @pytest.mark.parametrize("event_type", [
        "docker.scanned", "k8s.scanned", "terraform.scanned",
        "git.status.scanned", "ci.scanned",
        "env.scanned", "security.scanned", "packages.scanned",
        "quality.scanned", "testing.scanned", "docs.scanned",
        "dns.scanned",
    ])
    def test_devops_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # Audit
    @pytest.mark.parametrize("event_type", [
        "audit.scores.computed", "audit.system.scanned",
        "audit.deps.scanned", "audit.structure.scanned",
        "audit.clients.scanned",
    ])
    def test_audit_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # Audit L2
    @pytest.mark.parametrize("event_type", [
        "audit.system.deep_scanned",
        "audit.l2.risks.analyzed", "audit.l2.repo.analyzed",
        "audit.l2.quality.analyzed", "audit.l2.structure.analyzed",
        "audit.scores.enriched",
    ])
    def test_audit_l2_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # Posture
    @pytest.mark.parametrize("event_type", [
        "posture.platform.scanned", "posture.project.assessed",
        "posture.toolchain.scanned",
    ])
    def test_posture_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # GitHub
    @pytest.mark.parametrize("event_type", [
        "github.pulls.fetched", "github.runs.fetched",
        "github.workflows.fetched",
    ])
    def test_github_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)

    # Catalog
    @pytest.mark.parametrize("event_type", [
        "catalog.tools.scanned", "catalog.builders.scanned",
        "catalog.scripts.scanned", "pages.scanned",
    ])
    def test_catalog_type(self, store, cycle_id, event_type):
        assert event_type in self._cycle_types(store, cycle_id)


# ══════════════════════════════════════════════════════════════════════
#  3. DOMAINS — every domain appears in timeline facets
# ══════════════════════════════════════════════════════════════════════


class TestTimelineDomains:

    @pytest.mark.parametrize("domain", [
        "docker", "k8s", "terraform", "dns", "docs", "pages",
        "git", "env", "packages", "quality", "security", "testing",
        "audit", "posture", "index", "github", "catalog",
    ])
    def test_domain_in_by_adapter(self, by_adapter, domain):
        assert domain in by_adapter, f"Domain '{domain}' missing"

    def test_mediator_aggregate_exists(self, by_adapter):
        assert "mediator" in by_adapter


# ══════════════════════════════════════════════════════════════════════
#  4. CHAINS — cycle produces domain sub-chains
# ══════════════════════════════════════════════════════════════════════


class TestCycleChains:

    def test_cycle_chain_exists(self, chains, cycle_id):
        cycle = _chains_by_prefix(chains, cycle_id)
        assert cycle

    def test_has_domain_sub_chains(self, chains, cycle_id):
        """Cycle should split into audit, index, github, catalog sub-chains."""
        sub = _chains_by_prefix(chains, f"{cycle_id}:")
        assert len(sub) >= 3, \
            f"Only {len(sub)} domain sub-chains, expected >= 3"

    def test_audit_sub_chain(self, chains, cycle_id):
        audit = _chains_by_prefix(chains, f"{cycle_id}:audit")
        assert audit, "No audit sub-chain"
        assert audit[0]["entry_count"] >= 5

    def test_index_sub_chain(self, chains, cycle_id):
        idx = _chains_by_prefix(chains, f"{cycle_id}:index")
        assert idx, "No index sub-chain"
        assert idx[0]["entry_count"] >= 5

    def test_github_sub_chain(self, chains, cycle_id):
        gh = _chains_by_prefix(chains, f"{cycle_id}:github")
        assert gh, "No github sub-chain"

    def test_catalog_sub_chain(self, chains, cycle_id):
        cat = _chains_by_prefix(chains, f"{cycle_id}:catalog")
        assert cat, "No catalog sub-chain"


class TestExternalChains:

    def test_git_chain(self, chains):
        git = _chains_by_prefix(chains, "git:")
        assert git
        biggest = max(git, key=lambda c: c["entry_count"])
        assert biggest["entry_count"] > 10

    def test_chat_chains(self, chains):
        chat = [c for c in chains if "chat" in c.get("sources", [])]
        assert chat


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

    def test_no_duplicate_ids(self, entries):
        ids = [e["id"] for e in entries]
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        assert not dupes, f"Duplicate IDs: {dupes[:5]}"


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

    def test_total_entries(self, entries):
        assert len(entries) >= 100

    def test_total_chains(self, chains):
        assert len(chains) >= 5

    def test_total_domains(self, by_adapter):
        assert len(by_adapter) >= 15

    def test_event_store_events(self, store):
        assert store.count() >= 40

    def test_has_calendar(self, system):
        assert len(system["calendar"]) > 0
