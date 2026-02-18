"""
Tests for k8s_wizard — state translator (wizard_state_to_resources).

These are pure unit tests: dict in → list[dict] out. No subprocess, no network.
Tests verify the translation layer between wizard UI state and the flat
resource list that generate_k8s_wizard consumes.
"""

from src.core.services.k8s_wizard import (
    _svc_env_to_resources,
    _svc_volumes_to_pvc_resources,
    _sanitize_state,
    wizard_state_to_resources,
)


# ═══════════════════════════════════════════════════════════════════
#  _svc_env_to_resources
# ═══════════════════════════════════════════════════════════════════


class TestSvcEnvToResources:
    def test_hardcoded_creates_configmap(self):
        """Hardcoded env vars → ConfigMap resource."""
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api", [{"key": "DB_HOST", "type": "hardcoded", "value": "localhost"}],
            "default", "k8s",
        )
        assert has_config is True
        assert has_secrets is False
        assert len(resources) == 1
        cm = resources[0]
        assert cm["kind"] == "ConfigMap"
        assert cm["name"] == "api-config"
        assert cm["spec"]["data"]["DB_HOST"] == "localhost"

    def test_secret_creates_secret(self):
        """Secret env vars → Secret resource with placeholder."""
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api", [{"key": "DB_PASSWORD", "type": "secret"}],
            "default", "k8s",
        )
        assert has_config is False
        assert has_secrets is True
        assert len(resources) == 1
        sec = resources[0]
        assert sec["kind"] == "Secret"
        assert sec["name"] == "api-secrets"
        assert sec["spec"]["stringData"]["DB_PASSWORD"] == "CHANGE_ME"

    def test_mixed_creates_both(self):
        """Mix of hardcoded and secret → both ConfigMap and Secret."""
        resources, has_config, has_secrets = _svc_env_to_resources(
            "web",
            [
                {"key": "LOG_LEVEL", "type": "hardcoded", "value": "info"},
                {"key": "API_KEY", "type": "secret"},
            ],
            "production", "k8s",
        )
        assert has_config is True
        assert has_secrets is True
        assert len(resources) == 2
        kinds = {r["kind"] for r in resources}
        assert kinds == {"ConfigMap", "Secret"}
        # Both are in the correct namespace
        for r in resources:
            assert r["namespace"] == "production"

    def test_variable_type_goes_to_configmap(self):
        """Variable env vars → ConfigMap with varName as value."""
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api",
            [{"key": "CONFIG_URL", "type": "variable", "varName": "${CONFIG_URL}"}],
            "default", "k8s",
        )
        assert has_config is True
        assert has_secrets is False
        cm = resources[0]
        assert cm["spec"]["data"]["CONFIG_URL"] == "${CONFIG_URL}"

    def test_empty_env_vars_no_resources(self):
        """Empty env vars → no resources."""
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api", [], "default", "k8s",
        )
        assert resources == []
        assert has_config is False
        assert has_secrets is False

    def test_non_dict_items_skipped(self):
        """Non-dict items in env list → skipped silently.

        The function should be resilient to malformed input from the
        wizard frontend (e.g., strings or nulls mixed into the list).
        """
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api",
            ["bad-string", None, 42, {"key": "GOOD", "type": "hardcoded", "value": "ok"}],
            "default", "k8s",
        )
        assert has_config is True
        assert len(resources) == 1
        assert resources[0]["spec"]["data"]["GOOD"] == "ok"
        # Only 1 key in ConfigMap — garbage was skipped
        assert len(resources[0]["spec"]["data"]) == 1

    def test_items_without_key_skipped(self):
        """Items without `key` field → skipped silently.

        The `key` field is required to generate a valid env var.
        Missing it should not crash the function.
        """
        resources, has_config, has_secrets = _svc_env_to_resources(
            "api",
            [
                {"type": "hardcoded", "value": "orphan"},  # no key
                {"key": "", "type": "hardcoded", "value": "empty-key"},  # empty key
                {"key": "VALID", "type": "hardcoded", "value": "ok"},
            ],
            "default", "k8s",
        )
        assert has_config is True
        assert len(resources) == 1
        assert list(resources[0]["spec"]["data"].keys()) == ["VALID"]

    def test_naming_convention_explicit(self):
        """ConfigMap name → `{svc}-config`, Secret name → `{svc}-secrets`.

        These naming conventions are important because _build_env_vars
        references these exact names for envFrom wiring.
        """
        resources, _, _ = _svc_env_to_resources(
            "my-service",
            [
                {"key": "A", "type": "hardcoded", "value": "1"},
                {"key": "B", "type": "secret"},
            ],
            "ns", "k8s",
        )
        cm = next(r for r in resources if r["kind"] == "ConfigMap")
        sec = next(r for r in resources if r["kind"] == "Secret")
        assert cm["name"] == "my-service-config"
        assert sec["name"] == "my-service-secrets"

    def test_return_tuple_shape(self):
        """Return tuple → (list[dict], bool, bool).

        The caller (wizard_state_to_resources) relies on the exact
        tuple shape to wire envFrom references.
        """
        result = _svc_env_to_resources(
            "api",
            [{"key": "X", "type": "hardcoded", "value": "1"}],
            "default", "k8s",
        )
        assert isinstance(result, tuple)
        assert len(result) == 3
        resources, has_config, has_secrets = result
        assert isinstance(resources, list)
        assert isinstance(has_config, bool)
        assert isinstance(has_secrets, bool)


# ═══════════════════════════════════════════════════════════════════
#  _svc_volumes_to_pvc_resources
# ═══════════════════════════════════════════════════════════════════


class TestSvcVolumesToPvcResources:
    def test_pvc_dynamic(self):
        """PVC-dynamic volume → PVC resource."""
        result = _svc_volumes_to_pvc_resources(
            "api",
            [{"type": "pvc-dynamic", "name": "data", "accessMode": "ReadWriteOnce", "size": "10Gi"}],
            "default", "k8s",
        )
        assert len(result) == 1
        pvc = result[0]
        assert pvc["kind"] == "PersistentVolumeClaim"
        assert pvc["name"] == "api-data"
        assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert pvc["spec"]["storage"] == "10Gi"

    def test_pvc_static_with_pv_name(self):
        """PVC-static volume → PVC with volumeName."""
        result = _svc_volumes_to_pvc_resources(
            "db",
            [{"type": "pvc-static", "name": "pgdata", "pvName": "existing-pv-001"}],
            "default", "k8s",
        )
        assert len(result) == 1
        pvc = result[0]
        assert pvc["spec"]["volumeName"] == "existing-pv-001"

    def test_pvc_with_storage_class(self):
        """PVC with storageClass is preserved."""
        result = _svc_volumes_to_pvc_resources(
            "cache",
            [{"type": "pvc-dynamic", "name": "redis", "storageClass": "gp3"}],
            "default", "k8s",
        )
        assert result[0]["spec"]["storageClass"] == "gp3"

    def test_non_pvc_volumes_skipped(self):
        """EmptyDir and other types produce no PVC resources."""
        result = _svc_volumes_to_pvc_resources(
            "api",
            [
                {"type": "emptyDir", "name": "tmp"},
                {"type": "configMap", "configMapName": "cfg"},
                {"type": "secret", "secretName": "sec"},
                {"type": "hostPath", "hostPath": "/var/log"},
            ],
            "default", "k8s",
        )
        assert result == []

    def test_default_access_mode(self):
        """Default accessMode → ReadWriteOnce when not specified.

        K8s PVC spec: accessModes is required. The builder defaults
        to ReadWriteOnce when the wizard doesn't specify one.
        """
        result = _svc_volumes_to_pvc_resources(
            "api",
            [{"type": "pvc-dynamic", "name": "data"}],
            "default", "k8s",
        )
        assert result[0]["spec"]["accessModes"] == ["ReadWriteOnce"]

    def test_default_storage_size(self):
        """Default storage size → 10Gi when not specified.

        The builder defaults to 10Gi when the wizard doesn't provide
        a size — reasonable default for most workloads.
        """
        result = _svc_volumes_to_pvc_resources(
            "api",
            [{"type": "pvc-dynamic", "name": "data"}],
            "default", "k8s",
        )
        assert result[0]["spec"]["storage"] == "10Gi"

    def test_longhorn_config_passthrough(self):
        """Longhorn annotations → longhornConfig passed through to PVC spec.

        When present, the longhornConfig dict is attached to the PVC spec
        for downstream YAML generation to convert to annotations.
        """
        lh_config = {"numberOfReplicas": "3", "dataLocality": "best-effort"}
        result = _svc_volumes_to_pvc_resources(
            "api",
            [{"type": "pvc-dynamic", "name": "data", "longhornConfig": lh_config}],
            "default", "k8s",
        )
        assert result[0]["spec"]["longhornConfig"] == lh_config


# ═══════════════════════════════════════════════════════════════════
#  _sanitize_state
# ═══════════════════════════════════════════════════════════════════


class TestSanitizeState:
    def test_strips_transient_fields(self):
        """Transient/detection fields are removed."""
        state = {
            "_services": [{"name": "api"}],
            "_infraDecisions": [],
            "_appSvcCount": 1,      # transient — should be stripped
            "_infraSvcCount": 0,    # transient — should be stripped
            "_configMode": "multi", # transient — should be stripped
            "action": "setup",      # internal — should be stripped
            "namespace": "prod",    # keep
        }
        clean = _sanitize_state(state)
        assert "_appSvcCount" not in clean
        assert "_infraSvcCount" not in clean
        assert "_configMode" not in clean
        assert "action" not in clean
        assert clean["namespace"] == "prod"
        assert "_services" in clean

    def test_adds_metadata(self):
        """Sanitized state includes _savedAt and _version."""
        clean = _sanitize_state({"_services": [{"name": "api"}]})
        assert "_savedAt" in clean
        assert clean["_version"] == 1

    def test_strips_compose_from_services(self):
        """_compose key is removed from each service."""
        state = {
            "_services": [{"name": "api", "_compose": {"build": "."}}],
            "_infraDecisions": [{"name": "pg", "_compose": {"image": "pg:16"}}],
        }
        clean = _sanitize_state(state)
        assert "_compose" not in clean["_services"][0]
        assert "_compose" not in clean["_infraDecisions"][0]


# ═══════════════════════════════════════════════════════════════════
#  wizard_state_to_resources — the big translator
# ═══════════════════════════════════════════════════════════════════


class TestWizardStateToResources:
    def _simple_svc(self, **overrides):
        """Create a minimal app service dict."""
        base = {
            "name": "api",
            "kind": "Deployment",
            "image": "myapp:latest",
            "port": 8080,
            "replicas": 2,
        }
        base.update(overrides)
        return base

    def test_simple_deployment(self):
        """Single app service → Deployment + Service resources."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc()],
            "namespace": "default",
        })
        kinds = [r["kind"] for r in result]
        assert "Deployment" in kinds
        assert "Service" in kinds
        # Deployment has correct spec
        deploy = next(r for r in result if r["kind"] == "Deployment")
        assert deploy["spec"]["image"] == "myapp:latest"
        assert deploy["spec"]["replicas"] == 2

    def test_custom_namespace_generates_ns_resource(self):
        """Non-default namespace → Namespace resource created."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc()],
            "namespace": "production",
        })
        kinds = [r["kind"] for r in result]
        assert "Namespace" in kinds
        ns = next(r for r in result if r["kind"] == "Namespace")
        assert ns["name"] == "production"

    def test_default_namespace_no_ns_resource(self):
        """Default namespace → no Namespace resource."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc()],
            "namespace": "default",
        })
        kinds = [r["kind"] for r in result]
        assert "Namespace" not in kinds

    def test_deployment_with_env_vars(self):
        """Deployment with env vars → ConfigMap + Secret + envFrom wiring."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(envVars=[
                {"key": "LOG_LEVEL", "type": "hardcoded", "value": "info"},
                {"key": "DB_PASS", "type": "secret"},
            ])],
            "namespace": "default",
        })
        kinds = [r["kind"] for r in result]
        assert "ConfigMap" in kinds
        assert "Secret" in kinds
        # Verify names follow convention
        cm = next(r for r in result if r["kind"] == "ConfigMap")
        assert cm["name"] == "api-config"
        sec = next(r for r in result if r["kind"] == "Secret")
        assert sec["name"] == "api-secrets"

    def test_deployment_env_from_wired(self):
        """Deployment with both config + secret env vars → envFrom wires both refs.

        0.2.20d: The deployment spec must include envFrom references to both
        the ConfigMap and Secret generated alongside the workload, using the
        {svc_name}-config / {svc_name}-secrets naming convention.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(envVars=[
                {"key": "LOG_LEVEL", "type": "hardcoded", "value": "info"},
                {"key": "DB_PASS", "type": "secret"},
            ])],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        env_from = deploy["spec"]["envFrom"]
        assert isinstance(env_from, list)
        # ConfigMap ref
        cm_refs = [e for e in env_from if "configMapRef" in e]
        assert len(cm_refs) == 1
        assert cm_refs[0]["configMapRef"]["name"] == "api-config"
        # Secret ref
        sec_refs = [e for e in env_from if "secretRef" in e]
        assert len(sec_refs) == 1
        assert sec_refs[0]["secretRef"]["name"] == "api-secrets"

    def test_deployment_with_probes(self):
        """Deployment with probes → probes in spec."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                livenessProbe={"enabled": True, "type": "http", "path": "/health", "port": 8080},
                readinessProbe={"enabled": True, "type": "tcp", "port": 8080},
            )],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        assert "livenessProbe" in deploy["spec"]
        assert "readinessProbe" in deploy["spec"]

    def test_deployment_with_resource_limits(self):
        """Resource requests/limits are included."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                cpuRequest="100m", memRequest="128Mi",
                cpuLimit="500m", memLimit="256Mi",
            )],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        res = deploy["spec"]["resources"]
        assert res["requests"]["cpu"] == "100m"
        assert res["limits"]["memory"] == "256Mi"

    def test_statefulset_has_headless_service(self):
        """StatefulSet → headless service name + headless Service resource."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(kind="StatefulSet")],
            "namespace": "default",
        })
        kinds = [r["kind"] for r in result]
        # Should have regular Service + headless Service
        services = [r for r in result if r["kind"] == "Service"]
        assert len(services) == 2
        headless = next(s for s in services if "headless" in s["name"])
        assert headless["spec"]["type"] == "None"
        # StatefulSet should reference headless service
        ss = next(r for r in result if r["kind"] == "StatefulSet")
        assert ss["spec"]["headlessServiceName"] == "api-headless"

    def test_job_with_extras(self):
        """Job with backoffLimit, completions, parallelism."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                kind="Job",
                port=None,  # Jobs usually don't have ports
                backoffLimit=6,
                completions=3,
                parallelism=2,
                restartPolicy="Never",
            )],
            "namespace": "default",
        })
        job = next(r for r in result if r["kind"] == "Job")
        assert job["spec"]["backoffLimit"] == 6
        assert job["spec"]["completions"] == 3
        assert job["spec"]["parallelism"] == 2
        # No Service for Jobs (no port)
        services = [r for r in result if r["kind"] == "Service"]
        assert len(services) == 0

    def test_cronjob_with_schedule(self):
        """CronJob with schedule and concurrency policy."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                kind="CronJob",
                port=None,
                schedule="0 */6 * * *",
                concurrencyPolicy="Replace",
            )],
            "namespace": "default",
        })
        cron = next(r for r in result if r["kind"] == "CronJob")
        assert cron["spec"]["schedule"] == "0 */6 * * *"
        assert cron["spec"]["concurrencyPolicy"] == "Replace"

    def test_skip_produces_nothing(self):
        """Infra service with kind=Skip → no resources."""
        result = wizard_state_to_resources({
            "_services": [],
            "_infraDecisions": [{"name": "redis", "kind": "Skip"}],
            "namespace": "default",
        })
        assert len(result) == 0

    def test_managed_produces_managed_resource(self):
        """Infra service with kind=Managed → Managed resource (placeholder)."""
        result = wizard_state_to_resources({
            "_services": [],
            "_infraDecisions": [{"name": "rds-postgres", "kind": "Managed"}],
            "namespace": "default",
        })
        assert len(result) == 1
        assert result[0]["kind"] == "Managed"
        assert result[0]["name"] == "rds-postgres"

    def test_ingress_single_service(self):
        """Single service with ingress host → Ingress with simple backend."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc()],
            "namespace": "default",
            "ingress": "app.example.com",
        })
        ing = next(r for r in result if r["kind"] == "Ingress")
        assert ing["spec"]["host"] == "app.example.com"
        assert ing["spec"]["service"] == "api"

    def test_ingress_multi_service(self):
        """Multiple services with ingress → Ingress with multi-path rules."""
        result = wizard_state_to_resources({
            "_services": [
                self._simple_svc(name="api"),
                self._simple_svc(name="web", port=3000),
            ],
            "namespace": "default",
            "ingress": "app.example.com",
        })
        ing = next(r for r in result if r["kind"] == "Ingress")
        assert ing["spec"]["host"] == "app.example.com"
        assert "_paths" in ing["spec"]
        assert len(ing["spec"]["_paths"]) == 2

    def test_output_dir_propagated(self):
        """Custom output_dir is set on all resources."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc()],
            "namespace": "default",
            "output_dir": "manifests/prod",
        })
        for r in result:
            assert r["output_dir"] == "manifests/prod"

    def test_deployment_strategy(self):
        """Deployment strategy is forwarded to spec."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                strategy="RollingUpdate",
                maxSurge=2,
                maxUnavailable=1,
            )],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        assert deploy["spec"]["strategy"] == "RollingUpdate"
        assert deploy["spec"]["maxSurge"] == 2
        assert deploy["spec"]["maxUnavailable"] == 1

    def test_statefulset_extras(self):
        """StatefulSet extras → podManagementPolicy + partition forwarded.

        K8s StatefulSet spec: podManagementPolicy controls how pods
        are created (OrderedReady or Parallel). Partition controls
        rolling update partitioning.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                kind="StatefulSet",
                podManagementPolicy="Parallel",
                partition=2,
            )],
            "namespace": "default",
        })
        ss = next(r for r in result if r["kind"] == "StatefulSet")
        assert ss["spec"]["podManagementPolicy"] == "Parallel"
        assert ss["spec"]["partition"] == 2

    def test_daemonset_extras(self):
        """DaemonSet extras → nodeSelector + tolerations forwarded.

        K8s DaemonSet spec: nodeSelector restricts which nodes run
        the DaemonSet, tolerations allow scheduling on tainted nodes.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                kind="DaemonSet",
                nodeSelector={"node-role.kubernetes.io/worker": "true"},
                tolerations=[{"key": "node.kubernetes.io/not-ready", "effect": "NoSchedule"}],
            )],
            "namespace": "default",
        })
        ds = next(r for r in result if r["kind"] == "DaemonSet")
        assert ds["spec"]["nodeSelector"]["node-role.kubernetes.io/worker"] == "true"
        assert len(ds["spec"]["tolerations"]) == 1

    def test_hpa_autoscaling(self):
        """HPA autoscaling → HorizontalPodAutoscaler resource with targets.

        When autoscaling.enabled is true, a separate HPA resource is
        created targeting the workload kind.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                autoscaling={
                    "enabled": True,
                    "minReplicas": 2,
                    "maxReplicas": 10,
                    "targetCPU": 80,
                },
            )],
            "namespace": "default",
        })
        kinds = [r["kind"] for r in result]
        assert "HorizontalPodAutoscaler" in kinds
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["name"] == "api-hpa"
        assert hpa["spec"]["minReplicas"] == 2
        assert hpa["spec"]["maxReplicas"] == 10
        assert hpa["spec"]["targetCPUUtilizationPercentage"] == 80
        assert hpa["spec"]["scaleTargetRef"]["kind"] == "Deployment"
        assert hpa["spec"]["scaleTargetRef"]["name"] == "api"

    def test_sidecars_passthrough(self):
        """Sidecars / initContainers / companions → passthrough to spec.

        The translator passes these multi-container configs straight
        to the workload spec for _build_pod_template to process.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                sidecars=[{"name": "envoy", "image": "envoy:latest"}],
                initContainers=[{"name": "migrate", "image": "api:v1", "command": "migrate"}],
                companions=[{"name": "redis", "image": "redis:7", "port": 6379}],
            )],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        assert deploy["spec"]["sidecars"] == [{"name": "envoy", "image": "envoy:latest"}]
        assert deploy["spec"]["initContainers"][0]["name"] == "migrate"
        assert deploy["spec"]["companions"][0]["name"] == "redis"

    def test_command_args_passthrough(self):
        """Command/args override → passthrough to spec."""
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                kind="Job",
                port=None,
                command="python run.py",
                args="--verbose",
            )],
            "namespace": "default",
        })
        job = next(r for r in result if r["kind"] == "Job")
        assert job["spec"]["command"] == "python run.py"
        assert job["spec"]["args"] == "--verbose"

    def test_service_type_forwarded(self):
        """Service type → ClusterIP / NodePort / LoadBalancer on K8s Service resource.

        The wizard's serviceType field is propagated to the K8s Service
        resource's spec.type. Default is ClusterIP.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(serviceType="NodePort")],
            "namespace": "default",
        })
        svc = next(r for r in result if r["kind"] == "Service")
        assert svc["spec"]["type"] == "NodePort"

    def test_mesh_annotations_in_spec(self):
        """Mesh annotations → spec.annotations when mesh.enabled.

        The translator calls _build_mesh_annotations and attaches
        the result to spec.annotations for _build_pod_template to use.
        """
        result = wizard_state_to_resources({
            "_services": [self._simple_svc(
                mesh={"enabled": True, "provider": "istio"},
            )],
            "namespace": "default",
        })
        deploy = next(r for r in result if r["kind"] == "Deployment")
        assert "annotations" in deploy["spec"]
        assert "sidecar.istio.io/inject" in deploy["spec"]["annotations"]


# ═══════════════════════════════════════════════════════════════════
#  0.2.15c-f  Infrastructure service wizard decisions + generation
# ═══════════════════════════════════════════════════════════════════


class TestInfraServiceTranslation:
    """0.2.15c-f — _infraDecisions translation to K8s resources.

    Infrastructure services (Redis, Postgres, RabbitMQ) declared via
    _infraDecisions follow the same pipeline as app services but must
    produce INDEPENDENT resources (not merged into app pods).

    Source of truth: K8s Deployment/StatefulSet/Service/PVC specs +
    wizard_state_to_resources behaviour.
    """

    def _infra_state(self, infra_decisions, services=None, **extras):
        """Build minimal wizard state with infra decisions."""
        state = {
            "namespace": "default",
            "_services": services or [],
            "_infraDecisions": infra_decisions,
        }
        state.update(extras)
        return state

    # ── 0.2.15c: Wizard decisions ─────────────────────────────────

    def test_skip_produces_zero_resources(self):
        """kind=Skip → zero resources. External/cloud-managed service.

        Pessimistic: not just 0 length but also no kinds at all.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "redis", "kind": "Skip"},
        ]))
        assert len(result) == 0
        assert isinstance(result, list)

    def test_managed_produces_marker_only(self):
        """kind=Managed → single Managed placeholder resource.

        No Deployment, no Service, no ConfigMap — just a marker.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "rds-postgres", "kind": "Managed"},
        ]))
        assert len(result) == 1
        r = result[0]
        assert r["kind"] == "Managed"
        assert r["name"] == "rds-postgres"
        assert r["namespace"] == "default"
        assert "spec" in r

    def test_default_kind_is_deployment(self):
        """Infra without explicit kind → Deployment.

        The default kind for both app and infra services is Deployment.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "redis", "image": "redis:7", "port": 6379},
        ]))
        deploy = next((r for r in result if r["kind"] == "Deployment"), None)
        assert deploy is not None, "Expected Deployment for infra service"
        assert deploy["name"] == "redis"

    def test_statefulset_kind_override(self):
        """kind=StatefulSet → StatefulSet resource, not Deployment.

        Infra services like Postgres should use StatefulSet for
        stable storage and network identity.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "postgres", "kind": "StatefulSet", "image": "postgres:15",
             "port": 5432},
        ]))
        kinds = [r["kind"] for r in result]
        assert "StatefulSet" in kinds
        assert "Deployment" not in kinds

    # ── 0.2.15d: Infra workload resources ─────────────────────────

    def test_infra_own_deployment_separate_from_app(self):
        """Infra service → own Deployment, separate from app.

        This is the key contract: infra services should NOT merge into app pods.
        Both app and infra should produce independent Deployment resources.
        """
        result = wizard_state_to_resources(self._infra_state(
            infra_decisions=[
                {"name": "redis", "image": "redis:7", "port": 6379},
            ],
            services=[
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2},
            ],
        ))
        deployments = [r for r in result if r["kind"] == "Deployment"]
        deploy_names = {d["name"] for d in deployments}
        assert "api" in deploy_names, "Missing app Deployment"
        assert "redis" in deploy_names, "Missing infra Deployment"
        assert len(deployments) == 2, f"Expected 2 Deployments, got {len(deployments)}"

    def test_infra_with_port_produces_service(self):
        """Infra service with port → own ClusterIP Service.

        Pessimistic: verify selector, port, targetPort, type.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "redis", "image": "redis:7", "port": 6379},
        ]))
        services = [r for r in result if r["kind"] == "Service"]
        assert len(services) >= 1
        svc = next(s for s in services if s["name"] == "redis")
        assert svc["spec"]["port"] == 6379
        assert svc["spec"]["target_port"] == 6379
        assert svc["spec"]["selector"] == "redis"
        assert svc["spec"]["type"] == "ClusterIP"

    def test_infra_without_port_no_service(self):
        """Infra service with NO port → no Service resource (negative test).

        Some infra services (e.g., batch workers) don't need network access.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "worker", "image": "worker:v1"},
        ]))
        services = [r for r in result if r["kind"] == "Service"]
        assert len(services) == 0, f"Expected no Service, got {len(services)}"

    def test_infra_plus_app_independent_services(self):
        """Infra + app → both produce independent Deployments + Services."""
        result = wizard_state_to_resources(self._infra_state(
            infra_decisions=[
                {"name": "redis", "image": "redis:7", "port": 6379},
            ],
            services=[
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2},
            ],
        ))
        services = [r for r in result if r["kind"] == "Service"]
        svc_names = {s["name"] for s in services}
        assert "api" in svc_names
        assert "redis" in svc_names

    def test_infra_statefulset_headless_service(self):
        """Infra StatefulSet → headless Service auto-generated.

        K8s: StatefulSets require a headless Service (clusterIP: None)
        for stable network identity. The wizard must create this automatically.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "postgres", "kind": "StatefulSet", "image": "postgres:15",
             "port": 5432},
        ]))
        services = [r for r in result if r["kind"] == "Service"]
        headless = [s for s in services if s["name"] == "postgres-headless"]
        assert len(headless) == 1, f"Expected headless Service, got {len(headless)}"
        assert headless[0]["spec"]["type"] == "None"
        assert headless[0]["spec"].get("headless") is True

    def test_infra_statefulset_servicename_ref(self):
        """Infra StatefulSet → spec.headlessServiceName references headless Service.

        K8s: StatefulSet.spec.serviceName MUST reference the headless Service.
        """
        result = wizard_state_to_resources(self._infra_state([
            {"name": "postgres", "kind": "StatefulSet", "image": "postgres:15",
             "port": 5432},
        ]))
        ss = next(r for r in result if r["kind"] == "StatefulSet")
        assert ss["spec"]["headlessServiceName"] == "postgres-headless"

    # ── 0.2.15e: Infra env var wiring ─────────────────────────────

    def test_infra_hardcoded_env_creates_configmap(self):
        """Infra service with hardcoded env → ConfigMap ({svc}-config).

        Same logic as app services — but verifying independently.
        """
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "redis",
                "image": "redis:7",
                "port": 6379,
                "envVars": [
                    {"key": "MAXMEMORY", "value": "128mb", "type": "hardcoded"},
                ],
            },
        ]))
        configmaps = [r for r in result if r["kind"] == "ConfigMap"]
        assert len(configmaps) == 1
        assert configmaps[0]["name"] == "redis-config"
        assert "MAXMEMORY" in configmaps[0]["spec"]["data"]

    def test_infra_secret_env_creates_secret(self):
        """Infra service with secret env → Secret ({svc}-secrets)."""
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "port": 5432,
                "envVars": [
                    {"key": "POSTGRES_PASSWORD", "value": "s3cret", "type": "secret"},
                ],
            },
        ]))
        secrets = [r for r in result if r["kind"] == "Secret"]
        assert len(secrets) == 1
        assert secrets[0]["name"] == "postgres-secrets"
        assert "POSTGRES_PASSWORD" in secrets[0]["spec"]["stringData"]

    def test_infra_mixed_env_creates_both(self):
        """Infra service with mixed env → both ConfigMap and Secret."""
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "port": 5432,
                "envVars": [
                    {"key": "POSTGRES_DB", "value": "mydb", "type": "hardcoded"},
                    {"key": "POSTGRES_PASSWORD", "value": "s3cret", "type": "secret"},
                ],
            },
        ]))
        configmaps = [r for r in result if r["kind"] == "ConfigMap"]
        secrets = [r for r in result if r["kind"] == "Secret"]
        assert len(configmaps) == 1
        assert len(secrets) == 1

    def test_infra_env_from_wired(self):
        """Infra ConfigMap/Secret → envFrom on workload spec.

        K8s: envFrom references ConfigMap/Secret by name for bulk injection.
        """
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "port": 5432,
                "envVars": [
                    {"key": "POSTGRES_DB", "value": "mydb", "type": "hardcoded"},
                    {"key": "POSTGRES_PASSWORD", "value": "s3cret", "type": "secret"},
                ],
            },
        ]))
        deploy = next(r for r in result if r["kind"] == "Deployment")
        env_from = deploy["spec"]["envFrom"]
        assert isinstance(env_from, list)
        # ConfigMap ref
        cm_refs = [e for e in env_from if "configMapRef" in e]
        assert len(cm_refs) == 1
        assert cm_refs[0]["configMapRef"]["name"] == "postgres-config"
        # Secret ref
        sec_refs = [e for e in env_from if "secretRef" in e]
        assert len(sec_refs) == 1
        assert sec_refs[0]["secretRef"]["name"] == "postgres-secrets"

    # ── 0.2.15f: Infra PVC / volumes ──────────────────────────────

    def test_infra_pvc_dynamic_creates_pvc(self):
        """Infra service with pvc-dynamic volume → PVC resource.

        Pessimistic: verify accessModes, storage, storageClass.
        """
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "port": 5432,
                "volumes": [
                    {
                        "name": "pgdata",
                        "mountPath": "/var/lib/postgresql/data",
                        "type": "pvc-dynamic",
                        "size": "20Gi",
                        "storageClass": "standard",
                    },
                ],
            },
        ]))
        pvcs = [r for r in result if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) == 1
        pvc = pvcs[0]
        assert pvc["name"] == "postgres-pgdata"
        assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert pvc["spec"]["storage"] == "20Gi"
        assert pvc["spec"]["storageClass"] == "standard"

    def test_infra_pvc_static_has_volume_name(self):
        """Infra pvc-static → PVC with volumeName for binding."""
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "volumes": [
                    {
                        "name": "pgdata",
                        "mountPath": "/var/lib/postgresql/data",
                        "type": "pvc-static",
                        "size": "50Gi",
                        "pvName": "nfs-pv-01",
                    },
                ],
            },
        ]))
        pvcs = [r for r in result if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) == 1
        assert pvcs[0]["spec"]["volumeName"] == "nfs-pv-01"

    def test_infra_emptydir_no_pvc(self):
        """Infra emptyDir volume → no PVC resource (negative test)."""
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "redis",
                "image": "redis:7",
                "port": 6379,
                "volumes": [
                    {"name": "tmp", "mountPath": "/tmp", "type": "emptyDir"},
                ],
            },
        ]))
        pvcs = [r for r in result if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) == 0

    def test_infra_statefulset_vct(self):
        """Infra StatefulSet with PVC → volumeClaimTemplates in spec.

        K8s: StatefulSets use volumeClaimTemplates (VCTs) instead of
        standalone PVCs. The template is embedded in the StatefulSet spec.
        """
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "kind": "StatefulSet",
                "image": "postgres:15",
                "port": 5432,
                "volumes": [
                    {
                        "name": "pgdata",
                        "mountPath": "/var/lib/postgresql/data",
                        "type": "pvc-dynamic",
                        "size": "20Gi",
                        "accessMode": "ReadWriteOnce",
                        "storageClass": "standard",
                    },
                ],
            },
        ]))
        ss = next(r for r in result if r["kind"] == "StatefulSet")
        assert "volumeClaimTemplates" in ss["spec"]
        vcts = ss["spec"]["volumeClaimTemplates"]
        assert len(vcts) == 1
        assert vcts[0]["name"] == "pgdata"
        assert vcts[0]["size"] == "20Gi"
        assert vcts[0]["accessMode"] == "ReadWriteOnce"
        assert vcts[0]["storageClass"] == "standard"

    def test_infra_pvc_default_size_10gi(self):
        """PVC without explicit size → defaults to 10Gi.

        K8s: _svc_volumes_to_pvc_resources defaults size to "10Gi".
        """
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "redis",
                "image": "redis:7",
                "port": 6379,
                "volumes": [
                    {
                        "name": "data",
                        "mountPath": "/data",
                        "type": "pvc-dynamic",
                        # No "size" key → must default to 10Gi
                    },
                ],
            },
        ]))
        pvcs = [r for r in result if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) == 1
        assert pvcs[0]["spec"]["storage"] == "10Gi"

    def test_infra_pvc_longhorn_config_passthrough(self):
        """PVC with longhornConfig → passthrough on PVC spec.

        The wizard passes Longhorn-specific config (replicas, dataLocality)
        through to the PVC resource for generate_k8s_wizard to wire as
        annotations.
        """
        lh_config = {"replicas": 3, "dataLocality": "best-effort"}
        result = wizard_state_to_resources(self._infra_state([
            {
                "name": "postgres",
                "image": "postgres:15",
                "port": 5432,
                "volumes": [
                    {
                        "name": "pgdata",
                        "mountPath": "/var/lib/postgresql/data",
                        "type": "pvc-dynamic",
                        "size": "50Gi",
                        "longhornConfig": lh_config,
                    },
                ],
            },
        ]))
        pvcs = [r for r in result if r["kind"] == "PersistentVolumeClaim"]
        assert len(pvcs) == 1
        assert pvcs[0]["spec"]["longhornConfig"] == lh_config
# ═══════════════════════════════════════════════════════════════════
#  0.2.16  HPA (Autoscaler) translation
# ═══════════════════════════════════════════════════════════════════


class TestHPATranslation:
    """0.2.16 — HorizontalPodAutoscaler translation.

    Source of truth: K8s autoscaling/v2 HPA spec +
    wizard_state_to_resources behaviour.
    """

    def _svc_with_hpa(self, name="api", kind="Deployment", **hpa_overrides):
        """Build a service dict with autoscaling enabled."""
        autoscaling = {"enabled": True, "minReplicas": 2, "maxReplicas": 10,
                       "targetCPU": 80}
        autoscaling.update(hpa_overrides)
        return {
            "name": name,
            "kind": kind,
            "image": f"{name}:latest",
            "port": 8080,
            "replicas": 2,
            "autoscaling": autoscaling,
        }

    def _state(self, services):
        return {"_services": services, "namespace": "default"}

    # ── 0.2.16a: HPA resource generation ──────────────────────────

    def test_hpa_created_when_enabled(self):
        """autoscaling.enabled=True → HPA resource alongside workload."""
        result = wizard_state_to_resources(self._state([self._svc_with_hpa()]))
        kinds = [r["kind"] for r in result]
        assert "HorizontalPodAutoscaler" in kinds

    def test_no_hpa_when_disabled(self):
        """autoscaling.enabled=False → no HPA (negative test)."""
        svc = self._svc_with_hpa()
        svc["autoscaling"]["enabled"] = False
        result = wizard_state_to_resources(self._state([svc]))
        kinds = [r["kind"] for r in result]
        assert "HorizontalPodAutoscaler" not in kinds

    def test_no_hpa_when_absent(self):
        """No autoscaling key → no HPA (negative test)."""
        svc = {"name": "api", "image": "api:latest", "port": 8080, "replicas": 2}
        result = wizard_state_to_resources(self._state([svc]))
        kinds = [r["kind"] for r in result]
        assert "HorizontalPodAutoscaler" not in kinds

    def test_hpa_naming_convention(self):
        """HPA name → {svc}-hpa."""
        result = wizard_state_to_resources(self._state([self._svc_with_hpa()]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["name"] == "api-hpa"

    # ── 0.2.16b: scaleTargetRef ───────────────────────────────────

    def test_scale_target_ref_deployment(self):
        """scaleTargetRef.kind → Deployment, name → service name."""
        result = wizard_state_to_resources(self._state([self._svc_with_hpa()]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        ref = hpa["spec"]["scaleTargetRef"]
        assert ref["kind"] == "Deployment"
        assert ref["name"] == "api"
        assert ref["apiVersion"] == "apps/v1"

    def test_scale_target_ref_statefulset(self):
        """StatefulSet with HPA → scaleTargetRef.kind is StatefulSet.

        K8s: HPA can target any scale resource. When the wizard service
        is a StatefulSet, the HPA must reference StatefulSet, not Deployment.
        """
        result = wizard_state_to_resources(self._state([
            self._svc_with_hpa(name="db", kind="StatefulSet"),
        ]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        ref = hpa["spec"]["scaleTargetRef"]
        assert ref["kind"] == "StatefulSet"
        assert ref["name"] == "db"

    # ── 0.2.16c: HPA metrics ─────────────────────────────────────

    def test_min_max_replicas(self):
        """minReplicas, maxReplicas from wizard state."""
        result = wizard_state_to_resources(self._state([
            self._svc_with_hpa(minReplicas=3, maxReplicas=15),
        ]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["spec"]["minReplicas"] == 3
        assert hpa["spec"]["maxReplicas"] == 15

    def test_min_max_defaults(self):
        """Default minReplicas=1, maxReplicas=10 when not specified."""
        svc = self._svc_with_hpa()
        del svc["autoscaling"]["minReplicas"]
        del svc["autoscaling"]["maxReplicas"]
        result = wizard_state_to_resources(self._state([svc]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["spec"]["minReplicas"] == 1
        assert hpa["spec"]["maxReplicas"] == 10

    def test_target_cpu(self):
        """targetCPU → targetCPUUtilizationPercentage in HPA spec."""
        result = wizard_state_to_resources(self._state([
            self._svc_with_hpa(targetCPU=75),
        ]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["spec"]["targetCPUUtilizationPercentage"] == 75

    def test_target_memory(self):
        """targetMemory → targetMemoryUtilizationPercentage in HPA spec."""
        result = wizard_state_to_resources(self._state([
            self._svc_with_hpa(targetMemory=85),
        ]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert hpa["spec"]["targetMemoryUtilizationPercentage"] == 85

    def test_no_target_cpu_field_absent(self):
        """No targetCPU → field absent from HPA spec (not zero).

        K8s: an HPA without CPU target is valid — it might use memory
        or custom metrics only. The field should not be present at all.
        """
        svc = self._svc_with_hpa()
        del svc["autoscaling"]["targetCPU"]
        result = wizard_state_to_resources(self._state([svc]))
        hpa = next(r for r in result if r["kind"] == "HorizontalPodAutoscaler")
        assert "targetCPUUtilizationPercentage" not in hpa["spec"]
