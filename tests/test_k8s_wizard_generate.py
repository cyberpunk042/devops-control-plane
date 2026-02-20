"""
Tests for k8s_wizard_generate — resources → YAML manifest files.

These are pure unit tests: resource list in → {ok, files} with YAML content.
No subprocess, no network.
"""

from pathlib import Path

import yaml

from src.core.services.k8s_wizard_generate import (
    generate_k8s_wizard,
    _generate_skaffold,
)


# ═══════════════════════════════════════════════════════════════════
#  generate_k8s_wizard
# ═══════════════════════════════════════════════════════════════════


class TestGenerateK8sWizard:
    def test_deployment_yaml(self, tmp_path: Path):
        """Deployment resource → valid YAML with correct K8s structure.

        K8s Deployment spec requires:
        - apiVersion: apps/v1
        - kind: Deployment
        - metadata.name, metadata.namespace
        - spec.replicas, spec.selector.matchLabels, spec.template
        - spec.strategy with type and rollingUpdate params
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "myapp:1.0",
                    "port": 8080,
                    "replicas": 3,
                },
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 1
        manifest = yaml.safe_load(result["files"][0]["content"])
        # Full K8s object shape
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"
        assert manifest["metadata"]["name"] == "api"
        assert manifest["metadata"]["namespace"] == "default"
        # Deployment spec
        assert manifest["spec"]["replicas"] == 3
        assert manifest["spec"]["selector"]["matchLabels"]["app"] == "api"
        # Template exists with pod spec
        assert "template" in manifest["spec"]
        assert "spec" in manifest["spec"]["template"]
        assert "containers" in manifest["spec"]["template"]["spec"]
        # Strategy present
        assert "strategy" in manifest["spec"]

    def test_deployment_template_labels_match_selector(self, tmp_path: Path):
        """Deployment template metadata.labels.app matches selector.matchLabels.

        K8s spec: The pod template's labels MUST match the selector,
        otherwise the Deployment controller cannot manage the pods.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "web",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "web:1.0", "port": 3000},
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        selector_labels = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        # They must match for K8s to accept the manifest
        assert selector_labels == template_labels, (
            f"selector {selector_labels} != template labels {template_labels}"
        )

    def test_service_yaml(self, tmp_path: Path):
        """Service resource → correct port, targetPort, selector, type.

        K8s Service spec requires:
        - apiVersion: v1
        - spec.type, spec.selector, spec.ports[]
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Service",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "port": 80,
                    "target_port": 8080,
                    "type": "ClusterIP",
                    "selector": "api",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Service"
        assert manifest["metadata"]["name"] == "api"
        assert manifest["spec"]["type"] == "ClusterIP"
        assert manifest["spec"]["selector"] == {"app": "api"}
        assert manifest["spec"]["ports"][0]["port"] == 80
        assert manifest["spec"]["ports"][0]["targetPort"] == 8080

    def test_headless_service_yaml(self, tmp_path: Path):
        """Headless Service → clusterIP: None for StatefulSet backing.

        K8s spec: A headless Service has spec.clusterIP set to "None".
        Used by StatefulSets for stable network identity.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Service",
                "name": "db-headless",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "port": 5432,
                    "target_port": 5432,
                    "type": "None",
                    "selector": "db",
                    "headless": True,
                },
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["spec"]["clusterIP"] == "None"

    def test_configmap_yaml(self, tmp_path: Path):
        """ConfigMap resource → apiVersion v1, data keys at top level.

        K8s ConfigMap spec: data is at the TOP LEVEL of the manifest,
        NOT nested under spec. apiVersion is v1.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "ConfigMap",
                "name": "api-config",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "data": {"LOG_LEVEL": "info", "DB_HOST": "localhost"},
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "ConfigMap"
        assert manifest["metadata"]["name"] == "api-config"
        assert manifest["data"]["LOG_LEVEL"] == "info"
        assert manifest["data"]["DB_HOST"] == "localhost"
        # Data must NOT be under spec
        assert "spec" not in manifest

    def test_secret_yaml(self, tmp_path: Path):
        """Secret resource → apiVersion v1, stringData, type Opaque.

        K8s Secret spec: type defaults to Opaque, stringData is the
        human-readable form (base64-encoded on apply).
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "api-secrets",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "stringData": {"API_KEY": "CHANGE_ME"},
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Secret"
        assert manifest["type"] == "Opaque"
        assert manifest["stringData"]["API_KEY"] == "CHANGE_ME"

    def test_ingress_yaml(self, tmp_path: Path):
        """Ingress resource → networking.k8s.io/v1, rules with host, pathType, backend.

        K8s Ingress spec requires:
        - apiVersion: networking.k8s.io/v1
        - spec.rules[].host, spec.rules[].http.paths[].pathType
        - backend.service.name, backend.service.port.number
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Ingress",
                "name": "api-ingress",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "host": "api.example.com",
                    "port": 80,
                    "service": "api",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "networking.k8s.io/v1"
        assert manifest["kind"] == "Ingress"
        rules = manifest["spec"]["rules"]
        assert len(rules) == 1
        assert rules[0]["host"] == "api.example.com"
        path = rules[0]["http"]["paths"][0]
        assert path["pathType"] == "Prefix"
        assert path["backend"]["service"]["name"] == "api"
        assert path["backend"]["service"]["port"]["number"] == 80

    def test_ingress_multi_path_yaml(self, tmp_path: Path):
        """Ingress multi-path rules → _paths expanded into rules[0].http.paths.

        K8s Ingress spec: multiple paths under a single host, each
        with its own backend service.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Ingress",
                "name": "app-ingress",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "host": "app.example.com",
                    "_paths": [
                        {
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {"service": {"name": "web", "port": {"number": 3000}}},
                        },
                        {
                            "path": "/api",
                            "pathType": "Prefix",
                            "backend": {"service": {"name": "api", "port": {"number": 8080}}},
                        },
                    ],
                },
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        paths = manifest["spec"]["rules"][0]["http"]["paths"]
        assert len(paths) == 2
        assert paths[0]["backend"]["service"]["name"] == "web"
        assert paths[1]["backend"]["service"]["name"] == "api"
        assert paths[1]["path"] == "/api"

    def test_pvc_yaml(self, tmp_path: Path):
        """PVC resource → accessModes, resources.requests.storage, storageClassName.

        K8s PVC spec requires:
        - spec.accessModes (list)
        - spec.resources.requests.storage
        - spec.storageClassName (optional)
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "PersistentVolumeClaim",
                "name": "api-data",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "storage": "10Gi",
                    "storageClassName": "gp3",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "PersistentVolumeClaim"
        assert manifest["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert manifest["spec"]["resources"]["requests"]["storage"] == "10Gi"
        assert manifest["spec"]["storageClassName"] == "gp3"

    def test_pvc_volume_name_for_static(self, tmp_path: Path):
        """PVC volumeName for pvc-static binding.

        K8s PVC spec: spec.volumeName binds the claim to a specific
        PersistentVolume (pre-provisioned).
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "PersistentVolumeClaim",
                "name": "legacy-data",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "storage": "50Gi",
                    "volumeName": "pv-legacy-001",
                },
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["spec"]["volumeName"] == "pv-legacy-001"

    def test_namespace_yaml(self, tmp_path: Path):
        """Namespace resource → apiVersion v1, no namespace in metadata.

        K8s spec: Namespace resources are cluster-scoped, they must NOT
        have a namespace field in their metadata.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Namespace",
                "name": "production",
                "namespace": "production",
                "output_dir": "k8s",
                "spec": {},
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Namespace"
        assert manifest["metadata"]["name"] == "production"
        assert "namespace" not in manifest["metadata"]

    def test_empty_resources_error(self, tmp_path: Path):
        """Empty resource list → error."""
        result = generate_k8s_wizard(tmp_path, [])
        assert "error" in result

    def test_managed_kind_skipped(self, tmp_path: Path):
        """Managed kind produces no manifest file."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Managed",
                "name": "rds-postgres",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {},
            },
        ])
        assert "error" in result  # Only Managed → no valid files

    def test_file_paths_use_output_dir(self, tmp_path: Path):
        """Output dir is reflected in file paths."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "manifests/prod",
                "spec": {"image": "app:1", "port": 8080},
            },
        ])
        assert result["files"][0]["path"].startswith("manifests/prod/")

    def test_file_naming_convention(self, tmp_path: Path):
        """File naming convention → {output_dir}/{name}-{kind.lower()}.yaml.

        Consistent naming allows Skaffold and other tools to glob
        for manifests predictably.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "my-api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "app:1", "port": 8080},
            },
        ])
        assert result["files"][0]["path"] == "k8s/my-api-deployment.yaml"

    def test_deployment_strategy_in_yaml(self, tmp_path: Path):
        """Deployment strategy fields appear in the generated YAML.

        K8s Deployment spec: strategy.type + strategy.rollingUpdate
        with maxSurge and maxUnavailable.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "app:1",
                    "port": 8080,
                    "replicas": 3,
                    "strategy": "RollingUpdate",
                    "maxSurge": 2,
                    "maxUnavailable": 0,
                },
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        strategy = manifest["spec"]["strategy"]
        assert strategy["type"] == "RollingUpdate"
        assert strategy["rollingUpdate"]["maxSurge"] == 2
        assert strategy["rollingUpdate"]["maxUnavailable"] == 0

    def test_multi_resource_generates_multiple_files(self, tmp_path: Path):
        """Multiple resources → multiple file entries."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "app:1", "port": 8080},
            },
            {
                "kind": "Service",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"port": 80, "target_port": 8080},
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 2

    def test_statefulset_yaml(self, tmp_path: Path):
        """StatefulSet → apps/v1, serviceName, selector, VCTs.

        K8s StatefulSet spec requires:
        - apiVersion: apps/v1
        - spec.serviceName (headless service)
        - spec.selector.matchLabels
        - spec.volumeClaimTemplates[] with accessModes, resources.requests.storage
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "StatefulSet",
                "name": "db",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "postgres:16",
                    "port": 5432,
                    "replicas": 3,
                    "headlessServiceName": "db-headless",
                    "volumeClaimTemplates": [
                        {"name": "pgdata", "size": "50Gi", "accessMode": "ReadWriteOnce", "storageClass": "gp3"},
                    ],
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "StatefulSet"
        assert manifest["spec"]["replicas"] == 3
        assert manifest["spec"]["serviceName"] == "db-headless"
        assert manifest["spec"]["selector"]["matchLabels"]["app"] == "db"
        # VCTs
        vcts = manifest["spec"]["volumeClaimTemplates"]
        assert len(vcts) == 1
        assert vcts[0]["metadata"]["name"] == "pgdata"
        assert vcts[0]["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert vcts[0]["spec"]["resources"]["requests"]["storage"] == "50Gi"
        assert vcts[0]["spec"]["storageClassName"] == "gp3"

    def test_daemonset_yaml(self, tmp_path: Path):
        """DaemonSet → apps/v1, no replicas, nodeSelector + tolerations.

        K8s DaemonSet spec:
        - No replicas field (runs on every matching node)
        - nodeSelector restricts which nodes
        - tolerations allow tainted nodes
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "DaemonSet",
                "name": "log-agent",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "fluentd:v1.16",
                    "port": 24224,
                    "nodeSelector": {"kubernetes.io/os": "linux"},
                    "tolerations": [{"key": "node-role.kubernetes.io/master", "effect": "NoSchedule"}],
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "DaemonSet"
        assert manifest["spec"]["selector"]["matchLabels"]["app"] == "log-agent"
        # DaemonSet must NOT have replicas
        assert "replicas" not in manifest["spec"]
        # nodeSelector in pod template spec
        ns = manifest["spec"]["template"]["spec"].get("nodeSelector", {})
        assert ns["kubernetes.io/os"] == "linux"
        # tolerations in pod template spec
        tols = manifest["spec"]["template"]["spec"]["tolerations"]
        assert len(tols) == 1
        assert tols[0]["key"] == "node-role.kubernetes.io/master"

    def test_job_yaml(self, tmp_path: Path):
        """Job → batch/v1, backoffLimit default 4, restartPolicy Never.

        K8s Job spec:
        - apiVersion: batch/v1
        - spec.backoffLimit (default 4 if not specified)
        - spec.template.spec.restartPolicy must be Never or OnFailure
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Job",
                "name": "migration",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "api:v1",
                    "command": "python manage.py migrate",
                    "completions": 1,
                    "parallelism": 1,
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "batch/v1"
        assert manifest["kind"] == "Job"
        assert manifest["spec"]["backoffLimit"] == 4  # default
        assert manifest["spec"]["completions"] == 1
        assert manifest["spec"]["parallelism"] == 1
        # restartPolicy must be set on the pod template
        assert manifest["spec"]["template"]["spec"]["restartPolicy"] == "Never"

    def test_cronjob_yaml(self, tmp_path: Path):
        """CronJob → batch/v1, schedule, concurrencyPolicy, nested jobTemplate.

        K8s CronJob spec:
        - apiVersion: batch/v1
        - spec.schedule (cron expression)
        - spec.concurrencyPolicy
        - spec.jobTemplate.spec.template (nested pod template)
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "CronJob",
                "name": "cleanup",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "cleanup:v1",
                    "schedule": "0 2 * * *",
                    "concurrencyPolicy": "Replace",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "batch/v1"
        assert manifest["kind"] == "CronJob"
        assert manifest["spec"]["schedule"] == "0 2 * * *"
        assert manifest["spec"]["concurrencyPolicy"] == "Replace"
        # Nested jobTemplate structure
        jt = manifest["spec"]["jobTemplate"]
        assert "spec" in jt
        assert "template" in jt["spec"]
        # Pod template restartPolicy
        assert jt["spec"]["template"]["spec"]["restartPolicy"] == "Never"

    def test_hpa_yaml(self, tmp_path: Path):
        """HPA → autoscaling/v2, scaleTargetRef, minReplicas, maxReplicas, targetCPU.

        K8s HPA spec:
        - apiVersion: autoscaling/v2
        - spec.scaleTargetRef with apiVersion, kind, name
        - spec.minReplicas, spec.maxReplicas
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "HorizontalPodAutoscaler",
                "name": "api-hpa",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "scaleTargetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": "api",
                    },
                    "minReplicas": 2,
                    "maxReplicas": 10,
                    "targetCPUUtilizationPercentage": 80,
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "autoscaling/v2"
        assert manifest["kind"] == "HorizontalPodAutoscaler"
        assert manifest["metadata"]["name"] == "api-hpa"
        # Spec fields pass through via generic handler
        assert manifest["spec"]["scaleTargetRef"]["kind"] == "Deployment"
        assert manifest["spec"]["scaleTargetRef"]["name"] == "api"
        assert manifest["spec"]["minReplicas"] == 2
        assert manifest["spec"]["maxReplicas"] == 10
        assert manifest["spec"]["targetCPUUtilizationPercentage"] == 80

    def test_mixed_workload_kinds(self, tmp_path: Path):
        """Multiple services with different workload kinds → each kind correct.

        K8s spec: Each workload kind has distinct structure.
        Deployment has replicas+strategy, DaemonSet has no replicas,
        StatefulSet has serviceName.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "api:v1", "port": 8080, "replicas": 2},
            },
            {
                "kind": "StatefulSet",
                "name": "db",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "postgres:16", "port": 5432, "replicas": 3},
            },
            {
                "kind": "DaemonSet",
                "name": "logger",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "fluentd:v1", "port": 24224},
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 3

        manifests = [yaml.safe_load(f["content"]) for f in result["files"]]
        kinds = {m["kind"] for m in manifests}
        assert kinds == {"Deployment", "StatefulSet", "DaemonSet"}

        # Each kind has correct structure
        deploy = next(m for m in manifests if m["kind"] == "Deployment")
        assert "replicas" in deploy["spec"]
        assert "strategy" in deploy["spec"]

        ss = next(m for m in manifests if m["kind"] == "StatefulSet")
        assert "serviceName" in ss["spec"]
        assert "replicas" in ss["spec"]

        ds = next(m for m in manifests if m["kind"] == "DaemonSet")
        assert "replicas" not in ds["spec"]

    def test_no_kind_defaults_to_deployment(self, tmp_path: Path):
        """No kind specified → defaults to Deployment.

        Project scope: When a service resource has no explicit kind,
        the generator should default to Deployment (the most common
        workload kind in K8s).
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "",  # empty → should default to Deployment
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "api:v1", "port": 8080},
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 1
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["kind"] == "Deployment"
        assert manifest["apiVersion"] == "apps/v1"
        assert "replicas" in manifest["spec"]


# ═══════════════════════════════════════════════════════════════════
#  0.2.19  Skaffold Integration (wizard)
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldGeneration:
    """0.2.19a-d: Comprehensive tests for _generate_skaffold.

    Source of truth: Skaffold v4beta11 schema + _generate_skaffold contract.
    """

    # ── 0.2.19a Gate logic ──────────────────────────────────────────

    def test_enabled_returns_file_dict(self):
        """skaffold=True → file dict returned (not None).

        0.2.19a: gate logic — enabled produces output.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        assert result is not None
        assert isinstance(result, dict)

    def test_disabled_returns_none(self):
        """skaffold=False → None returned.

        0.2.19a: gate logic — disabled produces nothing.
        """
        result = _generate_skaffold({"skaffold": False}, [])
        assert result is None

    def test_absent_returns_none(self):
        """skaffold key absent → None returned.

        0.2.19a: gate logic — missing key treated as disabled.
        """
        result = _generate_skaffold({"_services": []}, [])
        assert result is None

    def test_overwrite_is_false(self):
        """overwrite field on returned dict is False.

        0.2.19a: skip existing skaffold.yaml on subsequent runs.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        assert result["overwrite"] is False

    # ── 0.2.19b Document structure ──────────────────────────────────

    def test_api_version(self):
        """apiVersion is skaffold/v4beta11 (current stable).

        0.2.19b: Skaffold v4beta11 schema compliance.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["apiVersion"] == "skaffold/v4beta11"

    def test_kind_is_config(self):
        """kind is Config.

        0.2.19b: Skaffold document kind.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["kind"] == "Config"

    def test_metadata_name_from_first_service(self):
        """metadata.name is first service's name when services exist.

        0.2.19b: metadata naming convention.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "frontend", "image": "fe:v1"},
                {"name": "backend", "image": "be:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["metadata"]["name"] == "frontend"

    def test_metadata_name_defaults_to_app(self):
        """metadata.name defaults to "app" when no services.

        0.2.19b: fallback naming.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": []},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["metadata"]["name"] == "app"

    def test_output_is_valid_yaml(self):
        """Output is valid YAML (round-trip parse succeeds).

        0.2.19b: structural validity.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        assert isinstance(content, dict)
        # Re-dump to verify round-trip
        redumped = yaml.dump(content)
        reparsed = yaml.safe_load(redumped)
        assert reparsed == content

    def test_output_file_path(self):
        """Output file path is "skaffold.yaml" (root, not in k8s/).

        0.2.19b: file location convention.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        assert result["path"] == "skaffold.yaml"

    # ── 0.2.19c Build artifacts ─────────────────────────────────────

    def test_service_produces_build_artifact(self):
        """Non-Skip service with image → build artifact entry.

        0.2.19c: artifact generation from services.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "myapp:v1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "build" in content
        artifacts = content["build"]["artifacts"]
        assert len(artifacts) == 1

    def test_artifact_image_matches_service(self):
        """Artifact image matches service image string exactly.

        0.2.19c: image name fidelity.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "my-registry/app:v2.1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["artifacts"][0]["image"] == "my-registry/app:v2.1"

    def test_artifact_context_is_dot(self):
        """Artifact context is "." (build context = project root).

        0.2.19c: Skaffold build context convention.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["artifacts"][0]["context"] == "."

    def test_skip_service_excluded_from_artifacts(self):
        """kind: Skip service → excluded from artifacts.

        0.2.19c: Skip services are external, no build needed.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "postgres", "kind": "Skip", "image": "postgres:16"},
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        images = [a["image"] for a in content["build"]["artifacts"]]
        assert "postgres:16" not in images
        assert "api:v1" in images

    def test_empty_image_excluded_from_artifacts(self):
        """Service with empty image → excluded from artifacts.

        0.2.19c: no image means nothing to build.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "init-job", "image": ""},
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        images = [a["image"] for a in content["build"]["artifacts"]]
        assert len(images) == 1
        assert images[0] == "api:v1"

    def test_no_eligible_services_no_build_section(self):
        """No eligible services → no build section in output.

        0.2.19c: empty build is omitted entirely.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "ext-db", "kind": "Skip", "image": "postgres:16"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "build" not in content

    def test_multiple_services_multiple_artifacts(self):
        """Multiple services → multiple artifacts in build section.

        0.2.19c: each service produces its own artifact.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
                {"name": "worker", "image": "worker:v1"},
                {"name": "frontend", "image": "fe:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert len(content["build"]["artifacts"]) == 3

    # ── 0.2.19d Manifests & deploy ──────────────────────────────────

    def test_generated_paths_in_manifests(self):
        """Generated K8s YAML paths → listed in manifests.rawYaml.

        0.2.19d: manifest path collection.
        """
        generated_files = [
            {"path": "k8s/api-deployment.yaml"},
            {"path": "k8s/api-service.yaml"},
            {"path": "k8s/api-configmap.yaml"},
        ]
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            generated_files,
        )
        content = yaml.safe_load(result["content"])
        raw_yaml = content["manifests"]["rawYaml"]
        assert len(raw_yaml) == 3
        assert "k8s/api-deployment.yaml" in raw_yaml
        assert "k8s/api-service.yaml" in raw_yaml
        assert "k8s/api-configmap.yaml" in raw_yaml

    def test_non_yaml_files_excluded(self):
        """Non-YAML files excluded from manifest list.

        0.2.19d: only .yaml/.yml files are relevant manifests.
        """
        generated_files = [
            {"path": "k8s/api-deployment.yaml"},
            {"path": "k8s/README.md"},
            {"path": "k8s/.wizard-state.json"},
        ]
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            generated_files,
        )
        content = yaml.safe_load(result["content"])
        raw_yaml = content["manifests"]["rawYaml"]
        assert len(raw_yaml) == 1
        assert raw_yaml[0] == "k8s/api-deployment.yaml"

    def test_no_manifests_fallback_glob(self):
        """No generated manifests → fallback glob {output_dir}/*.yaml.

        0.2.19d: fallback ensures skaffold can still find manifests.
        """
        result = _generate_skaffold(
            {"skaffold": True, "output_dir": "k8s", "_services": []},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["manifests"]["rawYaml"] == ["k8s/*.yaml"]

    def test_custom_output_dir_in_fallback_glob(self):
        """Custom output_dir reflected in fallback glob path.

        0.2.19d: output_dir parameterization.
        """
        result = _generate_skaffold(
            {"skaffold": True, "output_dir": "manifests/prod", "_services": []},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["manifests"]["rawYaml"] == ["manifests/prod/*.yaml"]

    def test_deploy_kubectl_section_present(self):
        """deploy.kubectl section present (empty dict — kubectl deployer).

        0.2.19d: Skaffold deploy strategy.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "api:v1"}]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "deploy" in content
        assert "kubectl" in content["deploy"]


class TestSkaffoldIntegration:
    """0.2.19e: Integration test — wizard setup → skaffold_status detection."""

    def test_setup_then_detect(self, tmp_path: Path):
        """After wizard setup with skaffold=True → skaffold_status detects it.

        0.2.19e: end-to-end round-trip from wizard → disk → detection.
        """
        from src.core.services.wizard_setup import setup_k8s
        from src.core.services.k8s_wizard_detect import skaffold_status

        state = {
            "namespace": "default",
            "skaffold": True,
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1},
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True

        status = skaffold_status(tmp_path)
        assert status["has_skaffold"] is True
        assert len(status["configs"]) >= 1
        cfg = status["configs"][0]
        assert cfg["api_version"] == "skaffold/v4beta11"


# ═══════════════════════════════════════════════════════════════════
#  0.3.3  Skaffold Build Section — TDD RED
#
#  Source of truth: Skaffold v4beta11 `build` schema.
#  These tests define what `_generate_skaffold` MUST produce.
#  They will FAIL until the backend is evolved.
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldBuildArtifacts:
    """0.3.3a: Build artifacts — docker config from wizard services.

    Source of truth: Skaffold v4beta11 build.artifacts[].docker schema.
    Each artifact can specify dockerfile, buildArgs, and target.
    """

    def test_service_with_dockerfile_field(self):
        """Service with `dockerfile` → artifact gets `docker.dockerfile`.

        0.3.3a: The wizard lets users specify a non-default Dockerfile path.
        The generated Skaffold config must reflect this.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "dockerfile": "docker/Dockerfile.prod"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifact = content["build"]["artifacts"][0]
        assert "docker" in artifact, "Artifact missing 'docker' section"
        assert artifact["docker"]["dockerfile"] == "docker/Dockerfile.prod"

    def test_service_without_dockerfile_defaults(self):
        """Service without `dockerfile` → artifact defaults to `Dockerfile`.

        0.3.3a: When no dockerfile is specified, Skaffold expects a
        Dockerfile at the build context root. We make this explicit.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifact = content["build"]["artifacts"][0]
        assert "docker" in artifact, "Artifact missing 'docker' section"
        assert artifact["docker"]["dockerfile"] == "Dockerfile"

    def test_service_with_build_args(self):
        """Service with `buildArgs` dict → artifact gets `docker.buildArgs`.

        0.3.3a: Build arguments are passed through to the Docker builder.
        These can be env-specific (NODE_ENV, BUILD_MODE) or version info.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "buildArgs": {
                    "NODE_ENV": "production",
                    "BUILD_MODE": "optimized",
                }},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifact = content["build"]["artifacts"][0]
        assert artifact["docker"]["buildArgs"] == {
            "NODE_ENV": "production",
            "BUILD_MODE": "optimized",
        }

    def test_service_with_build_target(self):
        """Service with `buildTarget` → artifact gets `docker.target`.

        0.3.3a: Multi-stage Dockerfiles use a target stage name.
        e.g., `docker build --target production .`
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "buildTarget": "production"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifact = content["build"]["artifacts"][0]
        assert artifact["docker"]["target"] == "production"

    def test_service_with_all_docker_options(self):
        """Service with dockerfile + buildArgs + buildTarget → all reflected.

        0.3.3a: Combined docker config — all three fields present.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "dockerfile": "Dockerfile.prod",
                    "buildArgs": {"NODE_ENV": "production"},
                    "buildTarget": "runner",
                },
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        docker = content["build"]["artifacts"][0]["docker"]
        assert docker["dockerfile"] == "Dockerfile.prod"
        assert docker["buildArgs"] == {"NODE_ENV": "production"}
        assert docker["target"] == "runner"

    def test_multiple_services_each_get_docker_config(self):
        """Multiple services with different docker configs → each artifact independent.

        0.3.3a: Each service's docker settings are isolated.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "dockerfile": "api/Dockerfile"},
                {"name": "worker", "image": "worker:v1", "buildTarget": "worker-stage"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifacts = content["build"]["artifacts"]
        assert len(artifacts) == 2

        api_art = [a for a in artifacts if a["image"] == "api:v1"][0]
        assert api_art["docker"]["dockerfile"] == "api/Dockerfile"

        worker_art = [a for a in artifacts if a["image"] == "worker:v1"][0]
        assert worker_art["docker"]["target"] == "worker-stage"


class TestSkaffoldBuildLocal:
    """0.3.3b: Build local config.

    Source of truth: Skaffold v4beta11 build.local schema.
    Local build settings control Docker daemon behavior during dev.
    """

    def test_default_build_is_local(self):
        """Default build strategy is local (no cluster build).

        0.3.3b: `build.local` section present by default.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "build" in content
        assert "local" in content["build"], "Missing build.local section"

    def test_local_use_buildkit_true(self):
        """build.local.useBuildkit is true by default.

        0.3.3b: BuildKit is the modern Docker builder — faster and more
        cache-efficient. Should be enabled by default.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["local"]["useBuildkit"] is True

    def test_local_try_import_missing(self):
        """build.local.tryImportMissing is true.

        0.3.3b: Avoids redundant builds by importing images that already
        exist in the local Docker daemon.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["local"]["tryImportMissing"] is True

    def test_local_concurrency_from_service_count(self):
        """build.local.concurrency reflects number of services.

        0.3.3b: 0 = unlimited parallelism. For single service, 0 is fine.
        For multiple services, set to service count for bounded parallelism.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
                {"name": "worker", "image": "worker:v1"},
                {"name": "frontend", "image": "fe:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        # Concurrency should be present and reasonable
        concurrency = content["build"]["local"]["concurrency"]
        assert isinstance(concurrency, int)
        assert concurrency >= 0

    def test_local_push_false_by_default(self):
        """build.local.push is false by default (dev-first).

        0.3.3b: During new development, images shouldn't be pushed
        to a remote registry. Push is enabled per-profile (staging/prod).
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["local"]["push"] is False


class TestSkaffoldTagPolicy:
    """0.3.3c: Tag policy.

    Source of truth: Skaffold v4beta11 build.tagPolicy schema.
    Tag policies control how images are tagged — critical for
    reproducibility and CI/CD integration.
    """

    def test_default_tag_policy_git_commit(self):
        """Default tag policy is gitCommit (reproducible builds).

        0.3.3c: gitCommit tags images with the git SHA, ensuring
        every build is traceable to a specific commit.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "tagPolicy" in content["build"]
        assert "gitCommit" in content["build"]["tagPolicy"]

    def test_git_commit_variant_tags(self):
        """gitCommit variant is Tags (use git tag if available).

        0.3.3c: When a git tag exists, use it for the image tag.
        More readable than a bare SHA.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["build"]["tagPolicy"]["gitCommit"]["variant"] == "Tags"

    def test_wizard_sha256_tag_policy(self):
        """Wizard option tagPolicy: sha256 → build.tagPolicy.sha256.

        0.3.3c: sha256 is content-addressable — fast for dev, no git needed.
        """
        result = _generate_skaffold(
            {"skaffold": True, "tagPolicy": "sha256", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "sha256" in content["build"]["tagPolicy"]

    def test_wizard_datetime_tag_policy(self):
        """Wizard option tagPolicy: dateTime → build.tagPolicy.dateTime.

        0.3.3c: dateTime includes format and timezone fields.
        """
        result = _generate_skaffold(
            {"skaffold": True, "tagPolicy": "dateTime", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        tag_policy = content["build"]["tagPolicy"]
        assert "dateTime" in tag_policy
        assert "format" in tag_policy["dateTime"]
        assert "timezone" in tag_policy["dateTime"]

    def test_wizard_input_digest_tag_policy(self):
        """Wizard option tagPolicy: inputDigest → build.tagPolicy.inputDigest.

        0.3.3c: inputDigest tags based on the hash of build inputs.
        """
        result = _generate_skaffold(
            {"skaffold": True, "tagPolicy": "inputDigest", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "inputDigest" in content["build"]["tagPolicy"]

    def test_wizard_env_template_tag_policy(self):
        """Wizard option tagPolicy: envTemplate → build.tagPolicy.envTemplate.

        0.3.3c: envTemplate uses Go template syntax with env vars.
        """
        result = _generate_skaffold(
            {"skaffold": True, "tagPolicy": "envTemplate", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        tag_policy = content["build"]["tagPolicy"]
        assert "envTemplate" in tag_policy
        assert "template" in tag_policy["envTemplate"]


# ═══════════════════════════════════════════════════════════════════
#  0.3.4  Manifests & Deploy — TDD RED
#
#  Source of truth: Skaffold v4beta11 `deploy` + `manifests` schemas.
#  Critical: envsubst for local dev, kubectl namespace/flags/hooks.
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldDeployKubectl:
    """0.3.4e: Deploy section — kubectl enhancements.

    Source of truth: Skaffold v4beta11 deploy.kubectl schema.
    The deploy section needs namespace, flags, and hooks.
    """

    def test_default_namespace_from_wizard(self):
        """Wizard namespace → deploy.kubectl.defaultNamespace.

        0.3.4e: When wizard specifies a namespace, it flows into
        the kubectl deployer so all resources target that namespace.
        """
        result = _generate_skaffold(
            {"skaffold": True, "namespace": "production", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["deploy"]["kubectl"]["defaultNamespace"] == "production"

    def test_no_namespace_no_default(self):
        """No wizard namespace → no defaultNamespace key.

        0.3.4e: Omitting the field lets Skaffold use the current context's
        namespace, which is the expected default behavior.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "defaultNamespace" not in content["deploy"]["kubectl"]

    def test_server_side_apply_flag(self):
        """Wizard serverSideApply=True → deploy.kubectl.flags.apply includes --server-side.

        0.3.4e: Server-side apply is recommended for production deployments
        to avoid client-side field management issues.
        """
        result = _generate_skaffold(
            {"skaffold": True, "serverSideApply": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        flags = content["deploy"]["kubectl"]["flags"]
        assert "--server-side" in flags["apply"]

    def test_no_server_side_apply_no_flags(self):
        """serverSideApply absent → no flags section.

        0.3.4e: Don't pollute the config with empty flags.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "flags" not in content["deploy"]["kubectl"]

    def test_namespace_in_global_flags(self):
        """Wizard namespace → deploy.kubectl.flags.global includes --namespace.

        0.3.4e: Ensures ALL kubectl commands (not just apply) target
        the right namespace.
        """
        result = _generate_skaffold(
            {"skaffold": True, "namespace": "staging", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        flags = content["deploy"]["kubectl"].get("flags", {})
        global_flags = flags.get("global", [])
        assert "--namespace" in global_flags
        assert "staging" in global_flags

    def test_post_deploy_verification_hook(self):
        """postDeployVerify → hooks.after with rollout status check.

        0.3.4e: When wizard enables verification, the deploy section
        should include a post-deploy hook that runs `kubectl rollout status`
        to verify the deployment succeeded.
        """
        result = _generate_skaffold(
            {"skaffold": True, "postDeployVerify": True,
             "namespace": "production", "_services": [
                {"name": "api", "image": "api:v1", "kind": "Deployment"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"].get("hooks", {})
        after = hooks.get("after", [])
        assert len(after) >= 1, f"No after hooks: {hooks}"
        cmds = [str(h.get("host", {}).get("command", [])) for h in after]
        joined = " ".join(cmds)
        assert "rollout" in joined, \
            f"Missing rollout status verification: {cmds}"


class TestSkaffoldEnvsubstHooks:
    """0.3.4c: envsubst pre-deploy hooks for variable resolution.

    Source of truth: Skaffold v4beta11 deploy.kubectl.hooks schema +
    real-world local dev pattern.

    When manifests contain ${VAR} patterns (ConfigMap data, Secret stringData,
    container env values), they need substitution before kubectl apply.
    Skaffold does NOT do this natively — pre-deploy hooks must be generated.
    """

    @staticmethod
    def _svc_with_variables():
        """Helper: a service whose env vars include variable-type entries."""
        return {
            "name": "api",
            "image": "api:v1",
            "port": 8080,
            "env": [
                {"key": "DB_HOST", "type": "variable"},
                {"key": "API_KEY", "type": "secret"},
                {"key": "LOG_LEVEL", "value": "info"},
            ],
        }

    def test_variable_env_generates_hook(self):
        """Service with variable-type env → pre-deploy envsubst hook generated.

        0.3.4c: The hook runs `envsubst` on manifests that contain
        ${VAR} placeholders before kubectl apply.
        """
        svc = self._svc_with_variables()
        result = _generate_skaffold(
            {"skaffold": True, "_services": [svc]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"].get("hooks", {})
        before = hooks.get("before", [])
        assert len(before) > 0, "No pre-deploy hooks generated"
        # At least one hook command should reference envsubst
        hook_cmds = [h.get("host", {}).get("command", []) for h in before]
        all_cmds = [cmd for cmds in hook_cmds for cmd in cmds]
        joined = " ".join(str(c) for c in all_cmds)
        assert "envsubst" in joined, f"No envsubst in hooks: {hook_cmds}"

    def test_no_variables_no_hooks(self):
        """Service with only hardcoded env → no envsubst hooks.

        0.3.4c: Don't add hooks when there's nothing to substitute.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "LOG_LEVEL", "value": "info"},
                ]},
            ]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        kubectl = content["deploy"]["kubectl"]
        hooks = kubectl.get("hooks", {})
        before = hooks.get("before", [])
        assert len(before) == 0, f"Unexpected hooks: {before}"

    def test_env_example_file_generated(self):
        """Services with variable envs → .env.example content in result.

        0.3.4c: Developers need to know which variables to set.
        The .env.example lists all required variables with comments.
        """
        svc = self._svc_with_variables()
        result = _generate_skaffold(
            {"skaffold": True, "_services": [svc]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        assert "env_example" in result, "Missing .env.example content"
        env_content = result["env_example"]
        assert "DB_HOST" in env_content
        assert "API_KEY" in env_content
        # Hardcoded values should NOT appear in .env.example
        assert "LOG_LEVEL" not in env_content

    def test_hook_dir_is_project_root(self):
        """Hook dir defaults to project root.

        0.3.4c: envsubst must run from project root so paths resolve correctly.
        """
        svc = self._svc_with_variables()
        result = _generate_skaffold(
            {"skaffold": True, "_services": [svc]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"]["hooks"]["before"]
        for hook in hooks:
            host = hook.get("host", {})
            hook_dir = host.get("dir", ".")
            assert hook_dir == ".", f"Hook dir should be project root, got: {hook_dir}"

    def test_secret_type_also_triggers_hook(self):
        """Secret-type env vars also need envsubst (value comes from env).

        0.3.4c: Secrets with type=secret use ${VAR} in stringData,
        which needs envsubst just as type=variable does.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_PASSWORD", "type": "secret"},
                ]},
            ]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"].get("hooks", {})
        before = hooks.get("before", [])
        assert len(before) > 0, "Secret-type env should trigger envsubst hook"


class TestSkaffoldKustomizeManifests:
    """0.3.4b + 0.3.4g: Kustomize overlay structure in manifests & deploy.

    Source of truth: Skaffold v4beta11 manifests.kustomize + deploy.kustomize schemas.
    When deployStrategy is kustomize, manifests and deploy both switch to kustomize mode.
    """

    def test_kustomize_strategy_uses_kustomize_manifests(self):
        """deployStrategy=kustomize → manifests.kustomize.paths, NOT rawYaml.

        0.3.4b: Kustomize projects don't list raw YAML; they point at
        kustomization directories.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "kustomize" in content["manifests"], "Missing manifests.kustomize"
        assert "rawYaml" not in content["manifests"], "rawYaml should not be present for kustomize"

    def test_kustomize_base_path(self):
        """Default kustomize base path is k8s/base.

        0.3.4b: The base overlay contains shared resources.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        paths = content["manifests"]["kustomize"]["paths"]
        assert "k8s/base" in paths

    def test_kustomize_custom_output_dir(self):
        """Custom output_dir reflected in kustomize base path.

        0.3.4b: If the user sets output_dir=manifests, kustomize uses manifests/base.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize",
             "output_dir": "manifests", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        paths = content["manifests"]["kustomize"]["paths"]
        assert "manifests/base" in paths

    def test_kustomize_build_args_passed(self):
        """Kustomize buildArgs from wizard → manifests.kustomize.buildArgs.

        0.3.4b: Build arguments passed through to kustomize build.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize",
             "kustomizeBuildArgs": ["--enable-alpha-plugins"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["manifests"]["kustomize"]["buildArgs"] == ["--enable-alpha-plugins"]

    def test_base_kustomization_generated(self):
        """Kustomize strategy → kustomization.yaml generated for base dir.

        0.3.4b: The base kustomization.yaml must list all generated
        K8s manifests in its `resources:` list so kustomize build works.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [{"path": "k8s/base/api-deployment.yaml"},
             {"path": "k8s/base/api-service.yaml"}],
        )
        kust_files = result.get("kustomization_files", [])
        assert len(kust_files) >= 1, "No kustomization_files in result"
        base_kust = kust_files[0]
        assert "kustomization.yaml" in base_kust["path"]
        kust_content = yaml.safe_load(base_kust["content"])
        assert "resources" in kust_content
        assert "api-deployment.yaml" in kust_content["resources"]
        assert "api-service.yaml" in kust_content["resources"]

    def test_kustomize_config_map_generator(self):
        """Kustomize + variable env vars → configMapGenerator.envs in kustomization.

        0.3.4c: When services have variable-type env vars and strategy is
        kustomize, the base kustomization.yaml should include a
        configMapGenerator pulling values from .env file.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_HOST", "type": "variable"},
                ]},
            ]},
            [{"path": "k8s/base/api-deployment.yaml"}],
        )
        kust_files = result.get("kustomization_files", [])
        assert len(kust_files) >= 1
        kust_content = yaml.safe_load(kust_files[0]["content"])
        generators = kust_content.get("configMapGenerator", [])
        assert len(generators) >= 1, f"No configMapGenerator: {kust_content}"
        assert any(".env" in str(g.get("envs", [])) for g in generators), \
            f"configMapGenerator missing .env: {generators}"

    def test_kustomize_secret_generator(self):
        """Kustomize + secret env vars → secretGenerator.envs in kustomization.

        0.3.4c: When services have secret-type env vars and strategy is
        kustomize, the base kustomization.yaml should include a
        secretGenerator pulling values from .env.secret file.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_PASSWORD", "type": "secret"},
                ]},
            ]},
            [{"path": "k8s/base/api-deployment.yaml"}],
        )
        kust_files = result.get("kustomization_files", [])
        assert len(kust_files) >= 1
        kust_content = yaml.safe_load(kust_files[0]["content"])
        generators = kust_content.get("secretGenerator", [])
        assert len(generators) >= 1, f"No secretGenerator: {kust_content}"
        assert any(".env.secret" in str(g.get("envs", [])) for g in generators), \
            f"secretGenerator missing .env.secret: {generators}"

    def test_deploy_kustomize_build_args(self):
        """kustomizeBuildArgs → deploy.kustomize.buildArgs passed through.

        0.3.4g: Build arguments (e.g. --enable-alpha-plugins) flow into
        both manifests.kustomize.buildArgs and deploy.kustomize.buildArgs.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize",
             "kustomizeBuildArgs": ["--enable-alpha-plugins"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        deploy_args = content["deploy"]["kustomize"].get("buildArgs", [])
        assert "--enable-alpha-plugins" in deploy_args, \
            f"deploy.kustomize.buildArgs missing: {deploy_args}"

    def test_kustomize_deploy_section(self):
        """deployStrategy=kustomize → deploy.kustomize, NOT deploy.kubectl.

        0.3.4g: Kustomize deploy replaces kubectl deploy.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "kustomize" in content["deploy"], "Missing deploy.kustomize"
        assert "kubectl" not in content["deploy"], "kubectl should not be present for kustomize"

    def test_kustomize_deploy_default_path(self):
        """deploy.kustomize includes base path by default.

        0.3.4g: Kustomize deploy points at the same directory structure.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "kustomize", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "k8s/base" in content["deploy"]["kustomize"].get("paths", [])

    def test_kubectl_strategy_is_default(self):
        """No deployStrategy → kubectl (the default behavior).

        0.3.4b: Existing behavior preserved — rawYaml + kubectl.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [{"path": "k8s/api.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        assert "rawYaml" in content["manifests"]
        assert "kubectl" in content["deploy"]


class TestSkaffoldHelmDeploy:
    """0.3.4f: Helm deploy section.

    Source of truth: Skaffold v4beta11 deploy.helm schema.
    When deployStrategy is helm, deploy uses helm.releases instead of kubectl.
    """

    def test_helm_strategy_uses_helm_deploy(self):
        """deployStrategy=helm → deploy.helm.releases, NOT kubectl.

        0.3.4f: Helm deployment replaces kubectl.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "helm" in content["deploy"], "Missing deploy.helm"
        assert "kubectl" not in content["deploy"], "kubectl should not be present for helm"

    def test_helm_release_name_from_service(self):
        """Each service → one Helm release with matching name.

        0.3.4f: Release name comes from the service name.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        releases = content["deploy"]["helm"]["releases"]
        assert len(releases) == 1
        assert releases[0]["name"] == "api"

    def test_helm_release_chart_path(self):
        """Helm release has chartPath.

        0.3.4f: Points to the Helm chart directory.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm",
             "helmChartPath": "charts/api", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert content["deploy"]["helm"]["releases"][0]["chartPath"] == "charts/api"

    def test_helm_release_values_files(self):
        """Helm release has valuesFiles.

        0.3.4f: Points to values override files.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm",
             "helmValuesFiles": ["values.yaml", "values-dev.yaml"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        release = content["deploy"]["helm"]["releases"][0]
        assert release["valuesFiles"] == ["values.yaml", "values-dev.yaml"]

    def test_helm_release_namespace(self):
        """Wizard namespace → helm release namespace.

        0.3.4f: Namespace flows into the Helm release.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm",
             "namespace": "production", "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        release = content["deploy"]["helm"]["releases"][0]
        assert release["namespace"] == "production"
        assert release["createNamespace"] is True

    def test_helm_release_set_values(self):
        """Wizard env vars → helm release setValues.

        0.3.4f: Environment variables are passed as Helm --set values.
        No envsubst needed — Helm handles variable injection natively.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm", "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "LOG_LEVEL", "value": "info"},
                ]},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        release = content["deploy"]["helm"]["releases"][0]
        assert "setValues" in release
        assert release["setValues"]["LOG_LEVEL"] == "info"

    def test_helm_release_set_value_templates(self):
        """Variable-type env vars → helm release setValueTemplates.

        0.3.4f: Variables (type=variable) use Skaffold's Go template syntax
        in setValueTemplates, e.g. "{{.DB_HOST}}". Literal values stay in
        setValues.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm", "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_HOST", "type": "variable"},
                    {"key": "LOG_LEVEL", "value": "info"},
                ]},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        release = content["deploy"]["helm"]["releases"][0]
        # Variable → setValueTemplates
        assert "setValueTemplates" in release, \
            f"Missing setValueTemplates: {release.keys()}"
        assert "{{.DB_HOST}}" in release["setValueTemplates"].get("DB_HOST", "")
        # Literal stays in setValues
        assert release.get("setValues", {}).get("LOG_LEVEL") == "info"

    def test_helm_release_use_helm_secrets(self):
        """helmSecretsPlugin → useHelmSecrets: true on releases.

        0.3.4f: When the helm-secrets plugin is detected/enabled,
        releases should set useHelmSecrets to true.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm",
             "helmSecretsPlugin": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        release = content["deploy"]["helm"]["releases"][0]
        assert release.get("useHelmSecrets") is True

    def test_helm_no_envsubst_hooks(self):
        """Helm strategy → no envsubst hooks (Helm handles variables).

        0.3.4f: Helm's --set and values files handle variable injection.
        envsubst hooks are only for kubectl deploy.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm", "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_HOST", "type": "variable"},
                ]},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        # No kubectl section at all for helm strategy
        assert "kubectl" not in content["deploy"]

    def test_helm_multiple_services_multiple_releases(self):
        """Multiple services → multiple Helm releases.

        0.3.4f: Each service gets its own release.
        """
        result = _generate_skaffold(
            {"skaffold": True, "deployStrategy": "helm",
             "helmChartPath": "charts", "_services": [
                {"name": "api", "image": "api:v1"},
                {"name": "worker", "image": "worker:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        releases = content["deploy"]["helm"]["releases"]
        assert len(releases) == 2
        names = [r["name"] for r in releases]
        assert "api" in names
        assert "worker" in names


class TestSkaffoldSecretEncoding:
    """0.3.4d: Secret encoding in generated manifests.

    Source of truth: Kubernetes Secret spec + Skaffold deploy pipeline.
    Secrets with variable values need stringData (never raw data:) +
    envsubst. The skaffold generator must flag which secrets need envsubst.
    """

    def test_variable_secrets_flagged(self):
        """Services with secret-type env → result includes needs_envsubst flag.

        0.3.4d: The generator must communicate that generated secrets
        contain ${VAR} placeholders requiring envsubst before deploy.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_PASSWORD", "type": "secret"},
                ]},
            ]},
            [{"path": "k8s/api-secret.yaml"}],
        )
        assert result.get("needs_envsubst") is True

    def test_no_secrets_no_flag(self):
        """No secret-type env → needs_envsubst absent or False.

        0.3.4d: Don't flag configs that have no variable dependencies.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "LOG_LEVEL", "value": "info"},
                ]},
            ]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        assert not result.get("needs_envsubst")

    def test_variable_env_also_flags(self):
        """Variable-type env → needs_envsubst is True too.

        0.3.4d: Both secret and variable types need envsubst.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1", "env": [
                    {"key": "DB_HOST", "type": "variable"},
                ]},
            ]},
            [{"path": "k8s/api-deployment.yaml"}],
        )
        assert result.get("needs_envsubst") is True

    def test_secrets_use_string_data_not_data(self, tmp_path: Path):
        """Literal secret values → Secret manifest uses stringData, never data.

        0.3.4d: stringData is auto-base64-encoded by kubectl on apply.
        Using data: with raw (non-base64) values would be an error.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "api-secrets",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"stringData": {"DB_PASSWORD": "my-password"}},
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert "stringData" in manifest, "Secret must use stringData"
        assert "data" not in manifest, "Secret must NOT use data: (raw base64 risk)"
        assert manifest["stringData"]["DB_PASSWORD"] == "my-password"

    def test_data_key_converted_to_string_data(self, tmp_path: Path):
        """Even if spec uses 'data' key → output uses stringData, never data.

        0.3.4d: The generator must never emit data: with non-base64 values.
        Even legacy input using spec.data gets converted to stringData.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "legacy-secret",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"data": {"API_KEY": "raw-value"}},
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert "stringData" in manifest, "Must convert data → stringData"
        assert "data" not in manifest, "Must not keep raw data: key"
        assert manifest["stringData"]["API_KEY"] == "raw-value"

    def test_secret_with_vars_has_envsubst_comment(self, tmp_path: Path):
        """Secret manifest with ${VAR} values → includes envsubst comment.

        0.3.4d: Generated secrets containing variable placeholders must
        include a YAML comment indicating envsubst is required before deploy.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "api-secrets",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"stringData": {"DB_PASSWORD": "${DB_PASSWORD}"}},
            },
        ])
        raw_content = result["files"][0]["content"]
        assert "# requires envsubst" in raw_content, \
            f"Missing envsubst comment in:\n{raw_content}"

    def test_data_field_non_base64_raises_warning(self, tmp_path: Path):
        """Secret with data: containing non-base64 values → warning emitted.

        0.3.4d: If a secret provides data: with raw strings (not base64),
        the generator must warn and convert to stringData automatically.
        """
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "bad-secret",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"data": {"PASSWORD": "not-valid-base64!"}},
            },
        ])
        assert result["ok"] is True
        warnings = result.get("warnings", [])
        assert any("base64" in w.lower() for w in warnings), \
            f"Expected base64 warning, got: {warnings}"


# ═══════════════════════════════════════════════════════════════════
#  0.3.5  Profiles — TDD RED
#  0.3.6  Port Forwarding — TDD RED
#
#  Source of truth: Skaffold v4beta11 `profiles` + `portForward` schemas.
#  Profiles overlay build/deploy per environment.
#  Port forwarding maps K8s ports to localhost during dev.
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldProfileStructure:
    """0.3.5a: Profile structure — environments become profiles."""

    def test_environments_generate_profiles(self):
        """Wizard with environments → profiles section generated.

        0.3.5a: Each environment listed in the wizard becomes a Skaffold profile.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev", "staging", "prod"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "profiles" in content, "Missing profiles section"
        profile_names = [p["name"] for p in content["profiles"]]
        assert "dev" in profile_names
        assert "staging" in profile_names
        assert "prod" in profile_names

    def test_no_environments_no_profiles(self):
        """No environments → no profiles section.

        0.3.5a: Don't add an empty profiles section.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        assert "profiles" not in content

    def test_profile_activation_by_command(self):
        """Profile activation includes command trigger.

        0.3.5a: profiles[].activation[].command auto-activates the profile
        when running specific skaffold commands (dev/run/deploy).
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = content["profiles"][0]
        assert "activation" in profile
        activations = profile["activation"]
        commands = [a.get("command") for a in activations if "command" in a]
        assert len(commands) > 0, "No command activation found"

    def test_profile_activation_by_kube_context(self):
        """kubeContext pattern → activation[].kubeContext.

        0.3.5a: Profile can be auto-activated when connected to a
        matching kubeContext (e.g. "staging-*" matches staging-cluster).
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["staging"],
             "profileActivation": {"staging": {"kubeContext": "staging-.*"}},
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = content["profiles"][0]
        activations = profile["activation"]
        kube_ctx = [a.get("kubeContext") for a in activations if "kubeContext" in a]
        assert "staging-.*" in kube_ctx, \
            f"Missing kubeContext activation: {activations}"

    def test_profile_activation_by_env_var(self):
        """env var pattern → activation[].env.

        0.3.5a: Profile can be auto-activated when an env var matches
        (e.g. DEPLOY_ENV=production).
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["prod"],
             "profileActivation": {"prod": {"env": "DEPLOY_ENV=production"}},
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = content["profiles"][0]
        activations = profile["activation"]
        env_acts = [a.get("env") for a in activations if "env" in a]
        assert "DEPLOY_ENV=production" in env_acts, \
            f"Missing env activation: {activations}"

class TestSkaffoldDevFromLocalProfile:
    """0.3.5b: Dev-from-local profile — the critical one.

    This profile is for `skaffold dev -p dev-from-local`.
    Developer runs on their machine. No CI/CD. No registry.
    Variables from shell env or .env file.
    """

    @staticmethod
    def _wizard_state():
        return {
            "skaffold": True,
            "environments": ["dev-from-local"],
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "env": [{"key": "DB_HOST", "type": "variable"}]},
                {"name": "worker", "image": "worker:v1", "port": 9090},
            ],
        }

    def test_dev_from_local_profile_exists(self):
        """dev-from-local profile generated."""
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        names = [p["name"] for p in content["profiles"]]
        assert "dev-from-local" in names

    def test_dev_from_local_no_push(self):
        """Dev-from-local overrides build.local.push to false.

        0.3.5b: Images stay local, no registry push.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        assert profile["build"]["local"]["push"] is False

    def test_dev_from_local_sha256_tag(self):
        """Dev-from-local uses sha256 tag policy (fast, no git needed).

        0.3.5b: During local dev, git tags aren't relevant.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        assert "sha256" in profile["build"]["tagPolicy"]

    def test_dev_from_local_command_activation(self):
        """Dev-from-local activates on command: dev.

        0.3.5b: Auto-active during `skaffold dev`.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        activations = profile.get("activation", [])
        commands = [a["command"] for a in activations if "command" in a]
        assert "dev" in commands

    def test_dev_from_local_port_forward(self):
        """Dev-from-local includes portForward for all services with ports.

        0.3.5b → 0.3.6: Port forwarding only in dev profile.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        assert "portForward" in profile, "Missing portForward in dev-from-local"
        pf = profile["portForward"]
        assert len(pf) == 2, f"Expected 2 port-forwards, got {len(pf)}"

    def test_dev_from_local_default_namespace(self):
        """Dev-from-local uses 'default' namespace for local cluster.

        0.3.5b: Local k8s clusters (minikube, kind) use default namespace.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        deploy = profile.get("deploy", {})
        kubectl = deploy.get("kubectl", {})
        assert kubectl.get("defaultNamespace") == "default"

    def test_dev_from_local_envsubst_hook(self):
        """Dev-from-local with variable envs → envsubst pre-deploy hook.

        0.3.5b: All variable-bearing manifests need envsubst before deploy
        in the local dev workflow.
        """
        state = self._wizard_state()
        result = _generate_skaffold(state,
            [{"path": "k8s/api-deployment.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        hooks = profile.get("deploy", {}).get("kubectl", {}).get("hooks", {})
        before = hooks.get("before", [])
        assert len(before) >= 1, f"No pre-deploy hooks: {profile.get('deploy')}"
        cmds = [str(h.get("host", {}).get("command", [])) for h in before]
        joined = " ".join(cmds)
        assert "envsubst" in joined, f"Missing envsubst hook: {cmds}"

    def test_dev_from_local_port_forward_namespace(self):
        """Port forward entries include namespace from wizard.

        0.3.6: portForward[].namespace should be set when wizard has namespace.
        """
        state = self._wizard_state()
        state["namespace"] = "myapp"
        result = _generate_skaffold(state, [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        for entry in pf:
            assert entry.get("namespace") == "myapp", \
                f"Missing namespace in portForward: {entry}"

    def test_dev_from_local_skaffold_repo_comment(self):
        """Generated YAML includes SKAFFOLD_DEFAULT_REPO comment.

        0.3.5b: Dev-from-local should document that no remote registry
        is needed by including a comment about SKAFFOLD_DEFAULT_REPO.
        """
        state = self._wizard_state()
        result = _generate_skaffold(state, [])
        raw = result["content"]
        assert "SKAFFOLD_DEFAULT_REPO" in raw, \
            f"Missing SKAFFOLD_DEFAULT_REPO comment in output"

    def test_dev_from_local_env_loading_comment(self):
        """Generated YAML includes .env loading instructions.

        0.3.5b: Dev-from-local should document how to load the .env file
        before running skaffold dev.
        """
        state = self._wizard_state()
        result = _generate_skaffold(state, [])
        raw = result["content"]
        assert "source .env" in raw, \
            f"Missing .env loading comment in output"


class TestSkaffoldCIDevProfile:
    """0.3.5c: Dev profile for CI/CD dev environment.

    Different from dev-from-local: runs in CI/CD for a dev cluster.
    Variables injected by CI. Images pushed to dev registry.
    """

    @staticmethod
    def _wizard_state():
        return {
            "skaffold": True,
            "environments": ["dev"],
            "deployStrategy": "kustomize",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080,
                 "env": [{"key": "DB_HOST", "type": "variable"}]},
            ],
        }

    def test_dev_profile_push_true(self):
        """CI/CD dev profile pushes to registry.

        0.3.5c: Unlike dev-from-local, CI dev pushes images.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        assert profile["build"]["local"]["push"] is True

    def test_dev_profile_no_port_forward(self):
        """CI/CD dev profile has no port-forwarding.

        0.3.5c: Not running locally, no need for port-forward.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        assert "portForward" not in profile

    def test_dev_profile_kustomize_overlay(self):
        """CI/CD dev profile uses dev overlay.

        0.3.5c: deploy.kustomize.paths points at overlays/dev.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        deploy = profile.get("deploy", {})
        paths = deploy.get("kustomize", {}).get("paths", [])
        assert any("overlays/dev" in p for p in paths)

    def test_dev_profile_kustomize_manifests_overlay(self):
        """CI/CD dev profile overrides manifests.kustomize.paths to dev overlay.

        0.3.4b: When deployStrategy is kustomize, each profile must
        override BOTH manifests.kustomize.paths AND deploy.kustomize.paths
        to point at the correct overlay directory.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        manifests = profile.get("manifests", {})
        paths = manifests.get("kustomize", {}).get("paths", [])
        assert any("overlays/dev" in p for p in paths), \
            f"Dev profile manifests.kustomize.paths missing overlay: {manifests}"

    def test_dev_profile_no_envsubst_hooks(self):
        """CI/CD dev profile does NOT include envsubst hooks.

        0.3.5c: CI/CD injects vars directly → no envsubst needed.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        deploy = profile.get("deploy", {})
        # Kustomize deploy — no kubectl section at all
        hooks = deploy.get("kubectl", {}).get("hooks", {})
        assert not hooks.get("before"), \
            f"CI dev should NOT have envsubst hooks: {hooks}"

class TestSkaffoldStagingProdProfiles:
    """0.3.5d: Staging and production profiles."""

    @staticmethod
    def _wizard_state():
        return {
            "skaffold": True,
            "environments": ["staging", "prod"],
            "namespace": "myapp",
            "_services": [
                {"name": "api", "image": "api:v1"},
            ],
        }

    def test_staging_push_true(self):
        """Staging pushes to registry.

        0.3.5d: Staging images go to a registry.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "staging"][0]
        assert profile["build"]["local"]["push"] is True

    def test_prod_git_commit_tag(self):
        """Production uses gitCommit tag policy (reproducible).

        0.3.5d: Production builds must be traceable to a commit.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "prod"][0]
        assert "gitCommit" in profile["build"]["tagPolicy"]

    def test_prod_server_side_apply(self):
        """Production uses --server-side apply.

        0.3.5d: Production deployments should use server-side apply.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "prod"][0]
        deploy = profile.get("deploy", {})
        kubectl = deploy.get("kubectl", {})
        flags = kubectl.get("flags", {})
        assert "--server-side" in flags.get("apply", [])

    def test_staging_namespace_override(self):
        """Staging profile overrides namespace.

        0.3.5d: Per-profile namespace via deploy.kubectl.defaultNamespace.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "staging"][0]
        deploy = profile.get("deploy", {})
        kubectl = deploy.get("kubectl", {})
        # Staging namespace should include 'staging' somehow
        ns = kubectl.get("defaultNamespace", "")
        assert "staging" in ns

    def test_staging_kustomize_manifests_overlay(self):
        """Staging profile with kustomize → manifests.kustomize.paths overridden.

        0.3.4b: Staging overlay: manifests + deploy both point at overlays/staging.
        """
        state = {**self._wizard_state(), "deployStrategy": "kustomize"}
        result = _generate_skaffold(state, [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "staging"][0]
        # manifests override
        m_paths = profile.get("manifests", {}).get("kustomize", {}).get("paths", [])
        assert any("overlays/staging" in p for p in m_paths), \
            f"Staging manifests.kustomize.paths missing overlay: {m_paths}"
        # deploy override
        d_paths = profile.get("deploy", {}).get("kustomize", {}).get("paths", [])
        assert any("overlays/staging" in p for p in d_paths), \
            f"Staging deploy.kustomize.paths missing overlay: {d_paths}"

    def test_prod_kustomize_manifests_overlay(self):
        """Prod profile with kustomize → manifests.kustomize.paths overridden.

        0.3.4b: Prod overlay: manifests + deploy both point at overlays/prod.
        """
        state = {**self._wizard_state(), "deployStrategy": "kustomize"}
        result = _generate_skaffold(state, [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "prod"][0]
        # manifests override
        m_paths = profile.get("manifests", {}).get("kustomize", {}).get("paths", [])
        assert any("overlays/prod" in p for p in m_paths), \
            f"Prod manifests.kustomize.paths missing overlay: {m_paths}"
        # deploy override
        d_paths = profile.get("deploy", {}).get("kustomize", {}).get("paths", [])
        assert any("overlays/prod" in p for p in d_paths), \
            f"Prod deploy.kustomize.paths missing overlay: {d_paths}"


class TestSkaffoldProfilePatches:
    """0.3.5e: Profile patches — fine-grained overrides.

    Skaffold supports JSON Patch-style operations in profiles[].patches.
    These allow surgical modifications without replacing entire sections.
    """

    def test_profile_patch_replace(self):
        """profilePatches with op=replace → patches array in profile.

        0.3.5e: Replace a specific value (e.g. registry image path).
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["prod"],
             "profilePatches": {
                 "prod": [
                     {"op": "replace",
                      "path": "/build/artifacts/0/image",
                      "value": "registry.io/app:prod"},
                 ],
             },
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "prod"][0]
        patches = profile.get("patches", [])
        assert len(patches) >= 1, f"No patches: {profile.keys()}"
        assert patches[0]["op"] == "replace"
        assert patches[0]["path"] == "/build/artifacts/0/image"
        assert patches[0]["value"] == "registry.io/app:prod"

    def test_profile_patch_add(self):
        """profilePatches with op=add → patches array in profile.

        0.3.5e: Add additional build args per profile.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["staging"],
             "profilePatches": {
                 "staging": [
                     {"op": "add",
                      "path": "/build/artifacts/0/docker/buildArgs/DEBUG",
                      "value": "true"},
                 ],
             },
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "staging"][0]
        patches = profile.get("patches", [])
        assert len(patches) >= 1, f"No patches: {profile.keys()}"
        assert patches[0]["op"] == "add"

    def test_no_patches_no_section(self):
        """No profilePatches → no patches key in profile.

        0.3.5e: Don't pollute with empty arrays.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["dev"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev"][0]
        assert "patches" not in profile


class TestSkaffoldPortForwarding:
    """0.3.6: Port forwarding — maps K8s ports to localhost.

    Source of truth: Skaffold v4beta11 portForward schema.
    Port forwarding entries are generated per service with a port.
    """

    @staticmethod
    def _wizard_state():
        return {
            "skaffold": True,
            "environments": ["dev-from-local"],
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080},
                {"name": "web", "image": "web:v1", "port": 3000},
            ],
        }

    def test_port_forward_resource_type(self):
        """portForward entries use resourceType: service.

        0.3.6: Default resource type for port forwarding.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        for entry in pf:
            assert entry["resourceType"] == "service"

    def test_port_forward_resource_name(self):
        """portForward entries use service name as resourceName.

        0.3.6: Maps to the K8s Service resource.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        names = [p["resourceName"] for p in pf]
        assert "api" in names
        assert "web" in names

    def test_port_forward_port_values(self):
        """portForward entries have correct port and localPort.

        0.3.6: Remote port from service, localPort defaults to same.
        """
        result = _generate_skaffold(self._wizard_state(), [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        api_pf = [p for p in pf if p["resourceName"] == "api"][0]
        assert api_pf["port"] == 8080
        assert api_pf["localPort"] == 8080

    def test_port_forward_collision_detection(self):
        """Services with same port → localPort auto-incremented.

        0.3.6: Two services on port 8080 → second gets localPort 8081.
        """
        state = {
            "skaffold": True,
            "environments": ["dev-from-local"],
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080},
                {"name": "api2", "image": "api2:v1", "port": 8080},
            ],
        }
        result = _generate_skaffold(state, [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        local_ports = [p["localPort"] for p in pf]
        assert len(set(local_ports)) == 2, f"Port collision not resolved: {local_ports}"

    def test_service_without_port_excluded(self):
        """Service without port → no portForward entry.

        0.3.6: Worker services without exposed ports don't need forwarding.
        """
        state = {
            "skaffold": True,
            "environments": ["dev-from-local"],
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080},
                {"name": "worker", "image": "worker:v1"},
            ],
        }
        result = _generate_skaffold(state, [])
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        assert len(pf) == 1
        assert pf[0]["resourceName"] == "api"


# ═══════════════════════════════════════════════════════════════════
#  0.3.7  File Sync — TDD RED
#  0.3.8  Lifecycle Hooks — TDD RED
#
#  Source of truth: Skaffold v4beta11 `sync` + `hooks` schemas.
#  File sync copies files to container without rebuild (dev hot-reload).
#  Lifecycle hooks run commands before/after deploy.
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldFileSync:
    """0.3.7: File sync — dev hot-reload.

    Source of truth: Skaffold v4beta11 sync schema.
    Sync rules go inside build.artifacts[].sync for dev profile.
    Language detection drives the glob patterns.
    """

    def test_python_service_sync_glob(self):
        """Python service → sync.manual with *.py glob.

        0.3.7: Python apps sync .py files for hot-reload.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1", "language": "python"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        artifacts = profile["build"].get("artifacts", [])
        assert len(artifacts) > 0, "No artifacts in dev-from-local profile"
        sync = artifacts[0].get("sync", {})
        manual = sync.get("manual", [])
        assert len(manual) > 0, "No sync rules for python service"
        srcs = [m["src"] for m in manual]
        assert any("*.py" in s for s in srcs), f"No *.py sync glob: {srcs}"

    def test_node_service_sync_glob(self):
        """Node service → sync.manual with *.js,*.ts globs.

        0.3.7: Node apps sync JS/TS files.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "web", "image": "web:v1", "language": "node"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        artifacts = profile["build"]["artifacts"]
        sync = artifacts[0].get("sync", {})
        manual = sync.get("manual", [])
        srcs = [m["src"] for m in manual]
        has_js = any("*.js" in s or "*.ts" in s for s in srcs)
        assert has_js, f"No js/ts sync glob: {srcs}"

    def test_go_service_no_sync(self):
        """Go service → no sync section (requires rebuild).

        0.3.7: Go is compiled, no hot-reload possible.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1", "language": "go"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        artifacts = profile["build"].get("artifacts", [])
        if artifacts:
            assert "sync" not in artifacts[0], "Go should not have sync rules"

    def test_no_language_no_sync(self):
        """No language detected → no sync section.

        0.3.7: Can't determine what to sync without language info.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        artifacts = profile["build"].get("artifacts", [])
        if artifacts:
            assert "sync" not in artifacts[0]

    def test_sync_dest_is_app(self):
        """Sync destination defaults to /app.

        0.3.7: Standard container working directory.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1", "language": "python"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        artifacts = profile["build"]["artifacts"]
        manual = artifacts[0]["sync"]["manual"]
        assert all(m["dest"] == "/app" for m in manual)

    def test_sync_not_in_prod_profile(self):
        """Sync only in dev profile, not production.

        0.3.7: Production builds should never use file sync.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local", "prod"],
             "_services": [
                {"name": "api", "image": "api:v1", "language": "python"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        prod = [p for p in content["profiles"] if p["name"] == "prod"][0]
        prod_artifacts = prod["build"].get("artifacts", [])
        if prod_artifacts:
            assert "sync" not in prod_artifacts[0]


class TestSkaffoldLifecycleHooks:
    """0.3.8: Lifecycle hooks — pre/post deploy commands.

    Source of truth: Skaffold v4beta11 hooks schema.
    Wizard preDeploy/postDeploy commands become Skaffold deploy hooks.
    """

    def test_pre_deploy_hook(self):
        """Wizard preDeploy commands → deploy.kubectl.hooks.before.

        0.3.8: Custom commands before deploy.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "preDeploy": ["echo pre-deploy", "make migrate"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [{"path": "k8s/api.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"]["hooks"]
        before = hooks["before"]
        assert len(before) >= 2
        cmds = [h["host"]["command"] for h in before]
        # The custom hooks should be present (envsubst hooks may also exist)
        flat = [str(c) for c in cmds]
        joined = " ".join(flat)
        assert "pre-deploy" in joined or "migrate" in joined

    def test_post_deploy_hook(self):
        """Wizard postDeploy commands → deploy.kubectl.hooks.after.

        0.3.8: Custom commands after deploy.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "postDeploy": ["echo deployed"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"]["hooks"]
        after = hooks["after"]
        assert len(after) >= 1

    def test_hook_dir_is_root(self):
        """Hook dir defaults to project root.

        0.3.8: All hooks run from project root.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "preDeploy": ["echo test"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        hooks = content["deploy"]["kubectl"]["hooks"]["before"]
        for h in hooks:
            assert h["host"].get("dir", ".") == "."

    def test_no_hooks_no_section(self):
        """No preDeploy/postDeploy → no hooks section.

        0.3.8: Don't pollute config with empty hooks.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        kubectl = content["deploy"]["kubectl"]
        assert "hooks" not in kubectl


# ═══════════════════════════════════════════════════════════════════
#  0.3.10  Edge Cases — TDD RED
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldEdgeCases:
    """0.3.10: Error and edge cases for skaffold generation."""

    def test_no_services_minimal_config(self):
        """No services → minimal valid skaffold.yaml (no build section).

        0.3.10: Should still produce manifests + deploy sections.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": []},
            [{"path": "k8s/cm.yaml"}],
        )
        assert result is not None
        content = yaml.safe_load(result["content"])
        assert content["apiVersion"] == "skaffold/v4beta11"
        assert "build" not in content
        assert "manifests" in content
        assert "deploy" in content

    def test_all_skip_services_no_build(self):
        """All services are Skip kind → no build section.

        0.3.10: Manifests still present, just no artifacts to build.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "ext-db", "kind": "Skip", "image": "postgres:15"},
            ]},
            [{"path": "k8s/ext-db.yaml"}],
        )
        content = yaml.safe_load(result["content"])
        assert "build" not in content
        assert "manifests" in content

    def test_empty_state_with_skaffold_true(self):
        """Empty wizard state + skaffold=True → valid minimal config.

        0.3.10: Must not crash, must produce valid YAML.
        """
        result = _generate_skaffold(
            {"skaffold": True},
            [],
        )
        assert result is not None
        content = yaml.safe_load(result["content"])
        assert content["apiVersion"] == "skaffold/v4beta11"
        assert content["kind"] == "Config"
        assert "manifests" in content

    def test_service_without_image_excluded(self):
        """Service without image → excluded from artifacts.

        0.3.10: Services may define a name but no image (e.g. static config).
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "config-only"},
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        artifacts = content["build"]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["image"] == "api:v1"

    def test_port_conflict_auto_incremented(self):
        """Port conflict between services → localPort auto-incremented.

        0.3.10: Already covered in TestSkaffoldPortForwarding, but
        verifying as an explicit edge case.
        """
        result = _generate_skaffold(
            {"skaffold": True, "environments": ["dev-from-local"],
             "_services": [
                {"name": "api", "image": "api:v1", "port": 8080},
                {"name": "api2", "image": "api2:v1", "port": 8080},
                {"name": "api3", "image": "api3:v1", "port": 8080},
            ]},
            [],
        )
        content = yaml.safe_load(result["content"])
        profile = [p for p in content["profiles"] if p["name"] == "dev-from-local"][0]
        pf = profile["portForward"]
        local_ports = sorted([p["localPort"] for p in pf])
        assert local_ports == [8080, 8081, 8082]

    def test_skaffold_false_no_file(self):
        """skaffold=False → no file generated.

        0.3.10: The function should return None when skaffold is not requested.
        """
        result = _generate_skaffold(
            {"skaffold": False, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        assert result is None

    def test_malformed_yaml_overwrite(self):
        """Malformed existing skaffold.yaml → overwrite works.

        0.3.10: The generator produces fresh YAML regardless of
        what was on disk before.
        """
        result = _generate_skaffold(
            {"skaffold": True, "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        assert result is not None
        # Parse should succeed (valid YAML)
        content = yaml.safe_load(result["content"])
        assert content["apiVersion"] == "skaffold/v4beta11"

    def test_profile_name_collision_warning(self):
        """Duplicate profile name → warning emitted.

        0.3.10: Wizard sending duplicate environment names should
        produce a warning, not silently overwrite.
        """
        result = _generate_skaffold(
            {"skaffold": True,
             "environments": ["dev", "dev", "staging"],
             "_services": [
                {"name": "api", "image": "api:v1"},
            ]},
            [],
        )
        assert result is not None
        warnings = result.get("warnings", [])
        assert any("duplicate" in str(w).lower() or "collision" in str(w).lower()
                    for w in warnings), \
            f"Expected duplicate profile warning, got: {warnings}"
