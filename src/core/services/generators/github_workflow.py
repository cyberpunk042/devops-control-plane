"""
GitHub Actions workflow generator.

Produces CI and lint workflows from detected stack information.
Templates follow GitHub Actions best practices:
- Pinned action versions
- Dependency caching
- Matrix testing where appropriate
- Minimal permissions
"""

from __future__ import annotations

from pathlib import Path

from src.core.models.template import GeneratedFile


def _python_ci_job(version_matrix: list[str] | None = None) -> str:
    """Python CI job: install, lint, type-check, test."""
    versions = version_matrix or ["3.11", "3.12"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  python:
    name: Python — lint, types, test
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]" 2>/dev/null || pip install -e .
          pip install ruff mypy pytest 2>/dev/null || true

      - name: Lint (ruff)
        run: ruff check .

      - name: Type check (mypy)
        run: mypy src/ --ignore-missing-imports

      - name: Test (pytest)
        run: pytest --tb=short -q
"""


def _node_ci_job(version_matrix: list[str] | None = None) -> str:
    """Node.js CI job: install, lint, test, build."""
    versions = version_matrix or ["18", "20"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  node:
    name: Node.js — lint, test, build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js ${{{{ matrix.node-version }}}}
        uses: actions/setup-node@v4
        with:
          node-version: ${{{{ matrix.node-version }}}}
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint --if-present

      - name: Test
        run: npm test --if-present

      - name: Build
        run: npm run build --if-present
"""


def _go_ci_job(version_matrix: list[str] | None = None) -> str:
    """Go CI job: vet, lint, test, build."""
    versions = version_matrix or ["1.21", "1.22"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  go:
    name: Go — vet, test, build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        go-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go ${{{{ matrix.go-version }}}}
        uses: actions/setup-go@v5
        with:
          go-version: ${{{{ matrix.go-version }}}}

      - name: Vet
        run: go vet ./...

      - name: Test
        run: go test -race -count=1 ./...

      - name: Build
        run: go build ./...
"""


def _rust_ci_job() -> str:
    """Rust CI job: check, clippy, test."""
    return """\
  rust:
    name: Rust — clippy, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: clippy, rustfmt

      - name: Cache
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Check
        run: cargo check

      - name: Clippy
        run: cargo clippy -- -D warnings

      - name: Format check
        run: cargo fmt -- --check

      - name: Test
        run: cargo test
"""


def _java_maven_ci_job() -> str:
    """Java Maven CI job."""
    return """\
  java:
    name: Java — build, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: maven

      - name: Build and test
        run: mvn -B verify
"""


def _java_gradle_ci_job() -> str:
    """Java Gradle CI job."""
    return """\
  java:
    name: Java — build, test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: gradle

      - name: Build and test
        run: ./gradlew build
"""


# Map stack name → job generator
_CI_JOBS: dict[str, callable] = {
    "python": _python_ci_job,
    "node": _node_ci_job,
    "typescript": _node_ci_job,
    "go": _go_ci_job,
    "rust": _rust_ci_job,
    "java-maven": _java_maven_ci_job,
    "java-gradle": _java_gradle_ci_job,
}


def _resolve_job(stack_name: str) -> callable | None:
    """Resolve a stack to its CI job generator."""
    if stack_name in _CI_JOBS:
        return _CI_JOBS[stack_name]
    for prefix, gen in _CI_JOBS.items():
        if stack_name.startswith(prefix + "-") or stack_name.startswith(prefix):
            return gen
    return None


# ── Docker CI job ───────────────────────────────────────────────


def _docker_ci_job(
    *,
    image_name: str = "app",
    registry: str = "",
    registry_type: str = "",
    build_args: dict[str, str] | None = None,
    use_buildx: bool = True,
    use_cache: bool = True,
    dockerfile: str = "Dockerfile",
    context: str = ".",
) -> str:
    """Docker build + push CI job.

    Args:
        image_name: Image name (without registry prefix).
        registry: Registry URL (e.g. 'ghcr.io/org').
        registry_type: 'ghcr' | 'dockerhub' | 'custom' | ''.
        build_args: Docker build args to pass with --build-arg.
        use_buildx: Whether to use docker/setup-buildx-action.
        use_cache: Whether to use GHA layer caching.
        dockerfile: Path to Dockerfile.
        context: Build context directory.
    """
    steps: list[str] = []

    # Checkout
    steps.append("      - uses: actions/checkout@v4")

    # Buildx
    if use_buildx:
        steps.append("""\
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3""")

    # Registry login
    if registry_type == "ghcr":
        steps.append("""\
      - name: Log in to GHCR
        if: github.event_name == 'push'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}""")
    elif registry_type == "dockerhub":
        steps.append("""\
      - name: Log in to DockerHub
        if: github.event_name == 'push'
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}""")
    elif registry_type == "custom" and registry:
        steps.append(f"""\
      - name: Log in to registry
        if: github.event_name == 'push'
        uses: docker/login-action@v3
        with:
          registry: {registry}
          username: ${{{{ secrets.REGISTRY_USERNAME }}}}
          password: ${{{{ secrets.REGISTRY_PASSWORD }}}}""")

    # Build image tag
    if registry:
        full_image = f"{registry}/{image_name}"
    else:
        full_image = image_name

    # Build command
    build_parts: list[str] = []
    build_parts.append(f"          docker build")
    build_parts.append(f"            -f {dockerfile}")
    build_parts.append(f"            -t {full_image}:${{{{{{ github.sha }}}}}}")
    build_parts.append(f"            -t {full_image}:latest")

    if build_args:
        for key, val in build_args.items():
            build_parts.append(f"            --build-arg {key}={val}")

    if use_cache:
        build_parts.append("            --cache-from type=gha")
        build_parts.append("            --cache-to type=gha,mode=max")

    build_parts.append(f"            {context}")

    build_step = "\n".join(build_parts)
    steps.append(f"""\
      - name: Build Docker image
        run: |
{build_step}""")

    # Push (only on push to main, only if registry configured)
    if registry:
        steps.append(f"""\
      - name: Push Docker image
        if: github.event_name == 'push'
        run: |
          docker push {full_image}:${{{{{{ github.sha }}}}}}
          docker push {full_image}:latest""")

    steps_str = "\n\n".join(steps)

    return f"""\
  docker:
    name: Docker — build{" & push" if registry else ""}
    runs-on: ubuntu-latest
    needs: [test]
    if: github.event_name == 'push'

    steps:
{steps_str}
"""


def generate_docker_ci(
    docker_services: list[dict],
    *,
    project_name: str = "",
    test_job: str = "",
) -> GeneratedFile | None:
    """Generate a Docker build/push CI workflow.

    Args:
        docker_services: List of dicts, each with:
            name, image, registry, registry_type, build_args,
            use_buildx, use_cache, dockerfile, context.
        project_name: For the workflow name.
        test_job: If provided, include this test job YAML before docker jobs.

    Returns:
        GeneratedFile or None if no services.
    """
    if not docker_services:
        return None

    wf_name = f"{project_name} Docker CI" if project_name else "Docker CI"

    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
"""
    # Minimal test job placeholder so docker can depend on it
    test_block = test_job or """\
  test:
    name: Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: echo "Tests placeholder"
"""

    docker_blocks: list[str] = []
    for svc in docker_services:
        job_yaml = _docker_ci_job(
            image_name=svc.get("name", "app"),
            registry=svc.get("registry", ""),
            registry_type=svc.get("registry_type", ""),
            build_args=svc.get("build_args"),
            use_buildx=svc.get("use_buildx", True),
            use_cache=svc.get("use_cache", True),
            dockerfile=svc.get("dockerfile", "Dockerfile"),
            context=svc.get("context", "."),
        )
        # For multiple services, make job names unique
        if len(docker_services) > 1:
            svc_name = svc.get("name", "app")
            job_yaml = job_yaml.replace(
                "  docker:", f"  docker-{svc_name}:", 1
            )
        docker_blocks.append(job_yaml)

    content = header + test_block + "\n" + "\n".join(docker_blocks)

    return GeneratedFile(
        path=".github/workflows/docker.yml",
        content=content,
        overwrite=False,
        reason=f"Docker CI for {len(docker_services)} service(s)",
    )


# ── K8s Deploy CI jobs ──────────────────────────────────────────


def _kubeconfig_step() -> str:
    """Common kubeconfig setup step from GHA secrets."""
    return """\
      - name: Set up kubeconfig
        run: |
          mkdir -p $HOME/.kube
          echo "${{ secrets.KUBECONFIG }}" | base64 -d > $HOME/.kube/config
          chmod 600 $HOME/.kube/config"""


def _kubectl_deploy_ci_job(
    *,
    manifest_dir: str = "k8s",
    namespace: str = "",
    app_name: str = "app",
    needs: list[str] | None = None,
) -> str:
    """Kubectl deploy CI job: dry-run → apply → rollout status."""
    ns_flag = f" -n {namespace}" if namespace else ""
    needs_list = needs or ["test"]

    return f"""\
  deploy:
    name: Deploy — kubectl
    runs-on: ubuntu-latest
    needs: {needs_list}
    if: github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

{_kubeconfig_step()}

      - name: Validate (dry-run)
        run: kubectl apply -f {manifest_dir}/{ns_flag} --dry-run=server

      - name: Apply manifests
        run: kubectl apply -f {manifest_dir}/{ns_flag}

      - name: Wait for rollout
        run: kubectl rollout status deployment/{app_name}{ns_flag} --timeout=120s
"""


def _skaffold_deploy_ci_job(
    *,
    profile: str = "",
    default_repo: str = "",
    skaffold_file: str = "",
    needs: list[str] | None = None,
) -> str:
    """Skaffold deploy CI job: install → run."""
    needs_list = needs or ["test"]

    run_parts = ["skaffold run"]
    if profile:
        run_parts.append(f"--profile {profile}")
    if default_repo:
        run_parts.append(f"--default-repo {default_repo}")
    if skaffold_file:
        run_parts.append(f"--filename {skaffold_file}")
    run_cmd = " ".join(run_parts)

    return f"""\
  deploy:
    name: Deploy — Skaffold
    runs-on: ubuntu-latest
    needs: {needs_list}
    if: github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

{_kubeconfig_step()}

      - name: Install Skaffold
        run: |
          curl -sLo skaffold https://storage.googleapis.com/skaffold/releases/latest/skaffold-linux-amd64
          chmod +x skaffold
          sudo mv skaffold /usr/local/bin/

      - name: Deploy with Skaffold
        run: {run_cmd}
"""


def _helm_deploy_ci_job(
    *,
    release_name: str = "app",
    chart_path: str = "charts/app",
    namespace: str = "",
    values_file: str = "",
    image_tag_ref: str = "${{ github.sha }}",
    needs: list[str] | None = None,
) -> str:
    """Helm deploy CI job: upgrade --install."""
    needs_list = needs or ["test"]

    cmd_parts = [
        f"helm upgrade --install {release_name} {chart_path}",
    ]
    if namespace:
        cmd_parts.append(f"--namespace {namespace}")
        cmd_parts.append("--create-namespace")
    if values_file:
        cmd_parts.append(f"-f {values_file}")
    cmd_parts.append(f"--set image.tag={image_tag_ref}")
    helm_cmd = " \\\n            ".join(cmd_parts)

    return f"""\
  deploy:
    name: Deploy — Helm
    runs-on: ubuntu-latest
    needs: {needs_list}
    if: github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

{_kubeconfig_step()}

      - name: Deploy with Helm
        run: |
          {helm_cmd}
"""


def generate_k8s_deploy_ci(
    deploy_config: dict,
    *,
    project_name: str = "",
) -> GeneratedFile | None:
    """Generate a K8s deploy CI workflow.

    Args:
        deploy_config: Dict with:
            method: 'kubectl' | 'skaffold' | 'helm'
            manifest_dir, namespace, app_name (kubectl)
            profile, default_repo, skaffold_file (skaffold)
            release_name, chart_path, values_file (helm)
            needs: list of job names to depend on
        project_name: For workflow naming.

    Returns:
        GeneratedFile or None.
    """
    method = deploy_config.get("method", "kubectl")
    needs = deploy_config.get("needs")

    if method == "kubectl":
        job_yaml = _kubectl_deploy_ci_job(
            manifest_dir=deploy_config.get("manifest_dir", "k8s"),
            namespace=deploy_config.get("namespace", ""),
            app_name=deploy_config.get("app_name", "app"),
            needs=needs,
        )
    elif method == "skaffold":
        job_yaml = _skaffold_deploy_ci_job(
            profile=deploy_config.get("profile", ""),
            default_repo=deploy_config.get("default_repo", ""),
            skaffold_file=deploy_config.get("skaffold_file", ""),
            needs=needs,
        )
    elif method == "helm":
        job_yaml = _helm_deploy_ci_job(
            release_name=deploy_config.get("release_name", "app"),
            chart_path=deploy_config.get("chart_path", "charts/app"),
            namespace=deploy_config.get("namespace", ""),
            values_file=deploy_config.get("values_file", ""),
            needs=needs,
        )
    else:
        return None

    wf_name = f"{project_name} Deploy" if project_name else "Deploy"

    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
"""
    content = header + job_yaml

    return GeneratedFile(
        path=".github/workflows/deploy.yml",
        content=content,
        overwrite=False,
        reason=f"K8s deploy via {method}",
    )


# ── Terraform CI job ────────────────────────────────────────────


# Provider → environment variables needed for authentication
_TERRAFORM_CREDENTIALS: dict[str, dict[str, str]] = {
    "aws": {
        "AWS_ACCESS_KEY_ID": "${{ secrets.AWS_ACCESS_KEY_ID }}",
        "AWS_SECRET_ACCESS_KEY": "${{ secrets.AWS_SECRET_ACCESS_KEY }}",
    },
    "google": {
        "GOOGLE_CREDENTIALS": "${{ secrets.GOOGLE_CREDENTIALS }}",
    },
    "azurerm": {
        "ARM_CLIENT_ID": "${{ secrets.ARM_CLIENT_ID }}",
        "ARM_CLIENT_SECRET": "${{ secrets.ARM_CLIENT_SECRET }}",
        "ARM_TENANT_ID": "${{ secrets.ARM_TENANT_ID }}",
        "ARM_SUBSCRIPTION_ID": "${{ secrets.ARM_SUBSCRIPTION_ID }}",
    },
}


def _terraform_ci_job(
    *,
    provider: str = "aws",
    working_directory: str = "terraform",
    workspaces: list[str] | None = None,
) -> str:
    """Terraform CI job: init → validate → plan → apply (guarded).

    PR  → plan only (no apply)
    Push to main → plan + apply -auto-approve
    """
    # Build env block for credentials
    creds = _TERRAFORM_CREDENTIALS.get(provider, {})
    env_lines = []
    for key, val in creds.items():
        env_lines.append(f"      {key}: {val}")
    env_block = "\n".join(env_lines)

    # Workspace step (optional)
    workspace_step = ""
    if workspaces:
        # Use TF_WORKSPACE environment variable with first workspace as default
        workspace_step = f"""
      - name: Select Terraform workspace
        run: terraform workspace select {workspaces[0]} || terraform workspace new {workspaces[0]}
"""

    return f"""\
  terraform:
    name: Terraform
    runs-on: ubuntu-latest

    defaults:
      run:
        working-directory: {working_directory}

    env:
{env_block}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
{workspace_step}
      - name: Terraform init
        run: terraform init -no-color

      - name: Terraform validate
        run: terraform validate -no-color

      - name: Terraform plan
        run: terraform plan -no-color -input=false

      - name: Terraform apply
        if: github.event_name == 'push'
        run: terraform apply -no-color -input=false -auto-approve
"""


def generate_terraform_ci(
    terraform_config: dict,
    *,
    project_name: str = "",
) -> GeneratedFile | None:
    """Generate a Terraform CI workflow (GitHub Actions).

    Args:
        terraform_config: Dict with:
            provider: 'aws' | 'google' | 'azurerm'
            working_directory: Path to terraform dir (default 'terraform')
            workspaces: Optional list of workspace names
            project_name: Optional project name for workflow naming
        project_name: For workflow naming (can also be in config).

    Returns:
        GeneratedFile or None.
    """
    provider = terraform_config.get("provider", "aws")
    working_dir = terraform_config.get("working_directory", "terraform")
    workspaces = terraform_config.get("workspaces")
    proj = project_name or terraform_config.get("project_name", "")

    job_yaml = _terraform_ci_job(
        provider=provider,
        working_directory=working_dir,
        workspaces=workspaces,
    )

    wf_name = f"{proj} Terraform" if proj else "Terraform"

    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
"""
    content = header + job_yaml

    return GeneratedFile(
        path=".github/workflows/terraform.yml",
        content=content,
        overwrite=False,
        reason=f"Terraform CI workflow ({provider} provider)",
    )


# ── DNS / CDN post-deploy steps ─────────────────────────────────


# CDN provider → purge command + required secrets
_CDN_PURGE_COMMANDS: dict[str, dict] = {
    "cloudflare": {
        "run": (
            'curl -X POST "https://api.cloudflare.com/client/v4'
            '/zones/${{ secrets.CLOUDFLARE_ZONE_ID }}/purge_cache" '
            '-H "Authorization: Bearer ${{ secrets.CLOUDFLARE_API_TOKEN }}" '
            '-H "Content-Type: application/json" '
            '--data \'{"purge_everything":true}\''
        ),
        "secrets": {
            "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
            "CLOUDFLARE_ZONE_ID": "${{ secrets.CLOUDFLARE_ZONE_ID }}",
        },
    },
    "cloudfront": {
        "run": (
            "aws cloudfront create-invalidation "
            "--distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} "
            '--paths "/*"'
        ),
        "secrets": {
            "AWS_ACCESS_KEY_ID": "${{ secrets.AWS_ACCESS_KEY_ID }}",
            "AWS_SECRET_ACCESS_KEY": "${{ secrets.AWS_SECRET_ACCESS_KEY }}",
            "CLOUDFRONT_DISTRIBUTION_ID": "${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }}",
        },
    },
    "netlify": {
        "run": "npx netlify-cli deploy --prod --dir=.",
        "secrets": {
            "NETLIFY_AUTH_TOKEN": "${{ secrets.NETLIFY_AUTH_TOKEN }}",
            "NETLIFY_SITE_ID": "${{ secrets.NETLIFY_SITE_ID }}",
        },
    },
}


def _dns_verify_ci_step(domains: list[str]) -> str:
    """Build a DNS verification step that checks each domain with dig."""
    checks = []
    for domain in domains:
        checks.append(
            f'echo "Checking {domain}..."\n'
            f'          dig +short {domain} A || echo "WARNING: {domain} has no A record"'
        )
    check_block = "\n          ".join(checks)

    return f"""\
      - name: Verify DNS resolution
        run: |
          {check_block}
"""


def _cdn_purge_ci_step(cdn_provider: str) -> str:
    """Build a CDN cache purge step for the given provider."""
    spec = _CDN_PURGE_COMMANDS.get(cdn_provider)
    if not spec:
        return ""
    return f"""\
      - name: Purge CDN cache ({cdn_provider})
        run: |
          {spec['run']}
"""


def generate_deploy_post_steps(
    deploy_config: dict,
    *,
    project_name: str = "",
) -> GeneratedFile | None:
    """Generate a post-deploy workflow with DNS verification and CDN purge.

    Args:
        deploy_config: Dict with:
            domains: List of domains to verify DNS for.
            cdn_provider: 'cloudflare' | 'cloudfront' | 'netlify'
            project_name: Optional project name for workflow naming.
        project_name: For workflow naming (can also be in config).

    Returns:
        GeneratedFile or None if nothing to do.
    """
    domains = deploy_config.get("domains", [])
    cdn_provider = deploy_config.get("cdn_provider", "")
    proj = project_name or deploy_config.get("project_name", "")

    if not domains and not cdn_provider:
        return None

    # Build steps
    steps: list[str] = ["      - uses: actions/checkout@v4\n"]

    if domains:
        steps.append(_dns_verify_ci_step(domains))

    if cdn_provider:
        purge_step = _cdn_purge_ci_step(cdn_provider)
        if purge_step:
            steps.append(purge_step)

    # Build env block from CDN secrets
    env_lines: list[str] = []
    if cdn_provider and cdn_provider in _CDN_PURGE_COMMANDS:
        secrets = _CDN_PURGE_COMMANDS[cdn_provider]["secrets"]
        for key, val in secrets.items():
            env_lines.append(f"      {key}: {val}")

    env_block = ""
    if env_lines:
        env_block = "\n    env:\n" + "\n".join(env_lines) + "\n"

    wf_name = f"{proj} Post-Deploy" if proj else "Post-Deploy"

    steps_block = "\n".join(steps)

    content = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  workflow_run:
    workflows: ["Deploy"]
    types: [completed]

permissions:
  contents: read

jobs:
  post_deploy:
    name: Post-Deploy Checks
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' }}}}
{env_block}
    steps:
{steps_block}
"""

    return GeneratedFile(
        path=".github/workflows/post-deploy.yml",
        content=content,
        overwrite=False,
        reason=f"Post-deploy checks (DNS verify: {len(domains)} domain(s), CDN: {cdn_provider or 'none'})",
    )


# ── Public API ──────────────────────────────────────────────────


def generate_ci(
    project_root: Path,
    stack_names: list[str],
    *,
    project_name: str = "",
) -> GeneratedFile | None:
    """Generate a comprehensive CI workflow for detected stacks.

    Args:
        project_root: Project root directory.
        stack_names: List of detected stack names.
        project_name: Optional project name for workflow naming.

    Returns:
        GeneratedFile or None if no stacks match.
    """
    job_blocks: list[str] = []
    seen_generators: set[int] = set()

    for name in stack_names:
        gen = _resolve_job(name)
        if gen and id(gen) not in seen_generators:
            job_blocks.append(gen())
            seen_generators.add(id(gen))

    if not job_blocks:
        return None

    wf_name = f"{project_name} CI" if project_name else "CI"

    header = f"""\
# Generated by DevOps Control Plane
name: {wf_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
"""

    content = header + "\n".join(job_blocks)

    return GeneratedFile(
        path=".github/workflows/ci.yml",
        content=content,
        overwrite=False,
        reason=f"Generated CI workflow for stacks: {', '.join(stack_names)}",
    )


# ── Lint workflow ───────────────────────────────────────────────


def _python_lint_steps() -> str:
    return """\
      - name: Lint (ruff)
        run: ruff check .

      - name: Format check (ruff)
        run: ruff format --check .

      - name: Type check (mypy)
        run: mypy src/ --ignore-missing-imports
"""


def _node_lint_steps() -> str:
    return """\
      - name: Lint (eslint)
        run: npm run lint --if-present

      - name: Format check (prettier)
        run: npx prettier --check . 2>/dev/null || true
"""


_LINT_STEPS: dict[str, callable] = {
    "python": _python_lint_steps,
    "node": _node_lint_steps,
    "typescript": _node_lint_steps,
}


def generate_lint(
    project_root: Path,
    stack_names: list[str],
) -> GeneratedFile | None:
    """Generate a lightweight lint-only workflow.

    Returns:
        GeneratedFile or None.
    """
    setup_blocks: list[str] = []
    lint_blocks: list[str] = []

    for name in stack_names:
        # Resolve lint steps
        gen = _LINT_STEPS.get(name)
        if not gen:
            for prefix, g in _LINT_STEPS.items():
                if name.startswith(prefix):
                    gen = g
                    break

        if gen and gen not in [g for g in lint_blocks]:
            if name.startswith("python") or name == "python":
                setup_blocks.append("""\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install lint tools
        run: pip install ruff mypy
""")
            elif name.startswith("node") or name == "node" or name == "typescript":
                setup_blocks.append("""\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install dependencies
        run: npm ci
""")
            lint_blocks.append(gen())

    if not lint_blocks:
        return None

    content = """\
# Generated by DevOps Control Plane
name: Lint

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

""" + "\n".join(setup_blocks) + "\n" + "\n".join(lint_blocks)

    return GeneratedFile(
        path=".github/workflows/lint.yml",
        content=content,
        overwrite=False,
        reason=f"Generated lint workflow for stacks: {', '.join(stack_names)}",
    )
