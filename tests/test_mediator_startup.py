"""Tests for Phase W3 — startup sequence verification.

Verifies that after the full registration sequence (as done by server.py),
all nodes exist, the dependency graph is correct, and the tree is ready
for the watcher to drive.

SPEC-9.1 through SPEC-9.5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations import register_all
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator_startup() -> QueryMediator:
    """Simulate the exact server.py startup path.

    This mirrors what server.py does:
      1. mediator_init(project_root) → creates empty DataTree + QueryMediator
      2. register_all(mediator) → registers index, detect, devops, posture
    """
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_all(m)
    return m


# ── SPEC-9.1: All domains registered ──────────────────────────────


class TestAllDomainsRegistered:
    """After startup, all five domains should have their nodes."""

    def test_total_node_count(
        self, mediator_startup: QueryMediator
    ) -> None:
        """Should have 52 registered nodes (9 index + 13 detect + 14 devops + 6 posture + 10 extra)."""
        paths = mediator_startup.tree.all_paths()
        assert len(paths) == 52, (
            f"Expected 52 nodes, got {len(paths)}: {sorted(paths)}"
        )

    def test_four_domains_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All five top-level branches should exist."""
        top = mediator_startup.tree.children("")
        names = sorted(c.path for c in top)
        assert names == ["detect", "devops", "extra", "index", "posture"], (
            f"Expected 5 domains, got: {names}"
        )

    def test_index_nodes_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All 9 index nodes registered."""
        expected = {
            "index.scan", "index.delta", "index.files", "index.dirs",
            "index.paths", "index.classify", "index.symbols",
            "index.peek", "index.stats",
        }
        paths = set(mediator_startup.tree.all_paths())
        missing = expected - paths
        assert not missing, f"Missing index nodes: {missing}"

    def test_detect_nodes_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All 13 detect nodes registered."""
        detect = {p for p in mediator_startup.tree.all_paths() if p.startswith("detect.")}
        assert len(detect) == 13

    def test_devops_nodes_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All 14 devops nodes registered (13 cards + status)."""
        devops = {p for p in mediator_startup.tree.all_paths() if p.startswith("devops.")}
        assert len(devops) == 14

    def test_posture_nodes_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All 6 posture nodes registered."""
        posture = {p for p in mediator_startup.tree.all_paths() if p.startswith("posture.")}
        assert len(posture) == 6

    def test_extra_nodes_present(
        self, mediator_startup: QueryMediator
    ) -> None:
        """All 10 extra nodes registered."""
        extra = {p for p in mediator_startup.tree.all_paths() if p.startswith("extra.")}
        assert len(extra) == 10


# ── SPEC-9.2: Registration order is correct ───────────────────────


class TestRegistrationOrder:
    """Dependencies should all be resolvable (no dangling depends_on)."""

    def test_no_dangling_dependencies(
        self, mediator_startup: QueryMediator
    ) -> None:
        """Every depends_on target should exist as a registered node or glob."""
        all_paths = set(mediator_startup.tree.all_paths())

        for path in all_paths:
            node = mediator_startup.tree.resolve(path)
            assert node is not None
            for dep in node.depends_on:
                if "*" in dep:
                    # Glob dependency (e.g. "devops.*") — pattern, not literal
                    continue
                assert dep in all_paths, (
                    f"{path} depends on '{dep}' which is not registered"
                )

    def test_all_nodes_have_resolvers(
        self, mediator_startup: QueryMediator
    ) -> None:
        """Every registered node should have a resolver function."""
        for path in mediator_startup.tree.all_paths():
            node = mediator_startup.tree.resolve(path)
            assert node is not None
            assert node.resolver is not None, f"{path} has no resolver"


# ── SPEC-9.3: Dependency graph integrity ───────────────────────────


class TestDependencyGraph:
    """The full dependency chain should be intact after startup."""

    def test_index_to_detect_chain(
        self, mediator_startup: QueryMediator
    ) -> None:
        """index.classify → all detect.* nodes."""
        deps = mediator_startup.tree.dependents("index.classify")
        detect_nodes = {p for p in mediator_startup.tree.all_paths() if p.startswith("detect.")}
        for dn in detect_nodes:
            assert dn in deps, f"{dn} not dependent on index.classify"

    def test_detect_to_devops_chain(
        self, mediator_startup: QueryMediator
    ) -> None:
        """Each detect.X → devops.X."""
        cards = [
            "docker", "k8s", "git", "github", "ci", "terraform",
            "env", "security", "packages", "quality", "testing",
            "docs", "dns",
        ]
        for card in cards:
            devops_node = mediator_startup.tree.resolve(f"devops.{card}")
            assert devops_node is not None
            assert f"detect.{card}" in devops_node.depends_on, (
                f"devops.{card} does not depend on detect.{card}"
            )

    def test_devops_to_devops_status_chain(
        self, mediator_startup: QueryMediator
    ) -> None:
        """devops.status depends on devops.* (glob)."""
        status_node = mediator_startup.tree.resolve("devops.status")
        assert status_node is not None
        assert "devops.*" in status_node.depends_on

    def test_posture_internal_chain(
        self, mediator_startup: QueryMediator
    ) -> None:
        """posture.full depends on 4 pillars, posture.summary depends on full."""
        full_node = mediator_startup.tree.resolve("posture.full")
        assert full_node is not None
        assert "posture.platform" in full_node.depends_on
        assert "posture.toolchain" in full_node.depends_on
        assert "posture.project" in full_node.depends_on
        assert "posture.runtime" in full_node.depends_on

        summary_node = mediator_startup.tree.resolve("posture.summary")
        assert summary_node is not None
        assert "posture.full" in summary_node.depends_on

    def test_full_cascade_from_scan(
        self, mediator_startup: QueryMediator
    ) -> None:
        """put("index.scan") cascades to at least 35 nodes."""
        all_deps = mediator_startup.tree.dependents("index.scan")
        assert len(all_deps) >= 35, (
            f"Cascade from index.scan got only {len(all_deps)} nodes, "
            f"expected ≥35: {sorted(all_deps)}"
        )


# ── SPEC-9.4: Diag is functional after startup ────────────────────


class TestDiagAfterStartup:
    """diag() should return accurate info after full registration."""

    def test_diag_summary(
        self, mediator_startup: QueryMediator
    ) -> None:
        """diag() should show 52 registered nodes."""
        info = mediator_startup.diag()
        assert info["tree"]["registered"] == 52

    def test_diag_node_detail(
        self, mediator_startup: QueryMediator
    ) -> None:
        """diag('index.scan') should show correct metadata."""
        info = mediator_startup.diag("index.scan")
        assert info["path"] == "index.scan"
        assert info["registered"] is True
        assert info["has_resolver"] is True
