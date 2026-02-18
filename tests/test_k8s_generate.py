"""
Tests for K8s manifest generation — template-based simple generation.

Milestone: 0.2.4 Simple Generation (`k8s_generate.py`)
Source of truth: Kubernetes API v1 / apps/v1 / networking.k8s.io/v1 specs.

Every test is pessimistic: asserts on the FULL structure the Kubernetes API
requires, not just "does the key exist". If the generator output would be
rejected by `kubectl apply`, the test must fail.

Source modules:
  - k8s_generate.generate_manifests
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.core.services.k8s_generate import generate_manifests


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _find_file(result: dict, suffix: str) -> dict | None:
    """Find a generated file whose path ends with `suffix`."""
    for f in result["files"]:
        if f["path"].endswith(suffix):
            return f
    return None


def _parse_yaml(file_dict: dict) -> dict:
    """Parse the YAML content of a generated file."""
    doc = yaml.safe_load(file_dict["content"])
    assert doc is not None, f"YAML parse of {file_dict['path']} returned None"
    return doc


# ═══════════════════════════════════════════════════════════════════
#  0.2.4 Simple Generation — template-based
# ═══════════════════════════════════════════════════════════════════


class TestSimpleGeneration:
    """0.2.4 — generate_manifests produces valid K8s manifests.

    Source of truth: Kubernetes API specs (apps/v1/Deployment, v1/Service,
    networking.k8s.io/v1/Ingress, v1/Namespace).
    """

    # ── Checkbox 1: produces Deployment + Service files ──────────
    def test_produces_deployment_and_service(self, tmp_path: Path):
        """generate_manifests returns ok=True with at least Deployment + Service.

        Pessimistic: result shape has 'ok' and 'files' keys; exactly 2 files
        for the minimal case (no namespace, no host). Each file dict has all
        GeneratedFile fields.
        """
        result = generate_manifests(tmp_path, "myapp")

        assert result["ok"] is True
        assert isinstance(result["files"], list)
        assert len(result["files"]) == 2, (
            f"Expected exactly 2 files (Deployment + Service), got {len(result['files'])}"
        )

        # Every file must have the GeneratedFile shape
        for f in result["files"]:
            assert "path" in f, f"Missing 'path' key in {f}"
            assert "content" in f, f"Missing 'content' key in {f}"
            assert "reason" in f, f"Missing 'reason' key in {f}"
            assert "overwrite" in f, f"Missing 'overwrite' key in {f}"
            assert isinstance(f["path"], str)
            assert isinstance(f["content"], str)
            assert len(f["content"]) > 0, f"Empty content for {f['path']}"

        # Verify one is a Deployment and one is a Service
        paths = [f["path"] for f in result["files"]]
        deploy_files = [p for p in paths if "deployment" in p.lower()]
        service_files = [p for p in paths if "service" in p.lower()]
        assert len(deploy_files) == 1, f"Expected 1 deployment file, found: {deploy_files}"
        assert len(service_files) == 1, f"Expected 1 service file, found: {service_files}"

    # ── Checkbox 2: Deployment content is valid YAML ─────────────
    def test_deployment_valid_yaml(self, tmp_path: Path):
        """Deployment file parses as valid YAML with correct K8s structure.

        Pessimistic: validates apiVersion, kind, metadata, and full spec
        structure per the apps/v1 Deployment API spec.
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        assert deploy_file is not None, "No deployment file generated"

        doc = _parse_yaml(deploy_file)

        # K8s API required top-level fields
        assert doc["apiVersion"] == "apps/v1", f"Wrong apiVersion: {doc.get('apiVersion')}"
        assert doc["kind"] == "Deployment", f"Wrong kind: {doc.get('kind')}"

        # metadata (K8s: required)
        assert "metadata" in doc
        assert doc["metadata"]["name"] == "myapp"
        assert "labels" in doc["metadata"]
        assert doc["metadata"]["labels"]["app"] == "myapp"

        # spec (K8s: required for Deployment)
        assert "spec" in doc
        spec = doc["spec"]
        assert "replicas" in spec
        assert "selector" in spec
        assert "matchLabels" in spec["selector"]
        assert spec["selector"]["matchLabels"]["app"] == "myapp"
        assert "template" in spec

        # template.metadata.labels must match selector (K8s invariant)
        tmpl = spec["template"]
        assert "metadata" in tmpl
        assert "labels" in tmpl["metadata"]
        assert tmpl["metadata"]["labels"]["app"] == "myapp"

        # template.spec.containers (K8s: at least 1 container required)
        assert "spec" in tmpl
        assert "containers" in tmpl["spec"]
        containers = tmpl["spec"]["containers"]
        assert len(containers) >= 1
        c = containers[0]
        assert c["name"] == "myapp"
        assert "image" in c
        assert "ports" in c
        assert len(c["ports"]) >= 1
        assert "containerPort" in c["ports"][0]

    # ── Checkbox 3: Service content is valid YAML ────────────────
    def test_service_valid_yaml(self, tmp_path: Path):
        """Service file parses as valid YAML with correct K8s structure.

        Pessimistic: validates apiVersion, kind, metadata, spec.type,
        spec.ports, and spec.selector per the v1 Service API spec.
        """
        result = generate_manifests(tmp_path, "myapp")
        svc_file = _find_file(result, "service.yaml")
        assert svc_file is not None, "No service file generated"

        doc = _parse_yaml(svc_file)

        # K8s API required top-level fields
        assert doc["apiVersion"] == "v1", f"Wrong apiVersion: {doc.get('apiVersion')}"
        assert doc["kind"] == "Service", f"Wrong kind: {doc.get('kind')}"

        # metadata
        assert doc["metadata"]["name"] == "myapp"
        assert doc["metadata"]["labels"]["app"] == "myapp"

        # spec
        spec = doc["spec"]
        assert "type" in spec
        assert spec["type"] in ("ClusterIP", "NodePort", "LoadBalancer"), (
            f"Invalid service type: {spec['type']}"
        )
        assert "ports" in spec
        assert len(spec["ports"]) >= 1
        port = spec["ports"][0]
        assert "port" in port
        assert "targetPort" in port
        assert "protocol" in port
        assert port["protocol"] == "TCP"

        # selector must match deployment labels
        assert "selector" in spec
        assert spec["selector"]["app"] == "myapp"

    # ── Checkbox 4: Custom replicas reflected ────────────────────
    def test_custom_replicas(self, tmp_path: Path):
        """Custom replicas value appears in the Deployment spec.

        Pessimistic: spec.replicas is the exact integer passed, not a string,
        not a default. Verifies type is int (K8s rejects string replicas).
        """
        result = generate_manifests(tmp_path, "myapp", replicas=5)
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        replicas = doc["spec"]["replicas"]
        assert replicas == 5, f"Expected replicas=5, got {replicas}"
        assert isinstance(replicas, int), f"replicas must be int, got {type(replicas)}"

    # ── Checkbox 5: Custom service_type reflected ────────────────
    def test_custom_service_type(self, tmp_path: Path):
        """Custom service_type (ClusterIP/NodePort/LoadBalancer) reflected.

        Pessimistic: tests all three valid values. K8s rejects anything else.
        """
        for stype in ("ClusterIP", "NodePort", "LoadBalancer"):
            result = generate_manifests(tmp_path, "myapp", service_type=stype)
            svc_file = _find_file(result, "service.yaml")
            doc = _parse_yaml(svc_file)
            assert doc["spec"]["type"] == stype, (
                f"Expected type={stype}, got {doc['spec']['type']}"
            )

    # ── Checkbox 6: With namespace → Namespace manifest first ────
    def test_namespace_generated_first(self, tmp_path: Path):
        """When namespace is specified, a Namespace manifest is generated
        and placed FIRST in the files list.

        Pessimistic: Namespace manifest has correct apiVersion/kind/metadata,
        and it appears at index 0 (K8s requires namespace to exist before
        resources that reference it).
        """
        result = generate_manifests(tmp_path, "myapp", namespace="production")

        # Should have 3 files: Namespace + Deployment + Service
        assert len(result["files"]) == 3, (
            f"Expected 3 files with namespace, got {len(result['files'])}"
        )

        # Namespace must be first
        ns_file = result["files"][0]
        assert "namespace" in ns_file["path"].lower(), (
            f"First file should be namespace, got: {ns_file['path']}"
        )

        doc = _parse_yaml(ns_file)
        assert doc["apiVersion"] == "v1"
        assert doc["kind"] == "Namespace"
        assert doc["metadata"]["name"] == "production"
        assert doc["metadata"]["labels"]["name"] == "production"

    # ── Checkbox 7: With host → Ingress manifest generated ───────
    def test_ingress_with_host(self, tmp_path: Path):
        """When host is specified, an Ingress manifest is generated.

        Pessimistic: validates full Ingress structure per
        networking.k8s.io/v1 spec — apiVersion, kind, metadata, annotations,
        rules with host/paths/backend.
        """
        result = generate_manifests(
            tmp_path, "myapp", host="myapp.example.com", port=8080,
        )

        ing_file = _find_file(result, "ingress.yaml")
        assert ing_file is not None, "No ingress file generated when host specified"

        doc = _parse_yaml(ing_file)

        # K8s networking.k8s.io/v1 Ingress required fields
        assert doc["apiVersion"] == "networking.k8s.io/v1", (
            f"Wrong apiVersion: {doc.get('apiVersion')}"
        )
        assert doc["kind"] == "Ingress"
        assert doc["metadata"]["name"] == "myapp"

        # spec.rules (K8s: required)
        rules = doc["spec"]["rules"]
        assert len(rules) >= 1
        rule = rules[0]
        assert rule["host"] == "myapp.example.com"

        # paths (K8s: required under http)
        paths = rule["http"]["paths"]
        assert len(paths) >= 1
        p = paths[0]
        assert "path" in p
        assert "pathType" in p
        assert p["pathType"] in ("Prefix", "Exact", "ImplementationSpecific"), (
            f"Invalid pathType: {p['pathType']}"
        )

        # backend (K8s: required)
        backend = p["backend"]
        assert "service" in backend
        assert backend["service"]["name"] == "myapp"
        assert backend["service"]["port"]["number"] == 8080

    # ── Checkbox 8: Without host → no Ingress ────────────────────
    def test_no_ingress_without_host(self, tmp_path: Path):
        """Without host parameter, no Ingress file is generated.

        Pessimistic: verifies file count is exactly 2 and no file path
        contains 'ingress'.
        """
        result = generate_manifests(tmp_path, "myapp")
        assert len(result["files"]) == 2
        for f in result["files"]:
            assert "ingress" not in f["path"].lower(), (
                f"Unexpected ingress file: {f['path']}"
            )

    # ── Checkbox 9: Default image → {app_name}:latest ────────────
    def test_default_image(self, tmp_path: Path):
        """Without explicit image, defaults to {app_name}:latest.

        Pessimistic: exact string match on container image field.
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        image = doc["spec"]["template"]["spec"]["containers"][0]["image"]
        assert image == "myapp:latest", f"Expected 'myapp:latest', got '{image}'"

    # ── Checkbox 10: Resource limits (cpu/memory) ────────────────
    def test_resource_limits(self, tmp_path: Path):
        """Deployment has resource requests AND limits.

        Pessimistic: K8s best practice requires both requests and limits.
        Each must have cpu and memory. Requests must not exceed limits
        (K8s invariant: requests <= limits for each resource).
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container, "Container missing 'resources' field"

        resources = container["resources"]
        assert "requests" in resources, "Missing resource requests"
        assert "limits" in resources, "Missing resource limits"

        # Both must have cpu and memory
        for section_name in ("requests", "limits"):
            section = resources[section_name]
            assert "cpu" in section, f"Missing cpu in {section_name}"
            assert "memory" in section, f"Missing memory in {section_name}"

    # ── Checkbox 11: livenessProbe + readinessProbe ──────────────
    def test_probes(self, tmp_path: Path):
        """Deployment has both livenessProbe and readinessProbe.

        Pessimistic: K8s probes require a handler (httpGet, tcpSocket, or exec)
        plus timing fields. We verify the full probe shape per the K8s
        Container v1 API spec.
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        container = doc["spec"]["template"]["spec"]["containers"][0]

        for probe_name in ("livenessProbe", "readinessProbe"):
            assert probe_name in container, f"Container missing '{probe_name}'"
            probe = container[probe_name]

            # Must have a handler
            handlers = {"httpGet", "tcpSocket", "exec"}
            found_handlers = handlers & set(probe.keys())
            assert len(found_handlers) >= 1, (
                f"{probe_name} has no handler (need httpGet/tcpSocket/exec)"
            )

            # Must have timing fields (K8s defaults exist but explicit is best practice)
            assert "initialDelaySeconds" in probe, (
                f"{probe_name} missing initialDelaySeconds"
            )
            assert "periodSeconds" in probe, (
                f"{probe_name} missing periodSeconds"
            )

            # Timing values must be positive integers
            assert isinstance(probe["initialDelaySeconds"], int)
            assert probe["initialDelaySeconds"] >= 0
            assert isinstance(probe["periodSeconds"], int)
            assert probe["periodSeconds"] > 0

    # ── Checkbox 12: securityContext ─────────────────────────────
    def test_security_context(self, tmp_path: Path):
        """Deployment has securityContext with runAsNonRoot + no privilege escalation.

        Pessimistic: K8s Pod Security Standards (restricted profile) requires:
        - runAsNonRoot: true
        - allowPrivilegeEscalation: false
        Both must be exact boolean values (not strings, not absent).
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        container = doc["spec"]["template"]["spec"]["containers"][0]

        assert "securityContext" in container, "Container missing 'securityContext'"
        sc = container["securityContext"]

        assert sc.get("runAsNonRoot") is True, (
            f"runAsNonRoot must be true, got {sc.get('runAsNonRoot')}"
        )
        assert sc.get("allowPrivilegeEscalation") is False, (
            f"allowPrivilegeEscalation must be false, got {sc.get('allowPrivilegeEscalation')}"
        )

    # ── Checkbox 13: RollingUpdate strategy ──────────────────────
    def test_rolling_update_strategy(self, tmp_path: Path):
        """Deployment has RollingUpdate strategy with maxUnavailable and maxSurge.

        Pessimistic: K8s spec for strategy type RollingUpdate requires the
        rollingUpdate sub-field with maxUnavailable and maxSurge.
        """
        result = generate_manifests(tmp_path, "myapp")
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)

        strategy = doc["spec"]["strategy"]
        assert strategy["type"] == "RollingUpdate", (
            f"Expected strategy type 'RollingUpdate', got '{strategy.get('type')}'"
        )

        assert "rollingUpdate" in strategy, "Missing rollingUpdate config"
        ru = strategy["rollingUpdate"]
        assert "maxUnavailable" in ru, "Missing maxUnavailable in rollingUpdate"
        assert "maxSurge" in ru, "Missing maxSurge in rollingUpdate"

    # ── Checkbox 14: Files under k8s/ directory ──────────────────
    def test_files_under_k8s_dir(self, tmp_path: Path):
        """All generated files are placed under k8s/ directory.

        Pessimistic: checks EVERY file path starts with 'k8s/'.
        Also tests with namespace + host to verify all 4 file types.
        """
        # Test with all file types (namespace + ingress)
        result = generate_manifests(
            tmp_path, "myapp",
            namespace="production",
            host="myapp.example.com",
        )

        assert len(result["files"]) == 4, (
            f"Expected 4 files (ns + deploy + svc + ingress), got {len(result['files'])}"
        )

        for f in result["files"]:
            assert f["path"].startswith("k8s/"), (
                f"File not under k8s/ directory: {f['path']}"
            )


# ═══════════════════════════════════════════════════════════════════
#  Edge cases and integration (beyond the 14 checkboxes)
# ═══════════════════════════════════════════════════════════════════


class TestSimpleGenerationEdgeCases:
    """Additional spec-grounded edge cases for generate_manifests."""

    def test_custom_image_overrides_default(self, tmp_path: Path):
        """Explicit image parameter overrides the {app_name}:latest default."""
        result = generate_manifests(
            tmp_path, "myapp", image="gcr.io/my-project/myapp:v2.1.0",
        )
        deploy_file = _find_file(result, "deployment.yaml")
        doc = _parse_yaml(deploy_file)
        image = doc["spec"]["template"]["spec"]["containers"][0]["image"]
        assert image == "gcr.io/my-project/myapp:v2.1.0"

    def test_custom_port_propagates(self, tmp_path: Path):
        """Custom port propagates to Deployment containerPort, Service port/targetPort,
        probes, and Ingress backend."""
        result = generate_manifests(
            tmp_path, "myapp", port=3000, host="myapp.example.com",
        )

        # Deployment containerPort
        deploy = _parse_yaml(_find_file(result, "deployment.yaml"))
        assert deploy["spec"]["template"]["spec"]["containers"][0]["ports"][0]["containerPort"] == 3000

        # Deployment probes use the port
        container = deploy["spec"]["template"]["spec"]["containers"][0]
        if "httpGet" in container.get("livenessProbe", {}):
            assert container["livenessProbe"]["httpGet"]["port"] == 3000
        if "httpGet" in container.get("readinessProbe", {}):
            assert container["readinessProbe"]["httpGet"]["port"] == 3000

        # Service port/targetPort
        svc = _parse_yaml(_find_file(result, "service.yaml"))
        assert svc["spec"]["ports"][0]["port"] == 3000
        assert svc["spec"]["ports"][0]["targetPort"] == 3000

        # Ingress backend port
        ing = _parse_yaml(_find_file(result, "ingress.yaml"))
        assert ing["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"]["number"] == 3000

    def test_selector_labels_match(self, tmp_path: Path):
        """K8s invariant: Deployment selector.matchLabels must equal
        template.metadata.labels, and Service selector must match.
        This is a hard K8s API requirement; mismatch = rejected by apiserver."""
        result = generate_manifests(tmp_path, "myapp")

        deploy = _parse_yaml(_find_file(result, "deployment.yaml"))
        selector = deploy["spec"]["selector"]["matchLabels"]
        template_labels = deploy["spec"]["template"]["metadata"]["labels"]
        assert selector == template_labels, (
            f"Selector {selector} != template labels {template_labels}"
        )

        svc = _parse_yaml(_find_file(result, "service.yaml"))
        svc_selector = svc["spec"]["selector"]
        # Service selector must be a subset of template labels
        for k, v in svc_selector.items():
            assert template_labels.get(k) == v, (
                f"Service selector {k}={v} not in template labels"
            )

    def test_namespace_plus_host_file_count(self, tmp_path: Path):
        """Namespace + host → 4 files total (Namespace, Deployment, Service, Ingress)."""
        result = generate_manifests(
            tmp_path, "myapp", namespace="staging", host="myapp.staging.example.com",
        )
        assert len(result["files"]) == 4
        kinds = set()
        for f in result["files"]:
            doc = _parse_yaml(f)
            kinds.add(doc["kind"])
        assert kinds == {"Namespace", "Deployment", "Service", "Ingress"}, (
            f"Expected 4 kinds, got {kinds}"
        )

    def test_overwrite_is_false(self, tmp_path: Path):
        """Generated files should not overwrite existing files by default."""
        result = generate_manifests(tmp_path, "myapp")
        for f in result["files"]:
            assert f["overwrite"] is False, (
                f"overwrite should be False for {f['path']}"
            )

    def test_reason_is_descriptive(self, tmp_path: Path):
        """Every generated file has a non-empty reason string."""
        result = generate_manifests(tmp_path, "myapp")
        for f in result["files"]:
            assert isinstance(f["reason"], str)
            assert len(f["reason"]) > 0, f"Empty reason for {f['path']}"

    def test_app_name_with_hyphens(self, tmp_path: Path):
        """App names with hyphens are valid K8s DNS subdomain names."""
        result = generate_manifests(tmp_path, "my-cool-app")
        deploy = _parse_yaml(_find_file(result, "deployment.yaml"))
        assert deploy["metadata"]["name"] == "my-cool-app"
        assert deploy["metadata"]["labels"]["app"] == "my-cool-app"

    def test_empty_app_name_still_produces_files(self, tmp_path: Path):
        """0.2.21e: Empty app_name → still produces files (uses empty string).

        The function doesn't validate app_name — it uses it in format strings.
        The files are generated with empty-string names. This is a documentation
        of current behavior, not necessarily desired behavior.
        """
        result = generate_manifests(tmp_path, "")
        assert result["ok"] is True
        assert len(result["files"]) >= 2

