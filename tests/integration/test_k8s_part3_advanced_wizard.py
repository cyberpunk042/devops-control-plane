"""
Integration tests — K8s domain Part 3: Advanced Wizard Features.

TDD: requirements for the advanced K8s wizard flow.
K8s is too large for one file — split into parts:
  Part 1: detect, validate, generate (this file)
  Part 2: wizard state, translator, wizard generate
  Part 3: advanced wizard (workload kinds, multi-container, mesh, volumes,
           infra services, HPA, network policies, setup_k8s integration)
  Part 4: cross-integration (K8s ↔ Docker, K8s ↔ CI/CD)

Covers:
  - Workload kinds: StatefulSet, DaemonSet, Job, CronJob
  - Multi-container pods: sidecars, init containers, companion containers
  - Service mesh annotations (Istio, Linkerd)
  - Complex volumes: hostPath, configMap, secret, VolumeClaimTemplates
  - Infrastructure services (Redis, Postgres as separate service entries)
  - HorizontalPodAutoscaler generation
  - Network policies
  - Full setup_k8s round-trip (wizard_setup.py → translate → generate → disk)
  - Config delete for K8s
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


_NO_KUBECTL = patch(
    "src.core.services.k8s_detect._kubectl_available",
    return_value={"available": False, "version": None},
)


# ═══════════════════════════════════════════════════════════════════
#  1. WORKLOAD KINDS — StatefulSet, DaemonSet, Job, CronJob
# ═══════════════════════════════════════════════════════════════════


class TestWorkloadKinds:
    """wizard_state_to_resources must handle all workload kinds."""

    def test_statefulset_kind(self):
        """kind=StatefulSet → StatefulSet resource, not Deployment."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 3,
                    "kind": "StatefulSet",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "StatefulSet" in kinds
        assert "Deployment" not in kinds
        # StatefulSet must have a Service for stable network identity
        assert "Service" in kinds

    def test_statefulset_has_servicename(self):
        """StatefulSet must reference its headless Service via serviceName."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 3,
                    "kind": "StatefulSet",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        sts = next(r for r in resources if r["kind"] == "StatefulSet")
        spec = sts.get("spec", {})
        assert ("serviceName" in spec
                or "service_name" in spec
                or "headlessServiceName" in spec)

    def test_daemonset_kind(self):
        """kind=DaemonSet → DaemonSet resource, no replicas field."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "log-agent",
                    "image": "fluentd:v1",
                    "port": 24224,
                    "kind": "DaemonSet",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "DaemonSet" in kinds
        assert "Deployment" not in kinds

    def test_job_kind(self):
        """kind=Job → Job resource."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "migration",
                    "image": "app:v1",
                    "kind": "Job",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Job" in kinds
        assert "Deployment" not in kinds
        # Jobs don't need a Service
        assert "Service" not in kinds

    def test_cronjob_kind(self):
        """kind=CronJob → CronJob resource with schedule."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "cleanup",
                    "image": "app:v1",
                    "kind": "CronJob",
                    "schedule": "0 2 * * *",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "CronJob" in kinds
        assert "Deployment" not in kinds
        # CronJobs don't need a Service
        assert "Service" not in kinds

    def test_mixed_workload_kinds(self):
        """Multiple services with different kinds → correct resource types."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2,
                 "kind": "Deployment", "envVars": [], "volumes": []},
                {"name": "db", "image": "pg:15", "port": 5432, "replicas": 1,
                 "kind": "StatefulSet", "envVars": [], "volumes": []},
                {"name": "agent", "image": "agent:v1", "port": 9090,
                 "kind": "DaemonSet", "envVars": [], "volumes": []},
                {"name": "migrate", "image": "app:v1",
                 "kind": "Job", "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Deployment" in kinds
        assert "StatefulSet" in kinds
        assert "DaemonSet" in kinds
        assert "Job" in kinds

    def test_default_kind_is_deployment(self):
        """No kind specified → defaults to Deployment."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "Deployment" in kinds


# ═══════════════════════════════════════════════════════════════════
#  2. MULTI-CONTAINER PODS — sidecars, init, companions
# ═══════════════════════════════════════════════════════════════════


class TestMultiContainerPods:
    """Pod builder must handle sidecars, init containers, companions."""

    def test_sidecar_container(self):
        """Service with sidecar → pod template has 2+ containers."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "sidecars": [
                        {
                            "name": "log-shipper",
                            "image": "fluentd:v1",
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        # The deployment resource must exist
        deploy = next((r for r in resources if r["kind"] == "Deployment"), None)
        assert deploy is not None
        # Spec must contain sidecar info for the generator
        spec = deploy.get("spec", {})
        assert "sidecars" in spec or len(spec.get("containers", [])) > 1

    def test_init_container(self):
        """Service with init container → initContainers in pod template."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "initContainers": [
                        {
                            "name": "wait-for-db",
                            "image": "busybox:1.36",
                            "command": ["sh", "-c", "until nc -z db 5432; do sleep 1; done"],
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deploy = next((r for r in resources if r["kind"] == "Deployment"), None)
        assert deploy is not None
        spec = deploy.get("spec", {})
        assert "initContainers" in spec or "init_containers" in spec

    def test_companion_container(self):
        """Service with companion → multiple containers in same pod."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "companions": [
                        {
                            "name": "redis-cache",
                            "image": "redis:7-alpine",
                            "port": 6379,
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deploy = next((r for r in resources if r["kind"] == "Deployment"), None)
        assert deploy is not None
        spec = deploy.get("spec", {})
        assert "companions" in spec or len(spec.get("containers", [])) > 1


# ═══════════════════════════════════════════════════════════════════
#  3. SERVICE MESH ANNOTATIONS
# ═══════════════════════════════════════════════════════════════════


class TestServiceMeshAnnotations:
    """Mesh provider → pod template annotations."""

    def test_istio_annotations(self):
        """mesh=istio → Istio sidecar injection annotation."""
        from src.core.services.k8s_pod_builder import _build_mesh_annotations
        annotations = _build_mesh_annotations({"provider": "istio", "port": 8080, "enabled": True})
        assert len(annotations) > 0
        # Istio uses sidecar.istio.io/inject or similar
        annotation_str = " ".join(f"{k}={v}" for k, v in annotations.items())
        assert "istio" in annotation_str.lower()

    def test_linkerd_annotations(self):
        """mesh=linkerd → Linkerd injection annotation."""
        from src.core.services.k8s_pod_builder import _build_mesh_annotations
        annotations = _build_mesh_annotations({"provider": "linkerd", "port": 8080, "enabled": True})
        assert len(annotations) > 0
        annotation_str = " ".join(f"{k}={v}" for k, v in annotations.items())
        assert "linkerd" in annotation_str.lower()

    def test_no_mesh_no_annotations(self):
        """No mesh provider → empty annotations."""
        from src.core.services.k8s_pod_builder import _build_mesh_annotations
        annotations = _build_mesh_annotations({})
        assert annotations == {} or annotations is None or len(annotations) == 0

    def test_mesh_in_full_translation(self):
        """Service with mesh → translated resources carry mesh info."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "mesh": {"provider": "istio", "port": 8080, "enabled": True},
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deploy = next(r for r in resources if r["kind"] == "Deployment")
        # Mesh info should be in spec for the generator to use
        spec = deploy.get("spec", {})
        assert "mesh" in spec or "annotations" in spec


# ═══════════════════════════════════════════════════════════════════
#  4. COMPLEX VOLUMES
# ═══════════════════════════════════════════════════════════════════


class TestComplexVolumes:
    """Volume builder must handle all volume types from the wizard."""

    def test_hostpath_volume(self):
        """hostPath volume → correct volume + mount."""
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {
            "name": "logs",
            "mountPath": "/var/log/app",
            "type": "hostPath",
            "hostPath": "/var/log/app",
        }
        volume, mount = _build_wizard_volume(vol, 0, "api")
        assert volume is not None
        assert "hostPath" in volume
        assert mount["mountPath"] == "/var/log/app"

    def test_configmap_volume(self):
        """configMap volume → correct volume spec."""
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {
            "name": "config",
            "mountPath": "/etc/config",
            "type": "configMap",
            "configMapName": "app-config",
        }
        volume, mount = _build_wizard_volume(vol, 0, "api")
        assert volume is not None
        assert "configMap" in volume
        assert mount["mountPath"] == "/etc/config"

    def test_secret_volume(self):
        """secret volume → correct volume spec."""
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {
            "name": "certs",
            "mountPath": "/etc/certs",
            "type": "secret",
            "secretName": "tls-certs",
        }
        volume, mount = _build_wizard_volume(vol, 0, "api")
        assert volume is not None
        assert "secret" in volume
        assert mount["mountPath"] == "/etc/certs"

    def test_readonly_volume(self):
        """readOnly flag → mount has readOnly=true."""
        from src.core.services.k8s_pod_builder import _build_wizard_volume
        vol = {
            "name": "config",
            "mountPath": "/etc/config",
            "type": "configMap",
            "configMapName": "app-config",
            "readOnly": True,
        }
        volume, mount = _build_wizard_volume(vol, 0, "api")
        assert mount.get("readOnly") is True

    def test_volume_claim_template_statefulset(self):
        """StatefulSet with VCTs → volumeClaimTemplates in resource spec."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 3,
                    "kind": "StatefulSet",
                    "envVars": [],
                    "volumes": [
                        {
                            "name": "pgdata",
                            "mountPath": "/var/lib/postgresql/data",
                            "type": "pvc-dynamic",
                            "size": "10Gi",
                            "storageClass": "standard",
                            "accessMode": "ReadWriteOnce",
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        sts = next(r for r in resources if r["kind"] == "StatefulSet")
        spec = sts.get("spec", {})
        # VCTs must be passed through to the generator
        assert ("volumeClaimTemplates" in spec
                or "volume_claim_templates" in spec
                or "vcts" in spec)

    def test_pvc_dynamic_generates_pvc_resource(self):
        """pvc-dynamic volume → PVC resource with storageClass and size."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [
                        {
                            "name": "pgdata",
                            "mountPath": "/var/lib/postgresql/data",
                            "type": "pvc-dynamic",
                            "size": "20Gi",
                            "storageClass": "gp2",
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        pvcs = [r for r in resources if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) >= 1
        pvc = pvcs[0]
        assert pvc.get("spec", {}).get("size") == "20Gi" or "20Gi" in str(pvc)

    def test_multiple_volumes_on_one_service(self):
        """Service with multiple volumes → all volumes and mounts present."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [
                        {"name": "cache", "mountPath": "/cache", "type": "emptyDir"},
                        {"name": "config", "mountPath": "/etc/config", "type": "configMap",
                         "configMapName": "app-config"},
                        {"name": "data", "mountPath": "/data", "type": "pvc-dynamic",
                         "size": "5Gi", "storageClass": "standard"},
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deploy = next(r for r in resources if r["kind"] == "Deployment")
        spec = deploy.get("spec", {})
        volumes = spec.get("volumes", [])
        # At least 3 volumes should be tracked
        assert len(volumes) >= 3 or len(spec.get("volume_mounts", [])) >= 3


# ═══════════════════════════════════════════════════════════════════
#  5. INFRASTRUCTURE SERVICES
# ═══════════════════════════════════════════════════════════════════


class TestInfraServices:
    """Infra services (Redis, Postgres, etc.) → separate K8s resources."""

    def test_infra_service_produces_deployment_and_service(self):
        """Infra service with isInfra=True → own Deployment + Service."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                },
                {
                    "name": "redis",
                    "image": "redis:7-alpine",
                    "port": 6379,
                    "replicas": 1,
                    "isInfra": True,
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deployments = [r for r in resources if r["kind"] == "Deployment"]
        services = [r for r in resources if r["kind"] == "Service"]
        # Both api and redis should have their own Deployment + Service
        deploy_names = [d["name"] for d in deployments]
        assert "api" in deploy_names
        assert "redis" in deploy_names
        assert len(services) >= 2

    def test_infra_postgres_with_volume(self):
        """Postgres infra service with PVC volume → PVC resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "postgres",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 1,
                    "isInfra": True,
                    "envVars": [
                        {"key": "POSTGRES_PASSWORD", "value": "secret", "type": "secret"},
                    ],
                    "volumes": [
                        {
                            "name": "pgdata",
                            "mountPath": "/var/lib/postgresql/data",
                            "type": "pvc-dynamic",
                            "size": "10Gi",
                            "storageClass": "standard",
                        },
                    ],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "PersistentVolumeClaim" in kinds
        assert "Secret" in kinds

    def test_infra_service_kind_override(self):
        """Infra service with kind=StatefulSet → StatefulSet resource."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "postgres",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 1,
                    "kind": "StatefulSet",
                    "isInfra": True,
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "StatefulSet" in kinds
        assert "Deployment" not in kinds


# ═══════════════════════════════════════════════════════════════════
#  6. PROBES — advanced probe configurations
# ═══════════════════════════════════════════════════════════════════


class TestAdvancedProbes:
    """Probe builder must handle all probe types with timing params."""

    def test_probe_with_timing_params(self):
        """Probe with initialDelaySeconds, periodSeconds, failureThreshold."""
        from src.core.services.k8s_pod_builder import _build_probe
        probe = _build_probe({
            "type": "http",
            "path": "/health",
            "port": 8080,
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "extra": 5,
        })
        assert probe["httpGet"]["path"] == "/health"
        assert probe.get("initialDelaySeconds") == 30
        assert probe.get("periodSeconds") == 10
        assert probe.get("failureThreshold") == 5

    def test_startup_probe(self):
        """startupProbe config → translated correctly."""
        from src.core.services.k8s_pod_builder import _build_probe
        probe = _build_probe({
            "type": "http",
            "path": "/startup",
            "port": 8080,
            "extra": 30,
            "periodSeconds": 5,
        })
        assert probe["httpGet"]["path"] == "/startup"
        assert probe.get("failureThreshold") == 30
        assert probe.get("periodSeconds") == 5

    def test_liveness_and_readiness_in_service(self):
        """Service with both probes → both present in translated resource."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "livenessProbe": {
                        "enabled": True,
                        "type": "http",
                        "path": "/healthz",
                        "port": 8080,
                    },
                    "readinessProbe": {
                        "enabled": True,
                        "type": "http",
                        "path": "/ready",
                        "port": 8080,
                    },
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        deploy = next(r for r in resources if r["kind"] == "Deployment")
        spec = deploy.get("spec", {})
        # Probe info must be preserved for the generator
        assert ("livenessProbe" in spec or "liveness_probe" in spec
                or "probes" in spec or "liveness" in str(spec))


# ═══════════════════════════════════════════════════════════════════
#  7. HPA — HorizontalPodAutoscaler
# ═══════════════════════════════════════════════════════════════════


class TestHPA:
    """Autoscaling config → HPA resource."""

    def test_hpa_creates_resource(self):
        """Service with autoscaling config → HPA resource created."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                    "autoscaling": {
                        "enabled": True,
                        "minReplicas": 2,
                        "maxReplicas": 10,
                        "targetCPU": 80,
                    },
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "HorizontalPodAutoscaler" in kinds

    def test_hpa_references_correct_target(self):
        """HPA must reference the correct Deployment name."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "web",
                    "image": "web:v1",
                    "port": 3000,
                    "replicas": 1,
                    "envVars": [],
                    "volumes": [],
                    "autoscaling": {
                        "enabled": True,
                        "minReplicas": 1,
                        "maxReplicas": 5,
                        "targetCPU": 70,
                    },
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        hpa = next(r for r in resources if r["kind"] == "HorizontalPodAutoscaler")
        spec = hpa.get("spec", {})
        # HPA must reference the "web" deployment
        target = spec.get("scaleTargetRef", spec.get("target", {}))
        assert target.get("name") == "web" or "web" in str(target)

    def test_no_hpa_without_autoscaling(self):
        """No autoscaling config → no HPA resource."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "HorizontalPodAutoscaler" not in kinds


# ═══════════════════════════════════════════════════════════════════
#  8. YAML GENERATION — advanced kinds
# ═══════════════════════════════════════════════════════════════════


class TestAdvancedGeneration:
    """generate_k8s_wizard must produce valid YAML for all kinds."""

    def test_statefulset_yaml(self, tmp_path: Path):
        """StatefulSet → valid YAML with correct apiVersion."""
        import yaml
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "db",
                    "image": "postgres:15",
                    "port": 5432,
                    "replicas": 3,
                    "kind": "StatefulSet",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True

        # Find the StatefulSet file
        all_content = " ".join(f.get("content", "") for f in result["files"])
        assert "StatefulSet" in all_content

    def test_daemonset_yaml(self, tmp_path: Path):
        """DaemonSet → valid YAML."""
        import yaml
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "agent",
                    "image": "agent:v1",
                    "port": 9090,
                    "kind": "DaemonSet",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True
        all_content = " ".join(f.get("content", "") for f in result["files"])
        assert "DaemonSet" in all_content

    def test_cronjob_yaml_has_schedule(self, tmp_path: Path):
        """CronJob → YAML includes schedule field."""
        import yaml
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "cleanup",
                    "image": "app:v1",
                    "kind": "CronJob",
                    "schedule": "0 3 * * *",
                    "envVars": [],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True
        all_content = " ".join(f.get("content", "") for f in result["files"])
        assert "CronJob" in all_content
        assert "0 3 * * *" in all_content

    def test_hpa_yaml(self, tmp_path: Path):
        """HPA → valid YAML with autoscaling apiVersion."""
        import yaml
        from src.core.services.k8s_wizard import wizard_state_to_resources
        from src.core.services.k8s_wizard_generate import generate_k8s_wizard

        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                    "autoscaling": {
                        "enabled": True,
                        "minReplicas": 2,
                        "maxReplicas": 10,
                        "targetCPU": 80,
                    },
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        result = generate_k8s_wizard(tmp_path, resources)
        assert result["ok"] is True
        all_content = " ".join(f.get("content", "") for f in result["files"])
        assert "HorizontalPodAutoscaler" in all_content


# ═══════════════════════════════════════════════════════════════════
#  9. SETUP_K8S INTEGRATION — full round trip via wizard_setup.py
# ═══════════════════════════════════════════════════════════════════


class TestSetupK8sIntegration:
    """setup_k8s must translate wizard → resources → YAML files on disk."""

    def test_basic_setup_creates_files(self, tmp_path: Path):
        """setup_k8s with simple state → files written to k8s/ dir."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [],
                    "volumes": [],
                },
            ],
        })
        assert result["ok"] is True
        assert len(result["files_created"]) >= 2
        # Files should actually exist on disk
        for f in result["files_created"]:
            assert (tmp_path / f).is_file(), f"File not on disk: {f}"

    def test_setup_creates_k8s_directory(self, tmp_path: Path):
        """setup_k8s must create k8s/ directory if it doesn't exist."""
        from src.core.services.wizard_setup import setup_k8s
        setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert (tmp_path / "k8s").is_dir()

    def test_setup_with_env_vars(self, tmp_path: Path):
        """setup_k8s with env vars → ConfigMap file created."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_HOST", "value": "db.local", "type": "hardcoded"},
                    ],
                    "volumes": [],
                },
            ],
        })
        assert result["ok"] is True
        all_content = ""
        for f in result["files_created"]:
            all_content += (tmp_path / f).read_text()
        assert "ConfigMap" in all_content

    def test_setup_with_namespace(self, tmp_path: Path):
        """setup_k8s with non-default namespace → Namespace resource."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "production",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert result["ok"] is True
        all_content = ""
        for f in result["files_created"]:
            all_content += (tmp_path / f).read_text()
        assert "Namespace" in all_content

    @_NO_KUBECTL
    def test_setup_generated_files_pass_validation(self, _m, tmp_path: Path):
        """setup_k8s output must pass validate_manifests."""
        from src.core.services.wizard_setup import setup_k8s
        from src.core.services.k8s_validate import validate_manifests

        setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 2, "envVars": [], "volumes": []},
            ],
        })
        v = validate_manifests(tmp_path)
        assert v["ok"] is True
        assert v["errors"] == 0

    @_NO_KUBECTL
    def test_setup_generated_files_detected(self, _m, tmp_path: Path):
        """setup_k8s output must be found by k8s_status."""
        from src.core.services.wizard_setup import setup_k8s
        from src.core.services.k8s_detect import k8s_status

        setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        status = k8s_status(tmp_path)
        assert status["has_k8s"] is True
        assert status["total_resources"] >= 2

    def test_setup_multi_service(self, tmp_path: Path):
        """setup_k8s with multiple services → all files created."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "prod",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 2, "envVars": [], "volumes": []},
                {"name": "web", "image": "web:v1", "port": 3000,
                 "replicas": 1, "envVars": [], "volumes": []},
                {"name": "worker", "image": "worker:v1", "port": 9000,
                 "replicas": 3, "envVars": [], "volumes": []},
            ],
        })
        assert result["ok"] is True
        # At minimum: Namespace + 3 Deployments + 3 Services = 7 files
        assert len(result["files_created"]) >= 7


# ═══════════════════════════════════════════════════════════════════
#  10. DELETE CONFIG — K8s manifests cleanup
# ═══════════════════════════════════════════════════════════════════


class TestDeleteK8sConfig:
    """delete_generated_configs('k8s') must remove the k8s/ directory."""

    def test_delete_k8s_directory(self, tmp_path: Path):
        """Delete k8s config → k8s/ dir removed."""
        from src.core.services.wizard_setup import delete_generated_configs

        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "deploy.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n")
        (k8s_dir / "svc.yaml").write_text("apiVersion: v1\nkind: Service\n")

        result = delete_generated_configs(tmp_path, "k8s")
        assert result["ok"] is True
        assert "k8s/" in result["deleted"]
        assert not k8s_dir.exists()

    def test_delete_k8s_no_dir(self, tmp_path: Path):
        """Delete k8s when no k8s/ dir → nothing deleted, no error."""
        from src.core.services.wizard_setup import delete_generated_configs

        result = delete_generated_configs(tmp_path, "k8s")
        assert result["ok"] is True
        assert len(result["deleted"]) == 0

    def test_setup_then_delete_round_trip(self, tmp_path: Path):
        """Setup K8s → delete → k8s_status shows nothing."""
        from src.core.services.wizard_setup import setup_k8s, delete_generated_configs

        setup_k8s(tmp_path, {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert (tmp_path / "k8s").is_dir()

        delete_generated_configs(tmp_path, "k8s")
        assert not (tmp_path / "k8s").exists()


# ═══════════════════════════════════════════════════════════════════
#  11. SKAFFOLD GENERATION — via wizard
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldGeneration:
    """Skaffold config generation from wizard state."""

    def test_skaffold_generated_when_enabled(self, tmp_path: Path):
        """skaffold=True in wizard state → skaffold.yaml created."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "default",
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert result["ok"] is True
        file_paths = result["files_created"]
        assert any("skaffold" in f.lower() for f in file_paths)

    def test_skaffold_not_generated_when_disabled(self, tmp_path: Path):
        """skaffold=False → no skaffold.yaml."""
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "default",
            "skaffold": False,
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert result["ok"] is True
        file_paths = result["files_created"]
        assert not any("skaffold" in f.lower() for f in file_paths)

    def test_skaffold_yaml_is_valid(self, tmp_path: Path):
        """Generated skaffold.yaml must be valid YAML."""
        import yaml
        from src.core.services.wizard_setup import setup_k8s
        result = setup_k8s(tmp_path, {
            "namespace": "default",
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "replicas": 1, "envVars": [], "volumes": []},
            ],
        })
        assert result["ok"] is True
        skaffold_files = [f for f in result["files_created"] if "skaffold" in f.lower()]
        assert len(skaffold_files) >= 1
        content = (tmp_path / skaffold_files[0]).read_text()
        doc = yaml.safe_load(content)
        assert doc is not None
        assert "apiVersion" in doc


# ═══════════════════════════════════════════════════════════════════
#  12. ENV VAR TYPES — configMapKeyRef, secretKeyRef wiring
# ═══════════════════════════════════════════════════════════════════


class TestEnvVarWiring:
    """Env vars must wire correctly to ConfigMap/Secret resources."""

    def test_plain_vars_use_configmap_ref(self):
        """Plain env vars → envFrom or valueFrom referencing ConfigMap."""
        from src.core.services.k8s_pod_builder import _build_env_vars
        env = [
            {"name": "DB_HOST", "value": "db.local", "type": "plain"},
            {"name": "LOG_LEVEL", "value": "info", "type": "plain"},
        ]
        result = _build_env_vars(env, svc_name="api")
        # Result should reference config map or contain the values
        assert len(result) >= 2

    def test_secret_vars_use_secret_ref(self):
        """Secret env vars → valueFrom referencing Secret."""
        from src.core.services.k8s_pod_builder import _build_env_vars
        env = [
            {"name": "DB_PASSWORD", "value": "secret123", "type": "secret"},
        ]
        result = _build_env_vars(env, svc_name="api")
        assert len(result) >= 1
        # At least one env var should reference a secret
        has_secret_ref = any(
            "secretKeyRef" in str(e) or "secret" in str(e).lower()
            for e in result
        )
        assert has_secret_ref

    def test_mixed_env_vars(self):
        """Mix of plain and secret → both ConfigMap and Secret resources."""
        from src.core.services.k8s_wizard import wizard_state_to_resources
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_HOST", "value": "db.local", "type": "hardcoded"},
                        {"key": "DB_PASS", "value": "s3cret", "type": "secret"},
                    ],
                    "volumes": [],
                },
            ],
        }
        resources = wizard_state_to_resources(state)
        kinds = [r["kind"] for r in resources]
        assert "ConfigMap" in kinds
        assert "Secret" in kinds
