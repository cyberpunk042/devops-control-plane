"""K8s wizard generate — manifest generation from resource definitions."""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.k8s_generate import (
    _build_pod_template,
    _api_version_for_kind,
)

logger = logging.getLogger(__name__)


def _generate_skaffold(data: dict, generated_files: list[dict]) -> dict | None:
    """Build a skaffold.yaml from the wizard state.

    Args:
        data: Wizard state (same shape as wizard_state_to_resources input).
            Supported fields:
            - skaffold (bool): Enable Skaffold config generation.
            - output_dir (str): Directory for generated manifests.
            - tagPolicy (str): One of "gitCommit" (default), "sha256",
              "dateTime", "inputDigest", "envTemplate".
            - _services (list[dict]): Services with image, dockerfile,
              buildArgs, buildTarget, kind fields.
        generated_files: The list of file dicts from generate_k8s_wizard output,
            used to collect manifest paths for the deploy section.

    Returns:
        A file dict {path, content, reason} or None if skaffold is disabled.
    """
    if not data.get("skaffold"):
        return None

    import yaml

    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    # ── Build artifacts ─────────────────────────────────────────────
    # One per non-Skip service with an image.  Each artifact now gets
    # a `docker` section per the Skaffold v4beta11 schema.
    artifacts: list[dict] = []
    for svc in data.get("_services", []):
        svc_kind = svc.get("kind", "Deployment")
        if svc_kind in ("Skip",):
            continue
        image = svc.get("image", "")
        if not image:
            continue

        # Docker build configuration (0.3.3a)
        docker_cfg: dict = {
            "dockerfile": svc.get("dockerfile", "Dockerfile"),
        }
        if svc.get("buildArgs"):
            docker_cfg["buildArgs"] = svc["buildArgs"]
        if svc.get("buildTarget"):
            docker_cfg["target"] = svc["buildTarget"]

        artifacts.append({
            "image": image,
            "context": ".",
            "docker": docker_cfg,
        })

    # ── Manifest paths ──────────────────────────────────────────────
    manifest_paths: list[str] = []
    for f in generated_files:
        path = f.get("path", "")
        if path.endswith(".yaml") or path.endswith(".yml"):
            manifest_paths.append(path)

    if not manifest_paths:
        manifest_paths = [f"{output_dir}/*.yaml"]

    # ── Tag policy (0.3.3c) ─────────────────────────────────────────
    tag_policy_name = data.get("tagPolicy", "gitCommit")
    tag_policy: dict = _build_tag_policy(tag_policy_name)

    # ── Assemble document ───────────────────────────────────────────
    skaffold_doc: dict = {
        "apiVersion": "skaffold/v4beta11",
        "kind": "Config",
        "metadata": {"name": data.get("_services", [{}])[0].get("name", "app")
                     if data.get("_services") else "app"},
    }

    if artifacts:
        # Local build configuration (0.3.3b)
        local_cfg: dict = {
            "push": False,
            "useBuildkit": True,
            "tryImportMissing": True,
            "concurrency": len(artifacts),
        }
        skaffold_doc["build"] = {
            "artifacts": artifacts,
            "local": local_cfg,
            "tagPolicy": tag_policy,
        }

    # ── Deploy strategy routing (0.3.4b/e/f/g) ──────────────────────
    deploy_strategy = data.get("deployStrategy", "kubectl")
    namespace = data.get("namespace")
    variable_vars = _collect_variable_env_keys(data.get("_services", []))
    secret_vars = _collect_secret_env_keys(data.get("_services", []))

    if deploy_strategy == "kustomize":
        # 0.3.4b: Kustomize manifests — point at overlay directories
        kustomize_base = f"{output_dir}/base"
        kustomize_manifest: dict = {"paths": [kustomize_base]}
        if data.get("kustomizeBuildArgs"):
            kustomize_manifest["buildArgs"] = data["kustomizeBuildArgs"]
        skaffold_doc["manifests"] = {"kustomize": kustomize_manifest}

        # 0.3.4g: Kustomize deploy
        kustomize_deploy: dict = {"paths": [kustomize_base]}
        if data.get("kustomizeBuildArgs"):
            kustomize_deploy["buildArgs"] = data["kustomizeBuildArgs"]
        skaffold_doc["deploy"] = {"kustomize": kustomize_deploy}

    elif deploy_strategy == "helm":
        # 0.3.4f: Helm deploy — per-service releases, no kubectl
        skaffold_doc["manifests"] = {"rawYaml": manifest_paths}
        releases = _build_helm_releases(data)
        skaffold_doc["deploy"] = {"helm": {"releases": releases}}

    else:
        # Default: kubectl (0.3.4e)
        skaffold_doc["manifests"] = {"rawYaml": manifest_paths}

        kubectl_cfg: dict = {}
        if namespace:
            kubectl_cfg["defaultNamespace"] = namespace

        # Flags: --server-side for apply, --namespace for global
        flags: dict = {}
        if data.get("serverSideApply"):
            flags["apply"] = ["--server-side"]
        if namespace:
            flags["global"] = ["--namespace", namespace]
        if flags:
            kubectl_cfg["flags"] = flags

        # envsubst hooks (0.3.4c): only for kubectl strategy
        hooks_before: list[dict] = []
        hooks_after: list[dict] = []

        if variable_vars:
            envsubst_hooks = _build_envsubst_hooks(manifest_paths)
            hooks_before.extend(envsubst_hooks)

        # 0.3.8: Lifecycle hooks from wizard preDeploy/postDeploy
        for cmd in data.get("preDeploy", []):
            hooks_before.append({
                "host": {"command": ["sh", "-c", cmd], "dir": "."},
            })
        for cmd in data.get("postDeploy", []):
            hooks_after.append({
                "host": {"command": ["sh", "-c", cmd], "dir": "."},
            })

        # 0.3.4e: Automatic post-deploy verification hooks
        if data.get("postDeployVerify"):
            ns_flag = f" -n {namespace}" if namespace else ""
            for svc in data.get("_services", []):
                svc_kind = svc.get("kind", "Deployment")
                if svc_kind in ("Deployment", "StatefulSet", "DaemonSet"):
                    svc_name = svc.get("name", "")
                    if svc_name:
                        verify_cmd = (
                            f"kubectl rollout status "
                            f"{svc_kind.lower()}/{svc_name}"
                            f"{ns_flag} --timeout=120s"
                        )
                        hooks_after.append({
                            "host": {"command": ["sh", "-c", verify_cmd], "dir": "."},
                        })

        if hooks_before or hooks_after:
            hooks: dict = {}
            if hooks_before:
                hooks["before"] = hooks_before
            if hooks_after:
                hooks["after"] = hooks_after
            kubectl_cfg["hooks"] = hooks

        skaffold_doc["deploy"] = {"kubectl": kubectl_cfg}

    # ── Profiles (0.3.5) ────────────────────────────────────────────
    environments = data.get("environments", [])
    warnings: list[str] = []

    # 0.3.10: Detect duplicate profile names
    if len(environments) != len(set(environments)):
        seen: set[str] = set()
        for env in environments:
            if env in seen:
                warnings.append(
                    f"Duplicate profile name '{env}' — only one copy will be generated"
                )
            seen.add(env)
        environments = list(dict.fromkeys(environments))  # deduplicate, preserve order

    if environments:
        # Stash manifest paths for profile builders (envsubst hooks)
        data["_generated_files"] = generated_files
        skaffold_doc["profiles"] = _build_profiles(data, environments, output_dir)

    content = yaml.dump(skaffold_doc, default_flow_style=False, sort_keys=False)

    # 0.3.5b: Inject developer instructions as YAML comments
    if "dev-from-local" in environments:
        dev_comment = (
            "# ── dev-from-local usage ─────────────────────────────────\n"
            "# export SKAFFOLD_DEFAULT_REPO=\"\"  # no remote registry\n"
            "# Load your .env file: set -a; source .env; set +a\n"
            "# Then run: skaffold dev -p dev-from-local\n"
        )
        content = content.replace(
            "- name: dev-from-local\n",
            dev_comment + "- name: dev-from-local\n",
        )
    result = {
        "path": "skaffold.yaml",
        "content": content,
        "reason": "Skaffold pipeline — build → push → deploy",
        "overwrite": False,
    }

    # .env.example (0.3.4c): list required variables for local dev
    if variable_vars:
        result["env_example"] = _build_env_example(variable_vars)
        result["needs_envsubst"] = True

    # 0.3.4b: Base kustomization.yaml referencing all generated manifests
    if deploy_strategy == "kustomize":
        kust_files = _build_kustomization_files(
            generated_files, output_dir, variable_vars, secret_vars,
        )
        if kust_files:
            result["kustomization_files"] = kust_files

    if warnings:
        result["warnings"] = warnings

    return result


def _build_profiles(
    data: dict, environments: list[str], output_dir: str,
) -> list[dict]:
    """Build Skaffold profiles from wizard environments.

    Each environment gets a profile with environment-specific overrides
    for build, deploy, and portForward settings.
    """
    return [
        _build_profile(env, data, output_dir)
        for env in environments
    ]


def _build_profile(env: str, data: dict, output_dir: str) -> dict:
    """Build a single Skaffold profile for a given environment.

    Profile flavors (0.3.5b-d):
    - dev-from-local: sha256 tag, no push, port-forward, default namespace
    - dev: push to registry, kustomize overlay, no port-forward
    - staging: push, namespace override
    - prod: gitCommit tag, server-side apply
    """
    services = data.get("_services", [])
    namespace = data.get("namespace")
    deploy_strategy = data.get("deployStrategy", "kubectl")

    profile: dict = {"name": env}

    if env == "dev-from-local":
        # 0.3.5b: The critical profile for local development
        profile["activation"] = [{"command": "dev"}]
        build_cfg: dict = {
            "local": {"push": False},
            "tagPolicy": {"sha256": {}},
        }
        # 0.3.7: File sync artifacts for hot-reload
        sync_artifacts = _build_sync_artifacts(services)
        if sync_artifacts:
            build_cfg["artifacts"] = sync_artifacts
        profile["build"] = build_cfg
        profile["deploy"] = {
            "kubectl": {"defaultNamespace": "default"},
        }

        # 0.3.5b: envsubst hooks for variable-bearing manifests
        variable_vars = _collect_variable_env_keys(services)
        if variable_vars:
            manifest_paths = [f.get("path", "") for f in data.get("_generated_files", [])]
            envsubst_hooks = _build_envsubst_hooks(manifest_paths)
            if envsubst_hooks:
                profile["deploy"]["kubectl"]["hooks"] = {"before": envsubst_hooks}
        # Port forwarding for all services with ports
        pf = _build_port_forward_entries(services, namespace=namespace)
        if pf:
            profile["portForward"] = pf

    elif env == "dev":
        # 0.3.5c: CI/CD dev — push, overlay, no port-forward
        profile["activation"] = [{"command": "run"}]
        profile["build"] = {
            "local": {"push": True},
        }
        if deploy_strategy == "kustomize":
            overlay_path = f"{output_dir}/overlays/dev"
            profile["manifests"] = {
                "kustomize": {"paths": [overlay_path]},
            }
            profile["deploy"] = {
                "kustomize": {"paths": [overlay_path]},
            }
        else:
            dev_ns = f"{namespace}-dev" if namespace else "dev"
            profile["deploy"] = {
                "kubectl": {"defaultNamespace": dev_ns},
            }

    elif env == "staging":
        # 0.3.5d: Staging — push, namespace override
        profile["activation"] = [{"command": "run"}]
        profile["build"] = {
            "local": {"push": True},
        }
        staging_ns = f"{namespace}-staging" if namespace else "staging"
        if deploy_strategy == "kustomize":
            overlay_path = f"{output_dir}/overlays/staging"
            profile["manifests"] = {
                "kustomize": {"paths": [overlay_path]},
            }
            profile["deploy"] = {
                "kustomize": {"paths": [overlay_path]},
            }
        else:
            profile["deploy"] = {
                "kubectl": {"defaultNamespace": staging_ns},
            }

    elif env == "prod":
        # 0.3.5d: Production — gitCommit tag, server-side apply
        profile["activation"] = [{"command": "deploy"}]
        profile["build"] = {
            "local": {"push": True},
            "tagPolicy": {"gitCommit": {"variant": "Tags"}},
        }
        prod_ns = namespace or "production"
        if deploy_strategy == "kustomize":
            overlay_path = f"{output_dir}/overlays/prod"
            profile["manifests"] = {
                "kustomize": {"paths": [overlay_path]},
            }
            profile["deploy"] = {
                "kustomize": {"paths": [overlay_path]},
            }
        else:
            profile["deploy"] = {
                "kubectl": {
                    "defaultNamespace": prod_ns,
                    "flags": {"apply": ["--server-side"]},
                },
            }

    else:
        # Generic environment profile
        profile["activation"] = [{"command": "run"}]
        profile["build"] = {"local": {"push": True}}
        profile["deploy"] = {
            "kubectl": {"defaultNamespace": env},
        }

    # 0.3.5a: Merge custom activation triggers (kubeContext, env)
    custom_activation = data.get("profileActivation", {}).get(env, {})
    if custom_activation:
        activations = profile.get("activation", [])
        if "kubeContext" in custom_activation:
            activations.append({"kubeContext": custom_activation["kubeContext"]})
        if "env" in custom_activation:
            activations.append({"env": custom_activation["env"]})
        profile["activation"] = activations

    # 0.3.5e: Merge profile patches (JSON Patch-style overrides)
    profile_patches = data.get("profilePatches", {}).get(env, [])
    if profile_patches:
        profile["patches"] = profile_patches

    return profile


def _build_port_forward_entries(
    services: list[dict], *, namespace: str | None = None,
) -> list[dict]:
    """Build Skaffold portForward entries for services with ports.

    Each service with a port gets a port-forward entry.
    Collision detection: if two services expose the same port,
    the second gets localPort incremented.
    """
    entries: list[dict] = []
    used_local_ports: set[int] = set()

    for svc in services:
        port = svc.get("port")
        if not port:
            continue

        local_port = port
        while local_port in used_local_ports:
            local_port += 1
        used_local_ports.add(local_port)

        entry = {
            "resourceType": "service",
            "resourceName": svc["name"],
            "port": port,
            "localPort": local_port,
        }
        if namespace:
            entry["namespace"] = namespace
        entries.append(entry)

    return entries


def _build_sync_artifacts(services: list[dict]) -> list[dict]:
    """Build artifact entries with sync rules for dev hot-reload.

    Each service with a language that supports hot-reload gets an artifact
    entry with sync.manual rules. Compiled languages (Go, Rust) are skipped.
    """
    artifacts: list[dict] = []
    for svc in services:
        if svc.get("kind") == "Skip" or not svc.get("image"):
            continue
        language = svc.get("language", "")
        sync_rules = _sync_rules_for_language(language)
        if not sync_rules:
            continue
        artifacts.append({
            "image": svc["image"],
            "sync": {"manual": sync_rules},
        })
    return artifacts


def _sync_rules_for_language(language: str) -> list[dict]:
    """Return sync.manual rules for a given language.

    Returns empty list for compiled languages or unknown languages.
    Sync rules map source globs to container destination /app.
    """
    globs: dict[str, list[dict]] = {
        "python": [{"src": "**/*.py", "dest": "/app", "strip": ""}],
        "node": [
            {"src": "**/*.js", "dest": "/app", "strip": ""},
            {"src": "**/*.ts", "dest": "/app", "strip": ""},
        ],
        "javascript": [{"src": "**/*.js", "dest": "/app", "strip": ""}],
        "typescript": [
            {"src": "**/*.ts", "dest": "/app", "strip": ""},
            {"src": "**/*.js", "dest": "/app", "strip": ""},
        ],
        "ruby": [{"src": "**/*.rb", "dest": "/app", "strip": ""}],
        "php": [{"src": "**/*.php", "dest": "/app", "strip": ""}],
    }
    return globs.get(language, [])


def _build_kustomization_files(
    generated_files: list[dict], output_dir: str,
    variable_vars: list[str] | None = None,
    secret_vars: list[str] | None = None,
) -> list[dict]:
    """Build kustomization.yaml files for kustomize-based projects.

    Generates a base kustomization.yaml that lists all generated K8s
    manifests under `resources:`. Only YAML files from generated_files
    are included; filenames are extracted from their full paths.

    When variable_vars is non-empty, adds configMapGenerator pulling
    from .env file. When secret_vars is non-empty, adds secretGenerator
    pulling from .env.secret file.
    """
    import yaml
    import posixpath

    # Collect YAML filenames relative to their directory
    resource_names: list[str] = []
    for f in generated_files:
        path = f.get("path", "")
        if path.endswith(".yaml") or path.endswith(".yml"):
            resource_names.append(posixpath.basename(path))

    if not resource_names:
        return []

    kust_doc: dict = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": resource_names,
    }

    # 0.3.4c: configMapGenerator for variable env vars
    if variable_vars:
        kust_doc["configMapGenerator"] = [{
            "name": "app-env",
            "envs": [".env"],
        }]

    # 0.3.4c: secretGenerator for secret env vars
    if secret_vars:
        kust_doc["secretGenerator"] = [{
            "name": "app-secrets",
            "envs": [".env.secret"],
        }]

    base_path = f"{output_dir}/base/kustomization.yaml"
    return [{
        "path": base_path,
        "content": yaml.dump(kust_doc, default_flow_style=False, sort_keys=False),
        "reason": "Kustomize base — references all generated manifests",
        "overwrite": False,
    }]


def _build_helm_releases(data: dict) -> list[dict]:
    """Build Skaffold helm.releases list from wizard state.

    Each non-Skip service with an image gets a Helm release.
    Namespace, chartPath, valuesFiles, and env vars flow through.
    """
    namespace = data.get("namespace")
    chart_path = data.get("helmChartPath", "charts")
    values_files = data.get("helmValuesFiles")
    use_helm_secrets = data.get("helmSecretsPlugin", False)
    releases: list[dict] = []

    for svc in data.get("_services", []):
        if svc.get("kind") == "Skip":
            continue
        if not svc.get("image"):
            continue

        release: dict = {
            "name": svc["name"],
            "chartPath": chart_path,
        }
        if values_files:
            release["valuesFiles"] = values_files
        if namespace:
            release["namespace"] = namespace
            release["createNamespace"] = True
        if use_helm_secrets:
            release["useHelmSecrets"] = True

        # Collect env vars: literals → setValues, variables → setValueTemplates
        set_values: dict = {}
        set_value_templates: dict = {}
        for env in svc.get("env", []):
            key = env.get("key", "")
            if not key:
                continue
            env_type = env.get("type", "")
            if env_type in ("variable", "secret"):
                # 0.3.4f: Variables use Go template syntax for Skaffold
                set_value_templates[key] = "{{." + key + "}}"
            elif env.get("value"):
                set_values[key] = env["value"]
        if set_values:
            release["setValues"] = set_values
        if set_value_templates:
            release["setValueTemplates"] = set_value_templates

        releases.append(release)

    return releases

def _build_tag_policy(name: str) -> dict:
    """Build a Skaffold tagPolicy dict from a policy name.

    Supported policies (Skaffold v4beta11 spec):
    - gitCommit: Tag with git SHA/tag. Default. Reproducible.
    - sha256: Content-addressable. Fast for dev, no git needed.
    - dateTime: Timestamp-based. Includes format + timezone.
    - inputDigest: Hash of build inputs.
    - envTemplate: Go template with env vars.
    """
    if name == "sha256":
        return {"sha256": {}}
    if name == "inputDigest":
        return {"inputDigest": {}}
    if name == "dateTime":
        return {"dateTime": {
            "format": "2006-01-02_15-04-05",
            "timezone": "Local",
        }}
    if name == "envTemplate":
        return {"envTemplate": {
            "template": "{{.IMAGE_NAME}}:{{.DIGEST_HEX}}",
        }}
    # Default: gitCommit
    return {"gitCommit": {"variant": "Tags"}}


def _collect_variable_env_keys(services: list[dict]) -> list[str]:
    """Scan services for env vars that need envsubst (type=variable or secret).

    Returns a deduplicated, sorted list of env var keys that will appear
    as ${KEY} placeholders in the generated manifests. These need to be
    resolved via envsubst before kubectl apply.
    """
    keys: set[str] = set()
    for svc in services:
        for env in svc.get("env", []):
            env_type = env.get("type", "")
            if env_type in ("variable", "secret"):
                key = env.get("key", "")
                if key:
                    keys.add(key)
    return sorted(keys)


def _collect_secret_env_keys(services: list[dict]) -> list[str]:
    """Scan services for env vars of type=secret only.

    Returns a deduplicated, sorted list of secret-only env var keys.
    Used by kustomize secretGenerator to pull secrets from .env.secret.
    """
    keys: set[str] = set()
    for svc in services:
        for env in svc.get("env", []):
            if env.get("type") == "secret":
                key = env.get("key", "")
                if key:
                    keys.add(key)
    return sorted(keys)


def _build_envsubst_hooks(manifest_paths: list[str]) -> list[dict]:
    """Build Skaffold pre-deploy hooks that run envsubst on manifests.

    Each hook is a host command that substitutes ${VAR} patterns
    in-place. Only concrete file paths get hooks (not globs).

    Skaffold hook schema (v4beta11):
        hooks.before[].host.command: [str]
        hooks.before[].host.dir: str
    """
    hooks: list[dict] = []
    for path in manifest_paths:
        # Skip glob patterns — envsubst can't run on globs
        if "*" in path or "?" in path:
            continue
        hooks.append({
            "host": {
                "command": ["sh", "-c", f"envsubst < {path} > {path}.tmp && mv {path}.tmp {path}"],
                "dir": ".",
            },
        })
    return hooks


def _build_env_example(variable_keys: list[str]) -> str:
    """Build .env.example content listing all required variables.

    Each variable gets a comment line and an empty assignment.
    This file tells developers which env vars to set before running
    `skaffold dev -p dev-from-local`.
    """
    lines = [
        "# Required environment variables for local development",
        "# Copy this file to .env and fill in the values:",
        "#   cp .env.example .env",
        "#   set -a; source .env; set +a",
        "#   skaffold dev -p dev-from-local",
        "",
    ]
    for key in variable_keys:
        lines.append(f"{key}=")
    lines.append("")
    return "\n".join(lines)

def generate_k8s_wizard(
    project_root: Path,
    resources: list[dict],
) -> dict:
    """Generate K8s manifests from wizard resource definitions.

    Args:
        resources: List of resource dicts with:
            kind: Deployment | StatefulSet | DaemonSet | Job | CronJob |
                  Service | ConfigMap | Ingress | Namespace | ...
            name: resource name
            namespace: target namespace
            spec: kind-specific fields (image, port, replicas, etc.)

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    import yaml
    from src.core.models.template import GeneratedFile

    if not resources:
        return {"error": "At least one resource is required"}

    files: list[dict] = []
    warnings: list[str] = []

    for res in resources:
        kind = (res.get("kind") or "").strip() or "Deployment"
        name = (res.get("name") or "").strip()
        namespace = (res.get("namespace") or "default").strip()
        spec = res.get("spec", {})

        if not name:
            continue

        # Skip Managed services — no manifest generated
        if kind == "Managed":
            continue

        manifest: dict = {
            "apiVersion": _api_version_for_kind(kind),
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
        }

        # ── Workload kinds (have pod templates) ──────────────────
        if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            pod_template = _build_pod_template(name, spec)

            if kind == "Deployment":
                replicas = spec.get("replicas", 1)
                manifest["spec"] = {
                    "replicas": replicas,
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Deployment strategy — use wizard values, not hardcoded
                strategy_type = spec.get("strategy", "RollingUpdate" if replicas > 1 else "Recreate")
                strategy_obj: dict = {"type": strategy_type}
                if strategy_type == "RollingUpdate":
                    strategy_obj["rollingUpdate"] = {
                        "maxSurge": spec.get("maxSurge", 1),
                        "maxUnavailable": spec.get("maxUnavailable", 0),
                    }
                manifest["spec"]["strategy"] = strategy_obj

            elif kind == "StatefulSet":
                replicas = spec.get("replicas", 1)
                svc_name = spec.get("headlessServiceName", f"{name}-headless")
                manifest["spec"] = {
                    "replicas": replicas,
                    "serviceName": svc_name,
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Pod management policy
                pmp = spec.get("podManagementPolicy")
                if pmp and pmp != "OrderedReady":  # OrderedReady is default
                    manifest["spec"]["podManagementPolicy"] = pmp
                # Update strategy
                ss_strategy = spec.get("strategy")
                if ss_strategy:
                    ss_update: dict = {"type": ss_strategy}
                    if ss_strategy == "RollingUpdate" and spec.get("partition") is not None:
                        part_val = spec["partition"]
                        if part_val and int(part_val) > 0:
                            ss_update["rollingUpdate"] = {"partition": int(part_val)}
                    manifest["spec"]["updateStrategy"] = ss_update
                # Volume claim templates
                vcts = spec.get("volumeClaimTemplates", [])
                if vcts:
                    manifest["spec"]["volumeClaimTemplates"] = []
                    for vct in vcts:
                        vct_spec: dict = {
                            "metadata": {"name": vct.get("name", "data")},
                            "spec": {
                                "accessModes": [vct.get("accessMode", "ReadWriteOnce")],
                                "resources": {
                                    "requests": {
                                        "storage": vct.get("size", "1Gi"),
                                    },
                                },
                            },
                        }
                        if vct.get("storageClass"):
                            vct_spec["spec"]["storageClassName"] = vct["storageClass"]
                        manifest["spec"]["volumeClaimTemplates"].append(vct_spec)

            elif kind == "DaemonSet":
                manifest["spec"] = {
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Node selector (string → dict)
                ns_raw = spec.get("nodeSelector")
                if ns_raw:
                    if isinstance(ns_raw, str):
                        # Parse "key=val,key2=val2" format
                        ns_dict = {}
                        for pair in ns_raw.split(","):
                            pair = pair.strip()
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                ns_dict[k.strip()] = v.strip()
                        if ns_dict:
                            pod_template["spec"]["nodeSelector"] = ns_dict
                    else:
                        pod_template["spec"]["nodeSelector"] = ns_raw
                # Tolerations
                if spec.get("tolerations"):
                    pod_template["spec"]["tolerations"] = spec["tolerations"]
                # Update strategy
                ds_strategy = spec.get("strategy")
                if ds_strategy:
                    ds_update: dict = {"type": ds_strategy}
                    if ds_strategy == "RollingUpdate" and spec.get("maxUnavailable"):
                        ds_update["rollingUpdate"] = {
                            "maxUnavailable": spec["maxUnavailable"],
                        }
                    manifest["spec"]["updateStrategy"] = ds_update

            elif kind == "Job":
                job_spec: dict = {
                    "template": pod_template,
                }
                # Job fields
                if spec.get("backoffLimit") is not None:
                    job_spec["backoffLimit"] = spec["backoffLimit"]
                else:
                    job_spec["backoffLimit"] = 4
                if spec.get("completions") is not None:
                    job_spec["completions"] = spec["completions"]
                if spec.get("parallelism") is not None:
                    job_spec["parallelism"] = spec["parallelism"]
                if spec.get("activeDeadlineSeconds"):
                    job_spec["activeDeadlineSeconds"] = spec["activeDeadlineSeconds"]
                if spec.get("ttlSecondsAfterFinished") is not None:
                    job_spec["ttlSecondsAfterFinished"] = spec["ttlSecondsAfterFinished"]
                # Jobs default to Never restart
                pod_template["spec"]["restartPolicy"] = spec.get("restartPolicy", "Never")
                manifest["spec"] = job_spec

            elif kind == "CronJob":
                schedule = spec.get("schedule", "0 * * * *")
                job_template_pod = pod_template
                job_template_pod["spec"]["restartPolicy"] = spec.get("restartPolicy", "Never")
                manifest["spec"] = {
                    "schedule": schedule,
                    "concurrencyPolicy": spec.get("concurrencyPolicy", "Forbid"),
                    "jobTemplate": {
                        "spec": {
                            "template": job_template_pod,
                            "backoffLimit": spec.get("backoffLimit", 4),
                        },
                    },
                }
                if spec.get("successfulJobsHistoryLimit") is not None:
                    manifest["spec"]["successfulJobsHistoryLimit"] = spec["successfulJobsHistoryLimit"]
                if spec.get("failedJobsHistoryLimit") is not None:
                    manifest["spec"]["failedJobsHistoryLimit"] = spec["failedJobsHistoryLimit"]
                if spec.get("activeDeadlineSeconds"):
                    manifest["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = spec["activeDeadlineSeconds"]
                # CronJob extras
                if spec.get("suspend"):
                    manifest["spec"]["suspend"] = True
                if spec.get("startingDeadlineSeconds"):
                    manifest["spec"]["startingDeadlineSeconds"] = int(spec["startingDeadlineSeconds"])
                if spec.get("ttlSecondsAfterFinished") is not None:
                    manifest["spec"]["jobTemplate"]["spec"]["ttlSecondsAfterFinished"] = spec["ttlSecondsAfterFinished"]

        elif kind == "Service":
            port = spec.get("port", 80)
            target_port = spec.get("target_port", port)
            svc_type = spec.get("type", "ClusterIP")
            manifest["spec"] = {
                "type": svc_type,
                "selector": {"app": spec.get("selector", name)},
                "ports": [{"port": port, "targetPort": target_port}],
            }
            # Headless service for StatefulSets
            if svc_type == "None" or spec.get("headless"):
                manifest["spec"]["clusterIP"] = "None"

        elif kind == "ConfigMap":
            manifest["data"] = spec.get("data", {})

        elif kind == "Secret":
            manifest["type"] = spec.get("type", "Opaque")
            # 0.3.4d: Always use stringData; validate data: values if provided
            if "stringData" in spec:
                manifest["stringData"] = spec["stringData"]
            elif "data" in spec:
                # Check if values are valid base64 — warn if not
                import base64
                raw_data = spec["data"]
                for k, v in raw_data.items():
                    try:
                        base64.b64decode(v, validate=True)
                    except Exception:
                        warnings.append(
                            f"Secret '{name}': data.{k} is not valid base64, "
                            f"converted to stringData"
                        )
                manifest["stringData"] = raw_data
            else:
                manifest["stringData"] = {}

        elif kind == "Ingress":
            manifest["apiVersion"] = "networking.k8s.io/v1"
            host = spec.get("host", f"{name}.example.com")
            # Multi-service: translator provides pre-built path rules
            if spec.get("_paths"):
                paths = spec["_paths"]
            else:
                # Single service: build simple default-backend path
                port = spec.get("port", 80)
                service = spec.get("service", name)
                paths = [{
                    "path": "/",
                    "pathType": "Prefix",
                    "backend": {
                        "service": {
                            "name": service,
                            "port": {"number": port},
                        },
                    },
                }]
            manifest["spec"] = {
                "rules": [{
                    "host": host,
                    "http": {
                        "paths": paths,
                    },
                }],
            }

        elif kind == "PersistentVolumeClaim":
            pvc_spec: dict = {
                "accessModes": spec.get("accessModes", ["ReadWriteOnce"]),
                "resources": {
                    "requests": {
                        "storage": spec.get("storage", spec.get("size", "1Gi")),
                    },
                },
            }
            sc = spec.get("storageClassName", spec.get("storageClass"))
            if sc:
                pvc_spec["storageClassName"] = sc
            # Bind to specific PV (pvc-static)
            if spec.get("volumeName"):
                pvc_spec["volumeName"] = spec["volumeName"]
            manifest["spec"] = pvc_spec
            # Longhorn annotations
            lh = spec.get("longhornConfig")
            if lh:
                manifest["metadata"].setdefault("annotations", {})
                if lh.get("replicas"):
                    manifest["metadata"]["annotations"]["longhorn.io/number-of-replicas"] = str(lh["replicas"])
                if lh.get("dataLocality"):
                    manifest["metadata"]["annotations"]["longhorn.io/data-locality"] = lh["dataLocality"]

        elif kind == "Namespace":
            del manifest["metadata"]["namespace"]
            manifest.pop("spec", None)

        else:
            # Generic: just metadata, user will edit
            manifest["spec"] = spec or {}

        content = yaml.dump(manifest, default_flow_style=False, sort_keys=False)

        # 0.3.4d: Secrets with ${VAR} placeholders need an envsubst reminder
        if kind == "Secret" and "${" in content:
            content = "# requires envsubst before kubectl apply\n" + content

        # Use output_dir from resource or default to k8s/
        out_dir = res.get("output_dir", "k8s")
        files.append(GeneratedFile(
            path=f"{out_dir}/{name}-{kind.lower()}.yaml",
            content=content,
            overwrite=False,
            reason=f"{kind} '{name}' in namespace '{namespace}'",
        ).model_dump())

    if not files:
        return {"error": "No valid resources to generate"}

    result: dict = {"ok": True, "files": files}
    if warnings:
        result["warnings"] = warnings
    return result
