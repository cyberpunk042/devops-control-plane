"""
Tests for k8s_pod_builder — probes, volumes, env vars, mesh, API versions.

These are pure unit tests: dict in → dict out, no subprocess, no network.
"""

from src.core.services.k8s_pod_builder import (
    _build_probe,
    _build_wizard_volume,
    _build_env_vars,
    _build_mesh_annotations,
    _api_version_for_kind,
)


# ═══════════════════════════════════════════════════════════════════
#  _build_probe
# ═══════════════════════════════════════════════════════════════════


class TestBuildProbe:
    def test_http_probe(self):
        """HTTP probe with all timing fields."""
        result = _build_probe({
            "type": "http",
            "path": "/healthz",
            "port": 3000,
            "initialDelaySeconds": 15,
            "periodSeconds": 10,
            "extra": 5,
        })
        assert result["httpGet"] == {"path": "/healthz", "port": 3000}
        assert result["initialDelaySeconds"] == 15
        assert result["periodSeconds"] == 10
        assert result["failureThreshold"] == 5

    def test_tcp_probe(self):
        """TCP probe with port only."""
        result = _build_probe({"type": "tcp", "port": 5432})
        assert result["tcpSocket"] == {"port": 5432}
        assert "httpGet" not in result
        assert "exec" not in result

    def test_exec_probe_with_command(self):
        """Exec probe wraps command in sh -c."""
        result = _build_probe({
            "type": "exec",
            "command": "pg_isready -U postgres",
        })
        assert result["exec"]["command"] == [
            "sh", "-c", "pg_isready -U postgres"
        ]

    def test_exec_probe_empty_command(self):
        """Exec probe with no command falls back to /bin/true."""
        result = _build_probe({"type": "exec"})
        assert result["exec"]["command"] == ["/bin/true"]

    def test_http_probe_defaults(self):
        """HTTP probe with no args uses defaults."""
        result = _build_probe({})
        assert result["httpGet"]["path"] == "/health"
        assert result["httpGet"]["port"] == 8080

    def test_zero_timing_values_omitted(self):
        """Timing values of 0 are not included."""
        result = _build_probe({
            "type": "http",
            "initialDelaySeconds": 0,
            "periodSeconds": 0,
            "extra": 0,
        })
        assert "initialDelaySeconds" not in result
        assert "periodSeconds" not in result
        assert "failureThreshold" not in result


# ═══════════════════════════════════════════════════════════════════
#  _build_wizard_volume
# ═══════════════════════════════════════════════════════════════════


class TestBuildWizardVolume:
    def test_pvc_dynamic_volume(self):
        """PVC volume → persistentVolumeClaim with svc-prefixed claim."""
        pod_vol, vm = _build_wizard_volume(
            {"type": "pvc-dynamic", "name": "data", "mountPath": "/data"},
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "data",
            "persistentVolumeClaim": {"claimName": "api-data"},
        }
        assert vm == {"name": "data", "mountPath": "/data"}

    def test_emptydir_with_memory_medium(self):
        """EmptyDir volume with Memory medium and size limit."""
        pod_vol, vm = _build_wizard_volume(
            {
                "type": "emptyDir",
                "name": "cache",
                "mountPath": "/tmp/cache",
                "medium": "Memory",
                "sizeLimit": "256Mi",
            },
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "cache",
            "emptyDir": {"medium": "Memory", "sizeLimit": "256Mi"},
        }
        assert vm == {"name": "cache", "mountPath": "/tmp/cache"}

    def test_configmap_volume_with_key(self):
        """ConfigMap volume with key → subPath on mount."""
        pod_vol, vm = _build_wizard_volume(
            {
                "type": "configMap",
                "configMapName": "app-config",
                "key": "config.yaml",
                "mountPath": "/etc/config/config.yaml",
            },
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "cm-app-config",
            "configMap": {
                "name": "app-config",
                "items": [{"key": "config.yaml", "path": "config.yaml"}],
            },
        }
        assert vm["subPath"] == "config.yaml"

    def test_secret_volume_with_key(self):
        """Secret volume with key → subPath on mount."""
        pod_vol, vm = _build_wizard_volume(
            {
                "type": "secret",
                "secretName": "tls-cert",
                "key": "tls.crt",
                "mountPath": "/etc/ssl/tls.crt",
            },
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "sec-tls-cert",
            "secret": {
                "secretName": "tls-cert",
                "items": [{"key": "tls.crt", "path": "tls.crt"}],
            },
        }
        assert vm["subPath"] == "tls.crt"

    def test_hostpath_volume(self):
        """HostPath volume with type."""
        pod_vol, vm = _build_wizard_volume(
            {
                "type": "hostPath",
                "name": "docker-sock",
                "mountPath": "/var/run/docker.sock",
                "hostPath": "/var/run/docker.sock",
                "hostType": "Socket",
            },
            index=0,
            svc_name="agent",
        )
        assert pod_vol == {
            "name": "docker-sock",
            "hostPath": {"path": "/var/run/docker.sock", "type": "Socket"},
        }
        assert vm == {"name": "docker-sock", "mountPath": "/var/run/docker.sock"}

    def test_no_mount_path_returns_none(self):
        """Volume with no mountPath is invalid → (None, None)."""
        pod_vol, vm = _build_wizard_volume(
            {"type": "emptyDir", "name": "bad"},
            index=0,
            svc_name="api",
        )
        assert pod_vol is None
        assert vm is None

    def test_unknown_type_returns_none(self):
        """Unknown volume type → (None, None)."""
        pod_vol, vm = _build_wizard_volume(
            {"type": "nfs-magic", "mountPath": "/mnt"},
            index=0,
            svc_name="api",
        )
        assert pod_vol is None
        assert vm is None

    def test_auto_generated_name_from_index(self):
        """PVC volume with no name → name derived from index."""
        pod_vol, vm = _build_wizard_volume(
            {"type": "pvc-dynamic", "mountPath": "/data"},
            index=3,
            svc_name="web",
        )
        assert pod_vol["name"] == "data-3"
        assert pod_vol["persistentVolumeClaim"]["claimName"] == "web-data-3"


# ═══════════════════════════════════════════════════════════════════
#  _build_env_vars
# ═══════════════════════════════════════════════════════════════════


class TestBuildEnvVars:
    def test_dict_input(self):
        """Dict input → simple name/value pairs."""
        result = _build_env_vars({"DB_HOST": "localhost", "DB_PORT": 5432})
        assert len(result) == 2
        names = {e["name"] for e in result}
        assert names == {"DB_HOST", "DB_PORT"}
        # Values are stringified
        port_entry = next(e for e in result if e["name"] == "DB_PORT")
        assert port_entry["value"] == "5432"

    def test_classic_secret_ref(self):
        """List with explicit secretName → secretKeyRef."""
        result = _build_env_vars([
            {"name": "DB_PASSWORD", "secretName": "db-credentials", "secretKey": "password"},
        ])
        assert len(result) == 1
        ref = result[0]["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "db-credentials"
        assert ref["key"] == "password"

    def test_classic_configmap_ref(self):
        """List with explicit configMapName → configMapKeyRef."""
        result = _build_env_vars([
            {"name": "LOG_LEVEL", "configMapName": "app-settings", "configMapKey": "log-level"},
        ])
        assert len(result) == 1
        ref = result[0]["valueFrom"]["configMapKeyRef"]
        assert ref["name"] == "app-settings"
        assert ref["key"] == "log-level"

    def test_wizard_secret_with_svc_name(self):
        """Wizard format type=secret + svc_name → {svc}-secrets reference."""
        result = _build_env_vars(
            [{"key": "API_KEY", "type": "secret", "value": ""}],
            svc_name="api",
        )
        assert len(result) == 1
        ref = result[0]["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "api-secrets"
        assert ref["key"] == "API_KEY"

    def test_wizard_variable_with_svc_name(self):
        """Wizard format type=variable + svc_name → {svc}-config reference."""
        result = _build_env_vars(
            [{"key": "CONFIG_URL", "type": "variable", "varName": "${CONFIG_URL}"}],
            svc_name="web",
        )
        assert len(result) == 1
        ref = result[0]["valueFrom"]["configMapKeyRef"]
        assert ref["name"] == "web-config"
        assert ref["key"] == "CONFIG_URL"

    def test_wizard_hardcoded(self):
        """Wizard format type=hardcoded or default → inline value."""
        result = _build_env_vars(
            [{"key": "NODE_ENV", "type": "hardcoded", "value": "production"}],
        )
        assert len(result) == 1
        assert result[0]["value"] == "production"

    def test_empty_input(self):
        """Empty/falsy input → empty list."""
        assert _build_env_vars(None) == []
        assert _build_env_vars([]) == []
        assert _build_env_vars({}) == []

    def test_skips_items_without_name_or_key(self):
        """List items missing both 'name' and 'key' → skipped."""
        result = _build_env_vars([
            {"value": "orphan"},           # no name/key
            {"key": "GOOD", "value": "ok"},
        ])
        assert len(result) == 1
        assert result[0]["name"] == "GOOD"

    def test_accepts_key_as_alias_for_name(self):
        """'key' field is accepted as alias for 'name'."""
        result = _build_env_vars([{"key": "MY_VAR", "value": "hello"}])
        assert result[0]["name"] == "MY_VAR"


# ═══════════════════════════════════════════════════════════════════
#  _build_mesh_annotations
# ═══════════════════════════════════════════════════════════════════


class TestBuildMeshAnnotations:
    def test_istio_inject(self):
        """Istio mesh → sidecar.istio.io/inject: true."""
        result = _build_mesh_annotations({"provider": "istio"})
        assert "sidecar.istio.io/inject" in result
        assert result["sidecar.istio.io/inject"] == "true"

    def test_linkerd_inject(self):
        """Linkerd mesh → linkerd.io/inject: enabled (not 'true')."""
        result = _build_mesh_annotations({"provider": "linkerd"})
        assert "linkerd.io/inject" in result
        assert result["linkerd.io/inject"] == "enabled"

    def test_istio_proxy_resources(self):
        """Istio proxy resource annotations are set."""
        result = _build_mesh_annotations({
            "provider": "istio",
            "proxyCpuRequest": "100m",
            "proxyMemRequest": "128Mi",
        })
        assert result["sidecar.istio.io/proxyCPU"] == "100m"
        assert result["sidecar.istio.io/proxyMemory"] == "128Mi"

    def test_consul_inject(self):
        """Consul mesh → consul.hashicorp.com/connect-inject: true."""
        result = _build_mesh_annotations({"provider": "consul"})
        assert result["consul.hashicorp.com/connect-inject"] == "true"

    def test_default_provider_is_istio(self):
        """No provider specified → empty annotations (no mesh configured)."""
        result = _build_mesh_annotations({})
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
#  _api_version_for_kind
# ═══════════════════════════════════════════════════════════════════


class TestApiVersionForKind:
    def test_deployment(self):
        assert _api_version_for_kind("Deployment") == "apps/v1"

    def test_statefulset(self):
        assert _api_version_for_kind("StatefulSet") == "apps/v1"

    def test_daemonset(self):
        assert _api_version_for_kind("DaemonSet") == "apps/v1"

    def test_job(self):
        assert _api_version_for_kind("Job") == "batch/v1"

    def test_cronjob(self):
        assert _api_version_for_kind("CronJob") == "batch/v1"

    def test_ingress(self):
        assert _api_version_for_kind("Ingress") == "networking.k8s.io/v1"

    def test_service_defaults_to_v1(self):
        """Service and other core resources → v1."""
        assert _api_version_for_kind("Service") == "v1"

    def test_unknown_kind_defaults_to_v1(self):
        assert _api_version_for_kind("CustomThing") == "v1"
