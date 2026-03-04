"""
GitHub Actions release workflow generator.

Generates a `.github/workflows/release.yml` that automates
build → test → publish on tag push.

Stack-aware — produces the correct build steps and publish
targets based on the detected project stacks.
"""

from __future__ import annotations

import shutil
from pathlib import Path


# ── Stack → workflow build/publish steps ────────────────────────────

_STACK_WORKFLOWS: dict[str, dict] = {
    "python": {
        "setup": "actions/setup-python@v5",
        "setup_with": {"python-version": "3.x"},
        "install": "pip install -e '.[dev]'",
        "build": "python -m build",
        "test": "pytest",
        "artifacts_path": "dist/*",
        "publish_targets": {
            "pypi": {
                "name": "Publish to PyPI",
                "uses": "pypa/gh-action-pypi-publish@release/v1",
                "with": {"password": "${{ secrets.PYPI_TOKEN }}"},
            },
            "testpypi": {
                "name": "Publish to TestPyPI",
                "uses": "pypa/gh-action-pypi-publish@release/v1",
                "with": {
                    "password": "${{ secrets.TEST_PYPI_TOKEN }}",
                    "repository-url": "https://test.pypi.org/legacy/",
                },
            },
        },
    },
    "node": {
        "setup": "actions/setup-node@v4",
        "setup_with": {"node-version": "20", "registry-url": "https://registry.npmjs.org"},
        "install": "npm ci",
        "build": "npm run build",
        "test": "npm test",
        "artifacts_path": "dist/*",
        "publish_targets": {
            "npm": {
                "name": "Publish to npm",
                "run": "npm publish",
                "env": {"NODE_AUTH_TOKEN": "${{ secrets.NPM_TOKEN }}"},
            },
        },
    },
    "typescript": {
        "setup": "actions/setup-node@v4",
        "setup_with": {"node-version": "20", "registry-url": "https://registry.npmjs.org"},
        "install": "npm ci",
        "build": "npm run build",
        "test": "npm test",
        "artifacts_path": "dist/*",
        "publish_targets": {
            "npm": {
                "name": "Publish to npm",
                "run": "npm publish",
                "env": {"NODE_AUTH_TOKEN": "${{ secrets.NPM_TOKEN }}"},
            },
        },
    },
    "rust": {
        "setup": "dtolnay/rust-toolchain@stable",
        "setup_with": {},
        "install": "",
        "build": "cargo build --release",
        "test": "cargo test",
        "artifacts_path": "target/release/*",
        "publish_targets": {
            "crates-io": {
                "name": "Publish to crates.io",
                "run": "cargo publish",
                "env": {"CARGO_REGISTRY_TOKEN": "${{ secrets.CARGO_REGISTRY_TOKEN }}"},
            },
        },
    },
    "go": {
        "setup": "actions/setup-go@v5",
        "setup_with": {"go-version": "stable"},
        "install": "",
        "build": "go build ./...",
        "test": "go test ./...",
        "artifacts_path": "",
        "publish_targets": {},
    },
    "ruby": {
        "setup": "ruby/setup-ruby@v1",
        "setup_with": {"ruby-version": "3.2", "bundler-cache": True},
        "install": "bundle install",
        "build": "gem build *.gemspec",
        "test": "bundle exec rspec",
        "artifacts_path": "*.gem",
        "publish_targets": {
            "rubygems": {
                "name": "Publish to RubyGems",
                "run": "gem push *.gem",
                "env": {"GEM_HOST_API_KEY": "${{ secrets.RUBYGEMS_API_KEY }}"},
            },
        },
    },
    "java": {
        "setup": "actions/setup-java@v4",
        "setup_with": {"java-version": "17", "distribution": "temurin"},
        "install": "",
        "build": "mvn package -DskipTests",
        "test": "mvn test",
        "artifacts_path": "target/*.jar",
        "publish_targets": {},
    },
    "dotnet": {
        "setup": "actions/setup-dotnet@v4",
        "setup_with": {"dotnet-version": "8.x"},
        "install": "dotnet restore",
        "build": "dotnet build -c Release --no-restore",
        "test": "dotnet test --no-build -c Release",
        "artifacts_path": "**/*.nupkg",
        "publish_targets": {
            "nuget": {
                "name": "Publish to NuGet",
                "run": "dotnet nuget push **/*.nupkg --api-key ${{ secrets.NUGET_API_KEY }} --source https://api.nuget.org/v3/index.json",
            },
        },
    },
    "elixir": {
        "setup": "erlef/setup-beam@v1",
        "setup_with": {"otp-version": "26", "elixir-version": "1.16"},
        "install": "mix deps.get",
        "build": "mix compile",
        "test": "mix test",
        "artifacts_path": "",
        "publish_targets": {
            "hex-pm": {
                "name": "Publish to Hex.pm",
                "run": "mix hex.publish --yes",
                "env": {"HEX_API_KEY": "${{ secrets.HEX_API_KEY }}"},
            },
        },
    },
    "docker": {
        "setup": "",
        "setup_with": {},
        "install": "",
        "build": "",
        "test": "",
        "artifacts_path": "",
        "publish_targets": {
            "ghcr": {
                "name": "Push to ghcr.io",
                "uses": "docker/build-push-action@v5",
                "with": {
                    "push": True,
                    "tags": "ghcr.io/${{ github.repository }}:${{ github.ref_name }}",
                },
            },
        },
    },
}


def generate_release_workflow(
    project_root: Path,
    detected_stacks: list[str],
    publish_targets: list[str] | None = None,
) -> str:
    """Generate a GitHub Actions release.yml workflow.

    Args:
        project_root: Project root path
        detected_stacks: List of detected stacks (e.g. ["python-flask"])
        publish_targets: Optional list of publish targets to enable
                        (e.g. ["pypi", "github-release"]).
                        If None, enables all available.

    Returns:
        The workflow YAML content as a string.
    """
    # Find the primary stack
    primary_stack = _resolve_primary_stack(detected_stacks)
    stack_config = _STACK_WORKFLOWS.get(primary_stack, {})

    has_makefile = (project_root / "Makefile").exists()
    has_dockerfile = (project_root / "Dockerfile").exists()

    lines: list[str] = []
    lines.append("# Auto-generated release workflow")
    lines.append("# Generated by devops-control-plane artifact system")
    lines.append(f"# Primary stack: {primary_stack}")
    lines.append(f"# Detected stacks: {', '.join(detected_stacks)}")
    lines.append("")
    lines.append("name: Release")
    lines.append("")
    lines.append("on:")
    lines.append("  push:")
    lines.append("    tags:")
    lines.append("      - 'v*'")
    lines.append("")
    lines.append("permissions:")
    lines.append("  contents: write")
    lines.append("  packages: write")
    lines.append("")
    lines.append("jobs:")

    # ── Build & Test job ──
    lines.append("  build:")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append("      - uses: actions/checkout@v4")

    # Setup step
    setup_action = stack_config.get("setup", "")
    if setup_action:
        lines.append(f"      - uses: {setup_action}")
        setup_with = stack_config.get("setup_with", {})
        if setup_with:
            lines.append("        with:")
            for k, v in setup_with.items():
                lines.append(f"          {k}: {_yaml_value(v)}")

    # Install
    install_cmd = stack_config.get("install", "")
    if install_cmd:
        lines.append("      - name: Install dependencies")
        if has_makefile:
            lines.append("        run: make install")
        else:
            lines.append(f"        run: {install_cmd}")

    # Build
    build_cmd = stack_config.get("build", "")
    if build_cmd:
        lines.append("      - name: Build")
        if has_makefile:
            lines.append("        run: make build")
        else:
            lines.append(f"        run: {build_cmd}")

    # Test
    test_cmd = stack_config.get("test", "")
    if test_cmd:
        lines.append("      - name: Test")
        if has_makefile:
            lines.append("        run: make test")
        else:
            lines.append(f"        run: {test_cmd}")

    # Upload artifacts
    artifacts_path = stack_config.get("artifacts_path", "")
    if artifacts_path:
        lines.append("      - name: Upload build artifacts")
        lines.append("        uses: actions/upload-artifact@v4")
        lines.append("        with:")
        lines.append("          name: build-artifacts")
        lines.append(f"          path: {artifacts_path}")

    # ── GitHub Release job (always) ──
    lines.append("")
    lines.append("  release:")
    lines.append("    needs: build")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append("      - uses: actions/checkout@v4")
    if artifacts_path:
        lines.append("      - name: Download artifacts")
        lines.append("        uses: actions/download-artifact@v4")
        lines.append("        with:")
        lines.append("          name: build-artifacts")
        lines.append("          path: dist/")
    lines.append("      - name: Create GitHub Release")
    lines.append("        uses: softprops/action-gh-release@v2")
    lines.append("        with:")
    lines.append("          generate_release_notes: true")
    if artifacts_path:
        lines.append("          files: dist/*")

    # ── Stack-specific publish jobs ──
    stack_targets = stack_config.get("publish_targets", {})
    for target_name, target_config in stack_targets.items():
        if publish_targets and target_name not in publish_targets:
            continue

        lines.append("")
        lines.append(f"  publish-{target_name}:")
        lines.append("    needs: build")
        lines.append("    runs-on: ubuntu-latest")
        lines.append("    steps:")
        lines.append("      - uses: actions/checkout@v4")

        if setup_action:
            lines.append(f"      - uses: {setup_action}")
            if setup_with:
                lines.append("        with:")
                for k, v in setup_with.items():
                    lines.append(f"          {k}: {_yaml_value(v)}")

        if artifacts_path:
            lines.append("      - name: Download artifacts")
            lines.append("        uses: actions/download-artifact@v4")
            lines.append("        with:")
            lines.append("          name: build-artifacts")
            lines.append("          path: dist/")

        pub_name = target_config.get("name", f"Publish to {target_name}")
        lines.append(f"      - name: {pub_name}")

        if "uses" in target_config:
            lines.append(f"        uses: {target_config['uses']}")
            pub_with = target_config.get("with", {})
            if pub_with:
                lines.append("        with:")
                for k, v in pub_with.items():
                    lines.append(f"          {k}: {_yaml_value(v)}")
        elif "run" in target_config:
            lines.append(f"        run: {target_config['run']}")

        pub_env = target_config.get("env", {})
        if pub_env:
            lines.append("        env:")
            for k, v in pub_env.items():
                lines.append(f"          {k}: {v}")

    # ── Docker publish (if Dockerfile exists) ──
    if has_dockerfile:
        docker_targets = _STACK_WORKFLOWS.get("docker", {}).get("publish_targets", {})
        ghcr_config = docker_targets.get("ghcr")
        if ghcr_config and (not publish_targets or "ghcr" in publish_targets):
            lines.append("")
            lines.append("  docker:")
            lines.append("    needs: build")
            lines.append("    runs-on: ubuntu-latest")
            lines.append("    steps:")
            lines.append("      - uses: actions/checkout@v4")
            lines.append("      - name: Log in to ghcr.io")
            lines.append("        uses: docker/login-action@v3")
            lines.append("        with:")
            lines.append("          registry: ghcr.io")
            lines.append("          username: ${{ github.actor }}")
            lines.append("          password: ${{ secrets.GITHUB_TOKEN }}")
            lines.append("      - name: Build and push")
            lines.append("        uses: docker/build-push-action@v5")
            lines.append("        with:")
            lines.append("          push: true")
            lines.append("          tags: |")
            lines.append("            ghcr.io/${{ github.repository }}:${{ github.ref_name }}")
            lines.append("            ghcr.io/${{ github.repository }}:latest")

    lines.append("")
    return "\n".join(lines)


def write_release_workflow(
    project_root: Path,
    detected_stacks: list[str],
    publish_targets: list[str] | None = None,
) -> dict:
    """Generate and write the release workflow file.

    Returns:
        {"path": str, "created": bool, "content": str}
    """
    workflow_dir = project_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = workflow_dir / "release.yml"

    existed = workflow_file.exists()
    content = generate_release_workflow(project_root, detected_stacks, publish_targets)
    workflow_file.write_text(content)

    return {
        "path": str(workflow_file.relative_to(project_root)),
        "created": not existed,
        "content": content,
    }


# ── Helpers ─────────────────────────────────────────────────────────


def _resolve_primary_stack(detected_stacks: list[str]) -> str:
    """Pick the primary stack from detected stacks.

    Preference: code stacks > infra stacks > static.
    """
    # Priority order for primary stack resolution
    priority = [
        "python", "node", "typescript", "rust", "go",
        "ruby", "java", "dotnet", "elixir",
        "docker", "helm", "terraform",
    ]

    for prio in priority:
        for stack in detected_stacks:
            base = stack.split("-")[0]
            if base == prio:
                return base
    return detected_stacks[0].split("-")[0] if detected_stacks else "python"


def _yaml_value(val: object) -> str:
    """Format a value for YAML."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)
