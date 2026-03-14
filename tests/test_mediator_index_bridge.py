"""
Tests for Phase 8F — backwards compatibility bridge.

Verifies that get_index() returns mediator-backed data when the
mediator is initialized, and falls back to the legacy singleton
when it's not.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.index import register_index
from src.core.services.mediator.tree import DataTree


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a project structure for bridge testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "src" / "utils.py").write_text(
        "class Helper:\n    def run(self): pass\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text(
        "# Project\n\nSee `main.py` for entry point.\n"
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    return tmp_path


@pytest.fixture
def mediator(project: Path) -> QueryMediator:
    """Create a mediator with index nodes registered and computed.

    Mirrors the real startup: register nodes, then compute them
    (as the watcher does on first cycle).  This warms the cache
    so peek() returns data in bridge tests.
    """
    tree = DataTree()
    m = QueryMediator(tree, project)
    register_index(m)

    # Simulate watcher first cycle: compute all index nodes in order
    for path in [
        "index.scan", "index.delta", "index.files", "index.dirs",
        "index.paths", "index.classify", "index.symbols", "index.peek",
        "index.stats",
    ]:
        m.get(path, force=True)

    return m


# ── Bridge tests ────────────────────────────────────────────────


class TestIndexBridge:
    """Tests for the get_index() mediator bridge."""

    def test_bridge_returns_ready_index(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When mediator is initialized, get_index() returns ready=True."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        assert idx.ready is True

    def test_bridge_has_file_map(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge index should contain file_map entries."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        assert "main.py" in idx.file_map
        assert "utils.py" in idx.file_map

    def test_bridge_has_dir_map(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge index should contain dir_map entries."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        assert "src" in idx.dir_map or "src/" in idx.dir_map

    def test_bridge_has_all_paths(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge index should have all_paths populated."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        assert isinstance(idx.all_paths, set)
        assert len(idx.all_paths) > 0

    def test_bridge_does_not_provide_symbols(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge now provides symbols (deadlock fixed in C1)."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        # Symbols are loaded from mediator (peek.py no longer cycles through bridge)
        assert idx.symbols_ready is True

    def test_bridge_does_not_provide_peek(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge now provides peek (deadlock fixed in C1)."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        # Peek is loaded from mediator (peek.py no longer cycles through bridge)
        assert idx.peek_cached is True

    def test_fallback_when_no_mediator(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When mediator is not initialized, fall back to legacy singleton."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", None)

        from src.core.services.project_index import get_index

        idx = get_index()
        # Legacy singleton starts with ready=False
        assert idx.ready is False

    def test_bridge_file_count(
        self, mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bridge should report correct file count."""
        import src.core.services.mediator as med_mod

        monkeypatch.setattr(med_mod, "mediator", mediator)

        from src.core.services.project_index import get_index

        idx = get_index()
        assert idx.file_count > 0
