"""K8s wizard — state translator and manifest generator.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.core.services.k8s_generate import (
    _build_probe, _build_wizard_volume, _build_pod_template,
    _build_env_vars, _build_mesh_annotations, _api_version_for_kind,
)


logger = logging.getLogger(__name__)

def skaffold_status(project_root: Path) -> dict:
    """Detect Skaffold configuration.

    Returns:
        {
            "available": bool (CLI exists),
            "configs": [{path, profiles: [str]}],
            "has_skaffold": bool,
        }
    """
    import shutil
    import yaml

    cli_available = shutil.which("skaffold") is not None

    configs: list[dict] = []
    skaffold_files = [
        "skaffold.yaml", "skaffold.yml",
    ]

    for f in skaffold_files:
        p = project_root / f
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                profiles = []
                if isinstance(data, dict) and "profiles" in data:
                    profiles = [
                        pr.get("name", "")
                        for pr in data["profiles"]
                        if isinstance(pr, dict) and pr.get("name")
                    ]
                configs.append({
                    "path": f,
                    "profiles": profiles,
                    "api_version": data.get("apiVersion", "") if isinstance(data, dict) else "",
                })
            except Exception:
                configs.append({"path": f, "profiles": [], "api_version": ""})

    return {
        "available": cli_available,
        "configs": configs,
        "has_skaffold": len(configs) > 0,
    }


# ═══════════════════════════════════════════════════════════════════
#  Multi-Environment Namespace Mapping
# ═══════════════════════════════════════════════════════════════════


def k8s_env_namespaces(project_root: Path) -> dict:
    """Map project environments to K8s namespaces.

    Reads project.yml environments and checks for env-specific
    namespace files or Kustomize overlays.

    Returns:
        {
            "environments": [{
                name, namespace, has_overlay, overlay_path
            }, ...],
        }
    """
    from src.core.config.loader import find_project_file, load_project

    config_path = find_project_file(project_root)
    if not config_path:
        return {"environments": []}

    project = load_project(config_path)
    envs: list[dict] = []

    for env in project.environments:
        name = env.name
        # Convention: namespace = project-name-env
        namespace = f"{project.name}-{name}" if project.name else name

        # Check for env-specific overlays
        overlay_paths = [
            f"k8s/overlays/{name}",
            f"k8s/envs/{name}",
            f"kubernetes/overlays/{name}",
            f"deploy/overlays/{name}",
        ]
        has_overlay = False
        overlay_path = ""
        for op in overlay_paths:
            if (project_root / op).is_dir():
                has_overlay = True
                overlay_path = op
                break

        # Check for env-specific values files (Helm)
        values_files = [
            f"values-{name}.yaml", f"values.{name}.yaml",
            f"helm/values-{name}.yaml", f"charts/values-{name}.yaml",
        ]
        values_file = ""
        for vf in values_files:
            if (project_root / vf).is_file():
                values_file = vf
                break

        envs.append({
            "name": name,
            "namespace": namespace,
            "default": env.default,
            "has_overlay": has_overlay,
            "overlay_path": overlay_path,
            "values_file": values_file,
        })

    return {"environments": envs}


# ═══════════════════════════════════════════════════════════════════
#  K8s Manifest Wizard — Translator + Generator
# ═══════════════════════════════════════════════════════════════════


def _svc_env_to_resources(
    svc_name: str,
    env_vars: list[dict],
    namespace: str,
    output_dir: str,
) -> tuple[list[dict], bool, bool]:
    """Extract ConfigMap / Secret resources from a service's envVars.

    Returns:
        (resources, has_config, has_secrets)
        - resources: ConfigMap and/or Secret resource dicts
        - has_config: True if a ConfigMap was generated (for envFrom wiring)
        - has_secrets: True if a Secret was generated
    """
    resources: list[dict] = []
    config_data: dict = {}
    secret_data: dict = {}

    for ev in env_vars:
        if not isinstance(ev, dict):
            continue
        key = ev.get("key", "")
        if not key:
            continue
        ev_type = ev.get("type", "hardcoded")
        if ev_type == "secret":
            # Placeholder — user replaces at deploy time
            secret_data[key] = "CHANGE_ME"
        elif ev_type == "variable":
            # Placeholder referencing external variable
            var_name = ev.get("varName", f"${{{key}}}")
            config_data[key] = var_name
        else:
            # Hardcoded value
            config_data[key] = ev.get("value", "")

    has_config = bool(config_data)
    has_secrets = bool(secret_data)

    if has_config:
        resources.append({
            "kind": "ConfigMap",
            "name": f"{svc_name}-config",
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {"data": config_data},
        })
    if has_secrets:
        resources.append({
            "kind": "Secret",
            "name": f"{svc_name}-secrets",
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {"stringData": secret_data},
        })

    return resources, has_config, has_secrets


def _svc_volumes_to_pvc_resources(
    svc_name: str,
    volumes: list[dict],
    namespace: str,
    output_dir: str,
) -> list[dict]:
    """Generate PVC resources for pvc-dynamic / pvc-static volumes."""
    resources: list[dict] = []
    for vol in volumes:
        vol_type = vol.get("type", "")
        if vol_type not in ("pvc-dynamic", "pvc-static"):
            continue
        vol_name = vol.get("name", "data")
        pvc_name = f"{svc_name}-{vol_name}"
        pvc_res: dict = {
            "kind": "PersistentVolumeClaim",
            "name": pvc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {
                "accessModes": [vol.get("accessMode", "ReadWriteOnce")],
                "storage": vol.get("size", "10Gi"),
            },
        }
        sc = vol.get("storageClass", "")
        if sc:
            pvc_res["spec"]["storageClass"] = sc
        if vol_type == "pvc-static" and vol.get("pvName"):
            pvc_res["spec"]["volumeName"] = vol["pvName"]
        # Longhorn annotations
        lh = vol.get("longhornConfig")
        if lh:
            pvc_res["spec"]["longhornConfig"] = lh
        resources.append(pvc_res)
    return resources


def _generate_skaffold(data: dict, generated_files: list[dict]) -> dict | None:
    """Build a skaffold.yaml from the wizard state.

    Args:
        data: Wizard state (same shape as wizard_state_to_resources input).
        generated_files: The list of file dicts from generate_k8s_wizard output,
            used to collect manifest paths for the deploy section.

    Returns:
        A file dict {path, content, reason} or None if skaffold is disabled.
    """
    if not data.get("skaffold"):
        return None

    import yaml

    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    # Collect build artifacts — one per service that has a local-looking image
    # (i.e. not a known registry image like postgres:16 or redis:7)
    artifacts: list[dict] = []
    for svc in data.get("_services", []):
        svc_kind = svc.get("kind", "Deployment")
        if svc_kind in ("Skip",):
            continue
        image = svc.get("image", "")
        if not image:
            continue
        # Heuristic: registry images contain '/' or ':' with a known base
        # Local images are typically just 'name:tag' or 'name:latest'
        # We include everything and let users prune
        artifacts.append({
            "image": image,
            "context": ".",
        })

    # Collect manifest paths from generated files
    manifest_paths: list[str] = []
    for f in generated_files:
        path = f.get("path", "")
        if path.endswith(".yaml") or path.endswith(".yml"):
            manifest_paths.append(path)

    # If no manifests, use the output dir glob
    if not manifest_paths:
        manifest_paths = [f"{output_dir}/*.yaml"]

    skaffold_doc: dict = {
        "apiVersion": "skaffold/v4beta11",
        "kind": "Config",
        "metadata": {"name": data.get("_services", [{}])[0].get("name", "app")
                     if data.get("_services") else "app"},
    }

    if artifacts:
        skaffold_doc["build"] = {"artifacts": artifacts}

    skaffold_doc["manifests"] = {"rawYaml": manifest_paths}

    skaffold_doc["deploy"] = {"kubectl": {}}

    content = yaml.dump(skaffold_doc, default_flow_style=False, sort_keys=False)
    return {
        "path": "skaffold.yaml",
        "content": content,
        "reason": "Skaffold pipeline — build → push → deploy",
        "overwrite": False,
    }


def wizard_state_to_resources(data: dict) -> list[dict]:
    """Translate wizard state into flat resource list for generate_k8s_wizard.

    Input shape (from frontend collector + saved state):
        {
            _services: [...],       # app services with all config
            _infraDecisions: [...], # infra decisions (StatefulSet/Managed/Skip)
            namespace: "default",
            output_dir: "k8s/",
            ingress: "host.example.com" or "",
            skaffold: true/false,
        }

    Output: list of resource dicts, each with:
        {kind, name, namespace, output_dir, spec: {...}}
    """
    services = data.get("_services", [])
    infra = data.get("_infraDecisions", [])
    namespace = data.get("namespace", "default")
    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    resources: list[dict] = []

    # ── Build infra lookup for dependency resolution ──
    # Maps infra name → {kind, port, has_config, has_secrets}
    infra_lookup: dict[str, dict] = {}
    for inf in infra:
        inf_name = inf.get("name", "")
        if not inf_name:
            continue
        infra_lookup[inf_name] = {
            "kind": inf.get("kind", "Skip"),
            "port": inf.get("port", ""),
        }

    # ── Process infrastructure decisions first ──
    # (so their ConfigMap/Secret names are known when we wire dependencies)
    for inf in infra:
        inf_name = inf.get("name", "")
        inf_kind = inf.get("kind", "Skip")
        if not inf_name or inf_kind == "Skip":
            continue

        inf_env_vars = inf.get("envVars", [])
        inf_volumes = inf.get("volumes", [])

        # Generate ConfigMap/Secret from env vars
        env_resources, has_cm, has_sec = _svc_env_to_resources(
            inf_name, inf_env_vars, namespace, output_dir,
        )
        resources.extend(env_resources)

        # Update lookup with generated resource info
        infra_lookup[inf_name]["has_config"] = has_cm
        infra_lookup[inf_name]["has_secrets"] = has_sec

        if inf_kind == "Managed":
            # Managed infra → only ConfigMap/Secret (no workload)
            # These get referenced by dependent services via envFrom
            continue

        # Self-hosted infra (StatefulSet, Deployment, DaemonSet)
        inf_port = inf.get("port", "")

        # Build workload resource
        inf_spec: dict = {
            "image": inf.get("image", inf_name),
            "_svc_name": inf_name,  # for env var naming convention
            "env": inf_env_vars,
            "wizardVolumes": inf_volumes,
        }
        if inf_port:
            inf_spec["port"] = int(inf_port)

        resources.append({
            "kind": inf_kind,
            "name": inf_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": inf_spec,
        })

        # Generate Service for self-hosted infra (if port set)
        if inf_port:
            svc_spec: dict = {
                "port": int(inf_port),
                "target_port": int(inf_port),
                "selector": inf_name,
            }
            if inf_kind == "StatefulSet":
                # Headless service for StatefulSet infra
                svc_spec["headless"] = True
                svc_dns = f"{inf_name}-headless"
                resources.append({
                    "kind": "Service",
                    "name": svc_dns,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": svc_spec,
                })
            else:
                svc_dns = inf_name
                svc_spec["type"] = "ClusterIP"
                resources.append({
                    "kind": "Service",
                    "name": svc_dns,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": svc_spec,
                })
            # Store the actual K8s Service DNS name for wait-for resolution
            infra_lookup[inf_name]["svc_dns"] = svc_dns

        # Generate PVC resources for infra volumes
        resources.extend(
            _svc_volumes_to_pvc_resources(inf_name, inf_volumes, namespace, output_dir)
        )

    # ── Process application services ──
    for svc in services:
        svc_name = svc.get("name", "")
        svc_kind = svc.get("kind", "Deployment")
        if not svc_name or svc_kind in ("Skip", "Managed"):
            continue

        env_vars = svc.get("envVars", [])
        volumes = svc.get("volumes", [])
        is_job = svc_kind in ("Job", "CronJob")

        # ── Generate ConfigMap/Secret from env vars ──
        env_resources, has_cm, has_sec = _svc_env_to_resources(
            svc_name, env_vars, namespace, output_dir,
        )
        resources.extend(env_resources)

        # ── Generate PVC resources from volumes ──
        resources.extend(
            _svc_volumes_to_pvc_resources(svc_name, volumes, namespace, output_dir)
        )

        # ── Build envFrom list (bulk ConfigMap/Secret refs) ──
        env_from: list[dict] = []
        if has_cm:
            env_from.append({"configMapRef": {"name": f"{svc_name}-config"}})
        if has_sec:
            env_from.append({"secretRef": {"name": f"{svc_name}-secrets"}})

        # Wire managed infra ConfigMap/Secret into dependent services
        dependencies = svc.get("dependencies", [])
        for dep_name in dependencies:
            dep_info = infra_lookup.get(dep_name, {})
            if dep_info.get("has_config"):
                env_from.append({"configMapRef": {"name": f"{dep_name}-config"}})
            if dep_info.get("has_secrets"):
                env_from.append({"secretRef": {"name": f"{dep_name}-secrets"}})

        # ── Build dependency wait-for init containers ──
        dep_init_containers: list[dict] = []
        for dep_name in dependencies:
            dep_info = infra_lookup.get(dep_name, {})
            # Skip wait-for for Managed infra — no K8s Service exists
            if dep_info.get("kind") == "Managed":
                continue
            dep_port = dep_info.get("port", "")
            if dep_port:
                # Use resolved K8s Service DNS name (e.g. postgres-headless for StatefulSet)
                dns_name = dep_info.get("svc_dns", dep_name)
                dep_init_containers.append({
                    "name": f"wait-for-{dep_name}",
                    "image": "busybox:1.36",
                    "command": (
                        f"echo 'Waiting for {dns_name}:{dep_port}…'; "
                        f"until nc -z {dns_name} {dep_port}; do sleep 2; done; "
                        f"echo 'Ready.'"
                    ),
                })

        # Merge user-defined init containers with dependency wait-fors
        all_init = dep_init_containers + (svc.get("initContainers") or [])

        # ── Flatten resources object ──
        res_obj = svc.get("resources") or {}

        # ── Build workload spec ──
        spec: dict = {
            "image": svc.get("image", f"{svc_name}:latest"),
            "_svc_name": svc_name,
            "env": env_vars,
            "wizardVolumes": volumes,
            "initContainers": all_init,
            "sidecars": svc.get("sidecars", []),
            "companions": svc.get("companions", []),
            "mesh": svc.get("mesh"),
            # Flatten resource limits
            "cpu_request": res_obj.get("cpu_request"),
            "cpu_limit": res_obj.get("cpu_limit"),
            "memory_request": res_obj.get("memory_request"),
            "memory_limit": res_obj.get("memory_limit"),
            # Health probes
            "readinessProbe": svc.get("readinessProbe"),
            "livenessProbe": svc.get("livenessProbe"),
        }

        # envFrom (only if there are refs to inject)
        if env_from:
            spec["envFrom"] = env_from

        # ── Kind-specific fields ──
        if svc_kind == "Deployment":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["replicas"] = int(svc.get("replicas", 2))
            spec["strategy"] = svc.get("strategy", "RollingUpdate")
            spec["maxSurge"] = svc.get("maxSurge", 1)
            spec["maxUnavailable"] = svc.get("maxUnavailable", 0)

        elif svc_kind == "StatefulSet":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["replicas"] = int(svc.get("replicas", 1))
            spec["headlessServiceName"] = svc.get(
                "headlessServiceName", f"{svc_name}-headless"
            )
            spec["podManagementPolicy"] = svc.get("podManagementPolicy", "OrderedReady")
            spec["strategy"] = svc.get("strategy")
            spec["partition"] = svc.get("partition")
            spec["volumeClaimTemplates"] = svc.get("volumeClaimTemplates", [])

        elif svc_kind == "DaemonSet":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["strategy"] = svc.get("strategy")
            spec["maxUnavailable"] = svc.get("maxUnavailable")
            spec["nodeSelector"] = svc.get("nodeSelector", "")
            spec["tolerations"] = svc.get("tolerations", [])
            spec["hostNetwork"] = svc.get("hostNetwork", False)
            spec["hostPID"] = svc.get("hostPID", False)
            spec["hostIPC"] = svc.get("hostIPC", False)

        elif svc_kind in ("Job", "CronJob"):
            spec["command"] = svc.get("command", "")
            spec["args"] = svc.get("args", "")
            spec["restartPolicy"] = svc.get("restartPolicy", "Never")
            spec["backoffLimit"] = int(svc.get("backoffLimit", 3))
            spec["completions"] = int(svc.get("completions", 1))
            spec["parallelism"] = int(svc.get("parallelism", 1))
            if svc.get("activeDeadlineSeconds"):
                spec["activeDeadlineSeconds"] = int(svc["activeDeadlineSeconds"])
            spec["ttlSecondsAfterFinished"] = int(svc.get("ttlSecondsAfterFinished", 3600))

            if svc_kind == "CronJob":
                spec["schedule"] = svc.get("schedule", "*/5 * * * *")
                spec["concurrencyPolicy"] = svc.get("concurrencyPolicy", "Forbid")
                spec["suspend"] = svc.get("suspend", False)
                spec["successfulJobsHistoryLimit"] = int(
                    svc.get("successfulJobsHistoryLimit", 3)
                )
                spec["failedJobsHistoryLimit"] = int(
                    svc.get("failedJobsHistoryLimit", 1)
                )
                if svc.get("startingDeadlineSeconds"):
                    spec["startingDeadlineSeconds"] = int(svc["startingDeadlineSeconds"])

        # Add workload resource
        resources.append({
            "kind": svc_kind,
            "name": svc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": spec,
        })

        # ── Generate Service resource (not for Jobs) ──
        svc_port = svc.get("port")
        if svc_port and not is_job:
            if svc_kind == "StatefulSet":
                # Headless service for StatefulSet
                hl_name = svc.get("headlessServiceName", f"{svc_name}-headless")
                resources.append({
                    "kind": "Service",
                    "name": hl_name,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "headless": True,
                        "port": int(svc_port),
                        "target_port": int(svc_port),
                        "selector": svc_name,
                    },
                })
                # Optional extra ClusterIP service
                if svc.get("alsoCreateClusterIP"):
                    resources.append({
                        "kind": "Service",
                        "name": svc_name,
                        "namespace": namespace,
                        "output_dir": output_dir,
                        "spec": {
                            "type": "ClusterIP",
                            "port": int(svc_port),
                            "target_port": int(svc_port),
                            "selector": svc_name,
                        },
                    })
            else:
                # Regular Service (Deployment, DaemonSet)
                resources.append({
                    "kind": "Service",
                    "name": svc_name,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "type": svc.get("serviceType", "ClusterIP"),
                        "port": int(svc_port),
                        "target_port": int(svc_port),
                        "selector": svc_name,
                    },
                })

    # ── Global: Namespace ──
    if namespace and namespace != "default":
        resources.insert(0, {
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
            "output_dir": output_dir,
        })

    # ── Global: Ingress ──
    ingress_host = data.get("ingress", "")
    if ingress_host:
        # Collect all services with ports for ingress rules
        svc_ports = []
        for svc in services:
            if svc.get("port") and svc.get("kind") not in ("Skip", "Managed", "Job", "CronJob"):
                svc_ports.append({
                    "name": svc["name"],
                    "port": int(svc["port"]),
                })
        if svc_ports:
            # If single service → simple ingress; multi → path-based
            if len(svc_ports) == 1:
                resources.append({
                    "kind": "Ingress",
                    "name": "ingress",
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "host": ingress_host if isinstance(ingress_host, str) and ingress_host != "true"
                                else f"{svc_ports[0]['name']}.example.com",
                        "service": svc_ports[0]["name"],
                        "port": svc_ports[0]["port"],
                    },
                })
            else:
                # Multi-service: one Ingress with path-based routing
                # The generate_k8s_wizard function handles single-service Ingress;
                # for multi we build the manifest spec manually
                rules_paths = []
                for sp in svc_ports:
                    rules_paths.append({
                        "path": f"/{sp['name']}",
                        "pathType": "Prefix",
                        "backend": {
                            "service": {
                                "name": sp["name"],
                                "port": {"number": sp["port"]},
                            },
                        },
                    })
                host = ingress_host if isinstance(ingress_host, str) and ingress_host != "true" \
                    else "app.example.com"
                resources.append({
                    "kind": "Ingress",
                    "name": "ingress",
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "host": host,
                        "_paths": rules_paths,  # pre-built path rules for generator
                    },
                })

    return resources


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

    for res in resources:
        kind = (res.get("kind") or "").strip()
        name = (res.get("name") or "").strip()
        namespace = (res.get("namespace") or "default").strip()
        spec = res.get("spec", {})

        if not kind or not name:
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
            manifest["stringData"] = spec.get("stringData", spec.get("data", {}))

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

    return {"ok": True, "files": files}


# ═══════════════════════════════════════════════════════════════════
#  Wizard State Persistence
# ═══════════════════════════════════════════════════════════════════


_STATE_FILE = ".wizard-state.json"

# Fields that are transient (derived from detection) and should not be persisted.
_STRIP_TOP = {
    "_appSvcCount", "_infraSvcCount", "_configMode",
    "_appServices", "_infraServices", "_classifiedModules",
    # backward-compat flat fields (superseded by _services[])
    "app_name", "image", "port", "replicas", "service_type",
    # internal keys
    "action",
}


def _sanitize_state(data: dict) -> dict:
    """Strip transient/detection fields before persisting."""
    from datetime import datetime, timezone

    clean = {k: v for k, v in data.items() if k not in _STRIP_TOP}
    # Strip raw compose data from each service / infra entry
    for svc in clean.get("_services", []):
        svc.pop("_compose", None)
    for inf in clean.get("_infraDecisions", []):
        inf.pop("_compose", None)
    # Add metadata
    clean["_savedAt"] = datetime.now(timezone.utc).isoformat()
    clean["_version"] = 1
    return clean


def load_wizard_state(project_root: Path) -> dict:
    """Load saved wizard state from k8s/.wizard-state.json.

    Returns:
        {"ok": True, ...state} or {"ok": False, "reason": "not_found"|"invalid"}
    """
    import json

    state_path = project_root / "k8s" / _STATE_FILE
    if not state_path.is_file():
        return {"ok": False, "reason": "not_found"}
    try:
        raw = state_path.read_text(encoding="utf-8")
        state = json.loads(raw)
        state["ok"] = True
        return state
    except (json.JSONDecodeError, ValueError):
        return {"ok": False, "reason": "invalid"}


def save_wizard_state(project_root: Path, data: dict) -> dict:
    """Persist wizard state to k8s/.wizard-state.json.

    Returns:
        {"ok": True, "path": "k8s/.wizard-state.json"} or {"error": ...}
    """
    import json

    if not data.get("_services") and not data.get("_infraDecisions"):
        return {"error": "Empty state — nothing to save"}

    k8s_dir = project_root / "k8s"
    k8s_dir.mkdir(exist_ok=True)

    clean = _sanitize_state(data)
    state_path = k8s_dir / _STATE_FILE
    state_path.write_text(
        json.dumps(clean, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "path": f"k8s/{_STATE_FILE}"}


def wipe_wizard_state(project_root: Path) -> dict:
    """Delete saved wizard state.

    Returns:
        {"ok": True}
    """
    state_path = project_root / "k8s" / _STATE_FILE
    if state_path.is_file():
        state_path.unlink()
    return {"ok": True}

