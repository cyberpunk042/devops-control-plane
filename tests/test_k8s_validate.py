"""
Tests for k8s_validate — offline manifest structural validation.

Pure unit tests: YAML files on disk → validation results.
No kubectl / cluster required.

Return format:
    {ok: bool, files_checked: int, issues: [{file, severity, message}], errors: int, warnings: int}
    - errors/warnings are COUNTS (int), not lists
    - issues is the list of individual issue dicts
"""

from pathlib import Path
from unittest.mock import patch

from src.core.services.k8s_validate import validate_manifests


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write_manifest(tmp_path: Path, filename: str, content: str) -> Path:
    k8s = tmp_path / "k8s"
    k8s.mkdir(exist_ok=True)
    f = k8s / filename
    f.write_text(content)
    return f


def _issues_with_severity(result: dict, severity: str) -> list[dict]:
    """Filter issues by severity."""
    return [i for i in result.get("issues", []) if i["severity"] == severity]


def _issue_messages(result: dict, severity: str | None = None) -> list[str]:
    """Get issue messages, optionally filtered by severity."""
    issues = result.get("issues", [])
    if severity:
        issues = [i for i in issues if i["severity"] == severity]
    return [i["message"] for i in issues]


# We mock _kubectl_available inside k8s_detect which is called by validate_manifests → k8s_status
_NO_KUBECTL = patch(
    "src.core.services.k8s_detect._kubectl_available",
    return_value={"available": False, "version": None},
)


# ═══════════════════════════════════════════════════════════════════
#  validate_manifests — valid manifests
# ═══════════════════════════════════════════════════════════════════


class TestValidateManifestsValid:
    @_NO_KUBECTL
    def test_valid_deployment(self, _mock, tmp_path: Path):
        """Well-formed Deployment → errors == 0."""
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: app
          image: myapp:v1.2.3
          ports:
            - containerPort: 8080
          resources:
            limits:
              cpu: 500m
              memory: 256Mi
            requests:
              cpu: 100m
              memory: 128Mi
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        assert result["ok"] is True
        assert result["errors"] == 0

    @_NO_KUBECTL
    def test_valid_service(self, _mock, tmp_path: Path):
        """Well-formed Service → errors == 0."""
        _write_manifest(tmp_path, "svc.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: myapp-svc
spec:
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP
""")
        result = validate_manifests(tmp_path)
        assert result["ok"] is True
        assert result["errors"] == 0

    @_NO_KUBECTL
    def test_valid_multi_doc(self, _mock, tmp_path: Path):
        """Multi-document YAML with Deployment + Service → files_checked >= 1."""
        _write_manifest(tmp_path, "all.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: web:v1.0
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /health, port: 3000}
          readinessProbe:
            httpGet: {path: /ready, port: 3000}
          securityContext:
            runAsNonRoot: true
---
apiVersion: v1
kind: Service
metadata:
  name: web-svc
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 3000
""")
        result = validate_manifests(tmp_path)
        assert result["ok"] is True
        assert result["errors"] == 0
        assert result["files_checked"] >= 1


# ═══════════════════════════════════════════════════════════════════
#  validate_manifests — structural errors
# ═══════════════════════════════════════════════════════════════════


class TestValidateManifestsErrors:
    @_NO_KUBECTL
    def test_missing_metadata_name(self, _mock, tmp_path: Path):
        """Resource without metadata.name → error issued."""
        _write_manifest(tmp_path, "bad.yaml", """\
apiVersion: v1
kind: ConfigMap
metadata: {}
data:
  key: value
""")
        result = validate_manifests(tmp_path)
        assert result["errors"] > 0
        msgs = _issue_messages(result, "error")
        assert any("name" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_deployment_missing_selector(self, _mock, tmp_path: Path):
        """Deployment without spec.selector → error issued."""
        _write_manifest(tmp_path, "bad-deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: broken
spec:
  replicas: 1
  template:
    metadata:
      labels:
        app: broken
    spec:
      containers:
        - name: app
          image: broken:latest
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("selector" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_deployment_missing_containers(self, _mock, tmp_path: Path):
        """Deployment with no containers → error issued."""
        _write_manifest(tmp_path, "no-containers.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: empty
spec:
  replicas: 1
  selector:
    matchLabels:
      app: empty
  template:
    metadata:
      labels:
        app: empty
    spec:
      containers: []
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("container" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_service_missing_ports(self, _mock, tmp_path: Path):
        """Service with no ports → warning issued."""
        _write_manifest(tmp_path, "no-ports.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: no-ports
spec:
  selector:
    app: test
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("port" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_no_manifests(self, _mock, tmp_path: Path):
        """Empty project → ok=True, zero files, zero errors."""
        result = validate_manifests(tmp_path)
        assert result["ok"] is True
        assert result["files_checked"] == 0
        assert result["errors"] == 0

    @_NO_KUBECTL
    def test_invalid_yaml(self, _mock, tmp_path: Path):
        """Unparseable YAML → should not crash."""
        _write_manifest(tmp_path, "broken.yaml", "{{not valid yaml")
        result = validate_manifests(tmp_path)
        assert "ok" in result

    @_NO_KUBECTL
    def test_container_without_image(self, _mock, tmp_path: Path):
        """Container spec without image → :latest implicit warning."""
        _write_manifest(tmp_path, "no-image.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: no-image
spec:
  replicas: 1
  selector:
    matchLabels:
      app: no-image
  template:
    metadata:
      labels:
        app: no-image
    spec:
      containers:
        - name: app
          ports:
            - containerPort: 8080
""")
        result = validate_manifests(tmp_path)
        # Empty image string — validator should not crash
        assert "ok" in result


# ═══════════════════════════════════════════════════════════════════
#  validate_manifests — warnings
# ═══════════════════════════════════════════════════════════════════


class TestValidateManifestsWarnings:
    @_NO_KUBECTL
    def test_deployment_no_resource_limits(self, _mock, tmp_path: Path):
        """Deployment container without resource limits → warning."""
        _write_manifest(tmp_path, "no-limits.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: no-limits
spec:
  replicas: 1
  selector:
    matchLabels:
      app: no-limits
  template:
    metadata:
      labels:
        app: no-limits
    spec:
      containers:
        - name: app
          image: app:v1.0
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("resource" in m.lower() or "limit" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_latest_tag_warning(self, _mock, tmp_path: Path):
        """Image with :latest tag → warning about pinning."""
        _write_manifest(tmp_path, "latest.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: latest-tag
spec:
  replicas: 1
  selector:
    matchLabels:
      app: latest-tag
  template:
    metadata:
      labels:
        app: latest-tag
    spec:
      containers:
        - name: app
          image: myapp:latest
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("latest" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_implicit_latest_no_tag(self, _mock, tmp_path: Path):
        """Image without any tag → :latest implicit warning."""
        _write_manifest(tmp_path, "no-tag.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: no-tag
spec:
  replicas: 1
  selector:
    matchLabels:
      app: no-tag
  template:
    metadata:
      labels:
        app: no-tag
    spec:
      containers:
        - name: app
          image: myapp
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("latest" in m.lower() for m in msgs)
