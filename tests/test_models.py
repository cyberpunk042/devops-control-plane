"""
Tests for domain models — serialization, validation, lookups.
"""

import json

from src.core.models import (
    Action,
    AdapterRequirement,
    DetectionRule,
    Environment,
    ExternalLinks,
    Module,
    ModuleRef,
    Project,
    ProjectState,
    Receipt,
    Stack,
    StackCapability,
)


class TestProject:
    """Project model tests."""

    def test_minimal_project(self):
        """A project needs only a name."""
        p = Project(name="test")
        assert p.name == "test"
        assert p.version == 1
        assert p.domains == ["service"]
        assert p.modules == []
        assert p.environments == []

    def test_full_project(self):
        """All fields populate correctly."""
        p = Project(
            name="my-app",
            description="Test app",
            repository="github.com/org/my-app",
            domains=["service", "library"],
            environments=[
                Environment(name="dev", default=True),
                Environment(name="prod"),
            ],
            modules=[
                ModuleRef(name="api", path="services/api", stack="python-fastapi"),
                ModuleRef(name="frontend", path="services/frontend", stack="node-nextjs"),
            ],
            external=ExternalLinks(ci="github-actions", registry="ghcr.io"),
        )
        assert len(p.modules) == 2
        assert len(p.environments) == 2
        assert p.external.ci == "github-actions"

    def test_get_environment(self):
        p = Project(
            name="test",
            environments=[
                Environment(name="dev", default=True),
                Environment(name="prod"),
            ],
        )
        assert p.get_environment("dev") is not None
        assert p.get_environment("dev").default is True
        assert p.get_environment("prod") is not None
        assert p.get_environment("staging") is None

    def test_default_environment(self):
        p = Project(
            name="test",
            environments=[
                Environment(name="staging"),
                Environment(name="prod", default=True),
            ],
        )
        assert p.default_environment().name == "prod"

    def test_default_environment_first_fallback(self):
        """When no env is marked default, return the first one."""
        p = Project(
            name="test",
            environments=[Environment(name="dev"), Environment(name="prod")],
        )
        assert p.default_environment().name == "dev"

    def test_default_environment_none(self):
        """No environments at all returns None."""
        p = Project(name="test")
        assert p.default_environment() is None

    def test_get_module(self):
        p = Project(
            name="test",
            modules=[
                ModuleRef(name="api", path="src/api"),
                ModuleRef(name="web", path="src/web"),
            ],
        )
        assert p.get_module("api").path == "src/api"
        assert p.get_module("missing") is None

    def test_modules_by_domain(self):
        p = Project(
            name="test",
            modules=[
                ModuleRef(name="api", path="src/api", domain="service"),
                ModuleRef(name="lib", path="src/lib", domain="library"),
                ModuleRef(name="web", path="src/web", domain="service"),
            ],
        )
        services = p.modules_by_domain("service")
        assert len(services) == 2
        assert all(m.domain == "service" for m in services)

    def test_serialization_roundtrip(self):
        """Project → JSON → Project should be identical."""
        p = Project(
            name="test",
            description="roundtrip test",
            environments=[Environment(name="dev", default=True)],
            modules=[ModuleRef(name="api", path="src/api", stack="python")],
        )
        data = json.loads(p.model_dump_json())
        p2 = Project.model_validate(data)
        assert p2.name == p.name
        assert len(p2.modules) == len(p.modules)
        assert p2.modules[0].stack == "python"


class TestModule:
    """Module model tests."""

    def test_declared_module(self):
        m = Module(name="api", path="src/api", stack_name="python-fastapi")
        assert m.name == "api"
        assert not m.detected
        assert m.effective_stack == "python-fastapi"

    def test_detected_module(self):
        m = Module(
            name="api",
            path="src/api",
            stack_name="python-fastapi",
            detected=True,
            detected_stack="python-fastapi",
            version="1.2.0",
            language="python",
        )
        assert m.is_detected
        assert m.effective_stack == "python-fastapi"
        assert m.version == "1.2.0"

    def test_effective_stack_detection_overrides(self):
        """Detected stack takes precedence over declared."""
        m = Module(
            name="api",
            path="src/api",
            stack_name="python",
            detected=True,
            detected_stack="python-fastapi",
        )
        assert m.effective_stack == "python-fastapi"

    def test_effective_stack_fallback(self):
        """Falls back to declared stack when detection hasn't run."""
        m = Module(name="api", path="src/api", stack_name="python")
        assert m.effective_stack == "python"

    def test_health_default(self):
        m = Module(name="api", path="src/api")
        assert m.health.status == "unknown"

    def test_serialization_roundtrip(self):
        m = Module(
            name="api",
            path="src/api",
            detected=True,
            version="2.0.0",
            dependencies=["shared-lib"],
        )
        data = json.loads(m.model_dump_json())
        m2 = Module.model_validate(data)
        assert m2.version == "2.0.0"
        assert m2.dependencies == ["shared-lib"]


class TestStack:
    """Stack model tests."""

    def test_minimal_stack(self):
        s = Stack(name="python")
        assert s.name == "python"
        assert s.capabilities == []
        assert not s.has_capability("test")

    def test_stack_with_capabilities(self):
        s = Stack(
            name="python-fastapi",
            capabilities=[
                StackCapability(name="install", adapter="python", command="pip install -e ."),
                StackCapability(name="lint", adapter="python", command="ruff check ."),
                StackCapability(name="test", adapter="python", command="pytest"),
            ],
        )
        assert s.has_capability("lint")
        assert not s.has_capability("deploy")
        assert s.get_capability("test").command == "pytest"
        assert s.capability_names == ["install", "lint", "test"]

    def test_detection_rule(self):
        rule = DetectionRule(
            files_any_of=["pyproject.toml", "setup.py"],
            content_contains={"pyproject.toml": "fastapi"},
        )
        assert "pyproject.toml" in rule.files_any_of
        assert rule.content_contains["pyproject.toml"] == "fastapi"

    def test_adapter_requirement(self):
        req = AdapterRequirement(adapter="python", min_version="3.11")
        assert req.adapter == "python"
        assert req.min_version == "3.11"

    def test_serialization_roundtrip(self):
        s = Stack(
            name="python-fastapi",
            requires=[AdapterRequirement(adapter="python", min_version="3.11")],
            detection=DetectionRule(files_any_of=["pyproject.toml"]),
            capabilities=[StackCapability(name="test", command="pytest")],
        )
        data = json.loads(s.model_dump_json())
        s2 = Stack.model_validate(data)
        assert s2.name == "python-fastapi"
        assert s2.requires[0].min_version == "3.11"
        assert s2.has_capability("test")


class TestAction:
    """Action model tests."""

    def test_action_creation(self):
        a = Action(id="lint-api", adapter="python", capability="lint", for_module="api")
        assert a.id == "lint-api"
        assert a.for_module == "api"

    def test_action_with_params(self):
        a = Action(
            id="build-api",
            adapter="docker",
            capability="build",
            params={"tag": "api:latest", "no_cache": False},
        )
        assert a.params["tag"] == "api:latest"


class TestReceipt:
    """Receipt model tests."""

    def test_success_receipt(self):
        r = Receipt.success("python", "lint-api", output="All checks passed")
        assert r.ok
        assert not r.failed
        assert r.status == "ok"
        assert r.output == "All checks passed"

    def test_failure_receipt(self):
        r = Receipt.failure("docker", "build-api", error="Image build failed")
        assert r.failed
        assert not r.ok
        assert r.error == "Image build failed"

    def test_skip_receipt(self):
        r = Receipt.skip("kubectl", "deploy-api", reason="Adapter not available")
        assert r.status == "skipped"
        assert not r.ok
        assert not r.failed

    def test_receipt_timestamps(self):
        r = Receipt.success("python", "test")
        assert r.started_at
        assert r.ended_at

    def test_serialization_roundtrip(self):
        r = Receipt.failure("docker", "build-api", error="timeout")
        data = json.loads(r.model_dump_json())
        r2 = Receipt.model_validate(data)
        assert r2.failed
        assert r2.error == "timeout"


class TestProjectState:
    """ProjectState model tests."""

    def test_fresh_state(self):
        s = ProjectState()
        assert s.schema_version == 1
        assert s.project_name == ""
        assert s.modules == {}
        assert s.adapters == {}

    def test_set_module_state(self):
        s = ProjectState()
        s.set_module_state("api", detected=True, stack="python-fastapi")
        assert "api" in s.modules
        assert s.modules["api"].detected is True
        assert s.modules["api"].stack == "python-fastapi"

    def test_update_module_state(self):
        """Updating an existing module merges fields."""
        s = ProjectState()
        s.set_module_state("api", detected=True, stack="python")
        s.set_module_state("api", version="1.0.0")
        assert s.modules["api"].stack == "python"
        assert s.modules["api"].version == "1.0.0"

    def test_set_adapter_state(self):
        s = ProjectState()
        s.set_adapter_state("docker", available=True, version="24.0.0")
        assert s.adapters["docker"].available is True
        assert s.adapters["docker"].version == "24.0.0"

    def test_touch_updates_timestamp(self):
        s = ProjectState()
        old_ts = s.updated_at
        import time
        time.sleep(0.01)
        s.touch()
        assert s.updated_at != old_ts

    def test_serialization_roundtrip(self):
        s = ProjectState(project_name="test")
        s.set_module_state("api", detected=True)
        s.set_adapter_state("docker", available=True)
        data = json.loads(s.model_dump_json())
        s2 = ProjectState.model_validate(data)
        assert s2.project_name == "test"
        assert s2.modules["api"].detected is True
        assert s2.adapters["docker"].available is True
