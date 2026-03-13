"""Tests for QueryMediator Phase 2 — detection domain registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.detect import register_detect
from src.core.services.mediator.registrations.index import register_index
from src.core.services.mediator.registrations.posture import register_posture
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator_detect() -> QueryMediator:
    """Mediator with index + detect nodes (detect depends on index.classify)."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_index(m)
    register_detect(m)
    return m


@pytest.fixture
def mediator_full() -> QueryMediator:
    """Mediator with posture, index, and detect nodes registered."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_posture(m)
    register_index(m)
    register_detect(m)
    return m


# ── Registration tests ─────────────────────────────────────────────


EXPECTED_DETECT_NODES = {
    "detect.docker",
    "detect.k8s",
    "detect.git",
    "detect.github",
    "detect.ci",
    "detect.terraform",
    "detect.env",
    "detect.security",
    "detect.packages",
    "detect.quality",
    "detect.testing",
    "detect.docs",
    "detect.dns",
}


class TestDetectRegistration:
    """Test that detect nodes are registered correctly."""

    def test_thirteen_detect_nodes_registered(
        self, mediator_detect: QueryMediator
    ) -> None:
        """All 13 detect nodes should be registered (plus 9 index nodes)."""
        paths = set(mediator_detect.tree.all_paths())
        detect_paths = {p for p in paths if p.startswith("detect.")}
        assert len(detect_paths) == 13
        assert detect_paths == EXPECTED_DETECT_NODES

    def test_detect_branch_exists(
        self, mediator_detect: QueryMediator
    ) -> None:
        """detect should be an auto-created branch."""
        node = mediator_detect.tree.resolve("detect")
        assert node is not None
        assert node.is_branch
        assert not node.is_registered  # auto-created

    def test_detect_branch_children(
        self, mediator_detect: QueryMediator
    ) -> None:
        """detect branch should have 13 children."""
        children = mediator_detect.tree.children("detect")
        assert len(children) == 13

    def test_all_have_resolvers(
        self, mediator_detect: QueryMediator
    ) -> None:
        """Every registered detect node should have a resolver."""
        for path in mediator_detect.tree.all_paths():
            node = mediator_detect.tree.resolve(path)
            assert node is not None
            assert node.resolver is not None, f"{path} has no resolver"


# ── TTL tests ──────────────────────────────────────────────────────


class TestDetectTTLs:
    """Test that TTLs are set correctly per plan."""

    def test_docker_ttl(self, mediator_detect: QueryMediator) -> None:
        node = mediator_detect.tree.resolve("detect.docker")
        assert node is not None
        assert node.ttl == 120

    def test_k8s_ttl(self, mediator_detect: QueryMediator) -> None:
        node = mediator_detect.tree.resolve("detect.k8s")
        assert node is not None
        assert node.ttl == 120

    def test_git_ttl_shorter(self, mediator_detect: QueryMediator) -> None:
        """Git has shorter TTL (30s) because it changes frequently."""
        node = mediator_detect.tree.resolve("detect.git")
        assert node is not None
        assert node.ttl == 30

    def test_env_ttl_medium(self, mediator_detect: QueryMediator) -> None:
        """Env has medium TTL (60s)."""
        node = mediator_detect.tree.resolve("detect.env")
        assert node is not None
        assert node.ttl == 60

    def test_infra_nodes_120s(self, mediator_detect: QueryMediator) -> None:
        """Infrastructure nodes should all have 120s TTL."""
        infra_nodes = [
            "detect.docker", "detect.k8s", "detect.terraform",
            "detect.dns", "detect.github", "detect.ci",
            "detect.security", "detect.packages", "detect.quality",
            "detect.testing", "detect.docs",
        ]
        for path in infra_nodes:
            node = mediator_detect.tree.resolve(path)
            assert node is not None
            assert node.ttl == 120, f"{path} has ttl={node.ttl}, expected 120"


# ── Persist flag tests ─────────────────────────────────────────────


class TestDetectPersist:
    """Test that persist flags are set correctly."""

    def test_git_not_persisted(self, mediator_detect: QueryMediator) -> None:
        """detect.git should NOT be persisted (changes too often)."""
        node = mediator_detect.tree.resolve("detect.git")
        assert node is not None
        assert node.persist is False

    def test_env_not_persisted(self, mediator_detect: QueryMediator) -> None:
        """detect.env should NOT be persisted."""
        node = mediator_detect.tree.resolve("detect.env")
        assert node is not None
        assert node.persist is False

    def test_infra_persisted(self, mediator_detect: QueryMediator) -> None:
        """All infrastructure detect nodes should be persisted."""
        persisted = [
            "detect.docker", "detect.k8s", "detect.terraform",
            "detect.dns", "detect.github", "detect.ci",
            "detect.security", "detect.packages", "detect.quality",
            "detect.testing", "detect.docs",
        ]
        for path in persisted:
            node = mediator_detect.tree.resolve(path)
            assert node is not None
            assert node.persist is True, f"{path} should be persisted"


# ── Dependency tests (detect depends on index.classify) ────────────


class TestDetectDependencies:
    """All detect nodes depend on index.classify (trilateral wiring)."""

    def test_depends_on_index_classify(
        self, mediator_detect: QueryMediator
    ) -> None:
        """Every detect node should depend on index.classify."""
        for path in mediator_detect.tree.all_paths():
            if not path.startswith("detect."):
                continue
            node = mediator_detect.tree.resolve(path)
            assert node is not None
            assert "index.classify" in node.depends_on, (
                f"{path} does not depend on index.classify"
            )

    def test_no_dependents_without_devops(
        self, mediator_detect: QueryMediator
    ) -> None:
        """Detect nodes have no dependents until devops is registered."""
        for path in mediator_detect.tree.all_paths():
            if not path.startswith("detect."):
                continue
            deps = mediator_detect.tree.dependents(path)
            assert deps == [], f"{path} has dependents={deps}"


# ── Combined tree tests ───────────────────────────────────────────


class TestCombinedTree:
    """Test that posture + detect registrations coexist correctly."""

    def test_combined_total_nodes(
        self, mediator_full: QueryMediator
    ) -> None:
        """Combined tree should have 28 registered nodes (6 posture + 9 index + 13 detect)."""
        paths = mediator_full.tree.all_paths()
        assert len(paths) == 28

    def test_three_top_level_branches(
        self, mediator_full: QueryMediator
    ) -> None:
        """Tree should have three top-level branches: detect, index, posture."""
        top = mediator_full.tree.children("")
        names = sorted(c.path for c in top)
        assert names == ["detect", "index", "posture"]

    def test_posture_still_works(
        self, mediator_full: QueryMediator
    ) -> None:
        """Posture nodes should still be intact with cascade."""
        deps = mediator_full.tree.dependents("posture.toolchain")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_detect_nodes_present(
        self, mediator_full: QueryMediator
    ) -> None:
        """All 13 detect nodes should be present alongside posture."""
        paths = set(mediator_full.tree.all_paths())
        assert EXPECTED_DETECT_NODES.issubset(paths)


# ── Diag tests ─────────────────────────────────────────────────────


class TestDetectDiag:
    """Test diagnostics for detect nodes."""

    def test_diag_summary_shows_twenty_eight(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag() should show 28 registered nodes (6 posture + 9 index + 13 detect)."""
        info = mediator_full.diag()
        assert info["tree"]["registered"] == 28

    def test_diag_detect_branch(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag('detect') should show branch info."""
        info = mediator_full.diag("detect")
        assert info["path"] == "detect"
        assert info["registered"] is False
        assert info["is_branch"] is True
        assert len(info["children"]) == 13

    def test_diag_docker_detail(
        self, mediator_full: QueryMediator
    ) -> None:
        """diag('detect.docker') should show correct metadata."""
        info = mediator_full.diag("detect.docker")
        assert info["path"] == "detect.docker"
        assert info["registered"] is True
        assert info["has_resolver"] is True
        assert info["ttl"] == 120
        assert info["persist"] is True
        assert info["cached"] is False  # not computed yet
        assert info["depends_on"] == ["index.classify"]

    def test_diag_persistent_count(
        self, mediator_full: QueryMediator
    ) -> None:
        """Persistent count: 5 posture + 11 detect + index persist nodes."""
        info = mediator_full.diag()
        # posture: platform, toolchain, project, full, summary = 5
        # detect: all except git and env = 11
        # index: varies (scan, symbols, peek, classify have persist)
        assert info["tree"]["persistent"] >= 16
