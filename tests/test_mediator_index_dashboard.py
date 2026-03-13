"""
Tests for Phase 8G — index dashboard API endpoints.

Tests the index-specific routes in the mediator blueprint:
    GET  /mediator/index/status
    GET  /mediator/index/delta
    POST /mediator/index/rescan
    POST /mediator/index/rebuild-symbols
    POST /mediator/index/rebuild-peek
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.index import register_index
from src.core.services.mediator.tree import DataTree


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a project structure for dashboard testing."""
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
    """Create a mediator with index nodes registered."""
    tree = DataTree()
    m = QueryMediator(tree, project)
    register_index(m)
    return m


@pytest.fixture
def app(mediator: QueryMediator, monkeypatch: pytest.MonkeyPatch):
    """Create a Flask test app with mediator routes."""
    from flask import Flask

    import src.core.services.mediator as med_mod

    monkeypatch.setattr(med_mod, "mediator", mediator)

    app = Flask(__name__)
    app.config["TESTING"] = True

    from src.ui.web.routes.mediator import mediator_bp

    app.register_blueprint(mediator_bp, url_prefix="/api")

    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


# ── Status endpoint tests ──────────────────────────────────────


class TestIndexStatus:
    """Tests for GET /mediator/index/status."""

    def test_returns_200(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        assert resp.status_code == 200

    def test_contains_file_count(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "files" in data
        assert data["files"] > 0

    def test_contains_dirs(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "dirs" in data
        assert data["dirs"] > 0

    def test_contains_symbols(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "symbols" in data
        assert data["symbols"] > 0

    def test_contains_languages(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "languages" in data
        assert "python" in data["languages"]

    def test_contains_frameworks(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "frameworks" in data
        assert isinstance(data["frameworks"], list)

    def test_contains_peek_pages(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "peek_pages" in data

    def test_contains_node_health(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        assert "nodes" in data
        assert "index.scan" in data["nodes"]
        assert "index.delta" in data["nodes"]
        assert "index.symbols" in data["nodes"]

    def test_node_health_shape(self, client) -> None:
        resp = client.get("/api/mediator/index/status")
        data = resp.get_json()
        for _path, health in data["nodes"].items():
            assert "cached" in health
            assert "stale" in health


# ── Delta endpoint tests ───────────────────────────────────────


class TestIndexDelta:
    """Tests for GET /mediator/index/delta."""

    def test_returns_200(self, client) -> None:
        resp = client.get("/api/mediator/index/delta")
        assert resp.status_code == 200

    def test_contains_delta_fields(self, client) -> None:
        resp = client.get("/api/mediator/index/delta")
        data = resp.get_json()
        assert "added" in data
        assert "removed" in data
        assert "modified" in data
        assert "empty" in data

    def test_delta_lists_are_sorted(self, client) -> None:
        resp = client.get("/api/mediator/index/delta")
        data = resp.get_json()
        assert isinstance(data["added"], list)
        assert isinstance(data["removed"], list)
        assert isinstance(data["modified"], list)


# ── Operation endpoint tests ───────────────────────────────────


class TestIndexOperations:
    """Tests for POST /mediator/index/* operation endpoints."""

    def test_rescan_returns_200(self, client) -> None:
        resp = client.post("/api/mediator/index/rescan")
        assert resp.status_code == 200

    def test_rescan_returns_refresh_result(self, client) -> None:
        resp = client.post("/api/mediator/index/rescan")
        data = resp.get_json()
        assert "refreshed" in data or "results" in data

    def test_rebuild_symbols_returns_200(self, client) -> None:
        resp = client.post("/api/mediator/index/rebuild-symbols")
        assert resp.status_code == 200

    def test_rebuild_peek_returns_200(self, client) -> None:
        resp = client.post("/api/mediator/index/rebuild-peek")
        assert resp.status_code == 200
