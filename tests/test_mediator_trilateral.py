"""Tests for Phase W2 — full cascade depth from index.scan through all domains.

Proves the trilateral bridge: one put("index.scan") at the root cascades
through index → detect → devops → posture. This is the SPEC-6 proof.

Posture cascade: posture.project depends on devops.* (wired in Chunk 6).
This means index.scan → detect.* → devops.* → posture.project → posture.full
→ posture.summary. The only posture nodes NOT in the cascade are
posture.platform, posture.toolchain, and posture.runtime (independent scanners).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.detect import register_detect
from src.core.services.mediator.registrations.devops import register_devops
from src.core.services.mediator.registrations.index import register_index
from src.core.services.mediator.registrations.posture import register_posture
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator_all() -> QueryMediator:
    """Mediator with all four domains: index, detect, devops, posture."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_index(m)
    register_detect(m)
    register_devops(m)
    register_posture(m)
    return m


# ── SPEC-6.1: detect.* depends on index.classify ──────────────────


class TestDetectDependsOnIndex:
    """SPEC-6.1: All detect nodes should declare index.classify dependency."""

    def test_all_detect_depend_on_index_classify(
        self, mediator_all: QueryMediator
    ) -> None:
        """Every detect.* node should have index.classify in depends_on."""
        for path in mediator_all.tree.all_paths():
            if not path.startswith("detect."):
                continue
            node = mediator_all.tree.resolve(path)
            assert node is not None
            assert "index.classify" in node.depends_on, (
                f"{path} does not depend on index.classify"
            )


# ── SPEC-6.2: cascade reaches detect ──────────────────────────────


class TestCascadeReachesDetect:
    """SPEC-6.2: put("index.scan") should invalidate all detect.* nodes."""

    def test_cascade_invalidates_all_detect_nodes(
        self, mediator_all: QueryMediator
    ) -> None:
        """Cascade from index.scan should reach all 13 detect nodes."""
        m = mediator_all

        # Trace the dependency graph from index.scan
        all_deps = m.tree.dependents("index.scan")

        # All detect nodes must be in the cascade set
        detect_nodes = {p for p in m.tree.all_paths() if p.startswith("detect.")}
        for dn in detect_nodes:
            assert dn in all_deps, (
                f"{dn} not reachable from index.scan cascade"
            )


# ── SPEC-6.3: cascade reaches devops ──────────────────────────────


class TestCascadeReachesDevops:
    """SPEC-6.3: put("index.scan") should invalidate all devops.* nodes."""

    def test_cascade_invalidates_all_devops_nodes(
        self, mediator_all: QueryMediator
    ) -> None:
        """Cascade from index.scan should reach all 14 devops nodes."""
        m = mediator_all

        all_deps = m.tree.dependents("index.scan")

        devops_nodes = {p for p in m.tree.all_paths() if p.startswith("devops.")}
        for dn in devops_nodes:
            assert dn in all_deps, (
                f"{dn} not reachable from index.scan cascade"
            )


# ── SPEC-6.4: cascade reaches posture via devops.* ────────────────


class TestCascadeReachesPosture:
    """SPEC-6.4: posture.project depends on devops.*, so index.scan
    cascades all the way to posture.project → posture.full → posture.summary.

    posture.platform, toolchain, runtime remain independent (not in cascade).
    """

    def test_posture_project_in_cascade(
        self, mediator_all: QueryMediator
    ) -> None:
        """posture.project should be in index.scan cascade via devops.*."""
        m = mediator_all
        all_deps = m.tree.dependents("index.scan")

        posture_in_cascade = {d for d in all_deps if d.startswith("posture.")}
        assert posture_in_cascade == {
            "posture.project", "posture.full", "posture.summary",
        }, (
            f"Expected project/full/summary in cascade, got: {posture_in_cascade}"
        )

    def test_independent_posture_pillars_not_in_cascade(
        self, mediator_all: QueryMediator
    ) -> None:
        """platform, toolchain, runtime are independent — not in cascade."""
        m = mediator_all
        all_deps = set(m.tree.dependents("index.scan"))

        for pillar in ["posture.platform", "posture.toolchain", "posture.runtime"]:
            assert pillar not in all_deps, (
                f"{pillar} should NOT be in index.scan cascade"
            )


# ── SPEC-6.5: full cascade depth ──────────────────────────────────


class TestFullCascadeDepth:
    """SPEC-6.5: Verify the complete cascade set from index.scan."""

    def test_cascade_set_size(
        self, mediator_all: QueryMediator
    ) -> None:
        """Cascade from index.scan should reach at least 39 nodes.

        8 index dependents + 14 detect + 14 devops + 3 posture = 39 minimum.
        """
        m = mediator_all

        all_deps = m.tree.dependents("index.scan")

        # 8 index (delta, files, dirs, paths, classify, symbols, peek, stats)
        # 14 detect (13 probes + wizard)
        # 14 devops (13 cards + status)
        # 3 posture (project, full, summary — via devops.*)
        assert len(all_deps) >= 39, (
            f"Expected at least 39 nodes in cascade, got {len(all_deps)}: "
            f"{sorted(all_deps)}"
        )

    def test_cascade_includes_all_index_dependents(
        self, mediator_all: QueryMediator
    ) -> None:
        """All 8 index dependent nodes are in the cascade."""
        m = mediator_all

        all_deps = set(m.tree.dependents("index.scan"))

        expected_index = {
            "index.delta", "index.files", "index.dirs", "index.paths",
            "index.classify", "index.symbols", "index.peek", "index.stats",
        }
        missing = expected_index - all_deps
        assert not missing, f"Missing index nodes from cascade: {missing}"

    def test_cascade_map_structure(
        self, mediator_all: QueryMediator
    ) -> None:
        """Verify the cascade chain: scan → classify → detect → devops."""
        m = mediator_all

        # index.classify depends on index.scan
        classify_node = m.tree.resolve("index.classify")
        assert classify_node is not None
        assert "index.scan" in classify_node.depends_on

        # detect.docker depends on index.classify
        docker_node = m.tree.resolve("detect.docker")
        assert docker_node is not None
        assert "index.classify" in docker_node.depends_on

        # devops.docker depends on detect.docker
        devops_docker = m.tree.resolve("devops.docker")
        assert devops_docker is not None
        assert "detect.docker" in devops_docker.depends_on

        # devops.status depends on devops.* (glob)
        devops_status = m.tree.resolve("devops.status")
        assert devops_status is not None
        assert "devops.*" in devops_status.depends_on


# ── SPEC-6.6: single file change → coherent system ────────────────


class TestCoherentInvalidation:
    """SPEC-6.6: put() at root actually invalidates cached data."""

    def test_put_scan_invalidates_detect_cache(
        self, mediator_all: QueryMediator
    ) -> None:
        """After put("index.scan"), detect.docker cache should be gone."""
        m = mediator_all

        # Manually seed cache entries for index.classify and detect.docker
        # (we can't call the real resolvers without real project setup)
        m.put("index.classify", data={"languages": {"py": 100}}, cascade=False)
        m.put("detect.docker", data={"installed": True}, cascade=False)

        # Verify they're cached
        assert m._get_cached("index.classify") is not None
        assert m._get_cached("detect.docker") is not None

        # Fire at the root — cascade should invalidate everything
        result = m.put("index.scan")

        # index.classify should be invalidated
        assert m._get_cached("index.classify") is None, (
            "index.classify should be invalidated after put(index.scan)"
        )

        # detect.docker should be invalidated
        assert m._get_cached("detect.docker") is None, (
            "detect.docker should be invalidated after put(index.scan)"
        )

        # The invalidated list should include both
        invalidated = set(result["invalidated"])
        assert "index.classify" in invalidated
        assert "detect.docker" in invalidated

    def test_put_scan_invalidates_devops_cache(
        self, mediator_all: QueryMediator
    ) -> None:
        """After put("index.scan"), devops.docker cache should be gone."""
        m = mediator_all

        # Seed cache
        m.put("index.classify", data={"languages": {"py": 100}}, cascade=False)
        m.put("detect.docker", data={"installed": True}, cascade=False)
        m.put("devops.docker", data={"status": "ok"}, cascade=False)

        assert m._get_cached("devops.docker") is not None

        # Fire at the root
        result = m.put("index.scan")

        # devops.docker should be invalidated
        assert m._get_cached("devops.docker") is None, (
            "devops.docker should be invalidated after put(index.scan)"
        )

        invalidated = set(result["invalidated"])
        assert "devops.docker" in invalidated
