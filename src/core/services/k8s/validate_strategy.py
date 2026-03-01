"""K8s validation — Layer 7: Deployment strategy validation.

Raw kubectl, Helm, Kustomize, Skaffold, and mixed strategy checks.
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import _K8S_KINDS


# ═══════════════════════════════════════════════════════════════════
#  Layer 7 — Deployment strategy validation
# ═══════════════════════════════════════════════════════════════════

# Regex to find ${VAR} envsubst patterns in raw manifest text
_ENVSUBST_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Standard K8s namespaces that exist without needing a Namespace manifest
_BUILTIN_NAMESPACES = frozenset({
    "default", "kube-system", "kube-public", "kube-node-lease",
})

# Workload kinds whose pod template labels can match a Service selector
_WORKLOAD_KINDS = {
    "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Pod",
}


def _validate_deployment_strategy(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Deployment strategy validation (Layer 7).

    Checks that the chosen deployment method is internally consistent.
    """
    # Raw kubectl checks apply when we have any raw manifests
    if all_resources:
        _strategy_raw_kubectl(project_root, status, all_resources, issues)

    # Helm checks apply when we have helm charts
    helm_charts = status.get("helm_charts", [])
    if helm_charts:
        _strategy_helm(project_root, status, helm_charts, issues)

    # Kustomize checks apply when kustomize is detected
    kustomize = status.get("kustomize", {})
    if kustomize.get("exists"):
        _strategy_kustomize(project_root, status, kustomize, all_resources, issues)

    # Skaffold checks apply when skaffold.yaml exists
    skaffold_file = project_root / "skaffold.yaml"
    if skaffold_file.is_file():
        _strategy_skaffold(project_root, skaffold_file, issues)

    # Mixed strategy coherence checks
    _strategy_mixed(
        project_root, status, all_resources,
        helm_charts, kustomize, skaffold_file, issues,
    )


def _strategy_raw_kubectl(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Raw kubectl deployment strategy checks (8 checks).

    These checks validate that raw K8s manifests are self-contained
    and can be successfully applied with `kubectl apply`.
    """

    # ── Pre-compute resource indices for cross-checks ─────────

    # All Namespace names defined in manifests
    defined_namespaces: set[str] = set()
    # All ConfigMap names by namespace
    defined_configmaps: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All Secret names by namespace
    defined_secrets: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All Service names by namespace
    defined_services: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All StorageClass names
    defined_storageclasses: set[str] = set()
    # All workload pod template labels by namespace
    workload_labels: list[tuple[str, dict]] = []  # (ns, labels_dict)

    for _path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        ns = res.get("metadata", {}).get("namespace", "") or "default"

        if kind == "Namespace":
            defined_namespaces.add(name)
        elif kind == "ConfigMap":
            defined_configmaps.setdefault(ns, set()).add(name)
        elif kind == "Secret":
            defined_secrets.setdefault(ns, set()).add(name)
        elif kind == "Service":
            defined_services.setdefault(ns, set()).add(name)
        elif kind == "StorageClass":
            defined_storageclasses.add(name)

        # Collect workload pod template labels
        if kind in _WORKLOAD_KINDS:
            if kind == "Pod":
                pod_labels = res.get("metadata", {}).get("labels", {})
            else:
                pod_labels = (
                    res.get("spec", {})
                    .get("template", {})
                    .get("metadata", {})
                    .get("labels", {})
                )
            if pod_labels:
                workload_labels.append((ns, pod_labels))

    # ── Check 1: Unresolved envsubst variables ────────────────
    for manifest in status.get("manifests", []):
        manifest_path = project_root / manifest["path"]
        if manifest_path.is_file():
            try:
                text = manifest_path.read_text(encoding="utf-8", errors="ignore")
                found_vars = _ENVSUBST_RE.findall(text)
                if found_vars:
                    unique_vars = sorted(set(found_vars))
                    issues.append({
                        "file": manifest["path"],
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: unresolved envsubst variables "
                            f"({', '.join('${' + v + '}' for v in unique_vars)})"
                            f" — manifests need envsubst processing before apply"
                        ),
                    })
            except Exception:
                pass

    # ── Check 2: Missing Namespace manifest ───────────────────
    referenced_namespaces: set[str] = set()
    for _path, res in all_resources:
        ns = res.get("metadata", {}).get("namespace", "")
        if ns:
            referenced_namespaces.add(ns)

    for ns in sorted(referenced_namespaces):
        if ns not in _BUILTIN_NAMESPACES and ns not in defined_namespaces:
            issues.append({
                "file": "deployment-strategy",
                "severity": "warning",
                "message": (
                    f"Raw kubectl: namespace '{ns}' referenced by resources "
                    f"but no Namespace manifest defined — "
                    f"kubectl apply will fail if namespace doesn't exist"
                ),
            })

    # ── Check 3: CRD ordering gap ─────────────────────────────
    # If a resource uses a non-standard apiVersion (contains a dot,
    # like cert-manager.io/v1) AND its kind is not in _K8S_KINDS,
    # it's a Custom Resource. Check if a CRD is present.
    has_crds = any(
        res.get("kind") == "CustomResourceDefinition"
        for _, res in all_resources
    )
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        api_version = res.get("apiVersion", "")
        name = res.get("metadata", {}).get("name", "?")
        # Custom resource heuristic: apiVersion has a domain (dot)
        # and kind is not a standard K8s kind
        if (
            kind
            and kind not in _K8S_KINDS
            and "." in api_version
            and kind != "CustomResourceDefinition"
            and not has_crds
        ):
            issues.append({
                "file": rel_path,
                "severity": "error",
                "message": (
                    f"Raw kubectl: {kind}/{name} is a Custom Resource "
                    f"(apiVersion: {api_version}) but no CRD manifest found — "
                    f"kubectl apply will fail without the CRD installed"
                ),
            })

    # ── Check 4: Raw Secret with literal data ─────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        if kind == "Secret":
            has_data = bool(res.get("data"))
            has_string_data = bool(res.get("stringData"))
            if has_data or has_string_data:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": (
                        f"Raw kubectl: Secret/{name} contains plaintext "
                        f"secret data in manifests — consider SealedSecret, "
                        f"ExternalSecret, or SOPS for production"
                    ),
                })

    # ── Check 5: ConfigMap/Secret reference gap ───────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind not in _WORKLOAD_KINDS and kind not in ("Job", "CronJob"):
            continue
        name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"

        # Get pod spec containers
        if kind in ("Job", "CronJob"):
            if kind == "CronJob":
                pod_spec = (
                    res.get("spec", {})
                    .get("jobTemplate", {})
                    .get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )
            else:
                pod_spec = (
                    res.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )
        elif kind == "Pod":
            pod_spec = res.get("spec", {})
        else:
            pod_spec = (
                res.get("spec", {})
                .get("template", {})
                .get("spec", {})
            )

        containers = pod_spec.get("containers", []) + pod_spec.get("initContainers", [])
        for container in containers:
            # Check envFrom references
            for env_from in container.get("envFrom", []):
                cm_ref = env_from.get("configMapRef", {})
                if cm_ref:
                    cm_name = cm_ref.get("name", "")
                    if cm_name and cm_name not in defined_configmaps.get(ns, set()):
                        issues.append({
                            "file": rel_path,
                            "severity": "warning",
                            "message": (
                                f"Raw kubectl: {kind}/{name} references "
                                f"ConfigMap '{cm_name}' via envFrom but "
                                f"no ConfigMap with that name found in manifests"
                            ),
                        })
                secret_ref = env_from.get("secretRef", {})
                if secret_ref:
                    s_name = secret_ref.get("name", "")
                    if s_name and s_name not in defined_secrets.get(ns, set()):
                        issues.append({
                            "file": rel_path,
                            "severity": "warning",
                            "message": (
                                f"Raw kubectl: {kind}/{name} references "
                                f"Secret '{s_name}' via envFrom but "
                                f"no Secret with that name found in manifests"
                            ),
                        })

        # Check volume references
        for vol in pod_spec.get("volumes", []):
            cm_vol = vol.get("configMap", {})
            if cm_vol:
                cm_name = cm_vol.get("name", "")
                if cm_name and cm_name not in defined_configmaps.get(ns, set()):
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: {kind}/{name} mounts "
                            f"ConfigMap '{cm_name}' as volume but "
                            f"no ConfigMap with that name found in manifests"
                        ),
                    })
            secret_vol = vol.get("secret", {})
            if secret_vol:
                s_name = secret_vol.get("secretName", "")
                if s_name and s_name not in defined_secrets.get(ns, set()):
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: {kind}/{name} mounts "
                            f"Secret '{s_name}' as volume but "
                            f"no Secret with that name found in manifests"
                        ),
                    })

    # ── Check 6: Service selector mismatch ────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "Service":
            continue
        name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"
        selector = res.get("spec", {}).get("selector", {})
        if not selector:
            continue  # headless or ExternalName

        # Check if any workload's pod labels are a superset of the selector
        matched = False
        for wl_ns, wl_labels in workload_labels:
            # Services match within same namespace (or if ns not set)
            if wl_ns != ns:
                continue
            # All selector labels must be present in workload labels
            if all(wl_labels.get(k) == v for k, v in selector.items()):
                matched = True
                break

        if not matched:
            issues.append({
                "file": rel_path,
                "severity": "warning",
                "message": (
                    f"Raw kubectl: Service/{name} selector "
                    f"{selector} matches no workload pod labels "
                    f"in namespace '{ns}'"
                ),
            })

    # ── Check 7: Ingress backend gap ──────────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "Ingress":
            continue
        ingress_name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"
        ns_services = defined_services.get(ns, set())

        # Check default backend
        default_backend = res.get("spec", {}).get("defaultBackend", {})
        if default_backend:
            svc_name = default_backend.get("service", {}).get("name", "")
            if svc_name and svc_name not in ns_services:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": (
                        f"Raw kubectl: Ingress/{ingress_name} default backend "
                        f"references Service '{svc_name}' not found in manifests"
                    ),
                })

        # Check rule backends
        for rule in res.get("spec", {}).get("rules", []):
            for path_entry in (rule.get("http", {}) or {}).get("paths", []):
                backend = path_entry.get("backend", {})
                svc_name = backend.get("service", {}).get("name", "")
                if svc_name and svc_name not in ns_services:
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: Ingress/{ingress_name} references "
                            f"backend Service '{svc_name}' not found in manifests"
                        ),
                    })

    # ── Check 8: PVC StorageClass gap ─────────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "PersistentVolumeClaim":
            continue
        name = res.get("metadata", {}).get("name", "?")
        sc_name = res.get("spec", {}).get("storageClassName", "")
        if sc_name and sc_name not in defined_storageclasses:
            issues.append({
                "file": rel_path,
                "severity": "info",
                "message": (
                    f"Raw kubectl: PVC/{name} uses StorageClass "
                    f"'{sc_name}' not defined in manifests — "
                    f"ensure it exists on the cluster"
                ),
            })


# SemVer regex — basic check: MAJOR.MINOR.PATCH with optional pre-release
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?"
    r"(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"
)


def _strategy_helm(
    project_root: Path,
    status: dict,
    helm_charts: list[dict],
    issues: list[dict],
) -> None:
    """Helm deployment strategy checks (13 checks).

    Validates Helm charts against the Chart.yaml v2 spec.
    """
    import yaml as _yaml

    for chart in helm_charts:
        chart_path = chart.get("path", "")
        chart_dir = project_root / chart_path
        chart_file = chart_dir / "Chart.yaml"
        chart_name = chart.get("name", "unknown")
        chart_type = chart.get("type", "application")
        has_templates = chart.get("has_templates", False)
        has_values = chart.get("has_values", False)
        has_lockfile = chart.get("has_lockfile", False)
        has_subcharts = chart.get("has_subcharts", False)

        # Parse Chart.yaml for extra data not in detection
        chart_data: dict = {}
        try:
            if chart_file.is_file():
                chart_data = _yaml.safe_load(
                    chart_file.read_text(encoding="utf-8")
                ) or {}
        except Exception:
            pass

        api_version = chart_data.get("apiVersion", "")
        dependencies = chart_data.get("dependencies", []) or []
        chart_version = str(chart_data.get("version", ""))
        chart_name_from_yaml = chart_data.get("name", "")

        # ── 1. No templates directory ─────────────────────────
        if not has_templates and chart_type == "application":
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: chart '{chart_name}' has no templates/ directory "
                    f"— application chart without templates cannot render manifests"
                ),
            })

        # ── 2. No values.yaml ─────────────────────────────────
        if not has_values:
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' has no values.yaml "
                    f"— no default configuration values defined"
                ),
            })

        # ── 3. Dependencies without lock ──────────────────────
        if dependencies and not has_lockfile:
            dep_names = [d.get("name", "?") for d in dependencies[:3]]
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has dependencies "
                    f"({', '.join(dep_names)}) but no Chart.lock "
                    f"— run 'helm dependency build'"
                ),
            })

        # ── 4. Deprecated apiVersion v1 ───────────────────────
        if api_version == "v1":
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' uses deprecated "
                    f"apiVersion v1 (Helm 2 format) — migrate to apiVersion v2"
                ),
            })

        # ── 5. Library chart with non-helper templates ────────
        if chart_type == "library" and has_templates:
            templates_dir = chart_dir / "templates"
            if templates_dir.is_dir():
                renderable = [
                    f.name for f in templates_dir.iterdir()
                    if f.is_file() and not f.name.startswith("_")
                ]
                if renderable:
                    issues.append({
                        "file": chart_path,
                        "severity": "warning",
                        "message": (
                            f"Helm: library chart '{chart_name}' has renderable "
                            f"templates ({', '.join(renderable[:3])}) — library "
                            f"charts should only contain _*.tpl helper files"
                        ),
                    })

        # ── 6. Orphaned subcharts ─────────────────────────────
        if has_subcharts and not dependencies:
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has charts/ subchart "
                    f"directory but no dependencies declared in Chart.yaml"
                ),
            })

        # ── 7. Missing required fields ────────────────────────
        if not chart_name_from_yaml:
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: Chart.yaml missing required field 'name'"
                ),
            })
        if not chart_data.get("version"):
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: Chart.yaml missing required field 'version'"
                ),
            })

        # ── 8. Invalid SemVer version ─────────────────────────
        if chart_version and not _SEMVER_RE.match(chart_version):
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' version '{chart_version}' "
                    f"is not valid SemVer — Helm spec requires SemVer 2"
                ),
            })

        # ── 9. No .helmignore ─────────────────────────────────
        helmignore = chart_dir / ".helmignore"
        if not helmignore.is_file():
            # Count files in project to see if worth warning
            try:
                file_count = sum(
                    1 for _ in project_root.rglob("*") if _.is_file()
                )
                if file_count > 20:
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' has no .helmignore "
                            f"— 'helm package' will include all {file_count} "
                            f"project files"
                        ),
                    })
            except Exception:
                pass

        # ── 10-11-12. Template directory checks ───────────────
        if has_templates:
            templates_dir = chart_dir / "templates"
            if templates_dir.is_dir():
                template_files = [
                    f.name for f in templates_dir.iterdir() if f.is_file()
                ]

                # 10. Missing NOTES.txt
                if "NOTES.txt" not in template_files:
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' templates/ has no "
                            f"NOTES.txt — no post-install notes for users"
                        ),
                    })

                # 11. No _helpers.tpl
                if not any(f.startswith("_") and f.endswith(".tpl") for f in template_files):
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' templates/ has no "
                            f"_helpers.tpl — no reusable template helpers defined"
                        ),
                    })

        # 12. No values.schema.json
        schema_file = chart_dir / "values.schema.json"
        if not schema_file.is_file():
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has no values.schema.json "
                    f"— values input is not schema-validated"
                ),
            })

        # ── 13. Local file:// dependency ──────────────────────
        for dep in dependencies:
            repo = dep.get("repository", "")
            dep_name = dep.get("name", "?")
            if repo.startswith("file://"):
                issues.append({
                    "file": chart_path,
                    "severity": "warning",
                    "message": (
                        f"Helm: chart '{chart_name}' dependency '{dep_name}' "
                        f"uses local repository ({repo}) — this won't resolve "
                        f"in a distributed chart"
                    ),
                })


def _strategy_kustomize(
    project_root: Path,
    status: dict,
    kustomize: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Kustomize deployment strategy checks (10 checks).

    Validates kustomization.yaml against the Kustomize spec.
    """
    import yaml as _yaml

    kust_path = kustomize.get("path", "")
    # Determine kustomize directory from the path
    # path could be "k8s/kustomization.yaml" — dir is "k8s"
    kust_file_path = project_root / kust_path
    if kust_file_path.is_file():
        kust_dir = kust_file_path.parent
    else:
        # Try as directory containing kustomization.yaml
        kust_dir = project_root / kust_path
        kust_file_path = None
        for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
            candidate = kust_dir / name
            if candidate.is_file():
                kust_file_path = candidate
                break

    if not kust_file_path or not kust_file_path.is_file():
        return

    # Parse kustomization content
    content: dict = {}
    try:
        content = _yaml.safe_load(
            kust_file_path.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return

    resources = content.get("resources", []) or []
    if not isinstance(resources, list):
        resources = []

    # ── 1. Missing resource file ──────────────────────────────
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        res_path = kust_dir / res_ref
        if not res_path.exists():
            issues.append({
                "file": kust_path,
                "severity": "error",
                "message": (
                    f"Kustomize: resource '{res_ref}' referenced in "
                    f"kustomization.yaml not found on disk"
                ),
            })

    # ── 2. Path traversal ─────────────────────────────────────
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        try:
            resolved = (kust_dir / res_ref).resolve()
            if not str(resolved).startswith(str(project_root.resolve())):
                issues.append({
                    "file": kust_path,
                    "severity": "error",
                    "message": (
                        f"Kustomize: resource '{res_ref}' traverses outside "
                        f"project root — potential security risk"
                    ),
                })
        except Exception:
            pass

    # ── 3. Overlays without base ──────────────────────────────
    overlays = kustomize.get("overlays", [])
    has_base = kustomize.get("has_bases", False)
    if overlays and not has_base:
        issues.append({
            "file": kust_path,
            "severity": "warning",
            "message": (
                f"Kustomize: overlays found ({', '.join(overlays[:3])}) "
                f"but no base/ directory — overlay/base pattern incomplete"
            ),
        })

    # ── 4. Secret generator with literals ─────────────────────
    secret_gen = content.get("secretGenerator", []) or []
    if isinstance(secret_gen, list):
        for sg in secret_gen:
            if isinstance(sg, dict) and sg.get("literals"):
                sg_name = sg.get("name", "?")
                issues.append({
                    "file": kust_path,
                    "severity": "warning",
                    "message": (
                        f"Kustomize: secretGenerator '{sg_name}' has "
                        f"plaintext secret literals in kustomization.yaml "
                        f"— avoid committing secrets to VCS"
                    ),
                })

    # ── 5. Duplicate resource ─────────────────────────────────
    seen_resources: set[str] = set()
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        if res_ref in seen_resources:
            issues.append({
                "file": kust_path,
                "severity": "error",
                "message": (
                    f"Kustomize: duplicate resource '{res_ref}' "
                    f"in resources list — kustomize build will fail"
                ),
            })
        seen_resources.add(res_ref)

    # ── 6. Patch targets missing resource ─────────────────────
    # Build index of known resource kinds+names from all_resources
    known_resources: set[tuple[str, str]] = set()  # (kind, name)
    for _, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        if kind and name:
            known_resources.add((kind, name))

    patches = content.get("patches", []) or []
    if isinstance(patches, list):
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            target = patch.get("target", {})
            if not isinstance(target, dict):
                continue
            t_kind = target.get("kind", "")
            t_name = target.get("name", "")
            if t_kind and t_name and (t_kind, t_name) not in known_resources:
                issues.append({
                    "file": kust_path,
                    "severity": "warning",
                    "message": (
                        f"Kustomize: patch targets {t_kind}/{t_name} but "
                        f"no matching resource found in manifests"
                    ),
                })

    # ── 7. Deprecated bases field ─────────────────────────────
    if content.get("bases"):
        issues.append({
            "file": kust_path,
            "severity": "info",
            "message": (
                f"Kustomize: deprecated 'bases' field used — "
                f"migrate to 'resources' entries (deprecated since kustomize v2.1.0)"
            ),
        })

    # ── 8. commonLabels immutability risk ──────────────────────
    if content.get("commonLabels"):
        issues.append({
            "file": kust_path,
            "severity": "info",
            "message": (
                f"Kustomize: commonLabels is used — label changes will "
                f"break immutable selector fields (spec.selector.matchLabels) "
                f"on existing Deployments"
            ),
        })

    # ── 9. Missing components directory ───────────────────────
    components = content.get("components", []) or []
    if isinstance(components, list):
        for comp_ref in components:
            if not isinstance(comp_ref, str):
                continue
            comp_path = kust_dir / comp_ref
            if not comp_path.is_dir():
                issues.append({
                    "file": kust_path,
                    "severity": "error",
                    "message": (
                        f"Kustomize: component '{comp_ref}' not found "
                        f"on disk — kustomize build will fail"
                    ),
                })

    # ── 10. Namespace override conflict ───────────────────────
    kust_namespace = content.get("namespace", "")
    if kust_namespace:
        hardcoded_ns = set()
        for _, res in all_resources:
            res_ns = res.get("metadata", {}).get("namespace", "")
            if res_ns and res_ns != kust_namespace:
                hardcoded_ns.add(res_ns)
        if hardcoded_ns:
            issues.append({
                "file": kust_path,
                "severity": "info",
                "message": (
                    f"Kustomize: namespace override '{kust_namespace}' set "
                    f"but resources have hardcoded namespaces "
                    f"({', '.join(sorted(hardcoded_ns)[:3])}) — "
                    f"override may conflict or be redundant"
                ),
            })


# Skaffold apiVersion prefixes considered "current" (v2+ and v3+ and v4+)
_SKAFFOLD_CURRENT_PREFIXES = ("skaffold/v2", "skaffold/v3", "skaffold/v4")


def _strategy_skaffold(
    project_root: Path,
    skaffold_file: Path,
    issues: list[dict],
) -> None:
    """Skaffold deployment strategy checks (7 checks).

    Validates skaffold.yaml against the Skaffold schema.
    """
    import yaml as _yaml

    try:
        content = _yaml.safe_load(
            skaffold_file.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return

    if not isinstance(content, dict):
        return

    api_version = content.get("apiVersion", "")
    build = content.get("build", {}) or {}
    deploy = content.get("deploy", {}) or {}
    manifests = content.get("manifests", {}) or {}
    profiles = content.get("profiles", []) or []

    # ── 1. Missing manifest file ────────────────────────────
    raw_yaml = manifests.get("rawYaml", []) or []
    if isinstance(raw_yaml, list):
        for ref in raw_yaml:
            if isinstance(ref, str) and not (project_root / ref).exists():
                issues.append({
                    "file": "skaffold.yaml",
                    "severity": "error",
                    "message": (
                        f"Skaffold: manifests.rawYaml references missing "
                        f"file '{ref}'"
                    ),
                })

    # ── 2. Missing Dockerfile ────────────────────────────────
    artifacts = build.get("artifacts", []) or []
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            docker = artifact.get("docker", {}) or {}
            dockerfile = docker.get("dockerfile", "")
            if dockerfile:
                # Resolve relative to artifact context or project root
                context = artifact.get("context", ".")
                df_path = project_root / context / dockerfile
                if not df_path.is_file():
                    image = artifact.get("image", "?")
                    issues.append({
                        "file": "skaffold.yaml",
                        "severity": "error",
                        "message": (
                            f"Skaffold: build artifact '{image}' references "
                            f"Dockerfile '{dockerfile}' not found on disk"
                        ),
                    })

    # ── 3. Deprecated apiVersion ─────────────────────────────
    if api_version and not any(
        api_version.startswith(p) for p in _SKAFFOLD_CURRENT_PREFIXES
    ):
        issues.append({
            "file": "skaffold.yaml",
            "severity": "warning",
            "message": (
                f"Skaffold: apiVersion '{api_version}' is deprecated "
                f"or outdated — consider migrating to v4beta+"
            ),
        })

    # ── 4 & 5. No deploy/manifests, or build without deploy ────
    has_deploy = bool(deploy)
    has_manifests = bool(manifests)
    has_build = bool(build.get("artifacts"))

    if not has_deploy and not has_manifests:
        if has_build:
            # Check 5: build without deploy
            issues.append({
                "file": "skaffold.yaml",
                "severity": "warning",
                "message": (
                    f"Skaffold: build section defined but no deploy "
                    f"or manifests section — images are built but not deployed"
                ),
            })
        else:
            # Check 4: truly empty
            issues.append({
                "file": "skaffold.yaml",
                "severity": "warning",
                "message": (
                    f"Skaffold: no deploy or manifests section "
                    f"— skaffold has no deployment configuration"
                ),
            })

    # ── 6. Empty default pipeline ────────────────────────────
    if (
        profiles
        and not has_build
        and not has_deploy
        and not has_manifests
    ):
        profile_names = [
            p.get("name", "?") for p in profiles[:3]
            if isinstance(p, dict)
        ]
        issues.append({
            "file": "skaffold.yaml",
            "severity": "info",
            "message": (
                f"Skaffold: default pipeline is empty, all config "
                f"lives in profiles ({', '.join(profile_names)}) "
                f"— requires --profile flag to deploy"
            ),
        })

    # ── 7. Non-reproducible tag policy ───────────────────────
    tag_policy = build.get("tagPolicy", {}) or {}
    if isinstance(tag_policy, dict):
        non_reproducible = {"sha256", "latest"}
        for policy_name in tag_policy:
            if policy_name in non_reproducible:
                issues.append({
                    "file": "skaffold.yaml",
                    "severity": "info",
                    "message": (
                        f"Skaffold: tagPolicy '{policy_name}' produces "
                        f"non-reproducible image tags — consider "
                        f"gitCommit or inputDigest for traceability"
                    ),
                })



def _strategy_mixed(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    helm_charts: list[dict],
    kustomize: dict,
    skaffold_file: Path,
    issues: list[dict],
) -> None:
    """Mixed strategy coherence checks (5 checks).

    Cross-strategy consistency validation.
    """
    import yaml as _yaml

    deployment_strategy = status.get("deployment_strategy", "none")
    has_helm = bool(helm_charts)
    has_kustomize = kustomize.get("exists", False)
    has_skaffold = skaffold_file.is_file()

    # ── 1. Duplicate resource across strategies ──────────────
    # Check if same (kind, name, namespace) appears in raw manifests AND
    # Helm templates
    if has_helm and all_resources:
        # Resources from standard manifest dirs (non-template paths)
        raw_resource_keys: set[tuple[str, str, str]] = set()
        helm_resource_keys: set[tuple[str, str, str]] = set()

        for rel_path, res in all_resources:
            kind = res.get("kind", "")
            name = res.get("metadata", {}).get("name", "")
            ns = res.get("metadata", {}).get("namespace", "") or "default"
            if not kind or not name:
                continue
            key = (kind, name, ns)
            # Check if this is inside a Helm chart templates/ dir
            is_helm_template = False
            for chart in helm_charts:
                chart_path = chart.get("path", "")
                if chart_path and rel_path.startswith(chart_path + "/templates/"):
                    is_helm_template = True
                    break
            if is_helm_template:
                helm_resource_keys.add(key)
            else:
                raw_resource_keys.add(key)

        duplicates = raw_resource_keys & helm_resource_keys
        for kind, name, ns in sorted(duplicates):
            issues.append({
                "file": "deployment-strategy",
                "severity": "warning",
                "message": (
                    f"Mixed: {kind}/{name} (namespace: {ns}) exists in both "
                    f"raw manifests and Helm templates — dual management risk"
                ),
            })

    # ── 2. Orphaned manifests alongside Kustomize ────────────
    if has_kustomize:
        kust_path = kustomize.get("path", "")
        kust_file_path = project_root / kust_path
        if kust_file_path.is_file():
            kust_dir = kust_file_path.parent
        else:
            kust_dir = project_root / kust_path
            kust_file_path = None
            for kf_name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                candidate = kust_dir / kf_name
                if candidate.is_file():
                    kust_file_path = candidate
                    break

        if kust_file_path and kust_file_path.is_file():
            try:
                kust_content = _yaml.safe_load(
                    kust_file_path.read_text(encoding="utf-8")
                ) or {}
                resources_list = kust_content.get("resources", []) or []
                if isinstance(resources_list, list):
                    listed = set(str(r) for r in resources_list if isinstance(r, str))
                    # Check for .yaml/.yml files in kust_dir not in resources
                    for f in sorted(kust_dir.iterdir()):
                        if (
                            f.is_file()
                            and f.suffix in (".yaml", ".yml")
                            and f.name not in (
                                "kustomization.yaml", "kustomization.yml",
                                "Kustomization",
                            )
                            and f.name not in listed
                        ):
                            issues.append({
                                "file": kust_path,
                                "severity": "warning",
                                "message": (
                                    f"Mixed: orphaned manifest '{f.name}' in "
                                    f"Kustomize directory but not listed in "
                                    f"resources — may be stale/unused"
                                ),
                            })
            except Exception:
                pass

    # ── 3. Mixed strategy undocumented ───────────────────────
    if deployment_strategy == "mixed":
        readme_found = any(
            (project_root / name).is_file()
            for name in (
                "README.md", "README.rst", "README.txt", "README",
                "docs/deployment.md", "docs/DEPLOYMENT.md",
                "DEPLOYMENT.md",
            )
        )
        if not readme_found:
            issues.append({
                "file": "deployment-strategy",
                "severity": "info",
                "message": (
                    f"Mixed: multiple deployment strategies detected "
                    f"but no README or deployment docs found — "
                    f"new contributors have no guide"
                ),
            })

    # ── 4. Helm + Kustomize without orchestrator ──────────────
    if has_helm and has_kustomize and not has_skaffold:
        # Check for ArgoCD/Flux markers
        has_argo = any(
            (project_root / d).is_dir()
            for d in ("argocd", ".argocd", "argo-cd")
        )
        has_flux = any(
            (project_root / d).is_dir()
            for d in ("flux", ".flux", "flux-system")
        )
        if not has_argo and not has_flux:
            issues.append({
                "file": "deployment-strategy",
                "severity": "info",
                "message": (
                    f"Mixed: both Helm and Kustomize active but no "
                    f"orchestrator (Skaffold/ArgoCD/Flux) detected — "
                    f"unclear which tool applies what"
                ),
            })

    # ── 5. Skaffold dual deployers ───────────────────────────
    if has_skaffold:
        try:
            skf = _yaml.safe_load(
                skaffold_file.read_text(encoding="utf-8")
            ) or {}
            if isinstance(skf, dict):
                skf_manifests = skf.get("manifests", {}) or {}
                skf_deploy = skf.get("deploy", {}) or {}
                has_raw_deploy = bool(skf_manifests.get("rawYaml"))
                has_helm_deploy = bool(skf_deploy.get("helm"))
                if has_raw_deploy and has_helm_deploy:
                    issues.append({
                        "file": "skaffold.yaml",
                        "severity": "warning",
                        "message": (
                            f"Skaffold: uses both Helm releases and rawYaml "
                            f"manifests — potential resource conflict in "
                            f"same namespace"
                        ),
                    })
        except Exception:
            pass
