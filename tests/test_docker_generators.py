"""
Tests for Docker generators — Dockerfile, dockerignore, compose generation.

Pure unit tests: stack name / module list in → GeneratedFile out.
No Docker daemon required.
"""

from pathlib import Path

import pytest

from src.core.services.generators.dockerfile import (
    generate_dockerfile,
    supported_stacks,
    _resolve_template,
)
from src.core.services.generators.dockerignore import generate_dockerignore
from src.core.services.generators.compose import generate_compose, _resolve_port


# ═══════════════════════════════════════════════════════════════════
#  supported_stacks
# ═══════════════════════════════════════════════════════════════════


class TestSupportedStacks:
    def test_returns_non_empty_list(self):
        """supported_stacks() returns a non-empty list."""
        stacks = supported_stacks()
        assert len(stacks) > 0

    def test_contains_major_stacks(self):
        """Must contain python, node, go, rust, java-maven."""
        stacks = supported_stacks()
        for expected in ("python", "node", "go", "rust", "java-maven"):
            assert expected in stacks, f"Missing: {expected}"


# ═══════════════════════════════════════════════════════════════════
#  _resolve_template
# ═══════════════════════════════════════════════════════════════════


class TestResolveTemplate:
    def test_exact_match(self):
        """Exact stack name → matching template."""
        assert _resolve_template("python") is not None
        assert _resolve_template("node") is not None
        assert _resolve_template("go") is not None

    def test_prefix_match(self):
        """python-flask → matches python template."""
        tmpl = _resolve_template("python-flask")
        assert tmpl is not None
        assert "python" in tmpl.lower()

    def test_no_match(self):
        """Unknown stack → None."""
        assert _resolve_template("cobol-mainframe") is None

    def test_longest_prefix_wins(self):
        """java-maven matches java-maven not java."""
        tmpl = _resolve_template("java-maven")
        assert tmpl is not None
        assert "mvn" in tmpl or "maven" in tmpl.lower()


# ═══════════════════════════════════════════════════════════════════
#  generate_dockerfile
# ═══════════════════════════════════════════════════════════════════


class TestGenerateDockerfile:
    def test_python(self, tmp_path: Path):
        """Python stack → GeneratedFile with full production-ready Dockerfile.

        Verifies all aspects per Docker best practices:
        1. Multi-stage build (builder + runtime)
        2. WORKDIR /app
        3. Dependency-first copy (requirements/pyproject before COPY . .)
        4. pip install
        5. COPY . . for source
        6. Non-root user (groupadd + useradd + USER app)
        7. EXPOSE 8000
        8. CMD to run the app
        9. COPY --from=builder (cross-stage)
        10. GeneratedFile metadata (path, overwrite, reason)
        """
        result = generate_dockerfile(tmp_path, "python")
        assert result is not None

        # 10. GeneratedFile metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "python" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # 1. Multi-stage build — at least 2 FROM lines
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2, f"Expected multi-stage, got {len(from_lines)} FROM"
        assert "AS builder" in content or "as builder" in content

        # 2. WORKDIR /app
        assert "WORKDIR /app" in content

        # 3. Dependency-first copy (before COPY . .)
        req_idx = next((i for i, l in enumerate(lines) if "requirements" in l or "pyproject" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert req_idx != -1, "Missing dependency file copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert req_idx < copy_all_idx, "Dependencies should be copied before source"

        # 4. pip install
        assert "pip install" in content

        # 5. COPY . . (source code)
        assert "COPY . ." in content

        # 6. Non-root user
        assert "groupadd" in content or "addgroup" in content
        assert "useradd" in content or "adduser" in content
        assert "USER app" in content

        # 7. EXPOSE
        assert "EXPOSE 8000" in content

        # 8. CMD
        assert "CMD" in content

        # 9. Cross-stage copy
        assert "COPY --from=builder" in content

    def test_python_flask_prefix(self, tmp_path: Path):
        """python-flask → matches python template."""
        result = generate_dockerfile(tmp_path, "python-flask")
        assert result is not None
        assert "FROM python:" in result.content

    def test_node(self, tmp_path: Path):
        """Node.js stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage, WORKDIR, dependency-first copy, npm ci,
        source copy, non-root user (alpine), EXPOSE 3000, CMD, cross-stage
        copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "node")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "node" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        pkg_idx = next((i for i, l in enumerate(lines) if "package" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert pkg_idx != -1, "Missing package.json copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert pkg_idx < copy_all_idx, "package.json should be copied before source"

        # npm ci
        assert "npm ci" in content

        # Non-root user (alpine uses addgroup/adduser)
        assert "addgroup" in content
        assert "adduser" in content
        assert "USER app" in content

        # EXPOSE 3000
        assert "EXPOSE 3000" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_go(self, tmp_path: Path):
        """Go stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (golang → alpine), WORKDIR, dependency-first
        copy, go build with CGO_ENABLED=0, non-root user, EXPOSE 8080,
        CMD, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "go")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "go" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage (golang builder → alpine runtime)
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "golang:" in content
        assert "alpine:" in content or "alpine" in from_lines[-1].lower()

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        mod_idx = next((i for i, l in enumerate(lines) if "go.mod" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert mod_idx != -1, "Missing go.mod copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert mod_idx < copy_all_idx, "go.mod should be copied before source"

        # go build + static binary
        assert "go build" in content
        assert "CGO_ENABLED=0" in content

        # Non-root user
        assert "addgroup" in content
        assert "adduser" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 8080" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_c(self, tmp_path: Path):
        """C stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (gcc/alpine builder → alpine runtime), WORKDIR,
        Makefile dependency-first copy, gcc/make build, non-root user,
        EXPOSE 8080, CMD, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "c")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "c" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2, f"Expected multi-stage, got {len(from_lines)} FROM"
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Build tools
        assert "gcc" in content.lower() or "make" in content.lower()

        # Source copy
        assert "COPY . ." in content

        # Non-root user
        assert "addgroup" in content or "groupadd" in content
        assert "adduser" in content or "useradd" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_cpp(self, tmp_path: Path):
        """C++ stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (gcc → alpine), WORKDIR, cmake support,
        CMakeLists/Makefile copy, build, non-root user, EXPOSE 8080,
        CMD, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "cpp")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "cpp" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2, f"Expected multi-stage, got {len(from_lines)} FROM"
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Build tools — cmake available
        assert "cmake" in content.lower()

        # CMakeLists copy
        assert "CMakeLists" in content

        # Source copy
        assert "COPY . ." in content

        # Non-root user
        assert "addgroup" in content or "groupadd" in content
        assert "adduser" in content or "useradd" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 8080" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_rust(self, tmp_path: Path):
        """Rust stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (rust → debian-slim), WORKDIR, Cargo.toml
        dependency-first copy, cargo build --release, non-root user,
        EXPOSE 8080, CMD, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "rust")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "rust" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "rust:" in content
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        cargo_idx = next((i for i, l in enumerate(lines) if "Cargo.toml" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert cargo_idx != -1, "Missing Cargo.toml copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert cargo_idx < copy_all_idx, "Cargo.toml should be copied before source"

        # cargo build --release
        assert "cargo build" in content
        assert "--release" in content

        # Non-root user
        assert "groupadd" in content or "addgroup" in content
        assert "useradd" in content or "adduser" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 8080" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_java_maven(self, tmp_path: Path):
        """Java Maven stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (maven → temurin-jre), WORKDIR, pom.xml
        dependency-first copy, mvn package, non-root user, EXPOSE 8080,
        CMD java -jar, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "java-maven")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "java-maven" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "maven:" in content.lower()
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        pom_idx = next((i for i, l in enumerate(lines) if "pom.xml" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert pom_idx != -1, "Missing pom.xml copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert pom_idx < copy_all_idx, "pom.xml should be copied before source"

        # Build
        assert "mvn" in content

        # Non-root user
        assert "addgroup" in content or "groupadd" in content
        assert "adduser" in content or "useradd" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 8080" in content

        # CMD
        assert "CMD" in content
        assert "java" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_dotnet(self, tmp_path: Path):
        """.NET stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (dotnet/sdk → dotnet/aspnet), WORKDIR,
        .csproj dependency-first copy, dotnet restore + publish, non-root
        user, EXPOSE 8080, CMD, cross-stage copy, GeneratedFile metadata.
        """
        result = generate_dockerfile(tmp_path, "dotnet")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "dotnet" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "dotnet/sdk" in content
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        proj_idx = next((i for i, l in enumerate(lines) if ".csproj" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert proj_idx != -1, "Missing .csproj copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert proj_idx < copy_all_idx, ".csproj should be copied before source"

        # Build
        assert "dotnet restore" in content
        assert "dotnet publish" in content

        # Non-root user
        assert "groupadd" in content or "addgroup" in content
        assert "useradd" in content or "adduser" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 8080" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_php(self, tmp_path: Path):
        """PHP stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (composer → php-fpm-alpine), WORKDIR,
        composer.json dependency-first copy, composer install, non-root
        user, EXPOSE 9000, CMD php-fpm, cross-stage copy, metadata.
        """
        result = generate_dockerfile(tmp_path, "php")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "php" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "composer:" in content
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        comp_idx = next((i for i, l in enumerate(lines) if "composer.json" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert comp_idx != -1, "Missing composer.json copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert comp_idx < copy_all_idx, "composer.json should be copied before source"

        # composer install
        assert "composer install" in content

        # Non-root user
        assert "addgroup" in content or "groupadd" in content
        assert "adduser" in content or "useradd" in content
        assert "USER app" in content

        # EXPOSE 9000
        assert "EXPOSE 9000" in content

        # CMD
        assert "CMD" in content
        assert "php-fpm" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_ruby(self, tmp_path: Path):
        """Ruby stack → GeneratedFile with full production-ready Dockerfile.

        Verifies: multi-stage (ruby-slim builder → ruby-slim runtime),
        WORKDIR, Gemfile dependency-first copy, bundle install, non-root
        user, EXPOSE 3000, CMD, cross-stage copy, metadata.
        """
        result = generate_dockerfile(tmp_path, "ruby")
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False
        assert "ruby" in result.reason.lower()

        content = result.content
        lines = content.splitlines()

        # Multi-stage build
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2
        assert "ruby:" in content
        assert "AS builder" in content or "as builder" in content

        # WORKDIR
        assert "WORKDIR /app" in content

        # Dependency-first copy
        gem_idx = next((i for i, l in enumerate(lines) if "Gemfile" in l and "COPY" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert gem_idx != -1, "Missing Gemfile copy"
        assert copy_all_idx != -1, "Missing COPY . ."
        assert gem_idx < copy_all_idx, "Gemfile should be copied before source"

        # bundle install
        assert "bundle install" in content

        # Non-root user
        assert "groupadd" in content or "addgroup" in content
        assert "useradd" in content or "adduser" in content
        assert "USER app" in content

        # EXPOSE
        assert "EXPOSE 3000" in content

        # CMD
        assert "CMD" in content

        # Cross-stage copy
        assert "COPY --from=builder" in content

    def test_unknown_stack_returns_none(self, tmp_path: Path):
        """Unknown stack → None."""
        result = generate_dockerfile(tmp_path, "cobol-mainframe")
        assert result is None

    def test_all_supported_stacks_generate(self, tmp_path: Path):
        """Every supported stack produces a non-empty GeneratedFile."""
        stacks = supported_stacks()
        for stack in stacks:
            result = generate_dockerfile(tmp_path, stack)
            assert result is not None, f"Failed for stack {stack}"
            assert len(result.content) > 50, f"Empty content for {stack}"

    def test_all_stacks_have_expose(self, tmp_path: Path):
        """All generated Dockerfiles include EXPOSE."""
        for stack in supported_stacks():
            result = generate_dockerfile(tmp_path, stack)
            assert "EXPOSE" in result.content, f"No EXPOSE for {stack}"

    def test_all_stacks_have_user(self, tmp_path: Path):
        """All generated Dockerfiles set a non-root USER."""
        for stack in supported_stacks():
            result = generate_dockerfile(tmp_path, stack)
            assert "USER" in result.content, f"No USER for {stack}"

    def test_reason_mentions_stack(self, tmp_path: Path):
        """GeneratedFile.reason mentions the stack name."""
        result = generate_dockerfile(tmp_path, "python")
        assert "python" in result.reason

    def test_overwrite_default_false(self, tmp_path: Path):
        """Default overwrite is False."""
        result = generate_dockerfile(tmp_path, "python")
        assert result.overwrite is False

    def test_all_stacks_use_multi_stage(self, tmp_path: Path):
        """ALL stacks must produce multi-stage Dockerfiles.

        Cross-cutting quality gate — verifies:
        1. ≥ 2 FROM lines (builder + runtime)
        2. Named builder stage (AS builder)
        3. Cross-stage COPY --from=builder
        4. Minimal runtime base (slim/alpine/distroless/jre)
        """
        minimal_bases = ("slim", "alpine", "distroless", "jre", "fpm", "aspnet")
        for stack in supported_stacks():
            result = generate_dockerfile(tmp_path, stack)
            content = result.content
            lines = content.splitlines()

            # 1. ≥ 2 FROM lines
            from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
            assert len(from_lines) >= 2, (
                f"{stack}: expected multi-stage (≥2 FROM), got {len(from_lines)}"
            )

            # 2. Named builder stage
            assert "AS builder" in content or "as builder" in content, (
                f"{stack}: missing named builder stage (AS builder)"
            )

            # 3. Cross-stage COPY
            assert "COPY --from=builder" in content, (
                f"{stack}: missing cross-stage COPY --from=builder"
            )

            # 4. Runtime base must be minimal
            runtime_from = from_lines[-1].strip()
            assert any(m in runtime_from.lower() for m in minimal_bases), (
                f"{stack}: runtime base is not minimal: {runtime_from}"
            )

    def test_custom_base_image(self, tmp_path: Path):
        """Custom base_image → replaces builder FROM, rest of template intact.

        Verifies:
        1. Custom base_image replaces the first FROM (builder stage)
        2. Runtime stage FROM remains unchanged
        3. All other template content preserved (WORKDIR, USER, EXPOSE, CMD)
        4. GeneratedFile metadata correct
        """
        custom = "myregistry.io/python:3.12-custom"
        result = generate_dockerfile(tmp_path, "python", base_image=custom)
        assert result is not None

        # Metadata
        assert result.path == "Dockerfile"
        assert result.overwrite is False

        content = result.content
        lines = content.splitlines()

        # 1. First FROM uses custom base image
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2, "Multi-stage should still be preserved"
        assert custom in from_lines[0], (
            f"Builder FROM should use custom image: {from_lines[0]}"
        )

        # 2. Runtime FROM is unchanged (original template runtime)
        assert "python:" in from_lines[-1], (
            f"Runtime FROM should be unchanged: {from_lines[-1]}"
        )

        # 3. Rest of template preserved
        assert "WORKDIR /app" in content
        assert "pip install" in content
        assert "USER app" in content
        assert "EXPOSE" in content
        assert "CMD" in content
        assert "COPY --from=builder" in content

    def test_custom_base_image_default_none(self, tmp_path: Path):
        """No base_image → template default used (backward compatible)."""
        result = generate_dockerfile(tmp_path, "python")
        content = result.content
        lines = content.splitlines()
        from_lines = [l for l in lines if l.strip().upper().startswith("FROM ")]
        # Default python base from template
        assert "python:3.12" in from_lines[0]

    # ── Framework variant matrix ────────────────────────────────
    # Validates that ALL framework-specific stack names resolve to
    # valid templates and produce production-ready Dockerfiles.

    _FRAMEWORK_VARIANTS = [
        # Python variants
        ("python-flask", "python"),
        ("python-fastapi", "python"),
        ("python-django", "python"),
        ("python-gunicorn", "python"),
        ("python-uvicorn", "python"),
        ("python-celery", "python"),
        ("python", "python"),
        # Node variants
        ("node-express", "node"),
        ("node-nextjs", "node"),
        ("node-nestjs", "node"),
        ("node-fastify", "node"),
        ("node-hono", "node"),
        ("node-koa", "node"),
        ("node", "node"),
        # Go variants
        ("go-gin", "go"),
        ("go-fiber", "go"),
        ("go-echo", "go"),
        ("go-chi", "go"),
        ("go-buffalo", "go"),
        ("go", "go"),
        # Rust variants
        ("rust-actix", "rust"),
        ("rust-axum", "rust"),
        ("rust-rocket", "rust"),
        ("rust-warp", "rust"),
        ("rust-hyper", "rust"),
        ("rust", "rust"),
        # Java variants
        ("java-maven", "java-maven"),
        ("java-gradle", "java-gradle"),
        ("java-spring", "java-maven"),
        ("java-quarkus", "java-maven"),
        ("java-micronaut", "java-maven"),
        # .NET variants
        ("dotnet-aspnet", "dotnet"),
        ("dotnet-minimal", "dotnet"),
        ("dotnet-worker", "dotnet"),
        ("dotnet", "dotnet"),
        # PHP
        ("php-laravel", "php"),
        ("php-symfony", "php"),
        ("php", "php"),
        # Ruby
        ("ruby-rails", "ruby"),
        ("ruby", "ruby"),
        # C / C++
        ("c-cmake", "c"),
        ("c", "c"),
        ("cpp-cmake", "cpp"),
        ("cpp", "cpp"),
    ]

    @pytest.mark.parametrize("variant,expected_base", _FRAMEWORK_VARIANTS)
    def test_framework_variant_resolves(self, tmp_path: Path, variant: str, expected_base: str):
        """Each framework variant resolves to a template and produces a valid Dockerfile.

        Verifies:
        1. generate_dockerfile returns a result (not None)
        2. Dockerfile has FROM, WORKDIR, COPY, EXPOSE, CMD
        3. Multi-stage build (≥ 2 FROM lines)
        4. Template matches the expected base stack
        """
        result = generate_dockerfile(tmp_path, variant)
        assert result is not None, (
            f"{variant}: should resolve to '{expected_base}' template but returned None"
        )

        content = result.content
        assert "FROM " in content, f"{variant}: missing FROM"
        assert "WORKDIR " in content, f"{variant}: missing WORKDIR"
        assert "COPY " in content, f"{variant}: missing COPY"
        assert "EXPOSE " in content, f"{variant}: missing EXPOSE"
        assert "CMD " in content or "ENTRYPOINT " in content, f"{variant}: missing CMD/ENTRYPOINT"

        # Multi-stage
        from_lines = [l for l in content.splitlines() if l.strip().upper().startswith("FROM ")]
        assert len(from_lines) >= 2, (
            f"{variant}: expected multi-stage (≥2 FROM), got {len(from_lines)}"
        )

        # Matches expected base template
        base_result = generate_dockerfile(tmp_path, expected_base)
        assert base_result is not None
        assert result.content == base_result.content, (
            f"{variant}: should produce same content as '{expected_base}'"
        )


# ═══════════════════════════════════════════════════════════════════
#  generate_dockerignore
# ═══════════════════════════════════════════════════════════════════


class TestGenerateDockerignore:
    def test_python_stacks(self, tmp_path: Path):
        """Python stacks → includes __pycache__, .venv."""
        result = generate_dockerignore(tmp_path, ["python"])
        assert "__pycache__" in result.content
        assert ".venv" in result.content or "venv" in result.content

    def test_node_stacks(self, tmp_path: Path):
        """Node stacks → includes node_modules."""
        result = generate_dockerignore(tmp_path, ["node"])
        assert "node_modules" in result.content

    def test_mixed_stacks(self, tmp_path: Path):
        """Python + Node → both patterns present."""
        result = generate_dockerignore(tmp_path, ["python", "node"])
        assert "__pycache__" in result.content
        assert "node_modules" in result.content

    def test_common_patterns_always_present(self, tmp_path: Path):
        """Common patterns (.git) always included."""
        result = generate_dockerignore(tmp_path, ["python"])
        assert ".git" in result.content

    def test_empty_stacks(self, tmp_path: Path):
        """Empty stack list → base patterns only."""
        result = generate_dockerignore(tmp_path, [])
        assert ".git" in result.content
        assert len(result.content) > 0

    def test_prefix_match(self, tmp_path: Path):
        """python-flask → matches python patterns."""
        result = generate_dockerignore(tmp_path, ["python-flask"])
        assert "__pycache__" in result.content

    def test_deduplication(self, tmp_path: Path):
        """python + python-flask → python patterns added once."""
        result = generate_dockerignore(tmp_path, ["python", "python-flask"])
        # Should not have duplicate python sections
        assert result.content.count("__pycache__") == 1

    def test_path_is_dockerignore(self, tmp_path: Path):
        """Output path is .dockerignore."""
        result = generate_dockerignore(tmp_path, ["python"])
        assert result.path == ".dockerignore"

    def test_metadata(self, tmp_path: Path):
        """GeneratedFile metadata correct.

        Verifies: path, overwrite=False, reason present.
        """
        result = generate_dockerignore(tmp_path, ["python"])
        assert result.path == ".dockerignore"
        assert result.overwrite is False
        assert result.reason  # non-empty reason

    def test_go_stacks(self, tmp_path: Path):
        """Go stack → Go binary/vendor patterns."""
        result = generate_dockerignore(tmp_path, ["go"])
        content = result.content
        # Should have common patterns
        assert ".git" in content
        # Should have Go-specific patterns
        assert "vendor" in content or "go.sum" in content or "*.exe" in content


# ═══════════════════════════════════════════════════════════════════
#  write_generated_file — overwrite behavior
# ═══════════════════════════════════════════════════════════════════


class TestWriteGeneratedFile:
    """Tests for write_generated_file overwrite behavior."""

    def test_overwrite_true(self, tmp_path: Path):
        """Existing file + overwrite=True → file is replaced.

        Verifies:
        1. File content is replaced
        2. Result indicates success
        3. written=True
        """
        from src.core.services.docker_generate import write_generated_file

        (tmp_path / "Dockerfile").write_text("ORIGINAL CONTENT\n")
        file_data = {
            "path": "Dockerfile",
            "content": "FROM python:3.12\nRUN echo replaced\n",
            "overwrite": True,
        }
        result = write_generated_file(tmp_path, file_data)
        assert result["ok"] is True
        assert result["written"] is True
        assert "replaced" in (tmp_path / "Dockerfile").read_text()
        assert "ORIGINAL" not in (tmp_path / "Dockerfile").read_text()

    def test_overwrite_false(self, tmp_path: Path):
        """Existing file + overwrite=False → file NOT replaced, error returned.

        Verifies:
        1. File content is preserved
        2. Result contains error message
        3. written=False
        """
        from src.core.services.docker_generate import write_generated_file

        (tmp_path / "Dockerfile").write_text("ORIGINAL CONTENT\n")
        file_data = {
            "path": "Dockerfile",
            "content": "FROM python:3.12\nRUN echo replaced\n",
            "overwrite": False,
        }
        result = write_generated_file(tmp_path, file_data)
        assert "error" in result
        assert result.get("written") is False
        assert "ORIGINAL" in (tmp_path / "Dockerfile").read_text()

    def test_new_file_written(self, tmp_path: Path):
        """No existing file → file is created regardless of overwrite flag.

        Verifies:
        1. File created on disk
        2. Content is correct
        3. written=True
        """
        from src.core.services.docker_generate import write_generated_file

        file_data = {
            "path": "Dockerfile",
            "content": "FROM python:3.12\n",
            "overwrite": False,
        }
        result = write_generated_file(tmp_path, file_data)
        assert result["ok"] is True
        assert result["written"] is True
        assert (tmp_path / "Dockerfile").exists()
        assert "python:3.12" in (tmp_path / "Dockerfile").read_text()


# ═══════════════════════════════════════════════════════════════════
#  Error Cases — 0.1.5
# ═══════════════════════════════════════════════════════════════════


class TestErrorCases:
    """Pessimistic error path tests for all Docker generation functions."""

    # ── generate_dockerfile ────────────────────────────────────

    def test_unknown_stack_returns_none(self, tmp_path: Path):
        """Unknown stack → generate_dockerfile returns None.

        Verifies: result is None, not an empty string or error dict.
        """
        result = generate_dockerfile(tmp_path, "totally-unknown-stack-xyz")
        assert result is None

    # ── generate_compose (wrapper) ─────────────────────────────

    def test_empty_modules_returns_error(self, tmp_path: Path):
        """Empty modules list → generate_compose returns error dict.

        Verifies: error key present, descriptive message.
        """
        from src.core.services.docker_generate import generate_compose

        result = generate_compose(tmp_path, modules=[], project_name="test")
        assert "error" in result
        assert "ok" not in result or result.get("ok") is not True

    def test_all_markdown_modules_still_generates(self, tmp_path: Path):
        """Markdown-only modules → compose generator is stack-agnostic, still generates.

        Verifies: compose generator treats all modules equally (doesn't filter by stack).
        """
        from src.core.services.docker_generate import generate_compose

        modules = [
            {"name": "docs", "stack": "markdown", "path": "docs/"},
        ]
        result = generate_compose(tmp_path, modules=modules, project_name="test")
        # Stack-agnostic: generates a service for any module
        assert result.get("ok") is True

    # ── generate_compose_from_wizard ───────────────────────────

    def test_empty_wizard_services_returns_error(self, tmp_path: Path):
        """Empty services list → error returned.

        Verifies: error key present, descriptive message.
        """
        from src.core.services.docker_generate import generate_compose_from_wizard

        result = generate_compose_from_wizard(tmp_path, services=[], project_name="test")
        assert "error" in result
        assert "service" in result["error"].lower() or "required" in result["error"].lower()

    def test_nameless_wizard_service_skipped(self, tmp_path: Path):
        """Service with empty name → skipped, remaining services generated.

        Verifies: compose still generated, nameless service not in output.
        """
        from src.core.services.docker_generate import generate_compose_from_wizard

        result = generate_compose_from_wizard(
            tmp_path,
            services=[
                {"name": "", "image": "redis"},
                {"name": "app", "image": "python:3.12"},
            ],
            project_name="test",
        )
        assert result.get("ok") is True
        content = result["file"]["content"]
        assert "app:" in content
        # Nameless service should not appear as a key
        import yaml
        parsed = yaml.safe_load(content)
        assert len(parsed["services"]) == 1
        assert "app" in parsed["services"]

    # ── write_generated_file ───────────────────────────────────

    def test_write_missing_path_returns_error(self, tmp_path: Path):
        """Missing path in file_data → error.

        Verifies: error key present, file not written.
        """
        from src.core.services.docker_generate import write_generated_file

        result = write_generated_file(tmp_path, {"content": "FROM x\n", "overwrite": False})
        assert "error" in result

    def test_write_missing_content_returns_error(self, tmp_path: Path):
        """Missing content in file_data → error.

        Verifies: error key present, file not written.
        """
        from src.core.services.docker_generate import write_generated_file

        result = write_generated_file(tmp_path, {"path": "Dockerfile", "overwrite": False})
        assert "error" in result

    def test_write_path_traversal_rejected(self, tmp_path: Path):
        """Path traversal attempt → rejected with error.

        Verifies: file_data with '../../../tmp/evil_file' is rejected,
        returns error dict, file NOT written outside project root.
        """
        from src.core.services.docker_generate import write_generated_file

        result = write_generated_file(tmp_path, {
            "path": "../../../tmp/evil_file",
            "content": "PWNED\n",
            "overwrite": True,
        })
        assert "error" in result
        assert "traversal" in result["error"].lower() or "outside" in result["error"].lower()

    # ── generate_dockerignore ──────────────────────────────────

    def test_unknown_stacks_still_generates(self, tmp_path: Path):
        """Unknown stacks → still generates base patterns.

        Verifies: result has content, includes common patterns like .git.
        """
        result = generate_dockerignore(tmp_path, ["totally-unknown-xyz"])
        assert result is not None
        assert result.content  # non-empty
        assert ".git" in result.content


# ═══════════════════════════════════════════════════════════════════
#  _resolve_port
# ═══════════════════════════════════════════════════════════════════


class TestResolvePort:
    def test_python(self):
        assert _resolve_port("python") == 8000

    def test_node(self):
        assert _resolve_port("node") == 3000

    def test_go(self):
        assert _resolve_port("go") == 8080

    def test_prefix_match(self):
        assert _resolve_port("python-flask") == 8000

    def test_unknown_defaults_8080(self):
        assert _resolve_port("unknown") == 8080


# ═══════════════════════════════════════════════════════════════════
#  generate_compose
# ═══════════════════════════════════════════════════════════════════


class TestGenerateCompose:
    def test_single_module(self, tmp_path: Path):
        """Single module → compose with one service.

        Verifies per Docker Compose spec:
        1. GeneratedFile metadata (path, overwrite, reason)
        2. services: key present
        3. Service name matches module name
        4. build: with context and dockerfile
        5. ports: mapping with correct stack port (python → 8000)
        6. restart: policy present
        7. Valid YAML (parseable by yaml.safe_load)
        8. Exactly one service in the parsed output
        """
        import yaml

        modules = [
            {"name": "api", "path": "src", "stack_name": "python-flask"},
        ]
        result = generate_compose(tmp_path, modules)
        assert result is not None

        # 1. Metadata
        assert result.path == "docker-compose.yml"
        assert result.overwrite is False
        assert "1 service" in result.reason

        content = result.content

        # 2-6. Content assertions
        assert "services:" in content
        assert "api:" in content
        assert "build:" in content
        assert "context:" in content
        assert "dockerfile:" in content or "Dockerfile" in content
        assert "8000:8000" in content  # python port
        assert "restart:" in content

        # 7. Valid YAML
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert "services" in parsed

        # 8. Exactly one service
        services = parsed["services"]
        assert len(services) == 1
        assert "api" in services
        assert "build" in services["api"]
        assert "ports" in services["api"]

    def test_multiple_modules(self, tmp_path: Path):
        """Two modules → compose with two services (app + web).

        Verifies per Docker Compose spec:
        1. GeneratedFile metadata — reason mentions 2 services
        2. Valid YAML — parseable
        3. Exactly 2 services in parsed output
        4. Each service has build, ports, restart
        5. Correct port per stack (python=8000, node=3000)
        6. Service names match module names
        """
        import yaml

        modules = [
            {"name": "api", "path": "api", "stack_name": "python-flask"},
            {"name": "web", "path": "web", "stack_name": "node"},
        ]
        result = generate_compose(tmp_path, modules)
        assert result is not None

        # 1. Metadata
        assert result.path == "docker-compose.yml"
        assert result.overwrite is False
        assert "2 service" in result.reason

        content = result.content

        # 2. Valid YAML
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert "services" in parsed

        # 3. Exactly 2 services
        services = parsed["services"]
        assert len(services) == 2

        # 6. Service names
        assert "api" in services
        assert "web" in services

        # 4. Each service has build, ports, restart
        for svc_name in ("api", "web"):
            svc = services[svc_name]
            assert "build" in svc, f"{svc_name}: missing build"
            assert "ports" in svc, f"{svc_name}: missing ports"
            assert "restart" in svc, f"{svc_name}: missing restart"

        # 5. Correct ports
        assert "8000:8000" in content  # python-flask
        assert "3000:3000" in content  # node

    def test_port_assignment(self, tmp_path: Path):
        """Python service gets port 8000, Node gets 3000."""
        modules = [
            {"name": "api", "path": "api", "stack_name": "python-flask"},
            {"name": "web", "path": "web", "stack_name": "node"},
        ]
        result = generate_compose(tmp_path, modules)
        assert "8000" in result.content
        assert "3000" in result.content

    def test_empty_modules(self, tmp_path: Path):
        """No modules → returns None."""
        result = generate_compose(tmp_path, [])
        assert result is None

    def test_skips_markdown_modules(self, tmp_path: Path):
        """Module with stack=markdown → skipped."""
        modules = [
            {"name": "docs", "path": "docs", "stack_name": "markdown"},
        ]
        result = generate_compose(tmp_path, modules)
        assert result is None

    def test_project_name(self, tmp_path: Path):
        """project_name kwarg → name: line in output."""
        modules = [
            {"name": "api", "path": "api", "stack_name": "python"},
        ]
        result = generate_compose(tmp_path, modules, project_name="myproject")
        assert "name: myproject" in result.content

    def test_own_dockerfile_context(self, tmp_path: Path):
        """Module with its own Dockerfile → build context is module path."""
        mod_dir = tmp_path / "api"
        mod_dir.mkdir()
        (mod_dir / "Dockerfile").write_text("FROM python:3.12\n")

        modules = [
            {"name": "api", "path": "api", "stack_name": "python"},
        ]
        result = generate_compose(tmp_path, modules)
        assert "./api" in result.content


# ═══════════════════════════════════════════════════════════════════
#  generate_compose_from_wizard — volumes, networks, env, depends_on
# ═══════════════════════════════════════════════════════════════════


class TestGenerateComposeWizard:
    """Tests for wizard-based compose generation (user-defined services)."""

    def test_compose_with_volumes(self, tmp_path: Path):
        """Wizard compose with volumes → volumes appear in YAML output.

        Verifies:
        1. Service has volumes key in parsed YAML
        2. Volume strings are present in content
        3. GeneratedFile metadata correct
        """
        import yaml
        from src.core.services.docker_generate import generate_compose_from_wizard

        services = [
            {
                "name": "db",
                "image": "postgres:15",
                "volumes": ["pgdata:/var/lib/postgresql/data", "./init:/docker-entrypoint-initdb.d"],
            },
        ]
        result = generate_compose_from_wizard(tmp_path, services)
        assert result["ok"] is True

        content = result["file"]["content"]
        parsed = yaml.safe_load(content)

        # Volumes in parsed output
        assert "volumes" in parsed["services"]["db"]
        vols = parsed["services"]["db"]["volumes"]
        assert len(vols) == 2
        assert any("pgdata" in v for v in vols)
        assert any("init" in v for v in vols)

    def test_compose_with_networks(self, tmp_path: Path):
        """Wizard compose with networks → top-level networks + per-service networks.

        Verifies:
        1. Service has networks key
        2. Top-level networks section created
        """
        import yaml
        from src.core.services.docker_generate import generate_compose_from_wizard

        services = [
            {
                "name": "api",
                "image": "myapp:latest",
                "networks": ["backend", "frontend"],
            },
        ]
        result = generate_compose_from_wizard(tmp_path, services)
        assert result["ok"] is True

        content = result["file"]["content"]
        parsed = yaml.safe_load(content)

        # Per-service networks
        assert "networks" in parsed["services"]["api"]
        nets = parsed["services"]["api"]["networks"]
        assert "backend" in nets
        assert "frontend" in nets

        # Top-level networks
        assert "networks" in parsed
        assert "backend" in parsed["networks"]
        assert "frontend" in parsed["networks"]

    def test_compose_with_environment(self, tmp_path: Path):
        """Wizard compose with env vars → environment in parsed YAML.

        Verifies:
        1. Dict environment → key: value in parsed output
        """
        import yaml
        from src.core.services.docker_generate import generate_compose_from_wizard

        services = [
            {
                "name": "api",
                "image": "myapp:latest",
                "environment": {"DATABASE_URL": "postgres://db/app", "DEBUG": "false"},
            },
        ]
        result = generate_compose_from_wizard(tmp_path, services)
        assert result["ok"] is True

        content = result["file"]["content"]
        parsed = yaml.safe_load(content)

        env = parsed["services"]["api"]["environment"]
        assert env["DATABASE_URL"] == "postgres://db/app"
        assert env["DEBUG"] == "false"

    def test_compose_with_ports(self, tmp_path: Path):
        """Wizard compose with ports → ports in parsed YAML.

        Verifies:
        1. Ports list present
        2. Correct port mapping strings
        """
        import yaml
        from src.core.services.docker_generate import generate_compose_from_wizard

        services = [
            {
                "name": "web",
                "image": "nginx:alpine",
                "ports": ["80:80", "443:443"],
            },
        ]
        result = generate_compose_from_wizard(tmp_path, services)
        assert result["ok"] is True

        content = result["file"]["content"]
        parsed = yaml.safe_load(content)

        ports = parsed["services"]["web"]["ports"]
        assert "80:80" in ports
        assert "443:443" in ports

    def test_compose_with_depends_on(self, tmp_path: Path):
        """Wizard compose with depends_on → dependency chain in YAML.

        Verifies:
        1. depends_on key present
        2. Correct dependency reference
        """
        import yaml
        from src.core.services.docker_generate import generate_compose_from_wizard

        services = [
            {
                "name": "api",
                "image": "myapp:latest",
                "depends_on": ["db", "redis"],
            },
            {
                "name": "db",
                "image": "postgres:15",
            },
            {
                "name": "redis",
                "image": "redis:7-alpine",
            },
        ]
        result = generate_compose_from_wizard(tmp_path, services)
        assert result["ok"] is True

        content = result["file"]["content"]
        parsed = yaml.safe_load(content)

        deps = parsed["services"]["api"]["depends_on"]
        assert "db" in deps
        assert "redis" in deps

        # All 3 services present
        assert len(parsed["services"]) == 3
