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
