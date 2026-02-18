"""
Helm chart generation from wizard state.

Generates a standard Helm chart directory:
    charts/{name}/
    ├── Chart.yaml
    ├── values.yaml              (0.4.5)
    ├── values-{env}.yaml        (0.4.7)
    ├── templates/               (0.4.6)
    │   ├── _helpers.tpl
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   ├── ingress.yaml
    │   ├── configmap.yaml
    │   ├── secret.yaml
    │   └── NOTES.txt
    └── .helmignore              (0.4.8)

This module covers section 0.4.4–0.4.8 of the alpha milestones.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _extract_app_version(services: list[dict]) -> str:
    """Extract appVersion from first service's image tag.

    'myapp:v1.2.3' → 'v1.2.3'
    'myapp' (no tag) → '1.0.0'
    """
    if not services:
        return "1.0.0"
    image = services[0].get("image", "")
    if ":" in image:
        return image.rsplit(":", 1)[1]
    return "1.0.0"


import re

_CHART_NAME_RE = re.compile(r"[^a-z0-9\-]")


def _sanitize_chart_name(name: str) -> str:
    """Sanitize a chart name for DNS label compliance.

    - lowercase
    - replace non-alphanumeric (except dash) with dash
    - collapse consecutive dashes
    - strip leading/trailing dashes
    - truncate to 63 chars
    """
    name = name.lower()
    name = _CHART_NAME_RE.sub("-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    name = name[:63]
    name = name.rstrip("-")
    return name or "app"


def _chart_name(services: list[dict]) -> str:
    """Derive chart name from first service, fallback 'app'."""
    if services:
        raw = services[0].get("name", "app")
        return _sanitize_chart_name(raw) if raw else "app"
    return "app"

def _split_image(image: str) -> tuple[str, str]:
    """Split 'repo:tag' into (repo, tag). No tag → ('repo', 'latest')."""
    if ":" in image:
        repo, tag = image.rsplit(":", 1)
        return repo, tag
    return image, "latest"


def _build_values_yaml(data: dict, services: list[dict]) -> dict:
    """Build values.yaml content dict from wizard state.

    Structure follows Helm best practices:
      replicaCount, image, service, ingress, resources, env, existingSecret
    """
    # Use first non-Skip service for top-level values
    active = [s for s in services if s.get("kind") != "Skip"]
    first = active[0] if active else {}

    if not first:
        # Minimal values for empty charts
        return {
            "replicaCount": 1,
            "image": {"repository": "nginx", "tag": "latest", "pullPolicy": "IfNotPresent"},
            "service": {"type": "ClusterIP", "port": 80},
            "ingress": {"enabled": False, "host": ""},
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "256Mi"},
            },
        }

    # Image
    repo, tag = _split_image(first.get("image", "nginx:latest"))

    # Env vars: separate plain from secret
    env_list: list[dict] = []
    has_secrets = False
    for env in first.get("env", []):
        key = env.get("key", "")
        if not key:
            continue
        if env.get("type") == "secret":
            has_secrets = True
            continue  # secrets go to existingSecret, not plain env
        env_list.append({"name": key, "value": env.get("value", "")})

    # Ingress
    ingress_host = data.get("ingress_host", "")

    values: dict = {
        "replicaCount": first.get("replicas", 1),
        "image": {
            "repository": repo,
            "tag": tag,
            "pullPolicy": "IfNotPresent",
        },
        "service": {
            "type": "ClusterIP",
            "port": first.get("port", 80),
        },
        "ingress": {
            "enabled": bool(ingress_host),
            "host": ingress_host,
        },
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "256Mi"},
        },
    }

    if env_list:
        values["env"] = env_list

    if has_secrets:
        values["existingSecret"] = f"{_chart_name(services)}-secrets"

    return values


def generate_helm_chart(data: dict, output_dir: Path) -> dict:
    """Generate a Helm chart directory from wizard state.

    Args:
        data: Wizard state dict with _services, _project_description, etc.
        output_dir: Root directory where charts/{name}/ will be created.

    Returns:
        dict with 'files' list of relative paths created.
    """
    if not data.get("helm_chart"):
        return {"files": []}

    services = list(data.get("_services", []))
    name = _chart_name(services)
    app_version = _extract_app_version(services)
    description = data.get(
        "_project_description",
        f"A Helm chart for {name}",
    )

    chart_dir = output_dir / "charts" / name
    chart_dir.mkdir(parents=True, exist_ok=True)

    files: list[str] = []

    # ── Chart.yaml ──────────────────────────────────────────────────
    chart_yaml = {
        "apiVersion": "v2",
        "name": name,
        "description": description,
        "type": "application",
        "version": "0.1.0",
        "appVersion": app_version,
    }
    chart_file = chart_dir / "Chart.yaml"
    chart_file.write_text(
        yaml.dump(chart_yaml, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    files.append(str(chart_file.relative_to(output_dir)))

    # ── values.yaml ─────────────────────────────────────────────────
    values = _build_values_yaml(data, services)
    values_file = chart_dir / "values.yaml"
    values_file.write_text(
        yaml.dump(values, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    files.append(str(values_file.relative_to(output_dir)))

    # ── templates/ ──────────────────────────────────────────────────
    tpl_files = _generate_templates(name, services, chart_dir)
    files.extend(str(f.relative_to(output_dir)) for f in tpl_files)

    # ── values-{env}.yaml (0.4.7) ──────────────────────────────────
    environments = data.get("environments", [])
    for env_name in environments:
        env_values = _build_env_overrides(env_name)
        env_file = chart_dir / f"values-{env_name}.yaml"
        env_file.write_text(
            yaml.dump(env_values, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        files.append(str(env_file.relative_to(output_dir)))

    # ── .helmignore (0.4.8) ─────────────────────────────────────────
    helmignore = chart_dir / ".helmignore"
    helmignore.write_text(_HELMIGNORE_CONTENT, encoding="utf-8")
    files.append(str(helmignore.relative_to(output_dir)))

    return {"files": files}


# ─────────────────────────────────────────────────────────────────────
#  Per-Environment overrides (0.4.7)
# ─────────────────────────────────────────────────────────────────────

_ENV_OVERRIDES: dict[str, dict] = {
    "dev": {
        "replicaCount": 1,
        "resources": {
            "requests": {"cpu": "50m", "memory": "64Mi"},
            "limits": {"cpu": "200m", "memory": "128Mi"},
        },
    },
    "staging": {
        "replicaCount": 2,
        "image": {"tag": "staging-latest"},
    },
    "prod": {
        "replicaCount": 3,
        "resources": {
            "requests": {"cpu": "250m", "memory": "256Mi"},
            "limits": {"cpu": "1000m", "memory": "512Mi"},
        },
    },
}


def _build_env_overrides(env_name: str) -> dict:
    """Return overrides dict for the given environment.

    Falls back to a minimal override if the environment is unknown.
    """
    return _ENV_OVERRIDES.get(env_name, {"replicaCount": 1})


# ─────────────────────────────────────────────────────────────────────
#  .helmignore (0.4.8)
# ─────────────────────────────────────────────────────────────────────

_HELMIGNORE_CONTENT = """\
# Patterns to ignore when building packages.
.git/
.gitignore
*.swp
*.bak
*.tmp
*.orig
__pycache__/
.venv/
.env
.idea/
.vscode/
*.pyc
"""


# ─────────────────────────────────────────────────────────────────────
#  Template generators (0.4.6)
# ─────────────────────────────────────────────────────────────────────

def _has_env_type(services: list[dict], env_type: str) -> bool:
    """Check if any service has env vars of the given type."""
    for svc in services:
        if svc.get("kind") == "Skip":
            continue
        for env in svc.get("env", []):
            if env.get("type") == env_type:
                return True
    return False


def _generate_templates(name: str, services: list[dict], chart_dir: Path) -> list[Path]:
    """Generate templates/ directory with standard Helm templates.

    Returns list of created file Paths.
    """
    tpl_dir = chart_dir / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # ── _helpers.tpl ────────────────────────────────────────────────
    helpers = _tpl_helpers(name)
    f = tpl_dir / "_helpers.tpl"
    f.write_text(helpers, encoding="utf-8")
    created.append(f)

    # ── deployment.yaml ─────────────────────────────────────────────
    f = tpl_dir / "deployment.yaml"
    f.write_text(_tpl_deployment(name), encoding="utf-8")
    created.append(f)

    # ── service.yaml ────────────────────────────────────────────────
    has_ports = any(
        s.get("port") for s in services if s.get("kind") != "Skip"
    )
    if has_ports or not services:
        f = tpl_dir / "service.yaml"
        f.write_text(_tpl_service(name), encoding="utf-8")
        created.append(f)

    # ── ingress.yaml ────────────────────────────────────────────────
    f = tpl_dir / "ingress.yaml"
    f.write_text(_tpl_ingress(name), encoding="utf-8")
    created.append(f)

    # ── configmap.yaml (conditional) ────────────────────────────────
    if _has_env_type(services, "literal"):
        f = tpl_dir / "configmap.yaml"
        f.write_text(_tpl_configmap(name), encoding="utf-8")
        created.append(f)

    # ── secret.yaml (conditional) ───────────────────────────────────
    if _has_env_type(services, "secret"):
        f = tpl_dir / "secret.yaml"
        f.write_text(_tpl_secret(name), encoding="utf-8")
        created.append(f)

    # ── NOTES.txt ───────────────────────────────────────────────────
    f = tpl_dir / "NOTES.txt"
    f.write_text(_tpl_notes(name), encoding="utf-8")
    created.append(f)

    return created


# ─────────────────────────────────────────────────────────────────────
#  Template content strings
# ─────────────────────────────────────────────────────────────────────

def _tpl_helpers(name: str) -> str:
    return f'''{{{{/*
Chart name.
*/}}}}
{{{{- define "{name}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{/*
Fully qualified app name.
*/}}}}
{{{{- define "{name}.fullname" -}}}}
{{{{- if .Values.fullnameOverride }}}}
{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- $name := default .Chart.Name .Values.nameOverride }}}}
{{{{- if contains $name .Release.Name }}}}
{{{{- .Release.Name | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}
{{{{- end }}}}
{{{{- end }}}}

{{{{/*
Common labels.
*/}}}}
{{{{- define "{name}.labels" -}}}}
helm.sh/chart: {{{{- include "{name}.name" . }}}}
app.kubernetes.io/name: {{{{ include "{name}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
{{{{- end }}}}
'''


def _tpl_deployment(name: str) -> str:
    return f'''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{name}.fullname" . }}}}
  labels:
    {{{{- include "{name}.labels" . | nindent 4 }}}}
spec:
  replicas: {{{{ .Values.replicaCount }}}}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{{{ include "{name}.name" . }}}}
      app.kubernetes.io/instance: {{{{ .Release.Name }}}}
  template:
    metadata:
      labels:
        {{{{- include "{name}.labels" . | nindent 8 }}}}
    spec:
      containers:
        - name: {{{{ include "{name}.name" . }}}}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - name: http
              containerPort: {{{{ .Values.service.port }}}}
              protocol: TCP
          {{{{- if .Values.env }}}}
          env:
            {{{{- range .Values.env }}}}
            - name: {{{{ .name }}}}
              value: {{{{ .value | quote }}}}
            {{{{- end }}}}
          {{{{- end }}}}
          {{{{- if .Values.existingSecret }}}}
          envFrom:
            - secretRef:
                name: {{{{ .Values.existingSecret }}}}
          {{{{- end }}}}
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
'''


def _tpl_service(name: str) -> str:
    return f'''apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{name}.fullname" . }}}}
  labels:
    {{{{- include "{name}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app.kubernetes.io/name: {{{{ include "{name}.name" . }}}}
    app.kubernetes.io/instance: {{{{ .Release.Name }}}}
'''


def _tpl_ingress(name: str) -> str:
    return f'''{{{{- if .Values.ingress.enabled -}}}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{{{ include "{name}.fullname" . }}}}
  labels:
    {{{{- include "{name}.labels" . | nindent 4 }}}}
spec:
  rules:
    - host: {{{{ .Values.ingress.host | quote }}}}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{{{ include "{name}.fullname" . }}}}
                port:
                  number: {{{{ .Values.service.port }}}}
{{{{- end }}}}
'''


def _tpl_configmap(name: str) -> str:
    return f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: {{{{ include "{name}.fullname" . }}}}-config
  labels:
    {{{{- include "{name}.labels" . | nindent 4 }}}}
data:
  {{{{- range .Values.env }}}}
  {{{{ .name }}}}: {{{{ .value | quote }}}}
  {{{{- end }}}}
'''


def _tpl_secret(name: str) -> str:
    return f'''apiVersion: v1
kind: Secret
metadata:
  name: {{{{ include "{name}.fullname" . }}}}-secret
  labels:
    {{{{- include "{name}.labels" . | nindent 4 }}}}
type: Opaque
data:
  {{{{/* Secret values should be provided via --set or external secret management */}}}}
  {{{{/* This template exists as a placeholder for the existingSecret reference */}}}}
'''


def _tpl_notes(name: str) -> str:
    return f'''1. Get the application URL by running these commands:
{{{{- if .Values.ingress.enabled }}}}
  http://{{{{ .Values.ingress.host }}}}
{{{{- else }}}}
  export POD_NAME=$(kubectl get pods --namespace {{{{ .Release.Namespace }}}} -l "app.kubernetes.io/name={{{{ include "{name}.name" . }}}},app.kubernetes.io/instance={{{{ .Release.Name }}}}" -o jsonpath="{{{{.items[0].metadata.name}}}}")
  kubectl --namespace {{{{ .Release.Namespace }}}} port-forward $POD_NAME 8080:{{{{ .Values.service.port }}}}
  echo "Visit http://127.0.0.1:8080"
{{{{- end }}}}
'''
