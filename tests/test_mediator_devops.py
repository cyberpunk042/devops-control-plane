"""Tests for QueryMediator Phase 3 — devops domain registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.detect import register_detect
from src.core.services.mediator.registrations.devops import register_devops
from src.core.services.mediator.registrations.posture import register_posture
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator_devops_only() -> QueryMediator:
    """Mediator with detect + devops nodes (devops depends on detect)."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_detect(m)
    register_devops(m)
    return m


@pytest.fixture
def mediator_full() -> QueryMediator:
    """Mediator with all three domains: posture, detect, devops."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_posture(m)
    register_detect(m)
    register_devops(m)
    return m


# ── Registration tests ─────────────────────────────────────────────


EXPECTED_DEVOPS_NODES = {
    "devops.docker",
    "devops.k8s",
    "devops.git",
    "devops.github",
    "devops.ci",
    "devops.terraform",
    "devops.env",
    "devops.security",
    "devops.packages",
    "devops.quality",
    "devops.testing",
    "devops.docs",
    "devops.dns",
}


class TestDevopsRegistration:
    """Test that devops nodes are registered correctly."""

    def test_thirteen_nodes_registered(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """14 devops nodes + 13 detect nodes = 27 total."""
        paths = set(mediator_devops_only.tree.all_paths())
        assert len(paths) == 27
        assert EXPECTED_DEVOPS_NODES.issubset(paths)

    def test_devops_branch_exists(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """devops should be an auto-created branch."""
        node = mediator_devops_only.tree.resolve("devops")
        assert node is not None
        assert node.is_branch
        assert not node.is_registered

    def test_devops_branch_children(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """devops branch should have 14 children (13 cards + status)."""
        children = mediator_devops_only.tree.children("devops")
        assert len(children) == 14

    def test_all_have_resolvers(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """Every registered devops node should have a resolver."""
        for path in EXPECTED_DEVOPS_NODES:
            node = mediator_devops_only.tree.resolve(path)
            assert node is not None
            assert node.resolver is not None, f"{path} has no resolver"


# ── TTL tests ──────────────────────────────────────────────────────


class TestDevopsTTLs:
    """Test that all devops nodes have TTL=None (mtime-delegated)."""

    def test_all_ttl_none(self, mediator_devops_only: QueryMediator) -> None:
        """All devops nodes should have ttl=None."""
        for path in EXPECTED_DEVOPS_NODES:
            node = mediator_devops_only.tree.resolve(path)
            assert node is not None
            assert node.ttl is None, f"{path} has ttl={node.ttl}, expected None"


# ── Persist tests ──────────────────────────────────────────────────


class TestDevopsPersist:
    """All devops nodes should NOT be persisted (delegated to get_cached)."""

    def test_all_not_persisted(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        for path in EXPECTED_DEVOPS_NODES:
            node = mediator_devops_only.tree.resolve(path)
            assert node is not None
            assert node.persist is False, f"{path} should not be persisted"


# ── Dependency tests ────────────────────────────────────────────────


DEPENDENCY_PAIRS = [
    ("devops.docker",    "detect.docker"),
    ("devops.k8s",       "detect.k8s"),
    ("devops.git",       "detect.git"),
    ("devops.github",    "detect.github"),
    ("devops.ci",        "detect.ci"),
    ("devops.terraform", "detect.terraform"),
    ("devops.env",       "detect.env"),
    ("devops.security",  "detect.security"),
    ("devops.packages",  "detect.packages"),
    ("devops.quality",   "detect.quality"),
    ("devops.testing",   "detect.testing"),
    ("devops.docs",      "detect.docs"),
    ("devops.dns",       "detect.dns"),
]


class TestDevopsDependencies:
    """Test detect.* → devops.* dependency chain."""

    @pytest.mark.parametrize("devops_path,detect_path", DEPENDENCY_PAIRS)
    def test_depends_on(
        self,
        mediator_devops_only: QueryMediator,
        devops_path: str,
        detect_path: str,
    ) -> None:
        """Each devops node should depend on its corresponding detect node."""
        node = mediator_devops_only.tree.resolve(devops_path)
        assert node is not None
        assert detect_path in node.depends_on, (
            f"{devops_path} depends_on={node.depends_on}, "
            f"expected {detect_path}"
        )

    @pytest.mark.parametrize("devops_path,detect_path", DEPENDENCY_PAIRS)
    def test_reverse_dependent(
        self,
        mediator_devops_only: QueryMediator,
        devops_path: str,
        detect_path: str,
    ) -> None:
        """Each detect node should list its devops node as a dependent."""
        deps = mediator_devops_only.tree.dependents(detect_path)
        assert devops_path in deps, (
            f"dependents({detect_path})={deps}, expected {devops_path}"
        )

    def test_detect_nodes_have_no_depends_on(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """Detect nodes should still have no dependencies."""
        for path in mediator_devops_only.tree.all_paths():
            if path.startswith("detect."):
                node = mediator_devops_only.tree.resolve(path)
                assert node is not None
                assert node.depends_on == [], (
                    f"{path} has depends_on={node.depends_on}"
                )


# ── Cascade tests ──────────────────────────────────────────────────


class TestDevopsCascade:
    """Test cascade from detect.* → devops.*."""

    def test_invalidate_detect_cascades_to_devops(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """Invalidating detect.docker should cascade to devops.docker."""
        m = mediator_devops_only
        # Pre-populate both caches with dummy data
        m.put("detect.docker", data={"test": "detect-value"})
        m.put("devops.docker", data={"test": "devops-value"})

        # Verify both are cached
        r1 = m.get("detect.docker")
        assert r1["meta"]["source"] == "cache"
        r2 = m.get("devops.docker")
        assert r2["meta"]["source"] == "cache"

        # Invalidate detect.docker → should cascade to devops.docker
        result = m.put("detect.docker", cascade=True)
        assert "detect.docker" in result["invalidated"]
        assert "devops.docker" in result["invalidated"]

    def test_invalidate_devops_does_not_cascade_to_detect(
        self, mediator_devops_only: QueryMediator
    ) -> None:
        """Invalidating devops.docker should NOT cascade up to detect.docker."""
        m = mediator_devops_only
        m.put("detect.docker", data={"test": "detect-value"})
        m.put("devops.docker", data={"test": "devops-value"})

        result = m.put("devops.docker", cascade=True)
        # devops.docker invalidated, but detect.docker should NOT be
        assert "devops.docker" in result["invalidated"]
        assert "detect.docker" not in result["invalidated"]

        # detect.docker should still be cached
        r = m.get("detect.docker")
        assert r["meta"]["source"] == "cache"


# ── Combined tree tests ───────────────────────────────────────────


class TestCombinedTree:
    """Test all three domains coexist correctly."""

    def test_thirty_two_total_nodes(
        self, mediator_full: QueryMediator
    ) -> None:
        """Combined tree should have 33 registered nodes."""
        paths = mediator_full.tree.all_paths()
        assert len(paths) == 33

    def test_three_top_level_branches(
        self, mediator_full: QueryMediator
    ) -> None:
        """Tree should have three top-level branches."""
        top = mediator_full.tree.children("")
        names = sorted(c.path for c in top)
        assert names == ["detect", "devops", "posture"]

    def test_posture_cascade_still_works(
        self, mediator_full: QueryMediator
    ) -> None:
        """Posture cascade should still be intact."""
        deps = mediator_full.tree.dependents("posture.toolchain")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_cross_domain_cascade(
        self, mediator_full: QueryMediator
    ) -> None:
        """detect → devops cascade in full tree."""
        deps = mediator_full.tree.dependents("detect.k8s")
        assert "devops.k8s" in deps


# ── Diag tests ─────────────────────────────────────────────────────


class TestDevopsDiag:
    """Test diagnostics for devops nodes."""

    def test_diag_summary_shows_thirty_two(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag() should show 33 registered nodes."""
        info = mediator_full.diag()
        assert info["tree"]["registered"] == 33

    def test_diag_devops_branch(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag('devops') should show branch info."""
        info = mediator_full.diag("devops")
        assert info["path"] == "devops"
        assert info["registered"] is False
        assert info["is_branch"] is True
        assert len(info["children"]) == 14

    def test_diag_devops_docker_detail(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag('devops.docker') should show correct metadata."""
        info = mediator_full.diag("devops.docker")
        assert info["path"] == "devops.docker"
        assert info["registered"] is True
        assert info["has_resolver"] is True
        assert info["ttl"] is None
        assert info["persist"] is False
        assert info["cached"] is False
        assert "detect.docker" in info["depends_on"]

    def test_diag_persistent_count(
        self, mediator_full: QueryMediator
    ) -> None:
        """Persistent count should be 16 (posture + detect only).

        posture: platform, toolchain, project, full, summary = 5
        detect: all except git and env = 11
        devops: all False = 0
        """
        info = mediator_full.diag()
        assert info["tree"]["persistent"] == 16
