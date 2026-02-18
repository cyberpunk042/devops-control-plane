"""
Tests for k8s_cluster — mocked kubectl operations.

Every test mocks _run_kubectl and _kubectl_available to avoid
needing a live cluster. The integration tests (tests/integration/)
cover live cluster scenarios separately.

No subprocess, no network.
"""

import json
from pathlib import Path
from unittest.mock import patch, call

import pytest

from src.core.services.k8s_cluster import (
    cluster_status,
    get_resources,
    k8s_pod_logs,
    k8s_apply,
    k8s_delete_resource,
    k8s_scale,
    k8s_events,
    k8s_describe,
    k8s_namespaces,
    k8s_storage_classes,
    _summarize_conditions,
)


# ── Helpers ──────────────────────────────────────────────────────

def _mock_result(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess.CompletedProcess."""
    return type("Result", (), {
        "returncode": returncode, "stdout": stdout, "stderr": stderr,
    })()


_KUBECTL_OK = {"available": True, "version": "v1.35.1"}
_KUBECTL_MISSING = {"available": False, "version": None}


# ═══════════════════════════════════════════════════════════════════
#  _summarize_conditions (pure logic — no mocking needed)
# ═══════════════════════════════════════════════════════════════════


class TestSummarizeConditions:
    def test_empty_conditions(self):
        """Empty list → empty string."""
        assert _summarize_conditions([]) == ""

    def test_true_conditions_joined(self):
        """Only True-status conditions appear, comma-joined."""
        conditions = [
            {"type": "Ready", "status": "True"},
            {"type": "MemoryPressure", "status": "False"},
            {"type": "Initialized", "status": "True"},
        ]
        result = _summarize_conditions(conditions)
        assert result == "Ready, Initialized"

    def test_no_true_conditions(self):
        """All False → empty string."""
        conditions = [
            {"type": "Ready", "status": "False"},
        ]
        assert _summarize_conditions(conditions) == ""


# ═══════════════════════════════════════════════════════════════════
#  get_resources (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestGetResources:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_returns_resource_list(self, mock_run, _):
        """get_resources → resources list with name, namespace, phase, conditions.

        kubectl API: `kubectl get <kind> -n <ns> -o json` returns
        {items: [{metadata: {name, namespace, creationTimestamp}, status: {phase, conditions}}]}
        """
        mock_run.return_value = _mock_result(stdout=json.dumps({
            "items": [
                {
                    "metadata": {"name": "web-abc123", "namespace": "default", "creationTimestamp": "2026-01-01T00:00:00Z"},
                    "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
                },
                {
                    "metadata": {"name": "api-def456", "namespace": "default", "creationTimestamp": "2026-01-02T00:00:00Z"},
                    "status": {"phase": "Running", "conditions": []},
                },
            ],
        }))
        result = get_resources(namespace="default", kind="pods")

        assert result["ok"] is True
        assert result["count"] == 2
        assert len(result["resources"]) == 2
        r0 = result["resources"][0]
        assert r0["name"] == "web-abc123"
        assert r0["namespace"] == "default"
        assert r0["phase"] == "Running"
        assert r0["conditions"] == "Ready"
        assert r0["created"] == "2026-01-01T00:00:00Z"

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_namespace_filter_passed(self, mock_run, _):
        """get_resources with namespace → passes `-n <ns>` to kubectl."""
        mock_run.return_value = _mock_result(stdout=json.dumps({"items": []}))
        get_resources(namespace="production", kind="pods")

        args = mock_run.call_args
        assert "-n" in args[0]
        assert "production" in args[0]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_kind_filter_passed(self, mock_run, _):
        """get_resources with kind → passes kind as first arg to kubectl get."""
        mock_run.return_value = _mock_result(stdout=json.dumps({"items": []}))
        get_resources(namespace="default", kind="deployments")

        args = mock_run.call_args
        assert "deployments" in args[0]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_MISSING)
    def test_kubectl_not_available(self, _):
        """get_resources kubectl not available → error."""
        result = get_resources()
        assert result["ok"] is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
#  k8s_pod_logs (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sPodLogs:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_returns_logs(self, mock_run, _):
        """k8s_pod_logs → {ok, pod, namespace, logs} with tail limit.

        kubectl API: `kubectl logs <pod> -n <ns> --tail <n>`
        """
        mock_run.return_value = _mock_result(stdout="line1\nline2\nline3\n")
        result = k8s_pod_logs(namespace="default", pod="web-abc123", tail=50)

        assert result["ok"] is True
        assert result["pod"] == "web-abc123"
        assert result["namespace"] == "default"
        assert "line1" in result["logs"]
        # Verify tail arg passed
        args = mock_run.call_args[0]
        assert "--tail" in args
        assert "50" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_container_filter(self, mock_run, _):
        """k8s_pod_logs with container → `-c <container>` arg passed."""
        mock_run.return_value = _mock_result(stdout="logs here")
        k8s_pod_logs(pod="web-abc", container="sidecar")

        args = mock_run.call_args[0]
        assert "-c" in args
        assert "sidecar" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    def test_missing_pod_name_error(self, _):
        """k8s_pod_logs missing pod name → error without calling kubectl."""
        result = k8s_pod_logs(pod="")
        assert result["ok"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_kubectl_failure(self, mock_run, _):
        """k8s_pod_logs kubectl failure → error dict."""
        mock_run.return_value = _mock_result(returncode=1, stderr="pod not found")
        result = k8s_pod_logs(pod="nonexistent")

        assert result["ok"] is False
        assert "pod not found" in result["error"]


# ═══════════════════════════════════════════════════════════════════
#  k8s_apply (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sApply:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_apply_file(self, mock_run, _, tmp_path: Path):
        """k8s_apply with file path → applies manifest, returns output.

        kubectl API: `kubectl apply -f <file>`
        """
        manifest = tmp_path / "deployment.yaml"
        manifest.write_text("kind: Deployment\n")
        mock_run.return_value = _mock_result(stdout="deployment.apps/api created")

        result = k8s_apply(tmp_path, "deployment.yaml")
        assert result["ok"] is True
        assert "created" in result["output"]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_namespace_override(self, mock_run, _, tmp_path: Path):
        """k8s_apply with namespace override → `-n` arg appended."""
        manifest = tmp_path / "svc.yaml"
        manifest.write_text("kind: Service\n")
        mock_run.return_value = _mock_result(stdout="service/api created")

        k8s_apply(tmp_path, "svc.yaml", namespace="production")
        args = mock_run.call_args[0]
        assert "-n" in args
        assert "production" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_apply_failure(self, mock_run, _, tmp_path: Path):
        """k8s_apply on failure → error dict."""
        manifest = tmp_path / "bad.yaml"
        manifest.write_text("invalid\n")
        mock_run.return_value = _mock_result(returncode=1, stderr="error validating data")

        result = k8s_apply(tmp_path, "bad.yaml")
        assert result["ok"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    def test_path_not_found(self, _, tmp_path: Path):
        """k8s_apply path not found → error (no kubectl called)."""
        result = k8s_apply(tmp_path, "nonexistent.yaml")
        assert result["ok"] is False
        assert "not found" in result["error"].lower() or "Path not found" in result["error"]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_MISSING)
    def test_kubectl_not_available(self, _):
        """0.2.21a: k8s_apply with kubectl unavailable → error."""
        result = k8s_apply(Path("/tmp"), "deploy.yaml")
        assert result["ok"] is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
#  k8s_delete_resource (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sDeleteResource:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_delete_resource(self, mock_run, _):
        """k8s_delete_resource → deletes by kind + name, returns output.

        kubectl API: `kubectl delete <kind> <name> -n <ns>`
        """
        mock_run.return_value = _mock_result(stdout='pod "web-abc" deleted')
        result = k8s_delete_resource("pod", "web-abc", namespace="default")

        assert result["ok"] is True
        assert "deleted" in result["output"]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_namespace_passed(self, mock_run, _):
        """k8s_delete_resource with namespace → `-n` arg passed."""
        mock_run.return_value = _mock_result(stdout="deleted")
        k8s_delete_resource("deployment", "api", namespace="staging")

        args = mock_run.call_args[0]
        assert "-n" in args
        assert "staging" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    def test_missing_kind_or_name_error(self, _):
        """k8s_delete_resource missing kind or name → error."""
        result = k8s_delete_resource("", "web")
        assert result["ok"] is False
        assert "error" in result

        result = k8s_delete_resource("pod", "")
        assert result["ok"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_MISSING)
    def test_kubectl_not_available(self, _):
        """0.2.21a: k8s_delete_resource with kubectl unavailable → error."""
        result = k8s_delete_resource("pod", "web")
        assert result["ok"] is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
#  k8s_scale (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sScale:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_scale_deployment(self, mock_run, _):
        """k8s_scale → scales deployment, returns output.

        kubectl API: `kubectl scale deployment/<name> --replicas=<n> -n <ns>`
        """
        mock_run.return_value = _mock_result(stdout="deployment.apps/api scaled")
        result = k8s_scale("api", 5, namespace="default")

        assert result["ok"] is True
        assert "scaled" in result["output"]
        args = mock_run.call_args[0]
        assert "deployment/api" in args
        assert "--replicas=5" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_kind_override(self, mock_run, _):
        """k8s_scale with kind override → `{kind}/{name}` format."""
        mock_run.return_value = _mock_result(stdout="scaled")
        k8s_scale("db", 3, kind="statefulset")

        args = mock_run.call_args[0]
        assert "statefulset/db" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    def test_missing_name_error(self, _):
        """k8s_scale missing name → error."""
        result = k8s_scale("", 3)
        assert result["ok"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_MISSING)
    def test_kubectl_not_available(self, _):
        """0.2.21a: k8s_scale with kubectl unavailable → error."""
        result = k8s_scale("api", 3)
        assert result["ok"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_subprocess_exception(self, mock_run, _):
        """0.2.21b: k8s_scale subprocess exception → error captured, not raised."""
        mock_run.return_value = _mock_result(returncode=1, stderr="connection refused")
        result = k8s_scale("api", 3)
        assert result["ok"] is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
#  k8s_events (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sEvents:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_returns_events(self, mock_run, _):
        """k8s_events → events list with type, reason, object, message, count.

        kubectl API: `kubectl get events -n <ns> -o json` returns
        {items: [{type, reason, involvedObject: {kind, name}, message, count}]}
        """
        mock_run.return_value = _mock_result(stdout=json.dumps({
            "items": [
                {
                    "type": "Normal",
                    "reason": "Scheduled",
                    "involvedObject": {"kind": "Pod", "name": "web-abc"},
                    "message": "Successfully assigned",
                    "count": 1,
                    "firstTimestamp": "2026-01-01T00:00:00Z",
                    "lastTimestamp": "2026-01-01T00:01:00Z",
                },
            ],
        }))
        result = k8s_events(namespace="default")

        assert result["ok"] is True
        assert result["count"] == 1
        ev = result["events"][0]
        assert ev["type"] == "Normal"
        assert ev["reason"] == "Scheduled"
        assert ev["object"] == "Pod/web-abc"
        assert ev["message"] == "Successfully assigned"
        assert ev["count"] == 1

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_namespace_filter(self, mock_run, _):
        """k8s_events with namespace → `-n <ns>` passed to kubectl."""
        mock_run.return_value = _mock_result(stdout=json.dumps({"items": []}))
        k8s_events(namespace="monitoring")

        args = mock_run.call_args[0]
        assert "-n" in args
        assert "monitoring" in args

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_kubectl_failure(self, mock_run, _):
        """k8s_events kubectl failure → error dict."""
        mock_run.return_value = _mock_result(returncode=1, stderr="forbidden")
        result = k8s_events()

        assert result["ok"] is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
#  k8s_describe (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sDescribe:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_describe_resource(self, mock_run, _):
        """k8s_describe → description string for kind/name.

        kubectl API: `kubectl describe <kind> <name> -n <ns>`
        """
        mock_run.return_value = _mock_result(stdout="Name: web-abc\nNamespace: default\n")
        result = k8s_describe("pod", "web-abc")

        assert result["ok"] is True
        assert "Name: web-abc" in result["description"]

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    def test_missing_kind_or_name_error(self, _):
        """k8s_describe missing kind/name → error (input validation)."""
        result = k8s_describe("", "web")
        assert result["ok"] is False

        result = k8s_describe("pod", "")
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════════
#  k8s_namespaces (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sNamespaces:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_returns_namespace_list(self, mock_run, _):
        """k8s_namespaces → list with name, status, created.

        kubectl API: `kubectl get namespaces -o json` returns
        {items: [{metadata: {name, creationTimestamp}, status: {phase}}]}
        """
        mock_run.return_value = _mock_result(stdout=json.dumps({
            "items": [
                {
                    "metadata": {"name": "default", "creationTimestamp": "2026-01-01T00:00:00Z"},
                    "status": {"phase": "Active"},
                },
                {
                    "metadata": {"name": "kube-system", "creationTimestamp": "2026-01-01T00:00:00Z"},
                    "status": {"phase": "Active"},
                },
            ],
        }))
        result = k8s_namespaces()

        assert result["ok"] is True
        assert result["count"] == 2
        ns = result["namespaces"][0]
        assert ns["name"] == "default"
        assert ns["status"] == "Active"
        assert ns["created"] == "2026-01-01T00:00:00Z"


# ═══════════════════════════════════════════════════════════════════
#  k8s_storage_classes (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestK8sStorageClasses:
    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_returns_storage_class_list(self, mock_run, _):
        """k8s_storage_classes → list with name, provisioner, is_default, reclaim_policy.

        kubectl API: `kubectl get storageclasses -o json` returns
        {items: [{metadata: {name, annotations}, provisioner, reclaimPolicy, volumeBindingMode}]}
        """
        mock_run.return_value = _mock_result(stdout=json.dumps({
            "items": [
                {
                    "metadata": {
                        "name": "gp3",
                        "annotations": {
                            "storageclass.kubernetes.io/is-default-class": "true",
                        },
                    },
                    "provisioner": "ebs.csi.aws.com",
                    "reclaimPolicy": "Delete",
                    "volumeBindingMode": "WaitForFirstConsumer",
                    "parameters": {"type": "gp3"},
                },
                {
                    "metadata": {"name": "local-path", "annotations": {}},
                    "provisioner": "rancher.io/local-path",
                    "reclaimPolicy": "Delete",
                    "volumeBindingMode": "WaitForFirstConsumer",
                },
            ],
        }))
        result = k8s_storage_classes()

        assert result["ok"] is True
        assert result["count"] == 2
        sc0 = result["storage_classes"][0]
        assert sc0["name"] == "gp3"
        assert sc0["provisioner"] == "ebs.csi.aws.com"
        assert sc0["is_default"] is True
        assert sc0["reclaim_policy"] == "Delete"
        assert sc0["volume_binding_mode"] == "WaitForFirstConsumer"
        assert sc0["parameters"] == {"type": "gp3"}

    @patch("src.core.services.k8s_cluster._kubectl_available", return_value=_KUBECTL_OK)
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_identifies_default_class(self, mock_run, _):
        """k8s_storage_classes identifies default class via annotation.

        K8s spec: The default StorageClass is marked via the annotation
        `storageclass.kubernetes.io/is-default-class: "true"`.
        """
        mock_run.return_value = _mock_result(stdout=json.dumps({
            "items": [
                {
                    "metadata": {"name": "standard", "annotations": {}},
                    "provisioner": "k8s.io/minikube-hostpath",
                },
                {
                    "metadata": {
                        "name": "fast",
                        "annotations": {
                            "storageclass.kubernetes.io/is-default-class": "true",
                        },
                    },
                    "provisioner": "ebs.csi.aws.com",
                },
            ],
        }))
        result = k8s_storage_classes()

        assert result["default_class"] == "fast"
        assert result["storage_classes"][0]["is_default"] is False
        assert result["storage_classes"][1]["is_default"] is True
