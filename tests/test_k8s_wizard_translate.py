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
