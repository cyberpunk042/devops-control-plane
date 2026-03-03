"""
Kubernetes deploy CI job generators.

Produces GitHub Actions jobs for deploying to K8s via:
  - kubectl (direct manifest apply)
  - Skaffold (dev/deploy tool)
  - Helm (chart-based deploy)

All three share a common ``_kubeconfig_step`` for cluster auth.
"""

from __future__ import annotations

from src.core.models.template import GeneratedFile


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
