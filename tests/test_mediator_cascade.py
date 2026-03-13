"""Tests for QueryMediator Phase 4 — Cascade Engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.detect import register_detect
from src.core.services.mediator.registrations.devops import register_devops
from src.core.services.mediator.registrations.posture import register_posture
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator() -> QueryMediator:
    """Full mediator: posture + detect + devops (with inter-deps + aggregate)."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_posture(m)
    register_detect(m)
    register_devops(m)
    return m


# ── Tree structure tests ──────────────────────────────────────────


class TestCascadeTreeStructure:
    """Test the tree after Phase 4 additions."""

    def test_thirty_three_total_nodes(self, mediator: QueryMediator) -> None:
        """33 nodes: 6 posture + 13 detect + 14 devops (13 cards + 1 status)."""
        paths = mediator.tree.all_paths()
        assert len(paths) == 33

    def test_devops_branch_has_fourteen_children(
        self, mediator: QueryMediator
    ) -> None:
        """devops branch now has 14 children (13 cards + status)."""
        children = mediator.tree.children("devops")
        assert len(children) == 14

    def test_devops_status_is_registered(
        self, mediator: QueryMediator
    ) -> None:
        """devops.status should be a registered node with a resolver."""
        node = mediator.tree.resolve("devops.status")
        assert node is not None
        assert node.is_registered
        assert node.resolver is not None
        assert node.ttl is None
        assert node.persist is False


# ── Inter-devops dependency tests ─────────────────────────────────


class TestInterDevopsDependencies:
    """Test that inter-devops dependencies mirror the _CASCADE dict."""

    def test_github_depends_on_git(self, mediator: QueryMediator) -> None:
        node = mediator.tree.resolve("devops.github")
        assert "devops.git" in node.depends_on

    def test_docker_depends_on_git(self, mediator: QueryMediator) -> None:
        node = mediator.tree.resolve("devops.docker")
        assert "devops.git" in node.depends_on

    def test_ci_depends_on_git_docker_github(
        self, mediator: QueryMediator
    ) -> None:
        node = mediator.tree.resolve("devops.ci")
        assert "devops.git" in node.depends_on
        assert "devops.docker" in node.depends_on
        assert "devops.github" in node.depends_on

    def test_k8s_depends_on_docker(self, mediator: QueryMediator) -> None:
        node = mediator.tree.resolve("devops.k8s")
        assert "devops.docker" in node.depends_on

    def test_ci_also_depends_on_detect(self, mediator: QueryMediator) -> None:
        """Inter-devops deps are ADDITIVE, not replacing detect deps."""
        node = mediator.tree.resolve("devops.ci")
        assert "detect.ci" in node.depends_on

    def test_nodes_without_inter_deps_unchanged(
        self, mediator: QueryMediator
    ) -> None:
        """Nodes not in _INTER_DEVOPS_DEPS have only detect.* dependency."""
        for name in ["terraform", "env", "security", "packages",
                     "quality", "testing", "docs"]:
            node = mediator.tree.resolve(f"devops.{name}")
            assert node.depends_on == [f"detect.{name}"], (
                f"devops.{name} deps={node.depends_on}"
            )


# ── Cascade chain tests ──────────────────────────────────────────


class TestCascadeChains:
    """Test the transitive cascade chains."""

    def test_git_cascades_to_github_docker_ci(
        self, mediator: QueryMediator
    ) -> None:
        """devops.git dependents should include github, docker, ci."""
        deps = mediator.tree.dependents("devops.git")
        assert "devops.github" in deps
        assert "devops.docker" in deps
        assert "devops.ci" in deps

    def test_docker_cascades_to_k8s_ci(
        self, mediator: QueryMediator
    ) -> None:
        """devops.docker dependents should include k8s and ci."""
        deps = mediator.tree.dependents("devops.docker")
        assert "devops.k8s" in deps
        assert "devops.ci" in deps

    def test_github_cascades_to_ci(self, mediator: QueryMediator) -> None:
        deps = mediator.tree.dependents("devops.github")
        assert "devops.ci" in deps

    def test_full_chain_from_detect_git(
        self, mediator: QueryMediator
    ) -> None:
        """detect.git should transitively cascade to all git-dependent cards."""
        deps = mediator.tree.dependents("detect.git")
        # Direct: devops.git
        assert "devops.git" in deps
        # Transitive via devops.git:
        assert "devops.docker" in deps
        assert "devops.github" in deps
        assert "devops.ci" in deps
        # Transitive via devops.docker:
        assert "devops.k8s" in deps
        # Aggregate:
        assert "devops.status" in deps

    def test_cascade_invalidation_works(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating detect.git should cascade through the whole chain."""
        m = mediator
        # Populate caches — use cascade=False to avoid clearing
        # dependent entries while seeding
        m.put("detect.git", data={"v": 0}, cascade=False)
        m.put("devops.git", data={"v": 1}, cascade=False)
        m.put("devops.docker", data={"v": 2}, cascade=False)
        m.put("devops.github", data={"v": 3}, cascade=False)
        m.put("devops.ci", data={"v": 4}, cascade=False)
        m.put("devops.k8s", data={"v": 5}, cascade=False)
        m.put("devops.status", data={"v": 6}, cascade=False)

        # Invalidate detect.git with cascade
        result = m.put("detect.git", cascade=True)
        inv = result["invalidated"]

        assert "detect.git" in inv
        assert "devops.git" in inv
        assert "devops.docker" in inv
        assert "devops.github" in inv
        assert "devops.ci" in inv
        assert "devops.k8s" in inv
        assert "devops.status" in inv


# ── Aggregate node tests ──────────────────────────────────────────


class TestAggregateNode:
    """Test devops.status aggregate node."""

    def test_status_depends_on_all_cards(
        self, mediator: QueryMediator
    ) -> None:
        """devops.status should depend on all 13 card nodes via glob."""
        node = mediator.tree.resolve("devops.status")
        # The actual depends_on is ["devops.*"] (glob)
        assert "devops.*" in node.depends_on

    def test_any_card_invalidation_cascades_to_status(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating any devops card should cascade to devops.status."""
        m = mediator
        for card_name in ["docker", "k8s", "git", "github", "ci", "terraform",
                          "env", "security", "packages", "quality", "testing",
                          "docs", "dns"]:
            # Populate status cache (no cascade to avoid clearing it)
            m.put("devops.status", data={"v": "status"}, cascade=False)
            # Populate the card itself so invalidation triggers
            m.put(f"devops.{card_name}", data={"v": card_name}, cascade=False)
            # Invalidate the card
            result = m.put(f"devops.{card_name}", cascade=True)
            assert "devops.status" in result["invalidated"], (
                f"devops.{card_name} didn't cascade to devops.status"
            )


# ── Legacy cascade equivalence tests ──────────────────────────────


class TestLegacyCascadeEquivalence:
    """Test that the mediator cascade produces the same or superset of keys."""

    def test_legacy_cascade_git(self) -> None:
        """_legacy_cascade('git') should produce the same as old _CASCADE."""
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("git")
        assert "git" in keys
        assert "github" in keys
        assert "docker" in keys
        assert "ci" in keys
        assert "pages" in keys
        assert "project-status" in keys

    def test_legacy_cascade_docker(self) -> None:
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("docker")
        assert "docker" in keys
        assert "ci" in keys
        assert "k8s" in keys
        assert "project-status" in keys

    def test_legacy_cascade_github(self) -> None:
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("github")
        assert "github" in keys
        assert "ci" in keys
        assert "project-status" in keys

    def test_legacy_cascade_pages(self) -> None:
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("pages")
        assert "pages" in keys
        assert "dns" in keys
        assert "project-status" in keys

    def test_legacy_cascade_no_cascade(self) -> None:
        """Cards not in _CASCADE should only have themselves + aggregate."""
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("terraform")
        assert keys == ["terraform", "project-status"]

    def test_legacy_cascade_non_integration(self) -> None:
        """Non-integration keys should not get aggregate."""
        from src.core.services.devops.cache import _legacy_cascade

        keys = _legacy_cascade("whatever")
        assert keys == ["whatever"]


# ── Mediator cascade function tests ───────────────────────────────


class TestMediatorCascade:
    """Test the _mediator_cascade function."""

    def test_mediator_cascade_returns_none_without_mediator(self) -> None:
        """When mediator is not initialized, should return None."""
        from src.core.services.devops.cache import _mediator_cascade

        # Mock get_mediator to raise
        with patch(
            "src.core.services.mediator.get_mediator",
            side_effect=RuntimeError("not initialized"),
        ):
            result = _mediator_cascade("docker")
            assert result is None

    def test_mediator_cascade_git(self, mediator: QueryMediator) -> None:
        """Mediator cascade for 'git' should produce superset of legacy."""
        from src.core.services.devops.cache import _mediator_cascade

        with patch(
            "src.core.services.mediator.get_mediator",
            return_value=mediator,
        ):
            keys = _mediator_cascade("git")
            assert keys is not None
            assert "git" in keys
            assert "docker" in keys
            assert "github" in keys
            assert "ci" in keys
            assert "k8s" in keys  # transitive: git → docker → k8s
            assert "project-status" in keys

    def test_mediator_cascade_docker(self, mediator: QueryMediator) -> None:
        from src.core.services.devops.cache import _mediator_cascade

        with patch(
            "src.core.services.mediator.get_mediator",
            return_value=mediator,
        ):
            keys = _mediator_cascade("docker")
            assert keys is not None
            assert "docker" in keys
            assert "k8s" in keys
            assert "ci" in keys
            assert "project-status" in keys

    def test_mediator_cascade_unknown_card(
        self, mediator: QueryMediator
    ) -> None:
        """Unknown card should return None (fallback to legacy)."""
        from src.core.services.devops.cache import _mediator_cascade

        with patch(
            "src.core.services.mediator.get_mediator",
            return_value=mediator,
        ):
            result = _mediator_cascade("pages")
            assert result is None  # no devops.pages node

    def test_mediator_superset_of_legacy_git(
        self, mediator: QueryMediator
    ) -> None:
        """Mediator cascade should be a superset of legacy for 'git'.

        Legacy: git, github, docker, ci, pages, project-status
        Mediator: git, docker, github, ci, k8s, project-status
        (mediator adds k8s transitively, but doesn't have pages)
        """
        from src.core.services.devops.cache import (
            _legacy_cascade,
            _mediator_cascade,
        )

        with patch(
            "src.core.services.mediator.get_mediator",
            return_value=mediator,
        ):
            legacy = set(_legacy_cascade("git"))
            mediator_keys = set(_mediator_cascade("git") or [])

            # Mediator should have all legacy keys EXCEPT 'pages'
            # (no devops.pages node exists)
            expected_common = legacy - {"pages"}
            assert expected_common.issubset(mediator_keys), (
                f"Missing from mediator: {expected_common - mediator_keys}"
            )

            # Mediator should additionally have k8s (transitive)
            assert "k8s" in mediator_keys


# ── Diag tests ────────────────────────────────────────────────────


class TestCascadeDiag:
    """Test diagnostics reflect Phase 4 changes."""

    def test_diag_shows_thirty_three(self, mediator: QueryMediator) -> None:
        info = mediator.diag()
        assert info["tree"]["registered"] == 33

    def test_diag_devops_branch_fourteen(
        self, mediator: QueryMediator
    ) -> None:
        info = mediator.diag("devops")
        assert len(info["children"]) == 14

    def test_diag_status_node(self, mediator: QueryMediator) -> None:
        info = mediator.diag("devops.status")
        assert info["registered"] is True
        assert info["has_resolver"] is True
        assert "devops.*" in info["depends_on"]
