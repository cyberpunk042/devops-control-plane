"""K8s manifest generation — templates and pod builder.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("k8s")

_DEPLOYMENT_TEMPLATE = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: {name}
          image: {image}
          ports:
            - containerPort: {port}
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
"""

_SERVICE_TEMPLATE = """apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  type: {service_type}
  ports:
    - port: {port}
      targetPort: {port}
      protocol: TCP
      name: http
  selector:
    app: {name}
"""

_INGRESS_TEMPLATE = """apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
    - host: {host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {name}
                port:
                  number: {port}
"""

_NAMESPACE_TEMPLATE = """apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    name: {namespace}
"""


def generate_manifests(
    project_root: Path,
    app_name: str,
    *,
    image: str = "",
    port: int = 8080,
    replicas: int = 2,
    service_type: str = "ClusterIP",
    host: str = "",
    namespace: str = "",
) -> dict:
    """Generate Kubernetes manifests for an application.

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    from src.core.models.template import GeneratedFile

    if not image:
        image = f"{app_name}:latest"

    files: list[dict] = []

    # Namespace (if specified)
    if namespace:
        ns_file = GeneratedFile(
            path=f"k8s/{namespace}-namespace.yaml",
            content=_NAMESPACE_TEMPLATE.format(namespace=namespace),
            overwrite=False,
            reason=f"Namespace for {app_name}",
        )
        files.append(ns_file.model_dump())

    # Deployment
    deploy_file = GeneratedFile(
        path=f"k8s/{app_name}-deployment.yaml",
        content=_DEPLOYMENT_TEMPLATE.format(
            name=app_name, image=image, port=port, replicas=replicas,
        ),
        overwrite=False,
        reason=f"Deployment for {app_name} ({replicas} replicas)",
    )
    files.append(deploy_file.model_dump())

    # Service
    svc_file = GeneratedFile(
        path=f"k8s/{app_name}-service.yaml",
        content=_SERVICE_TEMPLATE.format(
            name=app_name, port=port, service_type=service_type,
        ),
        overwrite=False,
        reason=f"Service ({service_type}) for {app_name}",
    )
    files.append(svc_file.model_dump())

    # Ingress (if host specified)
    if host:
        ing_file = GeneratedFile(
            path=f"k8s/{app_name}-ingress.yaml",
            content=_INGRESS_TEMPLATE.format(
                name=app_name, port=port, host=host,
            ),
            overwrite=False,
            reason=f"Ingress for {app_name} at {host}",
        )
        files.append(ing_file.model_dump())

    return {"ok": True, "files": files}

def _build_probe(probe: dict) -> dict:
    """Convert wizard probe format to K8s probe spec.

    Input shape (from _collectProbe in frontend):
        {type: "http"|"tcp"|"exec", path, port, command,
         initialDelaySeconds, periodSeconds, extra (→ failureThreshold)}
    """
    p: dict = {}
    ptype = probe.get("type", "http")
    if ptype == "http":
        p["httpGet"] = {
            "path": probe.get("path", "/health"),
            "port": int(probe.get("port", 8080)),
        }
    elif ptype == "tcp":
        p["tcpSocket"] = {"port": int(probe.get("port", 8080))}
    else:  # exec
        cmd = probe.get("command", "")
        p["exec"] = {"command": ["sh", "-c", cmd] if cmd else ["/bin/true"]}

    delay = probe.get("initialDelaySeconds")
    if delay and int(delay) > 0:
        p["initialDelaySeconds"] = int(delay)
    period = probe.get("periodSeconds")
    if period and int(period) > 0:
        p["periodSeconds"] = int(period)
    threshold = probe.get("extra")
    if threshold and int(threshold) > 0:
        p["failureThreshold"] = int(threshold)

    return p


def _build_wizard_volume(vol: dict, index: int, svc_name: str) -> tuple[dict | None, dict | None]:
    """Convert a wizard volume entry to (pod_volume_def, volume_mount).

    Returns (None, None) if the volume is invalid.
    The caller is responsible for deduplicating pod volumes by name.
    """
    mount_path = vol.get("mountPath", "")
    if not mount_path:
        return None, None

    vol_type = vol.get("type", "emptyDir")
    vol_name: str = ""
    pod_vol: dict = {}
    vm: dict = {}

    if vol_type in ("pvc-dynamic", "pvc-static"):
        vol_name = vol.get("name") or f"data-{index}"
        # PVC claim name also prefixed with svc name for uniqueness
        claim_name = f"{svc_name}-{vol_name}" if svc_name else vol_name
        pod_vol = {"name": vol_name, "persistentVolumeClaim": {"claimName": claim_name}}
        vm = {"name": vol_name, "mountPath": mount_path}

    elif vol_type == "emptyDir":
        vol_name = vol.get("name") or f"empty-{index}"
        empty_spec: dict = {}
        if vol.get("medium") == "Memory":
            empty_spec["medium"] = "Memory"
        if vol.get("sizeLimit"):
            empty_spec["sizeLimit"] = vol["sizeLimit"]
        pod_vol = {"name": vol_name, "emptyDir": empty_spec}
        vm = {"name": vol_name, "mountPath": mount_path}

    elif vol_type == "configMap":
        cm_name = vol.get("configMapName", "")
        vol_name = f"cm-{cm_name}" if cm_name else f"cm-{index}"
        cm_def: dict = {"name": cm_name}
        key = vol.get("key", "")
        if key:
            cm_def["items"] = [{"key": key, "path": key}]
        pod_vol = {"name": vol_name, "configMap": cm_def}
        vm = {"name": vol_name, "mountPath": mount_path}
        if key:
            vm["subPath"] = key

    elif vol_type == "secret":
        sec_name = vol.get("secretName", "")
        vol_name = f"sec-{sec_name}" if sec_name else f"sec-{index}"
        sec_def: dict = {"secretName": sec_name}
        key = vol.get("key", "")
        if key:
            sec_def["items"] = [{"key": key, "path": key}]
        pod_vol = {"name": vol_name, "secret": sec_def}
        vm = {"name": vol_name, "mountPath": mount_path}
        if key:
            vm["subPath"] = key

    elif vol_type == "hostPath":
        vol_name = vol.get("name") or f"hp-{index}"
        hp_def: dict = {"path": vol.get("hostPath", mount_path)}
        host_type = vol.get("hostType", "")
        if host_type:
            hp_def["type"] = host_type
        pod_vol = {"name": vol_name, "hostPath": hp_def}
        vm = {"name": vol_name, "mountPath": mount_path}

    else:
        return None, None

    return pod_vol, vm


def _build_pod_template(name: str, spec: dict) -> dict:
    """Build a pod template dict shared across all workload kinds.

    Handles: main container, init containers, sidecar containers,
    companion containers, volumes, probes, host access, and mesh annotations.
    """
    image = spec.get("image", f"{name}:latest")
    port = spec.get("port")

    # ── Main container ──
    main_container: dict = {
        "name": name,
        "image": image,
    }
    if port:
        main_container["ports"] = [{"containerPort": int(port)}]

    # Job/CronJob command/args override
    cmd = spec.get("command", "")
    if cmd:
        main_container["command"] = ["sh", "-c", cmd]
    args = spec.get("args", "")
    if args:
        main_container["args"] = args.split() if isinstance(args, str) else args

    # Resource limits
    resources: dict = {}
    if spec.get("cpu_limit") or spec.get("memory_limit"):
        resources["limits"] = {}
        if spec.get("cpu_limit"):
            resources["limits"]["cpu"] = spec["cpu_limit"]
        if spec.get("memory_limit"):
            resources["limits"]["memory"] = spec["memory_limit"]
    if spec.get("cpu_request") or spec.get("memory_request"):
        resources.setdefault("requests", {})
        if spec.get("cpu_request"):
            resources["requests"]["cpu"] = spec["cpu_request"]
        if spec.get("memory_request"):
            resources["requests"]["memory"] = spec["memory_request"]
    if resources:
        main_container["resources"] = resources

    # ── Health probes ──
    if spec.get("readinessProbe"):
        main_container["readinessProbe"] = _build_probe(spec["readinessProbe"])
    if spec.get("livenessProbe"):
        main_container["livenessProbe"] = _build_probe(spec["livenessProbe"])

    # ── Env vars ──
    # svc_name is used by the translator to set the correct ConfigMap/Secret name
    env_list = _build_env_vars(spec.get("env"), svc_name=spec.get("_svc_name", ""))
    if env_list:
        main_container["env"] = env_list

    # envFrom — bulk ConfigMap/Secret refs (set by translator)
    env_from = spec.get("envFrom")
    if env_from:
        main_container["envFrom"] = env_from

    pod_spec: dict = {
        "containers": [main_container],
    }

    # ── Init containers ──
    init_containers_list: list[dict] = []
    for ic in (spec.get("initContainers") or []):
        ic_spec: dict = {
            "name": ic.get("name", "init"),
            "image": ic.get("image", "busybox:1.36"),
        }
        cmd = ic.get("command", "")
        if cmd:
            ic_spec["command"] = ["sh", "-c", cmd]
        init_containers_list.append(ic_spec)

    # ── Sidecar containers ──
    # ── Volumes ──
    # Start with any pod-level volumes already provided (rare, for direct API)
    volumes: list[dict] = list(spec.get("_pod_volumes") or [])
    volume_mounts_main: list[dict] = list(spec.get("volumeMounts") or [])

    # Process wizard volumes (from _collectVolumes frontend)
    vol_names_seen: set[str] = {v.get("name", "") for v in volumes}
    for vi, wv in enumerate(spec.get("wizardVolumes") or []):
        pod_vol_def, vm_def = _build_wizard_volume(wv, vi, name)
        if pod_vol_def and vm_def:
            vn = pod_vol_def.get("name", "")
            if vn and vn not in vol_names_seen:
                volumes.append(pod_vol_def)
                vol_names_seen.add(vn)
            volume_mounts_main.append(vm_def)

    for sc in (spec.get("sidecars") or []):
        sc_spec: dict = {
            "name": sc.get("name", "sidecar"),
            "image": sc.get("image", ""),
        }
        cmd = sc.get("command", "")
        if cmd:
            sc_spec["command"] = ["sh", "-c", cmd]

        # Shared volume handling
        shared_vol = sc.get("sharedVolume", "")
        shared_mount = sc.get("sharedMount", "")
        if shared_vol and shared_mount:
            # Add emptyDir volume if not already present
            vol_names = {v.get("name") for v in volumes}
            if shared_vol not in vol_names:
                volumes.append({"name": shared_vol, "emptyDir": {}})
            sc_spec["volumeMounts"] = [{"name": shared_vol, "mountPath": shared_mount}]
            # Also mount in the main container
            volume_mounts_main.append({"name": shared_vol, "mountPath": shared_mount})

        if sc.get("nativeSidecar", True):
            # Native sidecar (K8s ≥ 1.28): add to initContainers with restartPolicy: Always
            sc_spec["restartPolicy"] = "Always"
            init_containers_list.append(sc_spec)
        else:
            # Regular sidecar: add to containers[]
            pod_spec["containers"].append(sc_spec)

    # ── Companion containers (from "move into pod") ──
    for comp in (spec.get("companions") or []):
        comp_spec: dict = {
            "name": comp.get("name", "companion"),
            "image": comp.get("image", ""),
        }
        if comp.get("port"):
            comp_spec["ports"] = [{"containerPort": int(comp["port"])}]
        comp_env = _build_env_vars(comp.get("env"))
        if comp_env:
            comp_spec["env"] = comp_env

        # Companion resource limits
        comp_res = comp.get("resources")
        if comp_res:
            res_spec: dict = {}
            if comp_res.get("cpu_limit") or comp_res.get("memory_limit"):
                res_spec["limits"] = {}
                if comp_res.get("cpu_limit"):
                    res_spec["limits"]["cpu"] = comp_res["cpu_limit"]
                if comp_res.get("memory_limit"):
                    res_spec["limits"]["memory"] = comp_res["memory_limit"]
            if comp_res.get("cpu_request") or comp_res.get("memory_request"):
                res_spec.setdefault("requests", {})
                if comp_res.get("cpu_request"):
                    res_spec["requests"]["cpu"] = comp_res["cpu_request"]
                if comp_res.get("memory_request"):
                    res_spec["requests"]["memory"] = comp_res["memory_request"]
            if res_spec:
                comp_spec["resources"] = res_spec

        # Companion volume mounts
        comp_vols = comp.get("volumes") or []
        if comp_vols:
            comp_volume_mounts: list[dict] = []
            vol_names = {v.get("name") for v in volumes}
            for cv in comp_vols:
                mount_path = cv.get("mountPath", "")
                vol_name = cv.get("name", "")
                vol_type = cv.get("type", "emptyDir")
                if not mount_path:
                    continue
                # Add to pod-level volumes if not already present
                if vol_name and vol_name not in vol_names:
                    if vol_type == "emptyDir":
                        volumes.append({"name": vol_name, "emptyDir": {}})
                    elif vol_type in ("pvc-dynamic", "pvc-static"):
                        volumes.append({
                            "name": vol_name,
                            "persistentVolumeClaim": {"claimName": vol_name},
                        })
                    elif vol_type == "configMap":
                        volumes.append({
                            "name": vol_name,
                            "configMap": {"name": vol_name},
                        })
                    elif vol_type == "secret":
                        volumes.append({
                            "name": vol_name,
                            "secret": {"secretName": vol_name},
                        })
                    vol_names.add(vol_name)
                if vol_name:
                    comp_volume_mounts.append({
                        "name": vol_name,
                        "mountPath": mount_path,
                    })
            if comp_volume_mounts:
                comp_spec["volumeMounts"] = comp_volume_mounts

        pod_spec["containers"].append(comp_spec)

        # Companion startup dependency → wait-for init container
        depends_on = comp.get("dependsOn")
        if depends_on and depends_on != "__main__":
            # Infrastructure service — use K8s DNS name
            wait_host = depends_on
            wait_port = str(comp.get("dependsOnPort") or spec.get("port", "8080"))

            wait_name = f"wait-for-{comp.get('name', 'companion')}"
            wait_cmd = (
                f"echo 'Waiting for {wait_host}:{wait_port}…'; "
                f"until nc -z {wait_host} {wait_port}; do sleep 2; done; "
                f"echo 'Ready.'"
            )
            init_containers_list.append({
                "name": wait_name,
                "image": "busybox:1.36",
                "command": ["sh", "-c", wait_cmd],
            })

    # ── Finalize initContainers (after ALL sources: user, sidecar, companion) ──
    if init_containers_list:
        pod_spec["initContainers"] = init_containers_list

    # ── VCT volumeMounts (StatefulSet) ──
    # VolumeClaimTemplates don't need pod volumes[] — K8s injects them.
    # But the container DOES need volumeMounts referencing each VCT by name.
    for vct in (spec.get("volumeClaimTemplates") or []):
        vct_name = vct.get("name", "")
        vct_mount = vct.get("mountPath", "")
        if vct_name and vct_mount:
            volume_mounts_main.append({
                "name": vct_name,
                "mountPath": vct_mount,
            })

    # ── Final volume assembly ──
    if volumes:
        pod_spec["volumes"] = volumes
    if volume_mounts_main:
        main_container["volumeMounts"] = volume_mounts_main

    # ── Host access flags (DaemonSet) ──
    if spec.get("hostNetwork"):
        pod_spec["hostNetwork"] = True
    if spec.get("hostPID"):
        pod_spec["hostPID"] = True
    if spec.get("hostIPC"):
        pod_spec["hostIPC"] = True

    # Build the template
    template: dict = {
        "metadata": {"labels": {"app": name}},
        "spec": pod_spec,
    }

    # ── Mesh annotations ──
    mesh = spec.get("mesh")
    if mesh:
        annotations = _build_mesh_annotations(mesh)
        if annotations:
            template["metadata"]["annotations"] = annotations

    return template


def _build_env_vars(env_spec, *, svc_name: str = "") -> list[dict]:
    """Build K8s env var list from various input formats.

    Handles:
    - dict: simple {KEY: value} mapping
    - list of {name, value} or {name, secretName} (classic K8s format)
    - list of {key, type, value, varName} (wizard frontend format)

    When svc_name is provided (set by the translator), wizard-format env vars
    use the service-name convention for ConfigMap/Secret references:
        secret  → secretKeyRef.name = "{svc_name}-secrets"
        variable → configMapKeyRef.name = "{svc_name}-config"
        hardcoded → configMapKeyRef.name = "{svc_name}-config"
    This ensures the references match the ConfigMap/Secret resources that
    the translator generates alongside the workload.
    """
    if not env_spec:
        return []
    if isinstance(env_spec, dict):
        return [{"name": k, "value": str(v)} for k, v in env_spec.items()]
    if isinstance(env_spec, list):
        result: list[dict] = []
        for item in env_spec:
            if not isinstance(item, dict):
                continue
            # Accept both "name" and "key" as the env var name
            env_name = item.get("name") or item.get("key")
            if not env_name:
                continue
            entry: dict = {"name": env_name}
            # Classic format: explicit secretKeyRef
            if item.get("secretName"):
                entry["valueFrom"] = {
                    "secretKeyRef": {
                        "name": item["secretName"],
                        "key": item.get("secretKey", env_name),
                    },
                }
            elif item.get("configMapName"):
                entry["valueFrom"] = {
                    "configMapKeyRef": {
                        "name": item["configMapName"],
                        "key": item.get("configMapKey", env_name),
                    },
                }
            # Wizard format: type-based routing
            elif item.get("type") == "secret":
                # Use service-name convention when svc_name is known
                if svc_name:
                    secret_ref_name = f"{svc_name}-secrets"
                else:
                    # Fallback: derive from varName
                    var_ref = (item.get("varName") or "").strip("${}")
                    secret_ref_name = var_ref.lower().replace("_", "-") if var_ref else env_name.lower().replace("_", "-")
                entry["valueFrom"] = {
                    "secretKeyRef": {
                        "name": secret_ref_name,
                        "key": env_name,
                    },
                }
            elif item.get("type") == "variable":
                if svc_name:
                    cm_ref_name = f"{svc_name}-config"
                else:
                    var_ref = (item.get("varName") or "").strip("${}")
                    cm_ref_name = var_ref.lower().replace("_", "-") if var_ref else "app-config"
                entry["valueFrom"] = {
                    "configMapKeyRef": {
                        "name": cm_ref_name,
                        "key": env_name,
                    },
                }
            else:
                # hardcoded: inline value for now.
                # When svc_name is set, the translator uses envFrom for bulk
                # ConfigMap injection, so hardcoded vars go into the ConfigMap
                # resource and don't need individual env entries. BUT we still
                # include them here as fallback for direct API use.
                entry["value"] = str(item.get("value", ""))
            result.append(entry)
        return result
    return []


def _mesh_annotation_prefixes() -> dict[str, dict]:
    """Mesh annotation prefixes — loaded from DataRegistry."""
    from src.core.data import get_registry
    return get_registry().mesh_annotations


def _build_mesh_annotations(mesh: dict) -> dict:
    """Build mesh-provider-specific annotations for pod template."""
    provider = mesh.get("provider", "istio")
    all_prefixes = _mesh_annotation_prefixes()
    prefixes = all_prefixes.get(provider, all_prefixes["istio"])

    annotations: dict = {}

    # Inject annotation
    inject_key = prefixes.get("inject", "")
    if inject_key:
        annotations[inject_key] = "true" if provider != "linkerd" else "enabled"

    # Proxy resources
    field_map = {
        "proxyCpuRequest": "proxyCPU",
        "proxyCpuLimit": "proxyCPULimit",
        "proxyMemRequest": "proxyMemory",
        "proxyMemLimit": "proxyMemoryLimit",
    }
    for mesh_key, prefix_key in field_map.items():
        val = mesh.get(mesh_key, "")
        anno_key = prefixes.get(prefix_key, "")
        if val and anno_key:
            annotations[anno_key] = val

    # Log level
    log_level = mesh.get("logLevel", "")
    log_key = prefixes.get("logLevel", "")
    if log_level and log_key:
        annotations[log_key] = log_level

    # Exclude ports
    for field, prefix_key in [("excludeInbound", "excludeInbound"), ("excludeOutbound", "excludeOutbound")]:
        val = mesh.get(field, "")
        anno_key = prefixes.get(prefix_key, "")
        if val and anno_key:
            annotations[anno_key] = val

    return annotations


def _api_version_for_kind(kind: str) -> str:
    """Resolve the conventional apiVersion for a K8s kind."""
    mapping = {
        "Deployment": "apps/v1",
        "StatefulSet": "apps/v1",
        "DaemonSet": "apps/v1",
        "ReplicaSet": "apps/v1",
        "Job": "batch/v1",
        "CronJob": "batch/v1",
        "Ingress": "networking.k8s.io/v1",
        "NetworkPolicy": "networking.k8s.io/v1",
        "HorizontalPodAutoscaler": "autoscaling/v2",
    }
    return mapping.get(kind, "v1")
