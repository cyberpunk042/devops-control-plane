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


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.k8s_pod_builder import (  # noqa: F401, E402
    _build_probe,
    _build_wizard_volume,
    _build_pod_template,
    _build_env_vars,
    _build_mesh_annotations,
    _mesh_annotation_prefixes,
    _api_version_for_kind,
)

