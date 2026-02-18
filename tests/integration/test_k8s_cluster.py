"""
Integration tests for k8s cluster operations.

Primary path: runs against a LIVE minikube cluster.
Fallback: mocks with a ⚠️ BIG WARNING if no cluster is available.

Run with:
    pytest tests/integration/test_k8s_cluster.py -v
"""

import subprocess
import warnings
from unittest.mock import patch

import pytest

from src.core.services.k8s_cluster import cluster_status, _detect_cluster_type


# ═══════════════════════════════════════════════════════════════════
#  Cluster detection fixture
# ═══════════════════════════════════════════════════════════════════


def _minikube_alive() -> bool:
    """Check if minikube cluster is running and reachable."""
    try:
        result = subprocess.run(
            ["minikube", "status", "--format", "{{.Host}}"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "Running" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _cluster_reachable() -> bool:
    """Check if any kubectl-reachable cluster is available."""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


MINIKUBE_ALIVE = _minikube_alive()
CLUSTER_REACHABLE = _cluster_reachable()

if not CLUSTER_REACHABLE:
    warnings.warn(
        "\n"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║  ⚠️  NO LIVE CLUSTER AVAILABLE — FALLING BACK TO MOCKS  ⚠️  ║\n"
        "║                                                            ║\n"
        "║  These tests are DESIGNED to run against a real minikube   ║\n"
        "║  cluster. Mock fallback covers basic shapes but does NOT   ║\n"
        "║  validate real cluster interaction.                        ║\n"
        "║                                                            ║\n"
        "║  To run properly: minikube start --driver=docker           ║\n"
        "╚══════════════════════════════════════════════════════════════╝\n",
        stacklevel=1,
    )


# ═══════════════════════════════════════════════════════════════════
#  0.2.2g  Cluster connectivity detection — LIVE
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not CLUSTER_REACHABLE,
    reason="No live cluster — see mock fallback tests below",
)
class TestClusterStatusLive:
    """Tests that run against a real cluster (minikube or other)."""

    def test_connected_true(self):
        """Live cluster → connected=True."""
        result = cluster_status()

        assert isinstance(result, dict)
        assert result["connected"] is True

    def test_context_is_string(self):
        """Context is a non-empty string."""
        result = cluster_status()

        assert "context" in result
        assert isinstance(result["context"], str)
        assert len(result["context"]) > 0

    def test_nodes_list(self):
        """At least one node, each with required fields."""
        result = cluster_status()

        assert "nodes" in result
        assert isinstance(result["nodes"], list)
        assert len(result["nodes"]) >= 1

        node = result["nodes"][0]
        assert isinstance(node, dict)
        assert "name" in node
        assert "ready" in node
        assert isinstance(node["ready"], bool)
        assert node["ready"] is True  # healthy cluster
        assert "version" in node
        assert isinstance(node["version"], str)

    def test_namespaces_include_defaults(self):
        """Default, kube-system, kube-public namespaces must exist."""
        result = cluster_status()

        assert "namespaces" in result
        assert isinstance(result["namespaces"], list)
        assert "default" in result["namespaces"]
        assert "kube-system" in result["namespaces"]
        assert "kube-public" in result["namespaces"]

    def test_return_shape_has_all_keys(self):
        """Full return shape validation including cluster_type."""
        result = cluster_status()

        required_keys = {"connected", "context", "nodes", "namespaces", "cluster_type"}
        assert required_keys.issubset(set(result.keys()))

    def test_cluster_type_present(self):
        """cluster_type is a dict with type and detected_via."""
        result = cluster_status()

        ct = result["cluster_type"]
        assert isinstance(ct, dict)
        assert "type" in ct
        assert "detected_via" in ct
        assert isinstance(ct["type"], str)
        assert isinstance(ct["detected_via"], str)


@pytest.mark.skipif(
    not MINIKUBE_ALIVE,
    reason="Minikube not running — skipping minikube-specific tests",
)
class TestClusterStatusMinikube:
    """Tests specific to minikube cluster type detection."""

    def test_context_is_minikube(self):
        """When minikube is running → context name is 'minikube'."""
        result = cluster_status()

        assert result["context"] == "minikube"

    def test_single_node_cluster(self):
        """Minikube is single-node → exactly 1 node."""
        result = cluster_status()

        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "minikube"

    def test_cluster_type_is_minikube(self):
        """0.2.2h: Minikube cluster → type='minikube'."""
        result = cluster_status()

        assert result["cluster_type"]["type"] == "minikube"
        assert result["cluster_type"]["detected_via"] == "context_name"


# ═══════════════════════════════════════════════════════════════════
#  0.2.2h  Cluster type detection — unit tests (pure logic)
# ═══════════════════════════════════════════════════════════════════


class TestDetectClusterType:
    """Unit tests for _detect_cluster_type — no cluster needed.

    0.2.2h: pattern matching on context names and node labels.
    """

    _REQUIRED_KEYS = {"type", "detected_via"}

    def test_minikube_from_context(self):
        """Context 'minikube' → type='minikube'."""
        result = _detect_cluster_type("minikube", [])
        assert isinstance(result, dict)
        assert set(result.keys()) == self._REQUIRED_KEYS
        assert result["type"] == "minikube"
        assert result["detected_via"] == "context_name"

    def test_kind_from_context(self):
        """Context 'kind-my-cluster' → type='kind'."""
        result = _detect_cluster_type("kind-my-cluster", [])
        assert result["type"] == "kind"
        assert result["detected_via"] == "context_name"

    def test_kind_bare_name(self):
        """Context 'kind-' prefix required."""
        result = _detect_cluster_type("kind-test", [])
        assert result["type"] == "kind"

    def test_docker_desktop_from_context(self):
        """Context 'docker-desktop' → type='docker_desktop'."""
        result = _detect_cluster_type("docker-desktop", [])
        assert result["type"] == "docker_desktop"
        assert result["detected_via"] == "context_name"

    def test_k3d_from_context(self):
        """Context 'k3d-mycluster' → type='k3d'."""
        result = _detect_cluster_type("k3d-mycluster", [])
        assert result["type"] == "k3d"
        assert result["detected_via"] == "context_name"

    def test_k3s_from_node_version(self):
        """Node kubelet version containing '+k3s' → type='k3s'."""
        nodes = [{"name": "node1", "ready": True, "roles": "", "version": "v1.28.3+k3s1"}]
        result = _detect_cluster_type("default", nodes)
        assert result["type"] == "k3s"
        assert result["detected_via"] == "node_version"

    def test_eks_from_arn_context(self):
        """Context 'arn:aws:eks:us-east-1:123456:cluster/prod' → type='eks'."""
        result = _detect_cluster_type(
            "arn:aws:eks:us-east-1:123456789:cluster/my-cluster", [],
        )
        assert result["type"] == "eks"
        assert result["detected_via"] == "context_name"

    def test_eks_from_eks_prefix(self):
        """Context containing 'eks' patterns."""
        result = _detect_cluster_type("eks-prod-cluster", [])
        assert result["type"] == "eks"

    def test_aks_from_context(self):
        """Context containing Azure AKS patterns."""
        result = _detect_cluster_type("my-aks-cluster", [])
        assert result["type"] == "aks"
        assert result["detected_via"] == "context_name"

    def test_gke_from_context(self):
        """Context 'gke_project_region_cluster' → type='gke'."""
        result = _detect_cluster_type("gke_my-project_us-central1_prod", [])
        assert result["type"] == "gke"
        assert result["detected_via"] == "context_name"

    def test_unknown_fallback(self):
        """Unrecognized context → type='unknown'."""
        result = _detect_cluster_type("my-custom-cluster", [])
        assert result["type"] == "unknown"
        assert result["detected_via"] == "none"

    def test_empty_context(self):
        """Empty/unknown context → type='unknown'."""
        result = _detect_cluster_type("", [])
        assert result["type"] == "unknown"

    def test_unknown_context_string(self):
        """Context 'unknown' (from error fallback) → type='unknown'."""
        result = _detect_cluster_type("unknown", [])
        assert result["type"] == "unknown"

    def test_return_shape_always_consistent(self):
        """Every result has exactly {type, detected_via}."""
        for ctx in ["minikube", "kind-x", "docker-desktop", "gke_p_r_c", "random"]:
            result = _detect_cluster_type(ctx, [])
            assert set(result.keys()) == self._REQUIRED_KEYS
            assert isinstance(result["type"], str)
            assert isinstance(result["detected_via"], str)

    def test_valid_type_values(self):
        """Type is always from the known enum set."""
        valid_types = {
            "minikube", "kind", "docker_desktop",
            "k3s", "k3d", "eks", "aks", "gke", "unknown",
        }
        for ctx, expected in [
            ("minikube", "minikube"),
            ("kind-test", "kind"),
            ("docker-desktop", "docker_desktop"),
            ("k3d-dev", "k3d"),
            ("gke_proj_region_name", "gke"),
            ("arn:aws:eks:us-east-1:123:cluster/x", "eks"),
            ("my-aks-cluster", "aks"),
            ("random-thing", "unknown"),
        ]:
            result = _detect_cluster_type(ctx, [])
            assert result["type"] in valid_types, f"Unexpected type for context '{ctx}': {result['type']}"
            assert result["type"] == expected


# ═══════════════════════════════════════════════════════════════════
#  0.2.2g  Cluster connectivity detection — MOCK FALLBACK
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    CLUSTER_REACHABLE,
    reason="Live cluster available — running live tests instead",
)
class TestClusterStatusMockFallback:
    """Mock-based tests when no live cluster is available.

    ⚠️  These are a SAFETY NET, not the primary test path.
    ⚠️  The real tests above are what matter.
    """

    @patch("src.core.services.k8s_cluster._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kubectl_not_available(self, _mock):
        """kubectl missing → connected=False, error message."""
        result = cluster_status()

        assert isinstance(result, dict)
        assert result["connected"] is False
        assert "error" in result

    @patch("src.core.services.k8s_cluster._kubectl_available",
           return_value={"available": True, "version": "v1.35.1"})
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_cluster_unreachable(self, mock_run, _mock_avail):
        """kubectl available but cluster unreachable → connected=False."""
        mock_result = type("Result", (), {
            "returncode": 1, "stdout": "", "stderr": "connection refused",
        })()
        mock_run.return_value = mock_result

        result = cluster_status()

        assert result["connected"] is False

    @patch("src.core.services.k8s_cluster._kubectl_available",
           return_value={"available": True, "version": "v1.35.1"})
    @patch("src.core.services.k8s_cluster._run_kubectl")
    def test_return_shape_with_mocks(self, mock_run, _mock_avail):
        """Even with mocks, return shape has required keys."""
        mock_result = type("Result", (), {
            "returncode": 1, "stdout": "", "stderr": "",
        })()
        mock_run.return_value = mock_result

        result = cluster_status()

        assert isinstance(result, dict)
        assert "connected" in result
        assert isinstance(result["connected"], bool)

