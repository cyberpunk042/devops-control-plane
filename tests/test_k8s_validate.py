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
import shutil

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


# ═══════════════════════════════════════════════════════════════════
#  0.2.3a — General (all kinds) — gap tests
# ═══════════════════════════════════════════════════════════════════


class TestValidateGeneral:
    """Tests for general checks that apply to all resource kinds."""

    @_NO_KUBECTL
    def test_unusual_api_version(self, _mock, tmp_path: Path):
        """0.2.3a: Unusual apiVersion (not in _K8S_API_VERSIONS) → warning."""
        _write_manifest(tmp_path, "unusual-api.yaml", """\
apiVersion: custom.example.com/v1beta99
kind: Deployment
metadata:
  name: unusual-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: unusual
  template:
    metadata:
      labels:
        app: unusual
    spec:
      containers:
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /health, port: 8080}
          readinessProbe:
            httpGet: {path: /ready, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("apiversion" in m.lower() or "unusual" in m.lower() for m in msgs), \
            f"Expected unusual apiVersion warning, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3a — Deployment-specific — gap tests
# ═══════════════════════════════════════════════════════════════════


class TestValidateDeploymentGaps:
    """Tests for Deployment checks not covered by existing tests."""

    @_NO_KUBECTL
    def test_missing_replicas(self, _mock, tmp_path: Path):
        """0.2.3a: Deployment missing replicas → warning (defaults to 1)."""
        _write_manifest(tmp_path, "no-replicas.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: no-replicas
spec:
  selector:
    matchLabels:
      app: no-replicas
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: no-replicas
    spec:
      containers:
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("replica" in m.lower() for m in msgs), \
            f"Expected replica warning, got: {msgs}"

    @_NO_KUBECTL
    def test_missing_strategy(self, _mock, tmp_path: Path):
        """0.2.3a: Deployment missing strategy → info (defaults to RollingUpdate)."""
        _write_manifest(tmp_path, "no-strategy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: no-strategy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: no-strategy
  template:
    metadata:
      labels:
        app: no-strategy
    spec:
      containers:
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("strategy" in m.lower() or "rollingupdate" in m.lower() for m in msgs), \
            f"Expected strategy info, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3a — Service-specific — gap tests
# ═══════════════════════════════════════════════════════════════════


class TestValidateServiceGaps:
    """Tests for Service checks not covered by existing tests."""

    @_NO_KUBECTL
    def test_no_selector(self, _mock, tmp_path: Path):
        """0.2.3a: Service without selector → warning."""
        _write_manifest(tmp_path, "no-selector.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: no-selector
spec:
  ports:
    - port: 80
      targetPort: 8080
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("selector" in m.lower() for m in msgs), \
            f"Expected selector warning, got: {msgs}"

    @_NO_KUBECTL
    def test_multi_port_unnamed(self, _mock, tmp_path: Path):
        """0.2.3a: Multi-port Service with unnamed ports → warning."""
        _write_manifest(tmp_path, "unnamed-ports.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: multi-port
spec:
  selector:
    app: test
  ports:
    - port: 80
      targetPort: 8080
    - port: 443
      targetPort: 8443
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("name" in m.lower() and "port" in m.lower() for m in msgs), \
            f"Expected unnamed port warning, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3a — Pod spec — gap tests
# ═══════════════════════════════════════════════════════════════════


class TestValidatePodSpecGaps:
    """Tests for pod spec checks not covered by existing tests."""

    def _deploy_with_container(self, tmp_path: Path, name: str, container_yaml: str):
        """Helper: Deployment with a single container block."""
        _write_manifest(tmp_path, f"{name}.yaml", f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
{container_yaml}
""")

    @_NO_KUBECTL
    def test_limits_without_requests(self, _mock, tmp_path: Path):
        """0.2.3a: resources.limits without requests → warning."""
        self._deploy_with_container(tmp_path, "limits-only", """\
        - name: app
          image: app:v1
          resources:
            limits:
              cpu: 500m
              memory: 256Mi
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("request" in m.lower() for m in msgs), \
            f"Expected requests warning, got: {msgs}"

    @_NO_KUBECTL
    def test_requests_without_limits(self, _mock, tmp_path: Path):
        """0.2.3a: resources.requests without limits → warning."""
        self._deploy_with_container(tmp_path, "requests-only", """\
        - name: app
          image: app:v1
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("limit" in m.lower() for m in msgs), \
            f"Expected limits warning, got: {msgs}"

    @_NO_KUBECTL
    def test_no_liveness_probe(self, _mock, tmp_path: Path):
        """0.2.3a: No livenessProbe → info."""
        self._deploy_with_container(tmp_path, "no-liveness", """\
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("livenessprobe" in m.lower() or "liveness" in m.lower() for m in msgs), \
            f"Expected livenessProbe info, got: {msgs}"

    @_NO_KUBECTL
    def test_no_readiness_probe(self, _mock, tmp_path: Path):
        """0.2.3a: No readinessProbe → info."""
        self._deploy_with_container(tmp_path, "no-readiness", """\
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          securityContext:
            runAsNonRoot: true""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("readinessprobe" in m.lower() or "readiness" in m.lower() for m in msgs), \
            f"Expected readinessProbe info, got: {msgs}"

    @_NO_KUBECTL
    def test_no_security_context(self, _mock, tmp_path: Path):
        """0.2.3a: No securityContext → info."""
        self._deploy_with_container(tmp_path, "no-sec-ctx", """\
        - name: app
          image: app:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("securitycontext" in m.lower() or "security" in m.lower() for m in msgs), \
            f"Expected securityContext info, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3a — Kind-specific validators — StatefulSet, Job, CronJob,
#           DaemonSet, Ingress, HPA
#  Tests written FIRST (TDD red) — backend validators don't exist yet
# ═══════════════════════════════════════════════════════════════════


class TestValidateStatefulSet:
    """0.2.3a: StatefulSet-specific structural validation."""

    @_NO_KUBECTL
    def test_missing_service_name(self, _mock, tmp_path: Path):
        """StatefulSet missing serviceName → error."""
        _write_manifest(tmp_path, "sts-no-svc.yaml", """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  replicas: 3
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: db
          image: postgres:15
          resources:
            limits: {cpu: 1, memory: 1Gi}
            requests: {cpu: 500m, memory: 512Mi}
          livenessProbe:
            tcpSocket: {port: 5432}
          readinessProbe:
            tcpSocket: {port: 5432}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("servicename" in m.lower() or "service_name" in m.lower() for m in msgs), \
            f"Expected serviceName error, got: {msgs}"

    @_NO_KUBECTL
    def test_empty_service_name(self, _mock, tmp_path: Path):
        """StatefulSet with serviceName as empty string → error."""
        _write_manifest(tmp_path, "sts-empty-svc.yaml", """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: ""
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: db
          image: postgres:15
          resources:
            limits: {cpu: 1, memory: 1Gi}
            requests: {cpu: 500m, memory: 512Mi}
          livenessProbe:
            tcpSocket: {port: 5432}
          readinessProbe:
            tcpSocket: {port: 5432}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("servicename" in m.lower() or "service_name" in m.lower() for m in msgs), \
            f"Expected serviceName error, got: {msgs}"


class TestValidateJob:
    """0.2.3a: Job-specific structural validation."""

    @_NO_KUBECTL
    def test_negative_backoff_limit(self, _mock, tmp_path: Path):
        """Job with negative backoffLimit → error."""
        _write_manifest(tmp_path, "job-bad-backoff.yaml", """\
apiVersion: batch/v1
kind: Job
metadata:
  name: bad-job
spec:
  backoffLimit: -1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: worker
          image: worker:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("backofflimit" in m.lower() or "backoff" in m.lower() for m in msgs), \
            f"Expected backoffLimit error, got: {msgs}"

    @_NO_KUBECTL
    def test_parallelism_gt_completions(self, _mock, tmp_path: Path):
        """Job with parallelism > completions → warning."""
        _write_manifest(tmp_path, "job-par-gt-comp.yaml", """\
apiVersion: batch/v1
kind: Job
metadata:
  name: oversized-job
spec:
  completions: 3
  parallelism: 10
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: worker
          image: worker:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("parallelism" in m.lower() or "completion" in m.lower() for m in msgs), \
            f"Expected parallelism warning, got: {msgs}"


class TestValidateCronJob:
    """0.2.3a: CronJob-specific structural validation."""

    @_NO_KUBECTL
    def test_missing_schedule(self, _mock, tmp_path: Path):
        """CronJob missing schedule → error."""
        _write_manifest(tmp_path, "cron-no-sched.yaml", """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: no-schedule
spec:
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: cron
              image: cron:v1
              resources:
                limits: {cpu: 500m, memory: 256Mi}
                requests: {cpu: 100m, memory: 128Mi}
              securityContext:
                runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("schedule" in m.lower() for m in msgs), \
            f"Expected schedule error, got: {msgs}"

    @_NO_KUBECTL
    def test_invalid_cron_expression(self, _mock, tmp_path: Path):
        """CronJob with invalid cron schedule → error."""
        _write_manifest(tmp_path, "cron-bad-sched.yaml", """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: bad-cron
spec:
  schedule: "not a cron"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: cron
              image: cron:v1
              resources:
                limits: {cpu: 500m, memory: 256Mi}
                requests: {cpu: 100m, memory: 128Mi}
              securityContext:
                runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("schedule" in m.lower() or "cron" in m.lower() for m in msgs), \
            f"Expected cron schedule error, got: {msgs}"

    @_NO_KUBECTL
    def test_invalid_concurrency_policy(self, _mock, tmp_path: Path):
        """CronJob with invalid concurrencyPolicy → warning."""
        _write_manifest(tmp_path, "cron-bad-policy.yaml", """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: bad-policy
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: Yolo
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: cron
              image: cron:v1
              resources:
                limits: {cpu: 500m, memory: 256Mi}
                requests: {cpu: 100m, memory: 128Mi}
              securityContext:
                runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("concurrency" in m.lower() for m in msgs), \
            f"Expected concurrencyPolicy warning, got: {msgs}"


class TestValidateDaemonSet:
    """0.2.3a: DaemonSet-specific structural validation."""

    @_NO_KUBECTL
    def test_has_replicas(self, _mock, tmp_path: Path):
        """DaemonSet with replicas field → warning (DaemonSet ignores it)."""
        _write_manifest(tmp_path, "ds-replicas.yaml", """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: node-agent
  template:
    metadata:
      labels:
        app: node-agent
    spec:
      containers:
        - name: agent
          image: agent:v2
          resources:
            limits: {cpu: 100m, memory: 64Mi}
            requests: {cpu: 50m, memory: 32Mi}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("replica" in m.lower() and ("daemonset" in m.lower() or "node-agent" in m.lower()) for m in msgs), \
            f"Expected DaemonSet replicas warning, got: {msgs}"


class TestValidateIngress:
    """0.2.3a: Ingress-specific structural validation."""

    @_NO_KUBECTL
    def test_missing_ingress_class(self, _mock, tmp_path: Path):
        """Ingress missing ingressClassName → warning."""
        _write_manifest(tmp_path, "ingress-no-class.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
spec:
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("ingressclass" in m.lower() or "ingress" in m.lower() for m in msgs), \
            f"Expected ingressClassName warning, got: {msgs}"

    @_NO_KUBECTL
    def test_path_without_path_type(self, _mock, tmp_path: Path):
        """Ingress rule path without pathType → error (required K8s 1.22+)."""
        _write_manifest(tmp_path, "ingress-no-pathtype.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            backend:
              service:
                name: web
                port:
                  number: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("pathtype" in m.lower() or "path_type" in m.lower() for m in msgs), \
            f"Expected pathType error, got: {msgs}"


class TestValidateHPA:
    """0.2.3a: HPA-specific structural validation."""

    @_NO_KUBECTL
    def test_min_gte_max(self, _mock, tmp_path: Path):
        """HPA with minReplicas >= maxReplicas → error."""
        _write_manifest(tmp_path, "hpa-bad-range.yaml", """\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: bad-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web
  minReplicas: 10
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("minreplica" in m.lower() or "maxreplica" in m.lower() or "replica" in m.lower() for m in msgs), \
            f"Expected HPA replica range error, got: {msgs}"

    @_NO_KUBECTL
    def test_non_scalable_target(self, _mock, tmp_path: Path):
        """HPA targeting non-scalable kind → error."""
        _write_manifest(tmp_path, "hpa-bad-target.yaml", """\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: bad-target
spec:
  scaleTargetRef:
    apiVersion: v1
    kind: ConfigMap
    name: settings
  minReplicas: 1
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("scalable" in m.lower() or "target" in m.lower() or "configmap" in m.lower() for m in msgs), \
            f"Expected non-scalable target error, got: {msgs}"

    @_NO_KUBECTL
    def test_no_metrics(self, _mock, tmp_path: Path):
        """HPA without metrics section → warning."""
        _write_manifest(tmp_path, "hpa-no-metrics.yaml", """\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: no-metrics
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web
  minReplicas: 1
  maxReplicas: 5
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("metric" in m.lower() for m in msgs), \
            f"Expected metrics warning, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3b — Layer 2 — Cross-resource consistency
#  Tests written FIRST (TDD red) — _validate_cross_resource doesn't
#  exist yet.
# ═══════════════════════════════════════════════════════════════════


class TestCrossResourceServiceSelector:
    """Service → Deployment selector alignment."""

    @_NO_KUBECTL
    def test_service_selector_matches_deployment(self, _mock, tmp_path: Path):
        """Service whose selector matches a Deployment's pod labels → no warning."""
        _write_manifest(tmp_path, "matched.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
---
apiVersion: v1
kind: Service
metadata:
  name: api-svc
spec:
  selector:
    app: api
  ports:
    - port: 80
      targetPort: 8080
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert not any("routes to nothing" in m.lower() for m in msgs)

    @_NO_KUBECTL
    def test_service_selector_no_match(self, _mock, tmp_path: Path):
        """Service whose selector matches NO Deployment → warning."""
        _write_manifest(tmp_path, "orphan-svc.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
---
apiVersion: v1
kind: Service
metadata:
  name: wrong-svc
spec:
  selector:
    app: totally-different
  ports:
    - port: 80
      targetPort: 8080
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("routes to nothing" in m.lower() for m in msgs), \
            f"Expected 'routes to nothing' warning, got: {msgs}"


class TestCrossResourceIngressBackend:
    """Ingress → Service backend alignment."""

    @_NO_KUBECTL
    def test_ingress_backend_not_found(self, _mock, tmp_path: Path):
        """Ingress references a Service that doesn't exist → warning."""
        _write_manifest(tmp_path, "ingress-orphan.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nonexistent-svc
                port:
                  number: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("backend" in m.lower() and "not found" in m.lower() for m in msgs), \
            f"Expected Ingress backend not found warning, got: {msgs}"

    @_NO_KUBECTL
    def test_ingress_backend_port_mismatch(self, _mock, tmp_path: Path):
        """Ingress port doesn't match Service port → warning."""
        _write_manifest(tmp_path, "ingress-port-mismatch.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: web-svc
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-svc
                port:
                  number: 9999
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("port" in m.lower() and "mismatch" in m.lower() for m in msgs), \
            f"Expected port mismatch warning, got: {msgs}"


class TestCrossResourceHPA:
    """HPA → target reference alignment."""

    @_NO_KUBECTL
    def test_hpa_target_not_found(self, _mock, tmp_path: Path):
        """HPA targets a Deployment that doesn't exist → warning."""
        _write_manifest(tmp_path, "hpa-orphan.yaml", """\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: web-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nonexistent-deploy
  minReplicas: 1
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("hpa" in m.lower() and "not found" in m.lower() for m in msgs), \
            f"Expected HPA target not found warning, got: {msgs}"

    @_NO_KUBECTL
    def test_hpa_targets_daemonset(self, _mock, tmp_path: Path):
        """HPA targeting a DaemonSet → error."""
        _write_manifest(tmp_path, "hpa-ds.yaml", """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-agent
spec:
  selector:
    matchLabels:
      app: node-agent
  template:
    metadata:
      labels:
        app: node-agent
    spec:
      containers:
        - name: agent
          image: agent:v2
          resources:
            limits: {cpu: 100m, memory: 64Mi}
            requests: {cpu: 50m, memory: 32Mi}
          securityContext:
            runAsNonRoot: true
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: DaemonSet
    name: node-agent
  minReplicas: 1
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("daemonset" in m.lower() and "autoscal" in m.lower() for m in msgs), \
            f"Expected DaemonSet autoscale error, got: {msgs}"


class TestCrossResourceEnvRefs:
    """Env var → Secret/ConfigMap existence."""

    @_NO_KUBECTL
    def test_secret_ref_not_defined(self, _mock, tmp_path: Path):
        """Container references Secret that doesn't exist in manifests → warning."""
        _write_manifest(tmp_path, "secret-ref.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-creds
                  key: password
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("secret" in m.lower() and "not defined" in m.lower() for m in msgs), \
            f"Expected Secret not defined warning, got: {msgs}"

    @_NO_KUBECTL
    def test_configmap_ref_not_defined(self, _mock, tmp_path: Path):
        """Container references ConfigMap that doesn't exist in manifests → warning."""
        _write_manifest(tmp_path, "cm-ref.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          env:
            - name: LOG_LEVEL
              valueFrom:
                configMapKeyRef:
                  name: app-config
                  key: log_level
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("configmap" in m.lower() and "not defined" in m.lower() for m in msgs), \
            f"Expected ConfigMap not defined warning, got: {msgs}"

    @_NO_KUBECTL
    def test_secret_ref_exists(self, _mock, tmp_path: Path):
        """Container references Secret that IS defined → no warning."""
        _write_manifest(tmp_path, "secret-ok.yaml", """\
apiVersion: v1
kind: Secret
metadata:
  name: db-creds
type: Opaque
data:
  password: cGFzc3dvcmQ=
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-creds
                  key: password
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert not any("secret" in m.lower() and "not defined" in m.lower() for m in msgs)


class TestCrossResourcePortAlignment:
    """containerPort ↔ Service targetPort."""

    @_NO_KUBECTL
    def test_port_mismatch(self, _mock, tmp_path: Path):
        """Service targetPort doesn't match container port → warning."""
        _write_manifest(tmp_path, "port-mismatch.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          ports:
            - containerPort: 3000
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 3000}
          readinessProbe:
            httpGet: {path: /r, port: 3000}
          securityContext:
            runAsNonRoot: true
---
apiVersion: v1
kind: Service
metadata:
  name: api-svc
spec:
  selector:
    app: api
  ports:
    - port: 80
      targetPort: 8080
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("port" in m.lower() and "mismatch" in m.lower() for m in msgs), \
            f"Expected port mismatch warning, got: {msgs}"


class TestCrossResourceStatefulSetService:
    """StatefulSet ↔ headless Service."""

    @_NO_KUBECTL
    def test_statefulset_no_headless_service(self, _mock, tmp_path: Path):
        """StatefulSet serviceName references a non-headless Service → error."""
        _write_manifest(tmp_path, "sts-not-headless.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: db-svc
spec:
  selector:
    app: db
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: db-svc
  replicas: 3
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: db
          image: postgres:15
          ports:
            - containerPort: 5432
          resources:
            limits: {cpu: 1, memory: 1Gi}
            requests: {cpu: 500m, memory: 512Mi}
          livenessProbe:
            tcpSocket: {port: 5432}
          readinessProbe:
            tcpSocket: {port: 5432}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("headless" in m.lower() for m in msgs), \
            f"Expected headless Service error, got: {msgs}"

    @_NO_KUBECTL
    def test_statefulset_headless_service_ok(self, _mock, tmp_path: Path):
        """StatefulSet serviceName references a headless Service → no error."""
        _write_manifest(tmp_path, "sts-headless-ok.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: db-svc
spec:
  clusterIP: None
  selector:
    app: db
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: db-svc
  replicas: 3
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: db
          image: postgres:15
          ports:
            - containerPort: 5432
          resources:
            limits: {cpu: 1, memory: 1Gi}
            requests: {cpu: 500m, memory: 512Mi}
          livenessProbe:
            tcpSocket: {port: 5432}
          readinessProbe:
            tcpSocket: {port: 5432}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert not any("headless" in m.lower() for m in msgs)


class TestCrossResourceServiceAccount:
    """ServiceAccount reference validation."""

    @_NO_KUBECTL
    def test_service_account_not_defined(self, _mock, tmp_path: Path):
        """Pod spec references SA not defined in manifests → info."""
        _write_manifest(tmp_path, "sa-ref.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      serviceAccountName: deployer
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("serviceaccount" in m.lower() and "not defined" in m.lower() for m in msgs), \
            f"Expected ServiceAccount not defined info, got: {msgs}"


class TestCrossResourceNamespace:
    """Namespace consistency."""

    @_NO_KUBECTL
    def test_mixed_namespaces_warning(self, _mock, tmp_path: Path):
        """Resources in different namespaces without Namespace resources → warning."""
        _write_manifest(tmp_path, "mixed-ns.yaml", """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-a
  namespace: ns-alpha
data:
  key: a
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-b
  namespace: ns-beta
data:
  key: b
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("namespace" in m.lower() for m in msgs), \
            f"Expected namespace warning, got: {msgs}"

    @_NO_KUBECTL
    def test_single_namespace_no_warning(self, _mock, tmp_path: Path):
        """All resources in the same namespace → no namespace warning."""
        _write_manifest(tmp_path, "same-ns.yaml", """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-a
  namespace: production
data:
  key: a
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-b
  namespace: production
data:
  key: b
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert not any("mixed namespace" in m.lower() for m in msgs)


class TestCrossResourceLabelOrphans:
    """Label orphan detection."""

    @_NO_KUBECTL
    def test_deployment_labels_not_selected(self, _mock, tmp_path: Path):
        """Deployment with pod labels that no Service selects → info."""
        _write_manifest(tmp_path, "orphan-labels.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: background-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: worker
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: worker
    spec:
      containers:
        - name: worker
          image: worker:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("unreachable" in m.lower() or "no service" in m.lower() for m in msgs), \
            f"Expected label orphan info, got: {msgs}"


class TestCrossResourcePVC:
    """PVC reference and access mode validation."""

    @_NO_KUBECTL
    def test_pvc_not_defined(self, _mock, tmp_path: Path):
        """Pod references PVC that doesn't exist in manifests → warning."""
        _write_manifest(tmp_path, "pvc-missing.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: my-data-pvc
      containers:
        - name: api
          image: api:v1
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("pvc" in m.lower() and "not defined" in m.lower() for m in msgs), \
            f"Expected PVC not defined warning, got: {msgs}"

    @_NO_KUBECTL
    def test_rwo_pvc_multi_replica(self, _mock, tmp_path: Path):
        """ReadWriteOnce PVC used by Deployment with replicas > 1 → error."""
        _write_manifest(tmp_path, "rwo-multi.yaml", """\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-data-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: my-data-pvc
      containers:
        - name: api
          image: api:v1
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("rwo" in m.lower() or "readwriteonce" in m.lower() for m in msgs), \
            f"Expected RWO multi-replica error, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3c — Layer 3 — Environment-aware validation
#  Tests written FIRST (TDD red) — _validate_env_aware doesn't
#  exist yet.
# ═══════════════════════════════════════════════════════════════════


def _write_project_yml(tmp_path: Path, envs: list[str]) -> Path:
    """Create a minimal project.yml with given environments."""
    import yaml
    data = {
        "name": "test-project",
        "version": 1,
        "environments": [{"name": e} for e in envs],
        "modules": [],
    }
    f = tmp_path / "project.yml"
    f.write_text(yaml.dump(data))
    return f


def _write_kustomize_base(tmp_path: Path, resources: list[str] | None = None) -> Path:
    """Create a kustomize base dir with kustomization.yaml."""
    import yaml
    base = tmp_path / "k8s" / "base"
    base.mkdir(parents=True, exist_ok=True)
    kust = {"resources": resources or ["deployment.yaml"]}
    (base / "kustomization.yaml").write_text(yaml.dump(kust))
    return base


def _write_kustomize_overlay(
    tmp_path: Path,
    name: str,
    namespace: str | None = None,
    resources: list[str] | None = None,
    patches: list[dict] | None = None,
) -> Path:
    """Create a kustomize overlay dir."""
    import yaml
    overlay = tmp_path / "k8s" / "overlays" / name
    overlay.mkdir(parents=True, exist_ok=True)
    kust: dict = {}
    if resources:
        kust["resources"] = resources
    else:
        kust["resources"] = ["../../base"]
    if namespace:
        kust["namespace"] = namespace
    if patches:
        kust["patches"] = patches
    (overlay / "kustomization.yaml").write_text(yaml.dump(kust))
    return overlay


class TestEnvAwareOverlayCompleteness:
    """Environment completeness — all declared envs should have overlays."""

    @_NO_KUBECTL
    def test_missing_overlay_for_env(self, _mock, tmp_path: Path):
        """project.yml declares dev+prod but only dev overlay exists → warning."""
        _write_project_yml(tmp_path, ["dev", "prod"])
        _write_kustomize_base(tmp_path)
        # Write a base deployment so k8s detection works
        _write_manifest(tmp_path, "base/deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        # Only create dev overlay, not prod
        _write_kustomize_overlay(tmp_path, "dev")
        # Also create a root kustomization so detection finds it
        import yaml
        (tmp_path / "k8s" / "kustomization.yaml").write_text(
            yaml.dump({"resources": ["base/deployment.yaml"]})
        )

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("prod" in m.lower() and "overlay" in m.lower() for m in msgs), \
            f"Expected missing overlay warning for prod, got: {msgs}"


class TestEnvAwareHelmValues:
    """Helm values completeness."""

    @_NO_KUBECTL
    def test_missing_helm_values_for_env(self, _mock, tmp_path: Path):
        """project.yml declares dev+prod, values-dev.yaml exists but not values-prod.yaml → warning."""
        _write_project_yml(tmp_path, ["dev", "prod"])
        # Create a Helm chart structure
        chart_dir = tmp_path / "helm"
        chart_dir.mkdir()
        (chart_dir / "Chart.yaml").write_text("name: test\nversion: 0.1.0\n")
        (chart_dir / "values.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-dev.yaml").write_text("replicas: 1\n")
        # No values-prod.yaml
        templates = chart_dir / "templates"
        templates.mkdir()
        _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("prod" in m.lower() and "values" in m.lower() for m in msgs), \
            f"Expected missing values file warning for prod, got: {msgs}"


class TestEnvAwareKustomizeOverlayValidity:
    """Kustomize overlay base resource existence."""

    @_NO_KUBECTL
    def test_overlay_references_missing_base(self, _mock, tmp_path: Path):
        """Overlay references a base resource that doesn't exist on disk → error."""
        _write_project_yml(tmp_path, ["dev"])
        base = _write_kustomize_base(tmp_path, resources=["deployment.yaml"])
        # Write the base deployment
        (base / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        # Overlay references a nonexistent extra resource
        _write_kustomize_overlay(tmp_path, "dev", resources=["../../base", "extra-missing.yaml"])
        import yaml
        (tmp_path / "k8s" / "kustomization.yaml").write_text(
            yaml.dump({"resources": ["base/deployment.yaml"]})
        )

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("missing" in m.lower() and "base" in m.lower() or "not found" in m.lower() for m in msgs), \
            f"Expected overlay missing base error, got: {msgs}"


class TestEnvAwareKustomizePatchTargets:
    """Kustomize patch target existence."""

    @_NO_KUBECTL
    def test_patch_targets_nonexistent_resource(self, _mock, tmp_path: Path):
        """Overlay patch targets a kind/name not in the base → error."""
        _write_project_yml(tmp_path, ["dev"])
        base = _write_kustomize_base(tmp_path, resources=["deployment.yaml"])
        (base / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        _write_kustomize_overlay(tmp_path, "dev", patches=[{
            "target": {
                "kind": "StatefulSet",
                "name": "nonexistent-db",
            },
            "patch": "- op: replace\n  path: /spec/replicas\n  value: 3",
        }])
        import yaml
        (tmp_path / "k8s" / "kustomization.yaml").write_text(
            yaml.dump({"resources": ["base/deployment.yaml"]})
        )

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("patch" in m.lower() and "nonexistent" in m.lower() or "not found" in m.lower() for m in msgs), \
            f"Expected patch target not found error, got: {msgs}"


class TestEnvAwareProdReplicaSanity:
    """Prod replica sanity."""

    @_NO_KUBECTL
    def test_single_replica_prod_no_hpa(self, _mock, tmp_path: Path):
        """Deployment with replicas: 1 in prod, no HPA → warning."""
        _write_project_yml(tmp_path, ["dev", "prod"])
        # Write a prod overlay that sets replicas: 1
        base = tmp_path / "k8s" / "base"
        base.mkdir(parents=True, exist_ok=True)
        import yaml
        (base / "kustomization.yaml").write_text(yaml.dump({"resources": ["deployment.yaml"]}))
        (base / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: test-project-prod
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        _write_kustomize_overlay(tmp_path, "dev")
        _write_kustomize_overlay(tmp_path, "prod", namespace="test-project-prod")
        (tmp_path / "k8s" / "kustomization.yaml").write_text(
            yaml.dump({"resources": ["base/deployment.yaml"]})
        )

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("prod" in m.lower() and "replica" in m.lower() for m in msgs), \
            f"Expected prod single-replica warning, got: {msgs}"


class TestEnvAwareDevResourceOversizing:
    """Dev resource oversizing."""

    @_NO_KUBECTL
    def test_high_replicas_dev(self, _mock, tmp_path: Path):
        """Dev environment with replicas > 3 → info."""
        _write_project_yml(tmp_path, ["dev", "prod"])
        # Write deployment with replicas: 5
        _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: test-project-dev
spec:
  replicas: 5
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("dev" in m.lower() and "replica" in m.lower() for m in msgs), \
            f"Expected dev high-replica info, got: {msgs}"


class TestEnvAwareNamespaceAlignment:
    """Namespace alignment between project config and kustomize overlay."""

    @_NO_KUBECTL
    def test_namespace_mismatch(self, _mock, tmp_path: Path):
        """Kustomize overlay sets namespace different from project convention → warning."""
        _write_project_yml(tmp_path, ["prod"])
        base = tmp_path / "k8s" / "base"
        base.mkdir(parents=True, exist_ok=True)
        import yaml
        (base / "kustomization.yaml").write_text(yaml.dump({"resources": ["deployment.yaml"]}))
        (base / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")
        # Overlay sets namespace "wrong-namespace" but project convention is "test-project-prod"
        _write_kustomize_overlay(tmp_path, "prod", namespace="wrong-namespace")
        (tmp_path / "k8s" / "kustomization.yaml").write_text(
            yaml.dump({"resources": ["base/deployment.yaml"]})
        )

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("namespace" in m.lower() and ("mismatch" in m.lower() or "alignment" in m.lower()) for m in msgs), \
            f"Expected namespace mismatch warning, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3d — Layer 4 — Cluster-aware validation
#  Tests written FIRST (TDD red) — _validate_cluster_aware doesn't
#  exist yet.
# ═══════════════════════════════════════════════════════════════════


# Shared mock for cluster_status returning a connected Minikube cluster
def _mock_cluster_minikube():
    return {
        "connected": True,
        "context": "minikube",
        "nodes": [{"name": "minikube", "ready": True, "roles": "control-plane", "version": "v1.28.0"}],
        "namespaces": ["default", "kube-system", "kube-public"],
        "cluster_type": {"type": "minikube", "detected_via": "context_name"},
    }


def _mock_cluster_eks():
    return {
        "connected": True,
        "context": "arn:aws:eks:us-east-1:123456:cluster/my-cluster",
        "nodes": [{"name": "ip-10-0-0-1", "ready": True, "roles": "", "version": "v1.28.0"}],
        "namespaces": ["default", "kube-system", "kube-public", "app-prod"],
        "cluster_type": {"type": "eks", "detected_via": "context_name"},
    }


_MOCK_CLUSTER_MINIKUBE = patch(
    "src.core.services.k8s_validate.cluster_status",
    side_effect=lambda: _mock_cluster_minikube(),
)

_MOCK_CLUSTER_EKS = patch(
    "src.core.services.k8s_validate.cluster_status",
    side_effect=lambda: _mock_cluster_eks(),
)


class TestClusterAwareServiceType:
    """Service type ↔ cluster type."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_loadbalancer_on_minikube(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """LoadBalancer Service on Minikube → warning."""
        _write_manifest(tmp_path, "service.yaml", """\
apiVersion: v1
kind: Service
metadata:
  name: web-lb
spec:
  type: LoadBalancer
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("loadbalancer" in m.lower() and "minikube" in m.lower() for m in msgs), \
            f"Expected LoadBalancer-on-minikube warning, got: {msgs}"


class TestClusterAwareIngressController:
    """Ingress ↔ ingress controller presence."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_ingress_no_controller(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """Ingress resource but no ingress-controller detected → warning."""
        _write_manifest(tmp_path, "ingress.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("ingress" in m.lower() and "controller" in m.lower() for m in msgs), \
            f"Expected no-ingress-controller warning, got: {msgs}"


class TestClusterAwareCertManager:
    """cert-manager annotations ↔ cert-manager presence."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_certmanager_annotations_no_certmanager(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """cert-manager annotations but cert-manager not detected → warning."""
        _write_manifest(tmp_path, "ingress.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
  tls:
    - hosts:
        - example.com
      secretName: web-tls
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("cert-manager" in m.lower() for m in msgs), \
            f"Expected cert-manager warning, got: {msgs}"


class TestClusterAwarePrometheusCRDs:
    """Prometheus CRDs ↔ Prometheus presence."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_servicemonitor_no_prometheus(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """ServiceMonitor resource but Prometheus not detected → warning."""
        _write_manifest(tmp_path, "monitor.yaml", """\
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-monitor
spec:
  selector:
    matchLabels:
      app: api
  endpoints:
    - port: metrics
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("prometheus" in m.lower() for m in msgs), \
            f"Expected Prometheus-not-detected warning, got: {msgs}"


class TestClusterAwareToolStrategy:
    """Tool ↔ strategy mismatch."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_helm_strategy_no_helm(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """Helm chart detected but helm binary not available → error."""
        # Create a Helm chart so deployment_strategy = "helm"
        chart_dir = tmp_path / "helm"
        chart_dir.mkdir()
        (chart_dir / "Chart.yaml").write_text("name: test\nversion: 0.1.0\n")
        (chart_dir / "values.yaml").write_text("replicas: 1\n")
        templates = chart_dir / "templates"
        templates.mkdir()
        _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

        # Force helm to be "not installed" regardless of dev machine
        _real_which = shutil.which
        with patch("shutil.which", side_effect=lambda name: None if name == "helm" else _real_which(name)):
            result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("helm" in m.lower() and ("not installed" in m.lower() or "not available" in m.lower()) for m in msgs), \
            f"Expected helm-not-available error, got: {msgs}"

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_kustomize_strategy_no_kustomize(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """Kustomize detected but kustomize binary not available → error."""
        import yaml
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "kustomization.yaml").write_text(yaml.dump({"resources": ["deployment.yaml"]}))
        _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

        # Force kustomize to be "not installed" regardless of dev machine
        _real_which = shutil.which
        with patch("shutil.which", side_effect=lambda name: None if name == "kustomize" else _real_which(name)):
            result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("kustomize" in m.lower() and ("not installed" in m.lower() or "not available" in m.lower()) for m in msgs), \
            f"Expected kustomize-not-available error, got: {msgs}"


class TestClusterAwareNamespace:
    """Namespace existence on cluster."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_namespace_not_on_cluster(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """Resource targets namespace not on cluster → info."""
        _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("namespace" in m.lower() and ("not exist" in m.lower() or "does not exist" in m.lower()) for m in msgs), \
            f"Expected namespace-not-on-cluster info, got: {msgs}"


class TestClusterAwareStorageClass:
    """StorageClass existence on cluster."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_storageclass_not_on_cluster(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """PVC references storageClassName not on cluster → warning."""
        _write_manifest(tmp_path, "pvc.yaml", """\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 10Gi
""")

        with patch(
            "src.core.services.k8s_validate.k8s_storage_classes",
            return_value={"ok": True, "storage_classes": [], "default_class": None},
        ):
            result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("storageclass" in m.lower() and "fast-ssd" in m.lower() for m in msgs), \
            f"Expected StorageClass-not-found warning, got: {msgs}"


class TestClusterAwareCRD:
    """CRD availability check."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_MINIKUBE
    def test_custom_crd_kind(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        """Non-standard kind → info about CRD."""
        _write_manifest(tmp_path, "custom.yaml", """\
apiVersion: stable.example.com/v1
kind: CronTab
metadata:
  name: my-crontab
spec:
  cronSpec: "* * * * */5"
  image: my-awesome-cron-image
""")

        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("crd" in m.lower() or "custom resource" in m.lower() for m in msgs), \
            f"Expected CRD info, got: {msgs}"


class TestClusterAwareVersionSkew:
    """kubectl version skew."""

    @_MOCK_CLUSTER_MINIKUBE
    def test_kubectl_version_skew(self, _mock_cluster, tmp_path: Path):
        """Client and server versions differ by >1 minor → warning."""
        # Mock kubectl available with a very different version
        with patch(
            "src.core.services.k8s_detect._kubectl_available",
            return_value={"available": True, "version": "v1.24.0"},
        ), patch(
            "src.core.services.k8s_validate._get_kubectl_server_version",
            return_value="v1.28.0",
        ):
            _write_manifest(tmp_path, "deployment.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
          securityContext:
            runAsNonRoot: true
""")

            result = validate_manifests(tmp_path)
            msgs = _issue_messages(result, "warning")
            assert any("version" in m.lower() and "skew" in m.lower() for m in msgs), \
                f"Expected kubectl version skew warning, got: {msgs}"


# ═══════════════════════════════════════════════════════════════════
#  0.2.3e — Layer 5 — Security & production readiness
# ═══════════════════════════════════════════════════════════════════


# ---------- Container security ----------

class TestSecurityRunAsRoot:
    """runAsUser: 0 → warning."""

    @_NO_KUBECTL
    def test_run_as_root(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsUser: 0
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("root" in m.lower() and "runas" in m.lower() for m in msgs), \
            f"Expected run-as-root warning, got: {msgs}"


class TestSecurityPrivileged:
    """privileged: true → error."""

    @_NO_KUBECTL
    def test_privileged_container(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            privileged: true
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "error")
        assert any("privileged" in m.lower() for m in msgs), \
            f"Expected privileged-container error, got: {msgs}"


class TestSecurityPrivilegeEscalation:
    """allowPrivilegeEscalation: true or missing → warning."""

    @_NO_KUBECTL
    def test_privilege_escalation_allowed(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("privilege escalation" in m.lower() for m in msgs), \
            f"Expected privilege-escalation warning, got: {msgs}"


class TestSecurityCapabilities:
    """missing capabilities.drop: ['ALL'] → info."""

    @_NO_KUBECTL
    def test_capabilities_not_dropped(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("capabilities" in m.lower() and "drop" in m.lower() for m in msgs), \
            f"Expected capabilities-not-dropped info, got: {msgs}"


class TestSecurityReadOnlyRootFS:
    """readOnlyRootFilesystem missing → info."""

    @_NO_KUBECTL
    def test_writable_root_filesystem(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("root filesystem" in m.lower() or "readonlyrootfilesystem" in m.lower() for m in msgs), \
            f"Expected writable-rootfs info, got: {msgs}"


class TestSecurityHostNetwork:
    """hostNetwork: true → warning."""

    @_NO_KUBECTL
    def test_host_network(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      hostNetwork: true
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("host network" in m.lower() for m in msgs), \
            f"Expected host-network warning, got: {msgs}"


class TestSecurityHostPID:
    """hostPID: true → warning."""

    @_NO_KUBECTL
    def test_host_pid(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      hostPID: true
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("host pid" in m.lower() for m in msgs), \
            f"Expected host-PID warning, got: {msgs}"


class TestSecurityHostIPC:
    """hostIPC: true → warning."""

    @_NO_KUBECTL
    def test_host_ipc(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      hostIPC: true
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("host ipc" in m.lower() for m in msgs), \
            f"Expected host-IPC warning, got: {msgs}"


# ---------- Operational safety ----------

class TestOperationalAutoMount:
    """automountServiceAccountToken not false → info."""

    @_NO_KUBECTL
    def test_token_auto_mounted(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("automount" in m.lower() or "token" in m.lower() for m in msgs), \
            f"Expected token-auto-mounted info, got: {msgs}"


class TestOperationalIdenticalProbes:
    """Liveness and readiness probes identical → warning."""

    @_NO_KUBECTL
    def test_identical_probes(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("identical" in m.lower() or "same probe" in m.lower() for m in msgs), \
            f"Expected identical-probes warning, got: {msgs}"


class TestOperationalNoPDB:
    """No PDB for HA deployment (replicas >= 2) → info."""

    @_NO_KUBECTL
    def test_no_pdb_for_ha(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("pdb" in m.lower() or "poddisruptionbudget" in m.lower() for m in msgs), \
            f"Expected no-PDB-for-HA info, got: {msgs}"


class TestOperationalImagePullNever:
    """imagePullPolicy: Never on cloud cluster → warning."""

    @_NO_KUBECTL
    @_MOCK_CLUSTER_EKS
    def test_image_pull_never_on_cloud(self, _mock_cluster, _mock_kubectl, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          imagePullPolicy: Never
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("imagepullpolicy" in m.lower() and "never" in m.lower() for m in msgs), \
            f"Expected imagePullPolicy-Never warning, got: {msgs}"


class TestOperationalNoNetworkPolicy:
    """No NetworkPolicy for namespace with Deployments → info."""

    @_NO_KUBECTL
    def test_no_network_policy(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: app-prod
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: api:v1
          securityContext:
            runAsNonRoot: true
          resources:
            limits: {cpu: 500m, memory: 256Mi}
            requests: {cpu: 100m, memory: 128Mi}
          livenessProbe:
            httpGet: {path: /h, port: 8080}
          readinessProbe:
            httpGet: {path: /r, port: 8080}
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "info")
        assert any("networkpolicy" in m.lower() or "network isolation" in m.lower() for m in msgs), \
            f"Expected no-network-isolation info, got: {msgs}"


# ---------- RBAC ----------

class TestRBACWildcardVerbs:
    """ClusterRole with wildcard verbs → warning."""

    @_NO_KUBECTL
    def test_wildcard_verbs(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "cr.yaml", """\
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: admin-all
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["*"]
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("wildcard" in m.lower() and "verb" in m.lower() for m in msgs), \
            f"Expected wildcard-verbs warning, got: {msgs}"


class TestRBACWildcardResources:
    """ClusterRole with wildcard resources → warning."""

    @_NO_KUBECTL
    def test_wildcard_resources(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "cr.yaml", """\
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: admin-all
rules:
  - apiGroups: [""]
    resources: ["*"]
    verbs: ["get", "list"]
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("wildcard" in m.lower() and "resource" in m.lower() for m in msgs), \
            f"Expected wildcard-resources warning, got: {msgs}"


class TestRBACDefaultSABinding:
    """ClusterRoleBinding binding to default SA → warning."""

    @_NO_KUBECTL
    def test_default_sa_clusterrolebinding(self, _mock, tmp_path: Path):
        _write_manifest(tmp_path, "crb.yaml", """\
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: admin-all
subjects:
  - kind: ServiceAccount
    name: default
    namespace: kube-system
""")
        result = validate_manifests(tmp_path)
        msgs = _issue_messages(result, "warning")
        assert any("default" in m.lower() and "serviceaccount" in m.lower() for m in msgs), \
            f"Expected default-SA-binding warning, got: {msgs}"




# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Cross-domain validation (THE DIFFERENTIATOR)
#  Seam 1: Docker ↔ K8s
# ═══════════════════════════════════════════════════════════════════

# Shared mock builders for Layer 6

def _mock_docker_status(
    *,
    has_dockerfile=False,
    has_compose=False,
    dockerfiles=None,
    dockerfile_details=None,
    compose_services=None,
    compose_service_details=None,
    **extra,
):
    """Build a docker_status return dict for mocking."""
    return {
        "available": False,
        "daemon_running": False,
        "compose_available": False,
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "compose_file": "docker-compose.yml" if has_compose else None,
        "dockerfiles": dockerfiles or [],
        "dockerfile_details": dockerfile_details or [],
        "compose_services": compose_services or [],
        "compose_service_details": compose_service_details or [],
        "services_count": len(compose_services or []),
        "has_dockerignore": False,
        "dockerignore_patterns": [],
        **extra,
    }


def _mock_ci_status(*, has_ci=False, providers=None):
    """Build a ci_status return dict for mocking."""
    return {
        "has_ci": has_ci,
        "providers": providers or [],
        "total_workflows": 0,
    }


def _mock_ci_workflows(*, workflows=None):
    """Build a ci_workflows return dict for mocking."""
    return {"workflows": workflows or []}


def _mock_terraform_status(*, has_terraform=False, providers=None, resources=None, **extra):
    """Build a terraform_status return dict for mocking."""
    return {
        "has_terraform": has_terraform,
        "cli": {"available": False, "version": None},
        "root": None,
        "files": [],
        "providers": providers or [],
        "modules": [],
        "resources": resources or [],
        "resource_count": len(resources or []),
        "backend": None,
        "initialized": False,
        **extra,
    }


# Patch targets for Layer 6
_PATCH_DOCKER = "src.core.services.k8s_validate.docker_status"
_PATCH_CI_STATUS = "src.core.services.k8s_validate.ci_status"
_PATCH_CI_WORKFLOWS = "src.core.services.k8s_validate.ci_workflows"
_PATCH_TERRAFORM = "src.core.services.k8s_validate.terraform_status"


class TestLayer6DockerK8s:
    """Docker ↔ K8s cross-domain checks (9 checks).

    Source of truth: Docker Compose spec, Kubernetes API.
    All issues prefixed with "Docker↔K8s:" for layer disambiguation.
    """

    # ── 1. Image name alignment ─────────────────────────────────
    def test_image_name_alignment_mismatch(self, tmp_path):
        """Compose builds image 'myapp', K8s references 'registry.io/other:v1' → warning.

        Pessimistic: exact 1 warning with Docker↔K8s: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: registry.io/other:v1
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": {"context": ".", "dockerfile": None, "args": None},
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "does not match" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected image alignment warning, got: {issues}"

    def test_image_name_alignment_match(self, tmp_path):
        """Compose image matches K8s image → no warning.

        Pessimistic: zero warnings with Docker↔K8s: image alignment.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "does not match" in i["message"].lower()
        ]
        assert len(issues) == 0, f"Should not warn when images match, got: {issues}"

    # ── 2. Port alignment ───────────────────────────────────────
    def test_port_alignment_mismatch(self, tmp_path):
        """Dockerfile EXPOSE 8080, K8s containerPort 3000 → warning.

        Pessimistic: at least 1 warning with Docker↔K8s: prefix mentioning ports.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
        ports:
        - containerPort: 3000
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [8080],
                "warnings": [],
            }],
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": {"context": ".", "dockerfile": None, "args": None},
                "ports": [{"host": 8080, "container": 8080, "protocol": "tcp"}],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "port" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected port alignment warning, got: {issues}"

    # ── 3. Environment variable coverage ────────────────────────
    def test_env_var_coverage_missing(self, tmp_path):
        """Compose defines env var DB_HOST, K8s has no matching env → info.

        Pessimistic: at least 1 info with Docker↔K8s: prefix mentioning DB_HOST.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [],
                "environment": {"DB_HOST": "localhost", "DB_PORT": "5432"},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "DB_HOST" in i["message"]
        ]
        assert len(issues) >= 1, f"Expected env var coverage info, got: {issues}"

    # ── 4. Volume pattern translation ───────────────────────────
    def test_volume_no_pvc(self, tmp_path):
        """Compose has named volume 'pgdata', K8s has no PVC → info.

        Pessimistic: at least 1 info with Docker↔K8s: prefix mentioning pgdata.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: db
spec:
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
      - name: db
        image: postgres:15
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["db"],
            compose_service_details=[{
                "name": "db",
                "image": "postgres:15",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": ["pgdata:/var/lib/postgresql/data"],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "pgdata" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected volume translation info, got: {issues}"

    # ── 5. Service parity ───────────────────────────────────────
    def test_service_parity_missing(self, tmp_path):
        """Compose defines [api, worker], K8s only has api → info for worker.

        Pessimistic: at least 1 info for 'worker', zero for 'api'.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api", "worker"],
            compose_service_details=[
                {
                    "name": "api",
                    "image": "myapp:latest",
                    "build": None,
                    "ports": [],
                    "environment": {},
                    "volumes": [],
                    "depends_on": [],
                    "healthcheck": None,
                },
                {
                    "name": "worker",
                    "image": "myapp-worker:latest",
                    "build": None,
                    "ports": [],
                    "environment": {},
                    "volumes": [],
                    "depends_on": [],
                    "healthcheck": None,
                },
            ],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        worker_issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "worker" in i["message"].lower() and "no k8s equivalent" in i["message"].lower()
        ]
        assert len(worker_issues) >= 1, f"Expected service parity info for worker, got: {worker_issues}"

        # api IS present, should NOT be flagged
        api_issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "'api'" in i["message"].lower() and "no k8s equivalent" in i["message"].lower()
        ]
        assert len(api_issues) == 0, f"api has K8s Deployment, should not be flagged, got: {api_issues}"

    # ── 6. Health check alignment ───────────────────────────────
    def test_healthcheck_compose_no_probe(self, tmp_path):
        """Compose defines healthcheck, K8s has no matching probe → info.

        Pessimistic: at least 1 info with Docker↔K8s: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "healthcheck" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected healthcheck alignment info, got: {issues}"

    # ── 7. Image pull policy ↔ build locality ───────────────────
    def test_pull_policy_always_with_local_build(self, tmp_path):
        """Compose builds locally, K8s imagePullPolicy: Always on cloud → warning.

        Pessimistic: at least 1 warning with Docker↔K8s: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
        imagePullPolicy: Always
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": {"context": ".", "dockerfile": None, "args": None},
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        # Mock cloud cluster
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()), \
             patch("src.core.services.k8s_validate.cluster_status", return_value={
                 "connected": True,
                 "cluster_type": {"type": "eks"},
                 "server_version": "1.28",
                 "namespaces": [],
             }):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "locally-built" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected pull policy vs local build warning, got: {issues}"

    # ── 8. Image pull secret ↔ private registry ─────────────────
    def test_private_registry_no_pull_secret(self, tmp_path):
        """Image from private registry, no imagePullSecrets → warning.

        Pessimistic: at least 1 warning with Docker↔K8s: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: 123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "private registry" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected private registry warning, got: {issues}"

    def test_private_registry_with_pull_secret(self, tmp_path):
        """Image from private registry WITH imagePullSecrets → no warning.

        Pessimistic: zero warnings with Docker↔K8s: private registry.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      imagePullSecrets:
      - name: ecr-creds
      containers:
      - name: api
        image: 123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔K8s:" in i["message"]
            and "private registry" in i["message"].lower()
        ]
        assert len(issues) == 0, f"Should not warn when imagePullSecrets present, got: {issues}"

    # ── 9. Service name continuity ──────────────────────────────
    def test_service_name_continuity_missing(self, tmp_path):
        """Compose service 'api' exists, K8s has no Service named 'api' → info.

        Pessimistic: at least 1 info with Docker↔K8s: prefix mentioning 'api'.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [{"host": 8080, "container": 8080, "protocol": "tcp"}],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "api" in i["message"].lower() and "not found as k8s service" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected service name continuity info, got: {issues}"

    def test_service_name_continuity_present(self, tmp_path):
        """Compose service 'api' exists, K8s HAS Service named 'api' → no info.

        Pessimistic: zero infos with Docker↔K8s: service name continuity for 'api'.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
---
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 8080
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [{"host": 8080, "container": 8080, "protocol": "tcp"}],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔K8s:" in i["message"]
            and "api" in i["message"].lower() and "not found as k8s service" in i["message"].lower()
        ]
        assert len(issues) == 0, f"Should not warn when K8s Service exists, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 2: Docker ↔ CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestLayer6DockerCI:
    """Docker ↔ CI/CD cross-domain checks (5 checks).

    Source of truth: GitHub Actions workflow schema, Docker build process.
    All issues prefixed with "Docker↔CI:".
    """

    # ── 1. Dockerfile not built in CI ───────────────────────────
    def test_dockerfile_exists_ci_no_build(self, tmp_path):
        """Dockerfile present, CI detected, but no docker build step → info.

        Pessimistic: at least 1 info with Docker↔CI: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [8080],
                "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "test",
                "name": "Test",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "npm test"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔CI:" in i["message"]
            and "build" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected Dockerfile-not-built-in-CI info, got: {issues}"

    # ── 2. CI builds but doesn't push ───────────────────────────
    def test_ci_builds_no_push(self, tmp_path):
        """CI has docker build but no push → warning.

        Pessimistic: at least 1 warning with Docker↔CI: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [],
                "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "build",
                "name": "Build",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "docker build -t myapp ."},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔CI:" in i["message"]
            and "push" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected CI-builds-but-no-push warning, got: {issues}"

    # ── 3. Registry login missing ───────────────────────────────
    def test_ci_push_no_login(self, tmp_path):
        """CI pushes to registry but no login step → warning.

        Pessimistic: at least 1 warning with Docker↔CI: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [],
                "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "build",
                "name": "Build",
                "runs_on": "ubuntu-latest",
                "steps_count": 3,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "docker build -t myapp ."},
                    {"run": "docker push myapp:latest"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔CI:" in i["message"]
            and "authentication" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected registry-login-missing warning, got: {issues}"

    # ── 4. Multi-stage test target unused ───────────────────────
    def test_multistage_unused_in_ci(self, tmp_path):
        """Dockerfile is multi-stage (has test stage), CI doesn't use --target → info.

        Pessimistic: at least 1 info with Docker↔CI: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim", "python:3.12-slim"],
                "stages": ["builder", "test"],
                "stage_count": 3,
                "ports": [],
                "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "build",
                "name": "Build",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "docker build -t myapp ."},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔CI:" in i["message"]
            and "test stage" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected multi-stage test target info, got: {issues}"

    # ── 5. Compose for integration testing ──────────────────────
    def test_compose_not_used_in_ci(self, tmp_path):
        """Compose available, CI doesn't use docker compose → info.

        Pessimistic: at least 1 info with Docker↔CI: prefix.
        """
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api", "db"],
            compose_service_details=[
                {"name": "api", "image": "myapp:latest", "build": None,
                 "ports": [], "environment": {}, "volumes": [],
                 "depends_on": [], "healthcheck": None},
                {"name": "db", "image": "postgres:15", "build": None,
                 "ports": [], "environment": {}, "volumes": [],
                 "depends_on": [], "healthcheck": None},
            ],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "test",
                "name": "Test",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "npm test"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔CI:" in i["message"]
            and "compose" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected compose-not-used-in-CI info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 3: Docker ↔ Terraform
# ═══════════════════════════════════════════════════════════════════


class TestLayer6DockerTerraform:
    """Docker ↔ Terraform cross-domain checks (2 checks)."""

    # ── 1. Registry provisioned ↔ image reference ───────────────
    def test_registry_mismatch(self, tmp_path):
        """Terraform creates ECR, images reference different registry → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: gcr.io/my-project/myapp:v1
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [],
                "warnings": [],
            }],
        )
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[
                {"type": "aws_ecr_repository", "name": "myapp", "file": "ecr.tf"},
            ],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔Terraform:" in i["message"]
            and "registry" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected Terraform registry mismatch warning, got: {issues}"

    # ── 2. No registry in IaC ───────────────────────────────────
    def test_no_registry_in_terraform(self, tmp_path):
        """Docker images built, Terraform exists but no registry resource → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [],
                "stage_count": 1,
                "ports": [],
                "warnings": [],
            }],
        )
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[
                {"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"},
                {"type": "aws_rds_instance", "name": "db", "file": "rds.tf"},
            ],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔Terraform:" in i["message"]
            and "no container registry" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected no-registry-in-Terraform info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 4: Docker ↔ Environments
# ═══════════════════════════════════════════════════════════════════


class TestLayer6DockerEnvironments:
    """Docker ↔ Environments cross-domain checks (2 checks)."""

    # ── 1. Compose override per environment ─────────────────────
    def test_compose_no_per_env_overrides(self, tmp_path):
        """project.yml has 2 envs, only base compose → info."""
        # Create project.yml with environments
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: development
  - name: production
""")
        # Create base compose only
        (tmp_path / "docker-compose.yml").write_text("""
services:
  api:
    image: myapp:latest
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Docker↔Environments:" in i["message"]
            and "environment" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected compose-override-per-env info, got: {issues}"

    # ── 2. Env file reference validity ──────────────────────────
    def test_compose_env_file_missing(self, tmp_path):
        """Compose references .env.production but file doesn't exist → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_compose=True,
            compose_services=["api"],
            compose_service_details=[{
                "name": "api",
                "image": "myapp:latest",
                "build": None,
                "ports": [],
                "environment": {},
                "volumes": [],
                "depends_on": [],
                "healthcheck": None,
                "env_file": [".env.production"],
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Docker↔Environments:" in i["message"]
            and ".env.production" in i["message"]
        ]
        assert len(issues) >= 1, f"Expected env-file-missing warning, got: {issues}"




# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 5: Terraform ↔ K8s
# ═══════════════════════════════════════════════════════════════════


class TestLayer6TerraformK8s:
    """Terraform ↔ K8s cross-domain checks (5 checks)."""

    # ── 1. Cloud cluster without IaC ────────────────────────────
    def test_cloud_cluster_no_terraform(self, tmp_path):
        """K8s on cloud cluster, no Terraform → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status(has_terraform=False)), \
             patch("src.core.services.k8s_validate.cluster_status", return_value={
                 "connected": True,
                 "cluster_type": {"type": "eks"},
                 "server_version": "1.28",
                 "namespaces": [],
             }):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔K8s:" in i["message"]
            and "cloud" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected cloud-without-IaC info, got: {issues}"

    # ── 2. Environment alignment ────────────────────────────────
    def test_terraform_env_missing(self, tmp_path):
        """project.yml has [dev, prod], Terraform has no workspace alignment → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: development
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔Environments:" in i["message"]
            and "environment" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected Terraform env alignment info, got: {issues}"

    # ── 3. Kubernetes provider conflict ─────────────────────────
    def test_k8s_provider_conflict(self, tmp_path):
        """Terraform has kubernetes provider AND raw K8s manifests → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["kubernetes", "aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Terraform↔K8s:" in i["message"]
            and "kubernetes provider" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected K8s provider conflict warning, got: {issues}"

    # ── 4. Database connection gap ──────────────────────────────
    def test_database_no_k8s_secret(self, tmp_path):
        """Terraform provisions RDS, K8s has no connection Secret → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[
                {"type": "aws_rds_instance", "name": "db", "file": "rds.tf"},
            ],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔K8s:" in i["message"]
            and "database" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected database connection gap info, got: {issues}"

    # ── 5. IAM ↔ ServiceAccount alignment ───────────────────────
    def test_iam_no_serviceaccount(self, tmp_path):
        """Terraform creates IAM role for K8s, no K8s ServiceAccount refs it → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[
                {"type": "aws_iam_role", "name": "k8s_pod_role", "file": "iam.tf"},
                {"type": "aws_iam_role_policy_attachment", "name": "k8s_pod_policy", "file": "iam.tf"},
            ],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔K8s:" in i["message"]
            and "iam" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected IAM/ServiceAccount alignment info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 6: Terraform ↔ CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestLayer6TerraformCI:
    """Terraform ↔ CI/CD cross-domain checks (3 checks)."""

    # ── 1. IaC not in CI pipeline ───────────────────────────────
    def test_terraform_not_in_ci(self, tmp_path):
        """Terraform exists, CI detected, no terraform steps → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "test",
                "name": "Test",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "npm test"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔CI:" in i["message"]
        ]
        assert len(issues) >= 1, f"Expected Terraform-not-in-CI info, got: {issues}"

    # ── 2. No plan-on-PR ────────────────────────────────────────
    def test_no_plan_on_pr(self, tmp_path):
        """Terraform + CI exist, CI has terraform apply but no plan on PR → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "terraform apply -auto-approve"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔CI:" in i["message"]
            and "plan" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected no-plan-on-PR info, got: {issues}"

    # ── 3. Apply without environment protection ─────────────────
    def test_apply_no_protection(self, tmp_path):
        """CI has terraform apply but no environment protection → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "terraform apply -auto-approve"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Terraform↔CI:" in i["message"]
            and "terraform apply" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected unguarded-apply warning, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 7: Terraform ↔ Environments
# ═══════════════════════════════════════════════════════════════════


class TestLayer6TerraformEnvironments:
    """Terraform ↔ Environments cross-domain checks (2 checks)."""

    # ── 1. Workspace ↔ environment alignment ────────────────────
    def test_workspace_env_mismatch(self, tmp_path):
        """project.yml has envs but Terraform has no corresponding .tfvars → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: development
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "eks.tf"}],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔Environments:" in i["message"]
            and "environment" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected workspace-env alignment info, got: {issues}"

    # ── 2. Variable file coverage ───────────────────────────────
    def test_no_tfvars_per_env(self, tmp_path):
        """project.yml has envs, Terraform has no per-env .tfvars → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: development
  - name: production
""")
        # Create terraform dir with main.tf but no per-env .tfvars
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "main.tf").write_text('resource "aws_eks_cluster" "main" {}')
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        tf = _mock_terraform_status(
            has_terraform=True,
            root="terraform",
            providers=["aws"],
            resources=[{"type": "aws_eks_cluster", "name": "main", "file": "terraform/main.tf"}],
            files=[{"path": "terraform/main.tf", "type": "main"}],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=tf):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Terraform↔Environments:" in i["message"]
            and "per-environment" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected no-tfvars-per-env info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 8: CI/CD ↔ K8s
# ═══════════════════════════════════════════════════════════════════


class TestLayer6CIK8s:
    """CI/CD ↔ K8s cross-domain checks (5 checks)."""

    # ── 1. Deploy step existence ────────────────────────────────
    def test_k8s_manifests_no_ci_deploy(self, tmp_path):
        """K8s manifests exist, CI has no deploy step → info."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "test",
                "name": "Test",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "npm test"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "CI↔K8s:" in i["message"]
            and "deploy" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected no-deploy-step info, got: {issues}"

    # ── 2. Image build→deploy chain ─────────────────────────────
    def test_deploy_without_build(self, tmp_path):
        """CI deploys to K8s but doesn't build images first → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [], "stage_count": 1, "ports": [], "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "CI↔K8s:" in i["message"]
            and "build" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected deploy-without-build warning, got: {issues}"

    # ── 3. Environment gates ────────────────────────────────────
    def test_ci_deploy_no_env_protection(self, tmp_path):
        """CI deploys to K8s, prod env exists, no environment protection → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "CI↔K8s:" in i["message"]
            and "production" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected env-gate info, got: {issues}"

    # ── 4. Deploy strategy ↔ CI tool alignment ──────────────────
    def test_helm_but_kubectl_in_ci(self, tmp_path):
        """K8s uses Helm, CI deploys with kubectl → warning."""
        chart_dir = tmp_path / "k8s" / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0")
        templates_dir = chart_dir / "templates"
        templates_dir.mkdir()
        (templates_dir / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "CI↔K8s:" in i["message"]
            and "helm" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected Helm-vs-kubectl warning, got: {issues}"

    # ── 5. Cluster credentials in CI ────────────────────────────
    def test_ci_deploy_no_kubeconfig(self, tmp_path):
        """CI deploys to K8s but no kubeconfig/token setup → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "CI↔K8s:" in i["message"]
            and "credentials" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected cluster-credentials warning, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 9: CI/CD ↔ Environments
# ═══════════════════════════════════════════════════════════════════


class TestLayer6CIEnvironments:
    """CI/CD ↔ Environments cross-domain checks (3 checks)."""

    # ── 1. CI environment coverage ──────────────────────────────
    def test_ci_missing_env_coverage(self, tmp_path):
        """project.yml has [dev, staging, prod], CI only targets dev → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: development
  - name: staging
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy-dev",
                "name": "Deploy Dev",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": "development",
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "CI↔Environments:" in i["message"]
        ]
        assert len(issues) >= 1, f"Expected CI env coverage gaps, got: {issues}"

    # ── 2. Secret injection per environment ─────────────────────
    def test_ci_no_secrets_for_env(self, tmp_path):
        """CI deploys to env but workflow has no secrets refs → warning."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
        env:
        - name: DB_PASSWORD
          value: changeme
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": "production",
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "CI↔Environments:" in i["message"]
            and "secret" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected secrets-not-injected warning, got: {issues}"

    # ── 3. Production protection ────────────────────────────────
    def test_ci_prod_no_approval(self, tmp_path):
        """CI deploys to production, no approval gates → info."""
        (tmp_path / "project.yml").write_text("""
name: myproject
environments:
  - name: production
""")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/deploy.yml",
            "provider": "github_actions",
            "name": "Deploy",
            "triggers": ["push"],
            "jobs": [{
                "id": "deploy",
                "name": "Deploy",
                "runs_on": "ubuntu-latest",
                "steps_count": 2,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "kubectl apply -f k8s/"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "CI↔Environments:" in i["message"]
            and "production" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected prod-no-approval info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Seam 10: Cross-cutting intelligence
# ═══════════════════════════════════════════════════════════════════


class TestLayer6CrossCutting:
    """Cross-cutting intelligence checks (3 checks)."""

    # ── 1. Version alignment ────────────────────────────────────
    def test_python_version_mismatch(self, tmp_path):
        """Dockerfile FROM python:3.12, CI setup-python 3.11 → warning."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [], "stage_count": 1, "ports": [], "warnings": [],
            }],
        )
        ci_wf = _mock_ci_workflows(workflows=[{
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push"],
            "jobs": [{
                "id": "test",
                "name": "Test",
                "runs_on": "ubuntu-latest",
                "steps_count": 3,
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}},
                    {"run": "pytest"},
                ],
                "needs": [],
                "environment": None,
            }],
            "issues": [],
        }])
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=True)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=ci_wf), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Cross-cutting:" in i["message"]
            and "version" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected version mismatch warning, got: {issues}"

    # ── 2. Pipeline completeness ────────────────────────────────
    def test_no_ci_with_full_stack(self, tmp_path):
        """Has Docker + K8s but no CI → info about missing automation."""
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        docker = _mock_docker_status(
            has_dockerfile=True,
            dockerfiles=["Dockerfile"],
            dockerfile_details=[{
                "path": "Dockerfile",
                "base_images": ["python:3.12-slim"],
                "stages": [], "stage_count": 1, "ports": [], "warnings": [],
            }],
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=docker), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status(has_ci=False)), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Cross-cutting:" in i["message"]
            and "ci" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected pipeline-completeness info, got: {issues}"

    # ── 3. Secret flow integrity ────────────────────────────────
    def test_env_secrets_not_in_k8s(self, tmp_path):
        """Project has .env with secrets, K8s has no corresponding Secrets → info."""
        (tmp_path / ".env").write_text("DB_PASSWORD=secret123\nAPI_KEY=key456\n")
        _write_manifest(tmp_path, "deploy.yaml", """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:latest
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)
        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Cross-cutting:" in i["message"]
        ]
        assert len(issues) >= 1, f"Expected secret flow integrity info, got: {issues}"


# ═══════════════════════════════════════════════════════════════════
#  Layer 7 — Deployment strategy validation
# ═══════════════════════════════════════════════════════════════════


class TestLayer7RawKubectl:
    """Raw kubectl deployment strategy checks (8 checks)."""

    # ── 1. Unresolved envsubst variables ────────────────────────
    def test_envsubst_var_detected(self, tmp_path):
        """Manifest with ${VAR} patterns → warning with exact structure.

        Spec: envsubst (GNU gettext) substitutes ${VAR_NAME} patterns.
        If manifests contain these patterns but no envsubst pipeline step
        is documented, the manifests will fail on `kubectl apply`.

        Pessimistic assertions:
        - Exactly ONE envsubst-related warning for the file
        - severity == "warning"
        - file == relative path to the manifest
        - message contains BOTH variable names (DB_HOST, IMAGE_TAG)
        - message mentions "envsubst" for actionability
        """
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:${IMAGE_TAG}
        env:
        - name: DB_HOST
          value: "${DB_HOST}"
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        # Filter to only envsubst-related issues
        envsubst_issues = [
            i for i in result["issues"]
            if "envsubst" in i["message"].lower()
        ]

        # Exactly one issue for this file
        assert len(envsubst_issues) == 1, \
            f"Expected exactly 1 envsubst issue, got {len(envsubst_issues)}: {envsubst_issues}"

        issue = envsubst_issues[0]

        # Full issue dict shape
        assert set(issue.keys()) == {"file", "severity", "message"}, \
            f"Issue keys mismatch: {set(issue.keys())}"

        # Severity is warning (not error, not info)
        assert issue["severity"] == "warning", \
            f"Expected severity 'warning', got '{issue['severity']}'"

        # File is the relative manifest path
        assert issue["file"] == "k8s/deploy.yaml", \
            f"Expected file 'k8s/deploy.yaml', got '{issue['file']}'"

        # Message contains both variable names
        assert "DB_HOST" in issue["message"], \
            f"Expected 'DB_HOST' in message: {issue['message']}"
        assert "IMAGE_TAG" in issue["message"], \
            f"Expected 'IMAGE_TAG' in message: {issue['message']}"

    def test_no_envsubst_no_warning(self, tmp_path):
        """Manifest without ${VAR} patterns → zero envsubst warnings.

        Pessimistic assertions:
        - No issue with 'envsubst' in its message exists at any severity
        """
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1.0.0
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        envsubst_issues = [
            i for i in result["issues"]
            if "envsubst" in i["message"].lower()
        ]
        assert len(envsubst_issues) == 0, \
            f"Expected zero envsubst issues, got: {envsubst_issues}"


    # ── 2. Missing Namespace manifest ──────────────────────────
    def test_missing_namespace_manifest(self, tmp_path):
        """Resource targets namespace 'production' but no Namespace manifest exists.

        Spec: kubectl apply will fail if the target namespace doesn't exist
        and isn't one of the built-in namespaces (default, kube-system, etc.).

        Pessimistic assertions:
        - Exactly ONE namespace-related warning
        - severity == "warning"
        - file == "deployment-strategy" (cross-resource check, not per-file)
        - message contains the namespace name 'production'
        - message mentions 'Namespace' and 'kubectl'
        - Built-in namespaces (default, kube-system) are NOT flagged
        """
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        ns_issues = [
            i for i in result["issues"]
            if "namespace" in i["message"].lower() and "production" in i["message"].lower()
            and i["severity"] == "warning"
        ]

        assert len(ns_issues) == 1, \
            f"Expected exactly 1 namespace warning, got {len(ns_issues)}: {ns_issues}"

        issue = ns_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}, \
            f"Issue keys mismatch: {set(issue.keys())}"
        assert issue["severity"] == "warning"
        assert issue["file"] == "deployment-strategy"
        assert "production" in issue["message"]
        assert "namespace" in issue["message"].lower()
        assert "kubectl" in issue["message"].lower()

    def test_namespace_manifest_present_no_warning(self, tmp_path):
        """Resource targets 'production' and Namespace manifest exists → no warning.

        Pessimistic assertions:
        - Zero warnings mentioning 'production' and 'namespace' together
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "namespace.yaml").write_text("""\
apiVersion: v1
kind: Namespace
metadata:
  name: production
""")
        (k8s / "deploy.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        ns_issues = [
            i for i in result["issues"]
            if "namespace" in i["message"].lower() and "production" in i["message"].lower()
            and "not defined" in i["message"].lower() or "no namespace" in i["message"].lower()
        ]
        assert len(ns_issues) == 0, \
            f"Expected zero namespace warnings, got: {ns_issues}"

    # ── 3. CRD ordering gap ────────────────────────────────────
    def test_cr_without_crd(self, tmp_path):
        """Custom Resource exists but no CRD manifest.

        Spec: kubectl apply will reject Custom Resources whose CRD
        is not already installed in the cluster. If the project ships
        CRs but not the CRD, deployment will fail.

        Pessimistic assertions:
        - Exactly ONE CRD-related error for this resource
        - severity == "error" (not warning — it will hard-fail)
        - file == relative path to the manifest
        - message contains the CR kind ('Certificate') and apiVersion
        """
        _write_manifest(tmp_path, "certificate.yaml", """\
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: my-cert
  namespace: default
spec:
  secretName: my-cert-tls
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer
  dnsNames:
  - example.com
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        crd_issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "crd" in i["message"].lower()
        ]

        assert len(crd_issues) == 1, \
            f"Expected exactly 1 CRD error, got {len(crd_issues)}: {crd_issues}"

        issue = crd_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["severity"] == "error"
        assert issue["file"] == "k8s/certificate.yaml"
        assert "Certificate" in issue["message"]
        assert "cert-manager.io/v1" in issue["message"]
        assert "kubectl" in issue["message"].lower()

    # ── 4. Raw Secret with literal data ────────────────────────
    def test_raw_secret_literal(self, tmp_path):
        """Secret with literal stringData → warning about plaintext.

        Spec: Kubernetes Secrets with data/stringData are base64-encoded,
        not encrypted. Committing them is a security risk. Best practice
        is SealedSecrets, ExternalSecrets, or SOPS.

        Pessimistic assertions:
        - Exactly ONE plaintext secret warning
        - severity == "warning"
        - file == relative path to the manifest
        - message mentions 'plaintext' or 'literal'
        - message mentions the secret name
        """
        _write_manifest(tmp_path, "secret.yaml", """\
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
  namespace: default
type: Opaque
stringData:
  password: "s3cret123"
  api_key: "ak_live_xxxxxxxxx"
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        secret_issues = [
            i for i in result["issues"]
            if i["severity"] == "warning"
            and ("plaintext" in i["message"].lower() or "literal" in i["message"].lower())
            and "secret" in i["message"].lower()
        ]

        assert len(secret_issues) == 1, \
            f"Expected exactly 1 plaintext secret warning, got {len(secret_issues)}: {secret_issues}"

        issue = secret_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["severity"] == "warning"
        assert issue["file"] == "k8s/secret.yaml"
        assert "db-credentials" in issue["message"]

    def test_sealed_secret_no_warning(self, tmp_path):
        """SealedSecret kind → no plaintext secret warning.

        Pessimistic: zero issues matching 'plaintext' and 'secret' at any severity.
        """
        _write_manifest(tmp_path, "sealed.yaml", """\
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: db-credentials
  namespace: default
spec:
  encryptedData:
    password: AgBy3i...
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        plaintext_issues = [
            i for i in result["issues"]
            if "plaintext" in i["message"].lower() and "secret" in i["message"].lower()
        ]
        assert len(plaintext_issues) == 0, \
            f"Expected zero plaintext secret issues for SealedSecret, got: {plaintext_issues}"

    # ── 5. ConfigMap/Secret reference gap ──────────────────────
    def test_configmap_ref_missing(self, tmp_path):
        """Deployment envFrom references ConfigMap not in manifests.

        Spec: kubectl apply succeeds but pod will CrashLoopBackoff
        if referenced ConfigMap doesn't exist at runtime.

        Pessimistic assertions:
        - Exactly ONE warning about missing ConfigMap
        - severity == "warning"
        - file == relative path to the deployment manifest
        - message contains the ConfigMap name 'app-config'
        - message contains the workload kind and name
        """
        _write_manifest(tmp_path, "deploy.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
        envFrom:
        - configMapRef:
            name: app-config
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        cm_issues = [
            i for i in result["issues"]
            if i["severity"] == "warning"
            and "app-config" in i["message"]
            and "Raw kubectl:" in i["message"]
            and "configmap" in i["message"].lower()
        ]

        assert len(cm_issues) == 1, \
            f"Expected exactly 1 ConfigMap ref warning, got {len(cm_issues)}: {cm_issues}"

        issue = cm_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["file"] == "k8s/deploy.yaml"
        assert "Deployment/api" in issue["message"]
        assert "app-config" in issue["message"]

    def test_configmap_ref_present_no_warning(self, tmp_path):
        """Deployment envFrom references ConfigMap that exists → no warning.

        Pessimistic: zero issues mentioning 'app-config' as missing.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "configmap.yaml").write_text("""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: default
data:
  LOG_LEVEL: info
""")
        (k8s / "deploy.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
        envFrom:
        - configMapRef:
            name: app-config
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        cm_issues = [
            i for i in result["issues"]
            if "app-config" in i["message"]
            and "not found" in i["message"].lower()
        ]
        assert len(cm_issues) == 0, \
            f"Expected zero missing ConfigMap warnings, got: {cm_issues}"

    # ── 6. Service selector mismatch ───────────────────────────
    def test_service_selector_no_match(self, tmp_path):
        """Service selects app=web but only Deployment with app=api exists.

        Spec: A Service with a selector that matches no pod labels
        will have zero endpoints and never route traffic.

        Pessimistic assertions:
        - Exactly ONE warning about unmatched selector
        - severity == "warning"
        - file == relative path to svc manifest
        - message contains 'web-svc' (the service name)
        - message contains 'selector'
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "deploy.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""")
        (k8s / "svc.yaml").write_text("""\
apiVersion: v1
kind: Service
metadata:
  name: web-svc
  namespace: default
spec:
  selector:
    app: web
  ports:
  - port: 80
    targetPort: 8080
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        svc_issues = [
            i for i in result["issues"]
            if i["severity"] == "warning"
            and "web-svc" in i["message"]
            and "Raw kubectl:" in i["message"]
            and "selector" in i["message"].lower()
        ]

        assert len(svc_issues) == 1, \
            f"Expected exactly 1 service selector warning, got {len(svc_issues)}: {svc_issues}"

        issue = svc_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["file"] == "k8s/svc.yaml"
        assert "Service/web-svc" in issue["message"]

    def test_service_selector_matches(self, tmp_path):
        """Service selects app=api and Deployment with app=api exists → no warning.

        Pessimistic: zero selector mismatch issues.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "deploy.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""")
        (k8s / "svc.yaml").write_text("""\
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  namespace: default
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 8080
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        svc_issues = [
            i for i in result["issues"]
            if "api-svc" in i["message"]
            and "selector" in i["message"].lower()
            and "no workload" in i["message"].lower()
        ]
        assert len(svc_issues) == 0, \
            f"Expected zero selector mismatch warnings, got: {svc_issues}"

    # ── 7. Ingress backend gap ─────────────────────────────────
    def test_ingress_missing_backend_service(self, tmp_path):
        """Ingress references Service 'api-svc' not in manifests.

        Spec: Ingress backends must reference existing Services.
        If the Service doesn't exist, the Ingress controller will
        return 502/503 for that path.

        Pessimistic assertions:
        - Exactly ONE warning about missing backend service
        - severity == "warning"
        - file == relative path to ingress manifest
        - message contains 'api-svc' and 'Ingress'
        """
        _write_manifest(tmp_path, "ingress.yaml", """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
  namespace: default
spec:
  rules:
  - host: example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-svc
            port:
              number: 80
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        ingress_issues = [
            i for i in result["issues"]
            if i["severity"] == "warning"
            and "api-svc" in i["message"]
            and "Raw kubectl:" in i["message"]
            and "ingress" in i["message"].lower()
        ]

        assert len(ingress_issues) == 1, \
            f"Expected exactly 1 Ingress backend warning, got {len(ingress_issues)}: {ingress_issues}"

        issue = ingress_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["file"] == "k8s/ingress.yaml"
        assert "web-ingress" in issue["message"]

    def test_ingress_backend_present(self, tmp_path):
        """Ingress references Service that exists → no backend warning.

        Pessimistic: zero issues about api-svc being missing.
        """
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "svc.yaml").write_text("""\
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  namespace: default
spec:
  selector:
    app: api
  ports:
  - port: 80
""")
        (k8s / "ingress.yaml").write_text("""\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-ingress
  namespace: default
spec:
  rules:
  - host: example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-svc
            port:
              number: 80
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        ingress_issues = [
            i for i in result["issues"]
            if "api-svc" in i["message"]
            and "missing" in i["message"].lower()
            and "ingress" in i["message"].lower()
        ]
        assert len(ingress_issues) == 0, \
            f"Expected zero Ingress backend warnings, got: {ingress_issues}"

    # ── 8. PVC StorageClass gap ────────────────────────────────
    def test_pvc_storageclass_gap(self, tmp_path):
        """PVC specifies storageClassName not in manifests.

        Spec: PVC will remain Pending if the StorageClass doesn't
        exist in the cluster and isn't defined in the manifests.

        Pessimistic assertions:
        - Exactly ONE info about missing StorageClass
        - severity == "info"
        - file == relative path to pvc manifest
        - message contains 'fast-ssd' (the SC name)
        - message contains 'StorageClass'
        """
        _write_manifest(tmp_path, "pvc.yaml", """\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: default
spec:
  storageClassName: fast-ssd
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        sc_issues = [
            i for i in result["issues"]
            if i["severity"] == "info"
            and "storageclass" in i["message"].lower()
            and "fast-ssd" in i["message"].lower()
        ]

        assert len(sc_issues) == 1, \
            f"Expected exactly 1 StorageClass info, got {len(sc_issues)}: {sc_issues}"

        issue = sc_issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["file"] == "k8s/pvc.yaml"
        assert "fast-ssd" in issue["message"]
        assert "StorageClass" in issue["message"]


def _make_helm_chart(
    tmp_path: Path,
    *,
    chart_yaml: str = "apiVersion: v2\nname: myapp\nversion: 1.0.0\n",
    values_yaml: str | None = "replicaCount: 1\n",
    templates: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
    chart_dir: str = "charts/myapp",
) -> Path:
    """Helper to create a Helm chart structure on disk."""
    d = tmp_path / chart_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "Chart.yaml").write_text(chart_yaml)
    if values_yaml is not None:
        (d / "values.yaml").write_text(values_yaml)
    if templates is not None:
        tpl_dir = d / "templates"
        tpl_dir.mkdir(exist_ok=True)
        for name, content in templates.items():
            (tpl_dir / name).write_text(content)
    if extra_files:
        for name, content in extra_files.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    return d


class TestLayer7Helm:
    """Helm deployment strategy checks (13 checks).

    Source of truth: Helm Chart.yaml v2 spec.
    All issues prefixed with "Helm:" for layer disambiguation.
    """

    # ── 1. No templates directory ──────────────────────────────
    def test_no_templates_dir(self, tmp_path):
        """Application chart without templates/ → error.

        Spec: Application charts must have templates/ to render manifests.
        Without it, `helm install` produces nothing.

        Pessimistic: exact 1 error, file == chart path, message contains chart name.
        """
        _make_helm_chart(tmp_path, templates=None)
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Helm:" in i["message"]
            and "templates" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        issue = issues[0]
        assert set(issue.keys()) == {"file", "severity", "message"}
        assert issue["file"] == "charts/myapp"
        assert "myapp" in issue["message"]

    def test_with_templates_dir_no_error(self, tmp_path):
        """Chart with templates/ → no templates error.

        Pessimistic: zero Helm errors about templates.
        """
        _make_helm_chart(tmp_path, templates={"deployment.yaml": "# placeholder"})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Helm:" in i["message"]
            and "templates" in i["message"].lower()
        ]
        assert len(issues) == 0, f"Unexpected templates error: {issues}"

    # ── 2. No values.yaml ──────────────────────────────────────
    def test_no_values_yaml(self, tmp_path):
        """Chart without values.yaml → warning.

        Spec: values.yaml provides default configuration. Without it,
        users must provide all values via --set or -f.

        Pessimistic: exact 1 warning, file == chart path, mentions chart name.
        """
        _make_helm_chart(tmp_path, values_yaml=None, templates={"deploy.yaml": "# tpl"})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "values" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"
        assert "myapp" in issues[0]["message"]

    # ── 3. Dependencies without lock ───────────────────────────
    def test_deps_no_lockfile(self, tmp_path):
        """Chart.yaml has dependencies but no Chart.lock → info.

        Spec: Chart.lock pins exact dependency versions.
        Without it, builds are non-reproducible.

        Pessimistic: exact 1 info, mentions dependency name 'redis'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: 1.0.0\ndependencies:\n- name: redis\n  version: 17.0.0\n  repository: https://charts.bitnami.com/bitnami\n",
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and "lock" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"
        assert "redis" in issues[0]["message"]

    # ── 4. Deprecated apiVersion v1 ────────────────────────────
    def test_deprecated_api_v1(self, tmp_path):
        """Chart.yaml with apiVersion v1 → warning.

        Spec: apiVersion v1 is Helm 2 format; v2 is required for Helm 3.

        Pessimistic: exact 1 warning, mentions 'v1' and 'v2'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v1\nname: myapp\nversion: 1.0.0\n",
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "apiversion" in i["message"].lower() and "v1" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"
        assert "v2" in issues[0]["message"]

    # ── 5. Library chart with non-helper templates ─────────────
    def test_library_with_renderable(self, tmp_path):
        """type: library with non-_ templates → warning.

        Spec: Library charts (type: library) should only contain
        _*.tpl helper files. Non-helper templates are silently ignored
        by Helm but indicate a misconfiguration.

        Pessimistic: exact 1 warning, mentions renderable file name.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: mylib\nversion: 1.0.0\ntype: library\n",
            templates={"deployment.yaml": "# renderable", "_helpers.tpl": "# helper"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "library" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "deployment.yaml" in issues[0]["message"]
        assert "mylib" in issues[0]["message"]

    def test_library_only_helpers_no_warn(self, tmp_path):
        """type: library with only _*.tpl files → no warning.

        Pessimistic: zero library-related warnings.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: mylib\nversion: 1.0.0\ntype: library\n",
            templates={"_helpers.tpl": "# helper", "_utils.tpl": "# more helpers"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "library" in i["message"].lower() and "renderable" in i["message"].lower()
        ]
        assert len(issues) == 0, f"Unexpected library warning: {issues}"

    # ── 6. Orphaned subcharts ──────────────────────────────────
    def test_orphaned_subcharts(self, tmp_path):
        """charts/ dir exists but no dependencies in Chart.yaml → info.

        Spec: charts/ should contain declared dependencies.
        Undeclared subcharts won't be managed by Helm.

        Pessimistic: exact 1 info, mentions 'charts/' or 'subchart'.
        """
        chart_dir = _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: 1.0.0\n",
            templates={"deploy.yaml": "# tpl"},
        )
        sub = chart_dir / "charts" / "redis"
        sub.mkdir(parents=True)
        (sub / "Chart.yaml").write_text("apiVersion: v2\nname: redis\nversion: 1.0.0\n")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and ("subchart" in i["message"].lower() or "charts/" in i["message"].lower())
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"

    # ── 7. Missing required fields ─────────────────────────────
    def test_missing_name(self, tmp_path):
        """Chart.yaml without name → error.

        Spec: `name` is a required field in Chart.yaml v2.

        Pessimistic: exact 1 error, mentions 'name' and 'required' or 'missing'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nversion: 1.0.0\n",
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Helm:" in i["message"]
            and "'name'" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert "required" in issues[0]["message"].lower() or "missing" in issues[0]["message"].lower()

    def test_missing_version(self, tmp_path):
        """Chart.yaml without version → error.

        Spec: `version` is a required field in Chart.yaml v2.

        Pessimistic: exact 1 error, mentions 'version' and 'required' or 'missing'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\n",
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Helm:" in i["message"]
            and "'version'" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert "required" in issues[0]["message"].lower() or "missing" in issues[0]["message"].lower()

    # ── 8. Invalid SemVer version ──────────────────────────────
    def test_invalid_semver(self, tmp_path):
        """Chart version 'latest' → warning.

        Spec: Helm requires versions to follow SemVer 2.0.0.
        'latest' is not SemVer — should be MAJOR.MINOR.PATCH.

        Pessimistic: exact 1 warning, mentions 'latest' and 'SemVer'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: latest\n",
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "semver" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "latest" in issues[0]["message"]

    # ── 9. No .helmignore ──────────────────────────────────────
    def test_no_helmignore(self, tmp_path):
        """Chart in project with >20 files but no .helmignore → info.

        Spec: .helmignore controls what `helm package` includes.
        Without it, all project files are packaged.

        Pessimistic: exact 1 info, mentions 'helmignore'.
        """
        _make_helm_chart(
            tmp_path,
            templates={"deploy.yaml": "# tpl"},
        )
        for i in range(25):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and "helmignore" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"

    # ── 10. Missing NOTES.txt ──────────────────────────────────
    def test_no_notes_txt(self, tmp_path):
        """templates/ has no NOTES.txt → info.

        Spec: NOTES.txt is rendered after `helm install` to show
        post-install instructions.

        Pessimistic: exact 1 info, mentions 'NOTES.txt'.
        """
        _make_helm_chart(
            tmp_path,
            templates={"deploy.yaml": "# tpl", "_helpers.tpl": "# h"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and "notes" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"

    # ── 11. No _helpers.tpl ────────────────────────────────────
    def test_no_helpers_tpl(self, tmp_path):
        """templates/ has no _helpers.tpl → info.

        Spec: _helpers.tpl is the conventional location for reusable
        named templates. Without it, charts lack shared template logic.

        Pessimistic: exact 1 info, mentions '_helpers' or 'helpers'.
        """
        _make_helm_chart(
            tmp_path,
            templates={"deploy.yaml": "# tpl", "NOTES.txt": "Thank you!"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and "helpers" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"

    # ── 12. No values.schema.json ──────────────────────────────
    def test_no_schema_json(self, tmp_path):
        """Chart without values.schema.json → info.

        Spec: values.schema.json provides JSON Schema validation
        for values.yaml inputs. Without it, invalid values
        aren't caught until render/install time.

        Pessimistic: exact 1 info, mentions 'schema'.
        """
        _make_helm_chart(
            tmp_path,
            templates={"deploy.yaml": "# tpl"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Helm:" in i["message"]
            and "schema" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "charts/myapp"

    # ── 13. Local file:// dependency ───────────────────────────
    def test_file_dep_warning(self, tmp_path):
        """Chart.yaml dependency with file:// repository → warning.

        Spec: file:// dependencies reference local filesystem paths.
        They work for development but break when the chart is
        distributed via a registry.

        Pessimistic: exact 1 warning, mentions 'file://' and dep name.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml=(
                "apiVersion: v2\nname: myapp\nversion: 1.0.0\n"
                "dependencies:\n- name: common\n  version: 1.0.0\n"
                "  repository: file://../common\n"
            ),
            templates={"deploy.yaml": "# tpl"},
            extra_files={"Chart.lock": "# lock"},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Helm:" in i["message"]
            and "file://" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "common" in issues[0]["message"]
        assert issues[0]["file"] == "charts/myapp"


def _make_kustomize(
    tmp_path: Path,
    kustomization: str,
    *,
    resource_files: dict[str, str] | None = None,
    extra_dirs: list[str] | None = None,
    kust_dir: str = "k8s",
) -> Path:
    """Helper to create a Kustomize project structure."""
    d = tmp_path / kust_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "kustomization.yaml").write_text(kustomization)
    if resource_files:
        for name, content in resource_files.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    if extra_dirs:
        for dir_name in extra_dirs:
            (d / dir_name).mkdir(parents=True, exist_ok=True)
    return d


class TestLayer7Kustomize:
    """Kustomize deployment strategy checks (10 checks).

    Source of truth: Kustomize spec.
    All issues prefixed with "Kustomize:" for layer disambiguation.
    """

    # ── 1. Missing resource file ───────────────────────────────
    def test_missing_resource_file(self, tmp_path):
        """resources: references file that doesn't exist → error.

        Spec: `kustomize build` will fail if a listed resource doesn't exist.

        Pessimistic: exact 1 error, file == kustomization path,
        message contains missing filename.
        """
        _make_kustomize(tmp_path, """\
resources:
- deployment.yaml
- missing-file.yaml
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Kustomize:" in i["message"]
            and "missing-file" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert set(issues[0].keys()) == {"file", "severity", "message"}
        assert "not found" in issues[0]["message"].lower()

    # ── 2. Path traversal in resources ─────────────────────────
    def test_path_traversal(self, tmp_path):
        """resources: entry uses ../../../ → error.

        Spec: references must stay within the project root.
        Escaping is a security risk.

        Pessimistic: exact 1 error, mentions 'traversal' or 'outside'.
        """
        _make_kustomize(tmp_path, """\
resources:
- ../../../etc/secrets.yaml
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Kustomize:" in i["message"]
            and ("traversal" in i["message"].lower() or "outside" in i["message"].lower())
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"

    # ── 3. Overlays without base ───────────────────────────────
    def test_overlays_no_base(self, tmp_path):
        """overlays/ exists but no base/ → warning.

        Spec: The overlay/base pattern requires a base directory.
        Overlays without a base have nothing to overlay.

        Pessimistic: exact 1 warning, mentions 'overlay' and 'base'.
        """
        kust = _make_kustomize(tmp_path, "resources: []\n")
        overlays = kust / "overlays" / "production"
        overlays.mkdir(parents=True)
        (overlays / "kustomization.yaml").write_text("resources:\n- ../../\n")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Kustomize:" in i["message"]
            and "overlay" in i["message"].lower() and "base" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"

    # ── 4. Secret literals in kustomization ────────────────────
    def test_secret_literals(self, tmp_path):
        """secretGenerator with literals → warning.

        Spec: Plaintext secrets in kustomization.yaml end up in VCS.
        Use envs, files, or external secret management.

        Pessimistic: exact 1 warning, mentions secret generator name.
        """
        _make_kustomize(tmp_path, """\
secretGenerator:
- name: db-creds
  literals:
  - password=s3cret123
  - api_key=ak_live_xxxx
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Kustomize:" in i["message"]
            and "secret" in i["message"].lower() and "literal" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "db-creds" in issues[0]["message"]

    # ── 5. Duplicate resource entry ────────────────────────────
    def test_duplicate_resource(self, tmp_path):
        """Same file listed twice in resources → error.

        Spec: `kustomize build` will fail with duplicate resources.

        Pessimistic: exact 1 error, mentions 'deployment.yaml'.
        """
        _make_kustomize(tmp_path, """\
resources:
- deployment.yaml
- deployment.yaml
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Kustomize:" in i["message"]
            and "duplicate" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert "deployment.yaml" in issues[0]["message"]

    # ── 6. Patch targets missing resource ──────────────────────
    def test_patch_targets_missing(self, tmp_path):
        """Patch targets kind+name not in resources → warning.

        Spec: Patch will be silently ignored if no matching resource.

        Pessimistic: exact 1 warning, mentions target kind/name.
        """
        _make_kustomize(tmp_path, """\
resources:
- deployment.yaml
patches:
- target:
    kind: Service
    name: nonexistent-svc
  patch: |-
    - op: add
      path: /metadata/annotations/foo
      value: bar
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Kustomize:" in i["message"]
            and "patch" in i["message"].lower() and "nonexistent-svc" in i["message"]
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "Service" in issues[0]["message"]

    # ── 7. Deprecated bases field ──────────────────────────────
    def test_deprecated_bases(self, tmp_path):
        """bases: field used → info.

        Spec: `bases` was deprecated in kustomize v2.1.0.
        Use `resources` instead.

        Pessimistic: exact 1 info, mentions 'bases' and 'deprecated'.
        """
        _make_kustomize(tmp_path, """\
bases:
- ../base
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Kustomize:" in i["message"]
            and "bases" in i["message"].lower() and "deprecated" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"

    # ── 8. commonLabels immutability risk ──────────────────────
    def test_common_labels_risk(self, tmp_path):
        """commonLabels used → info.

        Spec: commonLabels propagates to selector.matchLabels which
        are immutable on Deployments. Changing them later breaks
        rolling updates.

        Pessimistic: exact 1 info, mentions 'commonLabels'.
        """
        _make_kustomize(tmp_path, """\
commonLabels:
  app: myapp
  environment: prod
resources:
- deployment.yaml
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Kustomize:" in i["message"]
            and "commonlabels" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"

    # ── 9. Missing components directory ────────────────────────
    def test_missing_components_dir(self, tmp_path):
        """components: references directory that doesn't exist → error.

        Spec: `kustomize build` will fail if component dir is missing.

        Pessimistic: exact 1 error, mentions component path.
        """
        _make_kustomize(tmp_path, """\
components:
- components/logging
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Kustomize:" in i["message"]
            and "component" in i["message"].lower() and "not found" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert "logging" in issues[0]["message"]

    # ── 10. Namespace override conflict ────────────────────────
    def test_namespace_override_conflict(self, tmp_path):
        """namespace: set but resources have hardcoded namespaces → info.

        Spec: Kustomize namespace transformer overrides all namespaces.
        If resources already have different namespaces, the override
        may cause confusion or unintended namespace changes.

        Pessimistic: exact 1 info, mentions both namespaces.
        """
        _make_kustomize(tmp_path, """\
namespace: staging
resources:
- deployment.yaml
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Kustomize:" in i["message"]
            and "namespace" in i["message"].lower()
            and ("conflict" in i["message"].lower() or "override" in i["message"].lower())
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert "staging" in issues[0]["message"]
        assert "production" in issues[0]["message"]


def _make_skaffold(
    tmp_path: Path,
    skaffold_yaml: str,
    *,
    extra_files: dict[str, str] | None = None,
) -> None:
    """Helper to create skaffold.yaml and optional extra files."""
    (tmp_path / "skaffold.yaml").write_text(skaffold_yaml)
    if extra_files:
        for name, content in extra_files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)


class TestLayer7Skaffold:
    """Skaffold deployment strategy checks (7 checks).

    Source of truth: Skaffold schema.
    All issues prefixed with "Skaffold:" for layer disambiguation.
    """

    # ── 1. Missing manifest file ───────────────────────────────
    def test_missing_manifest(self, tmp_path):
        """rawYaml references file that doesn't exist → error.

        Spec: `skaffold dev/run` will fail if referenced manifest
        doesn't exist on disk.

        Pessimistic: exact 1 error, file == skaffold.yaml, mentions missing file.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
manifests:
  rawYaml:
  - k8s/deployment.yaml
  - k8s/missing.yaml
""", extra_files={"k8s/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Skaffold:" in i["message"]
            and "missing" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "skaffold.yaml"
        assert "missing.yaml" in issues[0]["message"]

    # ── 2. Missing Dockerfile ──────────────────────────────────
    def test_missing_dockerfile(self, tmp_path):
        """build.artifacts references Dockerfile that doesn't exist → error.

        Spec: Skaffold needs the Dockerfile to build the image.

        Pessimistic: exact 1 error, mentions 'Dockerfile' and image name.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
build:
  artifacts:
  - image: myapp
    docker:
      dockerfile: Dockerfile
manifests:
  rawYaml:
  - k8s/deployment.yaml
""", extra_files={"k8s/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "error" and "Skaffold:" in i["message"]
            and "dockerfile" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 error, got {len(issues)}: {issues}"
        assert issues[0]["file"] == "skaffold.yaml"
        assert "myapp" in issues[0]["message"]

    # ── 3. Deprecated apiVersion ───────────────────────────────
    def test_deprecated_api(self, tmp_path):
        """skaffold apiVersion v1beta1 → warning.

        Spec: v1beta1 is significantly outdated; current is v4beta+.

        Pessimistic: exact 1 warning, mentions the actual apiVersion.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v1beta1
kind: Config
build:
  artifacts: []
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Skaffold:" in i["message"]
            and "apiversion" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "v1beta1" in issues[0]["message"]

    # ── 4. No deploy or manifests section ──────────────────────
    def test_no_deploy_no_manifests(self, tmp_path):
        """No deploy and no manifests → warning.

        Spec: Without deploy/manifests, skaffold has nothing to deploy.

        Pessimistic: exact 1 warning, mentions 'deploy' or 'manifests'.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
build:
  artifacts:
  - image: myapp
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Skaffold:" in i["message"]
            and "deploy" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected warning about deploy, got: {issues}"
        assert issues[0]["file"] == "skaffold.yaml"

    # ── 5. Build without deploy ────────────────────────────────
    def test_build_without_deploy(self, tmp_path):
        """build defined but no deploy → warning.

        Spec: Building images without deploying them is likely
        a configuration gap.

        Pessimistic: at least 1 warning mentioning build and deploy.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
build:
  artifacts:
  - image: myapp
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Skaffold:" in i["message"]
            and "build" in i["message"].lower()
        ]
        assert len(issues) >= 1, f"Expected build-without-deploy warning, got: {issues}"

    # ── 6. Empty default pipeline ──────────────────────────────
    def test_empty_default_pipeline(self, tmp_path):
        """All config in profiles, empty default → info.

        Spec: If the default pipeline is empty, `skaffold dev`
        without --profile does nothing useful.

        Pessimistic: exact 1 info, mentions profile name.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
profiles:
- name: dev
  build:
    artifacts:
    - image: myapp
  manifests:
    rawYaml:
    - k8s/dev.yaml
""", extra_files={"k8s/dev.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Skaffold:" in i["message"]
            and "profile" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert "dev" in issues[0]["message"]

    # ── 7. Non-reproducible tag policy ─────────────────────────
    def test_non_reproducible_tag(self, tmp_path):
        """tagPolicy sha256 → info.

        Spec: sha256 and latest produce content-addressable or
        mutable tags that make rollback and audit difficult.
        Prefer gitCommit or inputDigest.

        Pessimistic: exact 1 info, mentions 'sha256' and 'tag'.
        """
        _make_skaffold(tmp_path, """\
apiVersion: skaffold/v4beta6
kind: Config
build:
  tagPolicy:
    sha256: {}
  artifacts:
  - image: myapp
manifests:
  rawYaml:
  - k8s/deployment.yaml
""", extra_files={"k8s/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Skaffold:" in i["message"]
            and "tag" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert "sha256" in issues[0]["message"]


class TestLayer7MixedStrategy:
    """Mixed strategy coherence checks (5 checks).

    Source of truth: Cross-strategy consistency rules.
    Checks 1-4 prefixed with "Mixed:", check 5 with "Skaffold:".
    """

    # ── 1. Duplicate resource across strategies ────────────────
    def test_duplicate_resource_raw_and_helm(self, tmp_path):
        """Same Deployment in raw manifests AND Helm templates → warning.

        Spec: When the same (kind, name, namespace) tuple appears in
        both raw manifests and Helm templates, applying both will
        cause resource conflicts — one will overwrite the other.

        Pessimistic: exact 1 warning with "Mixed:" prefix, mentions
        kind (Deployment), name (api), and namespace (default).
        """
        # Raw manifest
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""")
        # Helm chart with same resource
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: 1.0.0\n",
            templates={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
"""},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Mixed:" in i["message"]
            and "both" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert set(issues[0].keys()) == {"file", "severity", "message"}
        assert "Deployment" in issues[0]["message"]
        assert "api" in issues[0]["message"]
        assert "default" in issues[0]["message"]

    # ── 2. Orphaned manifests alongside Kustomize ──────────────
    def test_orphaned_manifest_kustomize(self, tmp_path):
        """Manifest in Kustomize dir but not listed in resources: → warning.

        Spec: Files in the same directory as kustomization.yaml that
        are not listed in `resources:` are not managed by Kustomize.
        They may be stale or accidentally excluded.

        Pessimistic: exact 1 warning with "Mixed:" prefix,
        mentions the orphaned filename.
        """
        kust_dir = _make_kustomize(tmp_path, """\
resources:
- deployment.yaml
""", resource_files={
            "deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: myapp:v1
""",
            "orphaned-service.yaml": """\
apiVersion: v1
kind: Service
metadata:
  name: api-svc
spec:
  selector:
    app: api
  ports:
  - port: 80
"""
        })
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Mixed:" in i["message"]
            and "orphan" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
        assert "orphaned-service.yaml" in issues[0]["message"]

    # ── 3. Mixed strategy undocumented ─────────────────────────
    def test_mixed_undocumented(self, tmp_path):
        """deployment_strategy == 'mixed' but no README → info.

        Spec: Multiple deployment strategies with no documentation
        makes it unclear for new contributors which tool applies
        to what.

        Pessimistic: exact 1 info with "Mixed:" prefix, mentions
        'documentation' or 'README' or 'guide'.
        """
        # Raw manifest
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deployment.yaml").write_text("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: raw-api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: raw-api
  template:
    metadata:
      labels:
        app: raw-api
    spec:
      containers:
      - name: raw-api
        image: raw:v1
""")
        # Helm chart (different resource to avoid check 1 noise)
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: helm-app\nversion: 1.0.0\n",
            templates={"deploy.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: helm-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: helm-api
  template:
    metadata:
      labels:
        app: helm-api
    spec:
      containers:
      - name: helm-api
        image: helm:v1
"""},
        )
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Mixed:" in i["message"]
            and "multiple" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"

    # ── 4. Helm + Kustomize without orchestrator ───────────────
    def test_helm_kustomize_no_orchestrator(self, tmp_path):
        """Both Helm and Kustomize active, no Skaffold/ArgoCD/Flux → info.

        Spec: When both Helm and Kustomize are present but no
        orchestrator (Skaffold, ArgoCD, Flux) exists, it's unclear
        which tool applies what.

        Pessimistic: exact 1 info with "Mixed:" prefix, mentions
        both 'Helm' and 'Kustomize' and 'orchestrator'.
        """
        # Helm chart
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: 1.0.0\n",
            templates={"deploy.yaml": "# tpl"},
        )
        # Kustomize
        _make_kustomize(tmp_path, """\
resources:
- deployment.yaml
""", resource_files={"deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kust-api
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kust-api
  template:
    metadata:
      labels:
        app: kust-api
    spec:
      containers:
      - name: kust-api
        image: kust:v1
"""})
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "info" and "Mixed:" in i["message"]
            and "helm" in i["message"].lower() and "kustomize" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 info, got {len(issues)}: {issues}"
        assert "orchestrator" in issues[0]["message"].lower()

    # ── 5. Skaffold dual deployers ─────────────────────────────
    def test_skaffold_dual_deployers(self, tmp_path):
        """Skaffold uses both helm and rawYaml deployers → warning.

        Spec: When skaffold.yaml has both manifests.rawYaml and
        deploy.helm, resources may conflict in the same namespace.

        Pessimistic: exact 1 warning with "Skaffold:" prefix
        (this is a Skaffold-internal check), mentions 'helm'
        and 'rawYaml'.
        """
        _make_helm_chart(
            tmp_path,
            chart_yaml="apiVersion: v2\nname: myapp\nversion: 1.0.0\n",
            templates={"deploy.yaml": "# tpl"},
        )
        k8s = tmp_path / "k8s"
        k8s.mkdir(exist_ok=True)
        (k8s / "service.yaml").write_text("""\
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  namespace: default
spec:
  selector:
    app: api
  ports:
  - port: 80
""")
        (tmp_path / "skaffold.yaml").write_text("""\
apiVersion: skaffold/v4beta6
kind: Config
manifests:
  rawYaml:
  - k8s/service.yaml
deploy:
  helm:
    releases:
    - name: myapp
      chartPath: charts/myapp
      namespace: default
""")
        with _NO_KUBECTL, \
             patch(_PATCH_DOCKER, return_value=_mock_docker_status()), \
             patch(_PATCH_CI_STATUS, return_value=_mock_ci_status()), \
             patch(_PATCH_CI_WORKFLOWS, return_value=_mock_ci_workflows()), \
             patch(_PATCH_TERRAFORM, return_value=_mock_terraform_status()):
            result = validate_manifests(tmp_path)

        issues = [
            i for i in result["issues"]
            if i["severity"] == "warning" and "Skaffold:" in i["message"]
            and "helm" in i["message"].lower() and "rawyaml" in i["message"].lower()
        ]
        assert len(issues) == 1, f"Expected 1 warning, got {len(issues)}: {issues}"
