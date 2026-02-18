"""
Tests for k8s_pod_builder — probes, volumes, env vars, mesh, API versions.

These are pure unit tests: dict in → dict out, no subprocess, no network.
"""

from src.core.services.k8s_pod_builder import (
    _build_probe,
    _build_wizard_volume,
    _build_pod_template,
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

    def test_readonly_flag(self):
        """ReadOnly flag → mount has readOnly=true.

        K8s VolumeMount spec: readOnly field controls whether the volume
        is mounted read-only. Must be boolean true, not a string.
        """
        pod_vol, vm = _build_wizard_volume(
            {"type": "secret", "secretName": "creds", "mountPath": "/etc/creds", "readOnly": True},
            index=0,
            svc_name="api",
        )
        assert vm is not None
        assert vm["readOnly"] is True
        assert isinstance(vm["readOnly"], bool)

    def test_readonly_absent_when_not_set(self):
        """Without readOnly flag, mount should NOT have readOnly key."""
        pod_vol, vm = _build_wizard_volume(
            {"type": "emptyDir", "name": "tmp", "mountPath": "/tmp"},
            index=0,
            svc_name="api",
        )
        assert "readOnly" not in vm

    def test_pvc_static_volume(self):
        """PVC-static volume → same persistentVolumeClaim structure as dynamic.

        K8s PersistentVolumeClaimVolumeSource: claimName is the only required
        field. Static and dynamic PVCs use the same pod volume definition —
        the difference is in the PVC resource itself, not the pod mount.
        """
        pod_vol, vm = _build_wizard_volume(
            {"type": "pvc-static", "name": "legacy-data", "mountPath": "/data"},
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "legacy-data",
            "persistentVolumeClaim": {"claimName": "api-legacy-data"},
        }
        assert vm == {"name": "legacy-data", "mountPath": "/data"}

    def test_emptydir_without_medium(self):
        """EmptyDir without medium → default emptyDir (empty spec).

        K8s EmptyDirVolumeSource: when medium is not set, the volume uses
        the node's default storage (disk). The emptyDir spec should be {}.
        """
        pod_vol, vm = _build_wizard_volume(
            {"type": "emptyDir", "name": "scratch", "mountPath": "/tmp/scratch"},
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "scratch",
            "emptyDir": {},
        }
        assert vm == {"name": "scratch", "mountPath": "/tmp/scratch"}

    def test_configmap_volume_without_key(self):
        """ConfigMap volume without key → mount entire ConfigMap as directory.

        K8s ConfigMapVolumeSource: when no items are specified, ALL keys
        in the ConfigMap are projected as files in the mount directory.
        No subPath should be set on the mount.
        """
        pod_vol, vm = _build_wizard_volume(
            {"type": "configMap", "configMapName": "app-config", "mountPath": "/etc/config"},
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "cm-app-config",
            "configMap": {"name": "app-config"},
        }
        assert "items" not in pod_vol["configMap"], "No items when key not specified"
        assert vm == {"name": "cm-app-config", "mountPath": "/etc/config"}
        assert "subPath" not in vm, "No subPath when key not specified"

    def test_secret_volume_without_key(self):
        """Secret volume without key → mount entire Secret as directory.

        K8s SecretVolumeSource: when no items are specified, ALL keys
        in the Secret are projected as files in the mount directory.
        No subPath should be set on the mount.
        """
        pod_vol, vm = _build_wizard_volume(
            {"type": "secret", "secretName": "db-creds", "mountPath": "/etc/secrets"},
            index=0,
            svc_name="api",
        )
        assert pod_vol == {
            "name": "sec-db-creds",
            "secret": {"secretName": "db-creds"},
        }
        assert "items" not in pod_vol["secret"], "No items when key not specified"
        assert vm == {"name": "sec-db-creds", "mountPath": "/etc/secrets"}
        assert "subPath" not in vm, "No subPath when key not specified"

    def test_hostpath_volume_without_type(self):
        """HostPath volume without type → type omitted from spec.

        K8s HostPathVolumeSource: type is optional. When omitted, no checks
        are performed before mounting. Only path is required.
        """
        pod_vol, vm = _build_wizard_volume(
            {
                "type": "hostPath",
                "name": "logs",
                "mountPath": "/var/log/app",
                "hostPath": "/var/log/app",
            },
            index=0,
            svc_name="agent",
        )
        assert pod_vol == {
            "name": "logs",
            "hostPath": {"path": "/var/log/app"},
        }
        assert "type" not in pod_vol["hostPath"], "type should be omitted when not specified"
        assert vm == {"name": "logs", "mountPath": "/var/log/app"}


# ═══════════════════════════════════════════════════════════════════
#  _build_pod_template
# ═══════════════════════════════════════════════════════════════════


class TestBuildPodTemplate:
    """_build_pod_template builds a K8s pod template spec.

    Source of truth: Kubernetes PodTemplateSpec (v1/PodSpec, v1/Container).
    """

    def test_main_container(self):
        """Main container with image, ports, resources, probes, security context.

        K8s Container spec: name, image required. ports, resources, probes,
        securityContext are optional but expected for production workloads.
        """
        tmpl = _build_pod_template("api", {
            "image": "myapp:v2",
            "port": 3000,
            "cpu_limit": "500m",
            "memory_limit": "256Mi",
            "cpu_request": "100m",
            "memory_request": "128Mi",
            "livenessProbe": {"type": "http", "path": "/healthz", "port": 3000},
            "readinessProbe": {"type": "tcp", "port": 3000},
        })

        # Template shape
        assert "metadata" in tmpl
        assert "labels" in tmpl["metadata"]
        assert tmpl["metadata"]["labels"]["app"] == "api"
        assert "spec" in tmpl

        # Containers
        containers = tmpl["spec"]["containers"]
        assert len(containers) >= 1
        main = containers[0]
        assert main["name"] == "api"
        assert main["image"] == "myapp:v2"

        # Ports
        assert main["ports"][0]["containerPort"] == 3000

        # Resources (K8s: requests and limits)
        assert main["resources"]["limits"]["cpu"] == "500m"
        assert main["resources"]["limits"]["memory"] == "256Mi"
        assert main["resources"]["requests"]["cpu"] == "100m"
        assert main["resources"]["requests"]["memory"] == "128Mi"

        # Probes
        assert "livenessProbe" in main
        assert "httpGet" in main["livenessProbe"]
        assert "readinessProbe" in main
        assert "tcpSocket" in main["readinessProbe"]

    def test_init_containers(self):
        """Init containers → initContainers field in pod spec.

        K8s PodSpec: initContainers is a list of containers that run
        before app containers. Each must have name and image.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "initContainers": [
                {"name": "migrate", "image": "api:v1", "command": "python manage.py migrate"},
                {"name": "seed", "image": "api:v1", "command": "python manage.py seed"},
            ],
        })

        assert "initContainers" in tmpl["spec"]
        inits = tmpl["spec"]["initContainers"]
        assert len(inits) == 2
        assert inits[0]["name"] == "migrate"
        assert inits[0]["image"] == "api:v1"
        # Command wrapped in sh -c
        assert inits[0]["command"] == ["sh", "-c", "python manage.py migrate"]
        assert inits[1]["name"] == "seed"

    def test_sidecar_containers(self):
        """Sidecar containers → additional containers (or native init with restartPolicy).

        K8s ≥ 1.28: native sidecars go to initContainers with restartPolicy: Always.
        K8s < 1.28: regular sidecars go to containers[].
        """
        # Native sidecar (default: nativeSidecar=True)
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "sidecars": [
                {"name": "log-shipper", "image": "fluent/fluent-bit:latest"},
            ],
        })
        # Native sidecar → initContainers with restartPolicy: Always
        assert "initContainers" in tmpl["spec"]
        sc = tmpl["spec"]["initContainers"][0]
        assert sc["name"] == "log-shipper"
        assert sc["restartPolicy"] == "Always"
        # Main container still in containers[0]
        assert tmpl["spec"]["containers"][0]["name"] == "api"

    def test_sidecar_non_native(self):
        """Non-native sidecar → added to containers[] alongside main."""
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "sidecars": [
                {"name": "envoy", "image": "envoyproxy/envoy:v1.28", "nativeSidecar": False},
            ],
        })
        containers = tmpl["spec"]["containers"]
        assert len(containers) == 2
        assert containers[0]["name"] == "api"
        assert containers[1]["name"] == "envoy"
        # Should NOT be in initContainers
        assert "initContainers" not in tmpl["spec"]

    def test_companion_containers(self):
        """Companion containers → multiple containers in same pod.

        K8s PodSpec: multiple containers in containers[] share network
        namespace and can share volumes.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "port": 8080,
            "companions": [
                {"name": "redis", "image": "redis:7", "port": 6379},
            ],
        })
        containers = tmpl["spec"]["containers"]
        assert len(containers) == 2
        assert containers[0]["name"] == "api"
        assert containers[1]["name"] == "redis"
        assert containers[1]["image"] == "redis:7"
        assert containers[1]["ports"][0]["containerPort"] == 6379

    def test_volumes_from_wizard(self):
        """Volumes from service config → volumes + volumeMounts.

        K8s PodSpec.volumes and Container.volumeMounts must reference
        each other by name.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "wizardVolumes": [
                {"type": "emptyDir", "name": "cache", "mountPath": "/cache"},
                {"type": "secret", "secretName": "creds", "mountPath": "/etc/creds"},
            ],
        })

        # Pod-level volumes
        assert "volumes" in tmpl["spec"]
        vol_names = {v["name"] for v in tmpl["spec"]["volumes"]}
        assert "cache" in vol_names
        assert "sec-creds" in vol_names

        # Container volumeMounts
        main = tmpl["spec"]["containers"][0]
        assert "volumeMounts" in main
        mount_names = {m["name"] for m in main["volumeMounts"]}
        assert "cache" in mount_names
        assert "sec-creds" in mount_names

        # Names must match between volumes and mounts (K8s invariant)
        for vm in main["volumeMounts"]:
            assert vm["name"] in vol_names, (
                f"VolumeMount '{vm['name']}' has no matching pod volume"
            )

    def test_mesh_annotations(self):
        """Mesh annotations → pod template annotations.

        K8s PodTemplateSpec.metadata.annotations: mesh providers use
        pod-level annotations for sidecar injection.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "mesh": {"provider": "istio"},
        })
        assert "annotations" in tmpl["metadata"]
        assert "sidecar.istio.io/inject" in tmpl["metadata"]["annotations"]
        assert tmpl["metadata"]["annotations"]["sidecar.istio.io/inject"] == "true"

    def test_host_access_flags(self):
        """Host access config → hostNetwork, hostPID fields.

        K8s PodSpec: hostNetwork, hostPID, hostIPC are booleans that grant
        the pod access to the host's network/PID/IPC namespace.
        Typically used for DaemonSets (node agents, monitoring).
        """
        tmpl = _build_pod_template("agent", {
            "image": "agent:v1",
            "hostNetwork": True,
            "hostPID": True,
        })
        assert tmpl["spec"]["hostNetwork"] is True
        assert tmpl["spec"]["hostPID"] is True

    def test_host_access_absent_by_default(self):
        """Without host access flags, hostNetwork/hostPID should not appear."""
        tmpl = _build_pod_template("api", {"image": "api:v1"})
        assert "hostNetwork" not in tmpl["spec"]
        assert "hostPID" not in tmpl["spec"]
        assert "hostIPC" not in tmpl["spec"]

    def test_volume_claim_templates(self):
        """VolumeClaimTemplates for StatefulSets → volumeMounts on main container.

        K8s StatefulSet spec: volumeClaimTemplates create PVCs automatically.
        The pod template doesn't list them in volumes[], but the container
        MUST have volumeMounts referencing each VCT by name.
        """
        tmpl = _build_pod_template("db", {
            "image": "postgres:16",
            "volumeClaimTemplates": [
                {"name": "pgdata", "mountPath": "/var/lib/postgresql/data"},
            ],
        })

        main = tmpl["spec"]["containers"][0]
        assert "volumeMounts" in main
        vct_mounts = [m for m in main["volumeMounts"] if m["name"] == "pgdata"]
        assert len(vct_mounts) == 1
        assert vct_mounts[0]["mountPath"] == "/var/lib/postgresql/data"

        # VCT volumes should NOT appear in pod spec volumes[]
        # (K8s auto-injects them for StatefulSets)
        pod_vols = tmpl["spec"].get("volumes", [])
        vct_in_pod = [v for v in pod_vols if v.get("name") == "pgdata"]
        assert len(vct_in_pod) == 0, (
            "VCT 'pgdata' should not be in pod volumes — K8s injects them"
        )

    def test_default_image(self):
        """Default image → {name}:latest when none provided.

        K8s Container spec: image is required. When not explicitly set,
        the builder defaults to {container_name}:latest.
        """
        tmpl = _build_pod_template("api", {})
        main = tmpl["spec"]["containers"][0]
        assert main["image"] == "api:latest"

    def test_no_port_no_ports_array(self):
        """No port → no ports array in container.

        K8s Container spec: ports is optional. When no port is specified,
        the field should be absent (not an empty list).
        """
        tmpl = _build_pod_template("worker", {"image": "worker:v1"})
        main = tmpl["spec"]["containers"][0]
        assert "ports" not in main, "ports should be absent when no port specified"

    def test_command_args_override(self):
        """Command/args override → command wrapped in sh -c.

        K8s Container spec: command overrides ENTRYPOINT, args overrides CMD.
        The builder wraps command strings in ["sh", "-c", cmd].
        """
        tmpl = _build_pod_template("job", {
            "image": "job:v1",
            "command": "python run_job.py --batch",
            "args": "--verbose --dry-run",
        })
        main = tmpl["spec"]["containers"][0]
        assert main["command"] == ["sh", "-c", "python run_job.py --batch"]
        assert main["args"] == ["--verbose", "--dry-run"]

    def test_resource_limits_absent_when_not_provided(self):
        """Resource limits only set when provided — no empty resources block.

        K8s Container spec: resources is optional. When no cpu/memory
        limits or requests are set, the key should be absent entirely.
        """
        tmpl = _build_pod_template("api", {"image": "api:v1"})
        main = tmpl["spec"]["containers"][0]
        assert "resources" not in main, (
            "resources should be absent when no limits/requests provided"
        )

    def test_env_vars_wired(self):
        """Env vars wired to main container.

        K8s Container spec: env is a list of EnvVar objects.
        Each has name (required) and either value or valueFrom.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "env": {"NODE_ENV": "production", "PORT": "3000"},
        })
        main = tmpl["spec"]["containers"][0]
        assert "env" in main
        env_names = {e["name"] for e in main["env"]}
        assert "NODE_ENV" in env_names
        assert "PORT" in env_names

    def test_envfrom_bulk_refs(self):
        """envFrom bulk refs (ConfigMap/Secret) wired to main container.

        K8s Container spec: envFrom allows bulk injection from ConfigMaps
        and Secrets without listing individual keys.
        """
        env_from = [
            {"configMapRef": {"name": "api-config"}},
            {"secretRef": {"name": "api-secrets"}},
        ]
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "envFrom": env_from,
        })
        main = tmpl["spec"]["containers"][0]
        assert "envFrom" in main
        assert len(main["envFrom"]) == 2
        assert main["envFrom"][0]["configMapRef"]["name"] == "api-config"
        assert main["envFrom"][1]["secretRef"]["name"] == "api-secrets"

    def test_sidecar_shared_volume(self):
        """Sidecar shared volume → emptyDir created, mounted in both sidecar and main.

        K8s PodSpec: sidecars can share data with the main container via
        shared volumes. The builder auto-creates an emptyDir for this.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "sidecars": [{
                "name": "log-collector",
                "image": "fluent-bit:latest",
                "sharedVolume": "shared-logs",
                "sharedMount": "/var/log/app",
                "nativeSidecar": False,
            }],
        })

        # Shared emptyDir volume created at pod level
        assert "volumes" in tmpl["spec"]
        shared_vols = [v for v in tmpl["spec"]["volumes"] if v["name"] == "shared-logs"]
        assert len(shared_vols) == 1
        assert shared_vols[0] == {"name": "shared-logs", "emptyDir": {}}

        # Main container has the mount
        main = tmpl["spec"]["containers"][0]
        assert "volumeMounts" in main
        main_mounts = [m for m in main["volumeMounts"] if m["name"] == "shared-logs"]
        assert len(main_mounts) == 1
        assert main_mounts[0]["mountPath"] == "/var/log/app"

        # Sidecar container has the mount
        sidecar = tmpl["spec"]["containers"][1]
        assert "volumeMounts" in sidecar
        sc_mounts = [m for m in sidecar["volumeMounts"] if m["name"] == "shared-logs"]
        assert len(sc_mounts) == 1
        assert sc_mounts[0]["mountPath"] == "/var/log/app"

    def test_companion_startup_dependency(self):
        """Companion startup dependency → wait-for init container with nc -z.

        When a companion has dependsOn, a busybox init container is created
        that waits for the dependency to be reachable via TCP.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "port": 8080,
            "companions": [{
                "name": "redis",
                "image": "redis:7",
                "port": 6379,
                "dependsOn": "postgres",
                "dependsOnPort": 5432,
            }],
        })

        assert "initContainers" in tmpl["spec"]
        wait_inits = [ic for ic in tmpl["spec"]["initContainers"]
                      if ic["name"].startswith("wait-for-")]
        assert len(wait_inits) == 1
        assert wait_inits[0]["image"] == "busybox:1.36"
        # The command must use nc -z to check TCP connectivity
        cmd_str = wait_inits[0]["command"][2]  # ["sh", "-c", "..."]
        assert "nc -z postgres 5432" in cmd_str

    def test_companion_volume_mounts(self):
        """Companion volume mounts → pod-level volumes + container volumeMounts.

        K8s PodSpec: companion containers can have their own volume mounts.
        Volumes are added at pod level, mounts on the companion container.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "companions": [{
                "name": "redis",
                "image": "redis:7",
                "volumes": [
                    {"name": "redis-data", "type": "emptyDir", "mountPath": "/data"},
                ],
            }],
        })

        # Pod-level volume created
        assert "volumes" in tmpl["spec"]
        redis_vols = [v for v in tmpl["spec"]["volumes"] if v["name"] == "redis-data"]
        assert len(redis_vols) == 1
        assert redis_vols[0] == {"name": "redis-data", "emptyDir": {}}

        # Companion has the mount
        companion = tmpl["spec"]["containers"][1]
        assert "volumeMounts" in companion
        assert companion["volumeMounts"][0] == {"name": "redis-data", "mountPath": "/data"}

    def test_companion_env_vars(self):
        """Companion env vars → env list on companion container.

        K8s Container spec: env is a list of EnvVar objects with name+value.
        Companion containers need their own env vars, independent from main.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "companions": [{
                "name": "redis",
                "image": "redis:7",
                "env": {"REDIS_MAXMEMORY": "256mb", "REDIS_APPENDONLY": "yes"},
            }],
        })
        companion = tmpl["spec"]["containers"][1]
        assert "env" in companion
        env_names = {e["name"] for e in companion["env"]}
        assert "REDIS_MAXMEMORY" in env_names
        assert "REDIS_APPENDONLY" in env_names
        # Main container should NOT have companion's env
        main = tmpl["spec"]["containers"][0]
        main_env_names = {e["name"] for e in main.get("env", [])}
        assert "REDIS_MAXMEMORY" not in main_env_names

    def test_companion_resource_limits(self):
        """Companion resource limits → resources block on companion container.

        K8s Container spec: resources.limits and resources.requests control
        CPU/memory allocation per container.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "companions": [{
                "name": "redis",
                "image": "redis:7",
                "resources": {
                    "cpu_limit": "500m",
                    "memory_limit": "512Mi",
                    "cpu_request": "100m",
                    "memory_request": "128Mi",
                },
            }],
        })
        companion = tmpl["spec"]["containers"][1]
        assert "resources" in companion
        assert companion["resources"]["limits"]["cpu"] == "500m"
        assert companion["resources"]["limits"]["memory"] == "512Mi"
        assert companion["resources"]["requests"]["cpu"] == "100m"
        assert companion["resources"]["requests"]["memory"] == "128Mi"
        # Main container should NOT inherit companion's resources
        main = tmpl["spec"]["containers"][0]
        assert "resources" not in main

    def test_volume_name_deduplication(self):
        """Volume name deduplication → same name not added twice.

        K8s PodSpec: volumes[] names must be unique. The builder must
        deduplicate when the same volume name appears in multiple sources.
        """
        tmpl = _build_pod_template("api", {
            "image": "api:v1",
            "wizardVolumes": [
                {"type": "emptyDir", "name": "shared", "mountPath": "/cache"},
                {"type": "emptyDir", "name": "shared", "mountPath": "/tmp"},
            ],
        })

        # Volume "shared" should appear only once in pod volumes
        assert "volumes" in tmpl["spec"]
        shared_vols = [v for v in tmpl["spec"]["volumes"] if v["name"] == "shared"]
        assert len(shared_vols) == 1, (
            f"Expected 1 'shared' volume, got {len(shared_vols)}"
        )

    def test_mesh_absent_no_annotations(self):
        """Mesh absent → no annotations key on template metadata.

        K8s PodTemplateSpec: when no mesh is configured, annotations
        should not be present (avoid empty annotations dict).
        """
        tmpl = _build_pod_template("api", {"image": "api:v1"})
        assert "annotations" not in tmpl["metadata"], (
            "annotations should be absent when no mesh configured"
        )

    def test_host_access_with_ipc(self):
        """hostIPC flag → hostIPC: true in pod spec.

        K8s PodSpec: hostIPC grants access to the host's IPC namespace.
        """
        tmpl = _build_pod_template("agent", {
            "image": "agent:v1",
            "hostIPC": True,
        })
        assert tmpl["spec"]["hostIPC"] is True


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

    def test_dict_values_stringified(self):
        """Dict input values stringified (int → str per K8s EnvVar.value spec).

        K8s EnvVar.value is always a string. Non-string values MUST be
        converted, otherwise the K8s API rejects the manifest.
        """
        result = _build_env_vars({"PORT": 8080, "DEBUG": True, "WORKERS": 4})
        for entry in result:
            assert isinstance(entry["value"], str), (
                f"Value for {entry['name']} must be str, got {type(entry['value'])}"
            )
        port = next(e for e in result if e["name"] == "PORT")
        assert port["value"] == "8080"
        debug = next(e for e in result if e["name"] == "DEBUG")
        assert debug["value"] == "True"

    def test_secret_key_defaults_to_env_name(self):
        """List secretKey defaults to env name when omitted.

        K8s secretKeyRef.key: when not explicitly provided, the builder
        should default to using the env var name as the key.
        """
        result = _build_env_vars([
            {"name": "DB_PASSWORD", "secretName": "db-credentials"},
        ])
        ref = result[0]["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "db-credentials"
        assert ref["key"] == "DB_PASSWORD", (
            f"secretKey should default to env name 'DB_PASSWORD', got '{ref['key']}'"
        )

    def test_wizard_secret_without_svc_name(self):
        """Wizard type=secret without svc_name → fallback derivation from varName.

        When svc_name is not provided, the builder derives the secret
        reference name from the varName field.
        """
        result = _build_env_vars([
            {"key": "API_KEY", "type": "secret", "varName": "${API_SECRET}"},
        ])
        assert len(result) == 1
        ref = result[0]["valueFrom"]["secretKeyRef"]
        # Derived from varName: strip ${}, lowercase, replace _ with -
        assert ref["name"] == "api-secret"
        assert ref["key"] == "API_KEY"

    def test_non_list_non_dict_returns_empty(self):
        """Non-list non-dict input → empty list.

        Defensive edge case: passing a string, int, or other type
        should return an empty list, not raise an exception.
        """
        assert _build_env_vars("bogus") == []
        assert _build_env_vars(42) == []
        assert _build_env_vars(True) == []

    def test_configmap_key_defaults_to_env_name(self):
        """List configMapKey defaults to env name when omitted.

        0.2.20b: K8s configMapKeyRef.key should default to the env var name
        when no explicit configMapKey is provided.
        """
        result = _build_env_vars([
            {"name": "LOG_LEVEL", "configMapName": "app-settings"},
        ])
        ref = result[0]["valueFrom"]["configMapKeyRef"]
        assert ref["name"] == "app-settings"
        assert ref["key"] == "LOG_LEVEL", (
            f"configMapKey should default to env name 'LOG_LEVEL', got '{ref['key']}'"
        )

    def test_wizard_variable_without_svc_name(self):
        """Wizard type=variable without svc_name → fallback derivation from varName.

        0.2.20c: When svc_name is not provided, the builder derives the
        configMap reference name from the varName field.
        """
        result = _build_env_vars([
            {"key": "CONFIG_URL", "type": "variable", "varName": "${APP_CONFIG}"},
        ])
        assert len(result) == 1
        ref = result[0]["valueFrom"]["configMapKeyRef"]
        # Derived from varName: strip ${}, lowercase, replace _ with -
        assert ref["name"] == "app-config"
        assert ref["key"] == "CONFIG_URL"



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

    def test_kuma_inject(self):
        """Kuma mesh → kuma.io/sidecar-injection annotation.

        Kuma uses kuma.io/sidecar-injection for injection control.
        Value should be 'true' (string, not boolean).
        """
        result = _build_mesh_annotations({"provider": "kuma"})
        assert "kuma.io/sidecar-injection" in result
        assert result["kuma.io/sidecar-injection"] == "true"

    def test_linkerd_proxy_resources(self):
        """Linkerd proxy resource annotations use different keys than Istio.

        Linkerd uses config.linkerd.io/proxy-cpu-request instead of
        sidecar.istio.io/proxyCPU. Both are loaded from the data catalog.
        """
        result = _build_mesh_annotations({
            "provider": "linkerd",
            "proxyCpuRequest": "200m",
            "proxyMemRequest": "256Mi",
        })
        assert result["config.linkerd.io/proxy-cpu-request"] == "200m"
        assert result["config.linkerd.io/proxy-memory-request"] == "256Mi"
        # Must NOT contain Istio keys
        assert "sidecar.istio.io/proxyCPU" not in result

    def test_log_level_annotation(self):
        """Log level annotation uses provider-specific key.

        Istio: sidecar.istio.io/logLevel
        Linkerd: config.linkerd.io/proxy-log-level
        """
        result = _build_mesh_annotations({
            "provider": "istio",
            "logLevel": "debug",
        })
        assert result["sidecar.istio.io/logLevel"] == "debug"

    def test_exclude_ports_annotations(self):
        """Exclude inbound/outbound ports annotations.

        Istio: traffic.sidecar.istio.io/excludeInboundPorts
        and traffic.sidecar.istio.io/excludeOutboundPorts.
        """
        result = _build_mesh_annotations({
            "provider": "istio",
            "excludeInbound": "8081,8082",
            "excludeOutbound": "5432",
        })
        assert result["traffic.sidecar.istio.io/excludeInboundPorts"] == "8081,8082"
        assert result["traffic.sidecar.istio.io/excludeOutboundPorts"] == "5432"

    def test_unknown_provider_falls_back_to_istio(self):
        """Unknown provider → falls back to Istio annotation prefixes.

        Code uses all_prefixes.get(provider, all_prefixes['istio']),
        so an unrecognized provider still gets Istio-style annotations.
        """
        result = _build_mesh_annotations({"provider": "cilium-mesh"})
        assert "sidecar.istio.io/inject" in result
        assert result["sidecar.istio.io/inject"] == "true"


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

    def test_replicaset(self):
        assert _api_version_for_kind("ReplicaSet") == "apps/v1"

    def test_networkpolicy(self):
        assert _api_version_for_kind("NetworkPolicy") == "networking.k8s.io/v1"

    def test_horizontalpodautoscaler(self):
        assert _api_version_for_kind("HorizontalPodAutoscaler") == "autoscaling/v2"
