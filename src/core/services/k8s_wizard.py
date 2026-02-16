"""K8s wizard — state translator and manifest generator.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.k8s_generate import (
    _build_probe, _build_wizard_volume, _build_pod_template,
    _build_env_vars, _build_mesh_annotations, _api_version_for_kind,
)


logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("k8s")


# ═══════════════════════════════════════════════════════════════════
#  K8s Manifest Wizard — Translator helpers
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


def wizard_state_to_resources(data: dict) -> list[dict]:
    """Translate wizard state into flat resource list for generate_k8s_wizard.

    Input shape (from frontend collector + saved state):
        {
            _services: [...],       # app services with all config
            _infraDecisions: [...], # infra services
            namespace: "...",
            output_dir: "k8s",
            ingress: "host.example.com" or "",
            skaffold: true/false,
        }

    Output: list of resource dicts, each with:
        {kind, name, namespace, output_dir, spec: {...}}
    """
    namespace = data.get("namespace", "default")
    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    resources: list[dict] = []
    services_needing_svc: list[dict] = []   # track for Service + Ingress

    # ── Namespace resource ──────────────────────────────────────
    if namespace and namespace != "default":
        resources.append({
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {},
        })

    # ── App + Infra services → workload resources ───────────────
    all_services = list(data.get("_services", []))
    all_services += list(data.get("_infraDecisions", []))

    for svc in all_services:
        svc_kind = svc.get("kind", "Deployment")
        svc_name = svc.get("name", "app")
        image = svc.get("image", "")

        if svc_kind in ("Skip", "Managed"):
            if svc_kind == "Managed":
                resources.append({
                    "kind": "Managed",
                    "name": svc_name,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {},
                })
            continue

        # ── Build workload spec ──
        spec: dict = {
            "image": image,
            "replicas": svc.get("replicas", 1),
        }

        # Port
        port = svc.get("port")
        if port:
            spec["port"] = port

        # Env vars
        env_vars = svc.get("envVars", [])
        if env_vars:
            env_list, env_from_refs = _build_env_vars(env_vars)
            spec["env"] = env_list
            if env_from_refs:
                spec["envFrom"] = env_from_refs

            # ConfigMap / Secret resources for env vars
            env_resources, has_config, has_secrets = _svc_env_to_resources(
                svc_name, env_vars, namespace, output_dir,
            )
            resources.extend(env_resources)
            if has_config:
                spec.setdefault("envFrom", []).append(
                    {"configMapRef": {"name": f"{svc_name}-config"}},
                )
            if has_secrets:
                spec.setdefault("envFrom", []).append(
                    {"secretRef": {"name": f"{svc_name}-secrets"}},
                )

        # Volumes
        volumes = svc.get("volumes", [])
        if volumes:
            vol_mounts = []
            vol_defs = []
            for vol in volumes:
                vm, vd = _build_wizard_volume(svc_name, vol)
                if vm:
                    vol_mounts.append(vm)
                if vd:
                    vol_defs.append(vd)
            if vol_mounts:
                spec["volumeMounts"] = vol_mounts
            if vol_defs:
                spec["volumes"] = vol_defs
            # PVC resources
            pvc_resources = _svc_volumes_to_pvc_resources(
                svc_name, volumes, namespace, output_dir,
            )
            resources.extend(pvc_resources)
            # StatefulSet VCTs
            if svc_kind == "StatefulSet":
                vcts = []
                for vol in volumes:
                    if vol.get("type") in ("pvc-dynamic", "pvc-static"):
                        vcts.append({
                            "name": vol.get("name", "data"),
                            "size": vol.get("size", "1Gi"),
                            "accessMode": vol.get("accessMode", "ReadWriteOnce"),
                            "storageClass": vol.get("storageClass", ""),
                        })
                if vcts:
                    spec["volumeClaimTemplates"] = vcts

        # Probes
        liveness = svc.get("livenessProbe", {})
        readiness = svc.get("readinessProbe", {})
        if liveness and liveness.get("enabled"):
            spec["livenessProbe"] = _build_probe(liveness)
        if readiness and readiness.get("enabled"):
            spec["readinessProbe"] = _build_probe(readiness)

        # Resources
        cpu_request = svc.get("cpuRequest", "")
        mem_request = svc.get("memRequest", "")
        cpu_limit = svc.get("cpuLimit", "")
        mem_limit = svc.get("memLimit", "")
        if cpu_request or mem_request or cpu_limit or mem_limit:
            res_spec: dict = {}
            if cpu_request or mem_request:
                res_spec["requests"] = {}
                if cpu_request:
                    res_spec["requests"]["cpu"] = cpu_request
                if mem_request:
                    res_spec["requests"]["memory"] = mem_request
            if cpu_limit or mem_limit:
                res_spec["limits"] = {}
                if cpu_limit:
                    res_spec["limits"]["cpu"] = cpu_limit
                if mem_limit:
                    res_spec["limits"]["memory"] = mem_limit
            spec["resources"] = res_spec

        # Service mesh
        mesh = svc.get("mesh", {})
        if mesh and mesh.get("enabled"):
            mesh_name = mesh.get("provider", "istio")
            mesh_annotations = _build_mesh_annotations(mesh_name, mesh)
            if mesh_annotations:
                spec["annotations"] = mesh_annotations

        # Deployment strategy
        strategy = svc.get("strategy")
        if strategy:
            spec["strategy"] = strategy
            if strategy == "RollingUpdate":
                if svc.get("maxSurge") is not None:
                    spec["maxSurge"] = svc["maxSurge"]
                if svc.get("maxUnavailable") is not None:
                    spec["maxUnavailable"] = svc["maxUnavailable"]

        # StatefulSet extras
        if svc_kind == "StatefulSet":
            spec["headlessServiceName"] = f"{svc_name}-headless"
            if svc.get("podManagementPolicy"):
                spec["podManagementPolicy"] = svc["podManagementPolicy"]
            if svc.get("partition") is not None:
                spec["partition"] = svc["partition"]

        # DaemonSet extras
        if svc_kind == "DaemonSet":
            if svc.get("nodeSelector"):
                spec["nodeSelector"] = svc["nodeSelector"]
            if svc.get("tolerations"):
                spec["tolerations"] = svc["tolerations"]

        # Job / CronJob extras
        if svc_kind in ("Job", "CronJob"):
            for jk in ("schedule", "concurrencyPolicy", "backoffLimit",
                        "completions", "parallelism", "activeDeadlineSeconds",
                        "ttlSecondsAfterFinished", "restartPolicy",
                        "successfulJobsHistoryLimit", "failedJobsHistoryLimit",
                        "suspend", "startingDeadlineSeconds"):
                val = svc.get(jk)
                if val is not None and val != "":
                    spec[jk] = val

        # Command override
        command = svc.get("command")
        if command:
            spec["command"] = command
        args = svc.get("args")
        if args:
            spec["args"] = args

        resources.append({
            "kind": svc_kind,
            "name": svc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": spec,
        })

        # Track for Service generation
        if port and svc_kind in ("Deployment", "StatefulSet", "DaemonSet"):
            svc_entry = {
                "name": svc_name,
                "port": port,
                "kind": svc_kind,
            }
            svc_type = svc.get("serviceType", "ClusterIP")
            if svc_type:
                svc_entry["serviceType"] = svc_type
            services_needing_svc.append(svc_entry)

    # ── K8s Service resources ───────────────────────────────────
    for svc_info in services_needing_svc:
        svc_name = svc_info["name"]
        port = svc_info["port"]
        svc_type = svc_info.get("serviceType", "ClusterIP")

        resources.append({
            "kind": "Service",
            "name": svc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {
                "port": port,
                "target_port": port,
                "type": svc_type,
                "selector": svc_name,
            },
        })

        # StatefulSet headless service
        if svc_info["kind"] == "StatefulSet":
            resources.append({
                "kind": "Service",
                "name": f"{svc_name}-headless",
                "namespace": namespace,
                "output_dir": output_dir,
                "spec": {
                    "port": port,
                    "target_port": port,
                    "type": "None",
                    "selector": svc_name,
                    "headless": True,
                },
            })

    # ── Ingress ──────────────────────────────────────────────────
    ingress_host = data.get("ingress", "")
    if ingress_host and services_needing_svc:
        if len(services_needing_svc) == 1:
            svc_info = services_needing_svc[0]
            resources.append({
                "kind": "Ingress",
                "name": f"{svc_info['name']}-ingress",
                "namespace": namespace,
                "output_dir": output_dir,
                "spec": {
                    "host": ingress_host,
                    "port": svc_info["port"],
                    "service": svc_info["name"],
                },
            })
        else:
            paths = []
            for idx, svc_info in enumerate(services_needing_svc):
                path_prefix = f"/{svc_info['name']}" if idx > 0 else "/"
                paths.append({
                    "path": path_prefix,
                    "pathType": "Prefix",
                    "backend": {
                        "service": {
                            "name": svc_info["name"],
                            "port": {"number": svc_info["port"]},
                        },
                    },
                })
            resources.append({
                "kind": "Ingress",
                "name": "app-ingress",
                "namespace": namespace,
                "output_dir": output_dir,
                "spec": {
                    "host": ingress_host,
                    "_paths": paths,
                },
            })

    return resources


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


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.k8s_wizard_detect import (  # noqa: F401, E402
    skaffold_status,
    k8s_env_namespaces,
)

from src.core.services.k8s_wizard_generate import (  # noqa: F401, E402
    generate_k8s_wizard,
    _generate_skaffold,
)


