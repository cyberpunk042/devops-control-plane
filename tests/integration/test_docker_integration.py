"""
Integration tests — Docker domain COMPLETE requirements.

TDD: these tests define EVERY capability the finished Docker integration
must have. Failures = what needs to be built/fixed.

Covers:
  - Detection (compose files, Dockerfile, daemon, services)
  - Service parsing (ports, volumes, env, health, depends_on, build, networks)
  - Container management (list, inspect, start, stop, restart, remove, logs, stats, exec)
  - Image management (list, pull, remove, prune)
  - Compose operations (build, up, down, restart, status, logs, stats)
  - Network management (list, prune)
  - Volume management (list, prune)
  - File generation (Dockerfile per stack, .dockerignore, compose from wizard)
  - Wizard setup (orchestrate detect→configure→generate→write)
  - Round-trip consistency (generate→detect must agree)
  - Cross-integration (Docker→CI/CD build step, Docker→K8s deployment map)
"""

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════
#  1. DETECTION — scan project, report what exists
# ═══════════════════════════════════════════════════════════════════


class TestDockerDetection:
    """docker_status must fully characterise a project's Docker setup."""

    # ── Compose file discovery ──────────────────────────────────

    def test_finds_docker_compose_yml(self, tmp_path: Path):
        """docker-compose.yml present → detected, ALL 42 in-scope fields parsed.

        Scope: all docker-compose service fields EXCEPT Security (cap_add,
        cap_drop, security_opt) and Limits (ulimits, sysctls).

        Fields (42 total):
          Original 14: name, image, build, ports, environment, volumes,
                       depends_on, command, entrypoint, restart, healthcheck,
                       deploy, networks, labels
          Identity (5): container_name, hostname, domainname, platform, profiles
          Runtime (9):  user, working_dir, stdin_open, tty, privileged, init,
                        read_only, pid, shm_size
          Networking (5): network_mode, dns, dns_search, extra_hosts, expose
          Files (5):    env_file, configs, secrets, tmpfs, devices
          Logging (1):  logging
          Lifecycle (3): stop_signal, stop_grace_period, pull_policy
        """
        from src.core.services.docker_detect import docker_status

        # Create env file for env_file field
        (tmp_path / "app.env").write_text("SECRET_KEY=abc123\n")

        (tmp_path / "docker-compose.yml").write_text(
            "version: '3.8'\n"
            "services:\n"
            "  web:\n"
            # ── Original 14 ──
            "    build:\n"
            "      context: ./app\n"
            "      dockerfile: Dockerfile.prod\n"
            "      args:\n"
            "        NODE_ENV: production\n"
            "    image: myapp:latest\n"
            "    ports:\n"
            "      - '8080:80'\n"
            "      - '8443:443/tcp'\n"
            "    environment:\n"
            "      DB_HOST: db\n"
            "      DB_PORT: '5432'\n"
            "    volumes:\n"
            "      - ./data:/app/data\n"
            "      - logs:/app/logs\n"
            "    depends_on:\n"
            "      - db\n"
            "    command: gunicorn app:app\n"
            "    entrypoint: /entrypoint.sh\n"
            "    restart: unless-stopped\n"
            "    healthcheck:\n"
            "      test: ['CMD-SHELL', 'curl -f http://localhost/']\n"
            "      interval: 30s\n"
            "      timeout: 10s\n"
            "      retries: 3\n"
            "    deploy:\n"
            "      replicas: 2\n"
            "      resources:\n"
            "        limits:\n"
            "          cpus: '0.5'\n"
            "          memory: 256M\n"
            "        reservations:\n"
            "          cpus: '0.25'\n"
            "          memory: 128M\n"
            "    networks:\n"
            "      - frontend\n"
            "      - backend\n"
            "    labels:\n"
            "      com.example.team: platform\n"
            "      com.example.tier: web\n"
            # ── Identity (5) ──
            "    container_name: web-container\n"
            "    hostname: web-host\n"
            "    domainname: example.local\n"
            "    platform: linux/amd64\n"
            "    profiles:\n"
            "      - dev\n"
            "      - debug\n"
            # ── Runtime (9) ──
            "    user: '1000:1000'\n"
            "    working_dir: /app\n"
            "    stdin_open: true\n"
            "    tty: true\n"
            "    privileged: false\n"
            "    init: true\n"
            "    read_only: true\n"
            "    pid: host\n"
            "    shm_size: 256m\n"
            # ── Networking (5) ──
            "    network_mode: bridge\n"
            "    dns:\n"
            "      - 8.8.8.8\n"
            "      - 8.8.4.4\n"
            "    dns_search:\n"
            "      - example.com\n"
            "    extra_hosts:\n"
            "      - 'myhost:192.168.1.100'\n"
            "    expose:\n"
            "      - '3000'\n"
            "      - '4000'\n"
            # ── Files (5) ──
            "    env_file:\n"
            "      - app.env\n"
            "    configs:\n"
            "      - my_config\n"
            "    secrets:\n"
            "      - my_secret\n"
            "    tmpfs:\n"
            "      - /tmp\n"
            "      - /run\n"
            "    devices:\n"
            "      - /dev/sda:/dev/xvdc:rwm\n"
            # ── Logging (1) ──
            "    logging:\n"
            "      driver: json-file\n"
            "      options:\n"
            "        max-size: 10m\n"
            "        max-file: '3'\n"
            # ── Lifecycle (3) ──
            "    stop_signal: SIGTERM\n"
            "    stop_grace_period: 30s\n"
            "    pull_policy: always\n"
            "  db:\n"
            "    image: postgres:16\n"
            "    environment:\n"
            "      POSTGRES_DB: mydb\n"
            "    volumes:\n"
            "      - pgdata:/var/lib/postgresql/data\n"
            "    networks:\n"
            "      - backend\n"
        )
        r = docker_status(tmp_path)

        # ── Top-level compose detection ──
        assert r["has_compose"] is True
        assert r["compose_file"] == "docker-compose.yml"
        assert r["compose_services"] == ["db", "web"]  # sorted
        assert r["services_count"] == 2

        # ── Service details: all present ──
        assert "compose_service_details" in r
        assert len(r["compose_service_details"]) == 2
        details_by_name = {s["name"]: s for s in r["compose_service_details"]}
        assert "web" in details_by_name
        assert "db" in details_by_name

        web = details_by_name["web"]

        # ── Original 14 fields ──
        # 1. name
        assert web["name"] == "web"
        # 2. image
        assert web["image"] == "myapp:latest"
        # 3. build
        assert web["build"] is not None
        assert web["build"]["context"] == "./app"
        assert web["build"]["dockerfile"] == "Dockerfile.prod"
        assert web["build"]["args"] == {"NODE_ENV": "production"}
        # 4. ports
        assert len(web["ports"]) == 2
        port_80 = [p for p in web["ports"] if p["container"] == 80]
        assert len(port_80) == 1
        assert port_80[0]["host"] == 8080
        assert port_80[0]["protocol"] == "tcp"
        port_443 = [p for p in web["ports"] if p["container"] == 443]
        assert len(port_443) == 1
        assert port_443[0]["protocol"] == "tcp"
        # 5. environment
        assert web["environment"] == {"DB_HOST": "db", "DB_PORT": "5432"}
        # 6. volumes
        assert len(web["volumes"]) == 2
        assert "./data:/app/data" in web["volumes"]
        assert "logs:/app/logs" in web["volumes"]
        # 7. depends_on
        assert web["depends_on"] == ["db"]
        # 8. command
        assert web["command"] == "gunicorn app:app"
        # 9. entrypoint
        assert web["entrypoint"] == "/entrypoint.sh"
        # 10. restart
        assert web["restart"] == "unless-stopped"
        # 11. healthcheck
        assert web["healthcheck"] is not None
        assert "curl" in web["healthcheck"]["test"]
        assert web["healthcheck"]["interval"] == "30s"
        assert web["healthcheck"]["timeout"] == "10s"
        assert web["healthcheck"]["retries"] == 3
        # 12. deploy
        assert web["deploy"] is not None
        assert web["deploy"]["replicas"] == 2
        assert web["deploy"]["cpu_limit"] == "0.5"
        assert web["deploy"]["memory_limit"] == "256M"
        assert web["deploy"]["cpu_request"] == "0.25"
        assert web["deploy"]["memory_request"] == "128M"
        # 13. networks
        assert sorted(web["networks"]) == ["backend", "frontend"]
        # 14. labels
        assert web["labels"] == {
            "com.example.team": "platform",
            "com.example.tier": "web",
        }

        # ── Identity (5) ──
        # 15. container_name
        assert web["container_name"] == "web-container"
        # 16. hostname
        assert web["hostname"] == "web-host"
        # 17. domainname
        assert web["domainname"] == "example.local"
        # 18. platform
        assert web["platform"] == "linux/amd64"
        # 19. profiles
        assert web["profiles"] == ["dev", "debug"]

        # ── Runtime (9) ──
        # 20. user
        assert web["user"] == "1000:1000"
        # 21. working_dir
        assert web["working_dir"] == "/app"
        # 22. stdin_open
        assert web["stdin_open"] is True
        # 23. tty
        assert web["tty"] is True
        # 24. privileged
        assert web["privileged"] is False
        # 25. init
        assert web["init"] is True
        # 26. read_only
        assert web["read_only"] is True
        # 27. pid
        assert web["pid"] == "host"
        # 28. shm_size
        assert web["shm_size"] == "256m"

        # ── Networking (5) ──
        # 29. network_mode
        assert web["network_mode"] == "bridge"
        # 30. dns
        assert web["dns"] == ["8.8.8.8", "8.8.4.4"]
        # 31. dns_search
        assert web["dns_search"] == ["example.com"]
        # 32. extra_hosts
        assert web["extra_hosts"] == ["myhost:192.168.1.100"]
        # 33. expose
        assert web["expose"] == [3000, 4000]

        # ── Files (5) ──
        # 34. env_file
        assert web["env_file"] == ["app.env"]
        # 35. configs
        assert web["configs"] == ["my_config"]
        # 36. secrets
        assert web["secrets"] == ["my_secret"]
        # 37. tmpfs
        assert web["tmpfs"] == ["/tmp", "/run"]
        # 38. devices
        assert web["devices"] == ["/dev/sda:/dev/xvdc:rwm"]

        # ── Logging (1) ──
        # 39. logging
        assert web["logging"] is not None
        assert web["logging"]["driver"] == "json-file"
        assert web["logging"]["options"] == {"max-size": "10m", "max-file": "3"}

        # ── Lifecycle (3) ──
        # 40. stop_signal
        assert web["stop_signal"] == "SIGTERM"
        # 41. stop_grace_period
        assert web["stop_grace_period"] == "30s"
        # 42. pull_policy
        assert web["pull_policy"] == "always"

        # ── db service: verify ALL 42 fields (None/empty defaults) ──
        db = details_by_name["db"]
        # Original 14
        assert db["name"] == "db"
        assert db["image"] == "postgres:16"
        assert db["build"] is None
        assert db["ports"] == []
        assert db["environment"] == {"POSTGRES_DB": "mydb"}
        assert len(db["volumes"]) == 1
        assert db["depends_on"] == []
        assert db["command"] is None
        assert db["entrypoint"] is None
        assert db["restart"] is None
        assert db["healthcheck"] is None
        assert db["deploy"] is None
        assert db["networks"] == ["backend"]
        assert db["labels"] == {}
        # Identity
        assert db["container_name"] is None
        assert db["hostname"] is None
        assert db["domainname"] is None
        assert db["platform"] is None
        assert db["profiles"] == []
        # Runtime
        assert db["user"] is None
        assert db["working_dir"] is None
        assert db["stdin_open"] is False
        assert db["tty"] is False
        assert db["privileged"] is False
        assert db["init"] is False
        assert db["read_only"] is False
        assert db["pid"] is None
        assert db["shm_size"] is None
        # Networking
        assert db["network_mode"] is None
        assert db["dns"] == []
        assert db["dns_search"] == []
        assert db["extra_hosts"] == []
        assert db["expose"] == []
        # Files
        assert db["env_file"] == []
        assert db["configs"] == []
        assert db["secrets"] == []
        assert db["tmpfs"] == []
        assert db["devices"] == []
        # Logging
        assert db["logging"] is None
        # Lifecycle
        assert db["stop_signal"] is None
        assert db["stop_grace_period"] is None
        assert db["pull_policy"] is None

    def test_finds_docker_compose_yaml(self, tmp_path: Path):
        """docker-compose.yaml (alt extension) → detected, fully parsed.

        Extension detection test — verifies .yaml is found and parsed
        identically to .yml. All 42 service fields must be present.
        """
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yaml").write_text(
            "version: '3'\nservices:\n  api:\n    image: myapp:latest\n"
        )
        r = docker_status(tmp_path)
        assert r["has_compose"] is True
        assert r["compose_file"] == "docker-compose.yaml"
        assert r["compose_services"] == ["api"]
        assert r["services_count"] == 1
        # Prove full parsing ran — all 42 keys present
        assert len(r["compose_service_details"]) == 1
        svc = r["compose_service_details"][0]
        assert svc["name"] == "api"
        assert svc["image"] == "myapp:latest"
        # All 42 keys must exist (parsing is extension-independent)
        expected_keys = {
            "name", "image", "build", "ports", "environment", "volumes",
            "depends_on", "command", "entrypoint", "restart", "healthcheck",
            "deploy", "networks", "labels",
            "container_name", "hostname", "domainname", "platform", "profiles",
            "user", "working_dir", "stdin_open", "tty", "privileged", "init",
            "read_only", "pid", "shm_size",
            "network_mode", "dns", "dns_search", "extra_hosts", "expose",
            "env_file", "configs", "secrets", "tmpfs", "devices",
            "logging",
            "stop_signal", "stop_grace_period", "pull_policy",
        }
        assert expected_keys.issubset(set(svc.keys())), (
            f"Missing keys: {expected_keys - set(svc.keys())}"
        )

    def test_finds_compose_yml(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        (tmp_path / "compose.yml").write_text("services:\n  web:\n    image: nginx\n")
        r = docker_status(tmp_path)
        assert r["compose_file"] is not None

    def test_finds_compose_yaml(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        (tmp_path / "compose.yaml").write_text("services:\n  web:\n    image: nginx\n")
        r = docker_status(tmp_path)
        assert r["compose_file"] is not None

    # ── Dockerfile discovery ────────────────────────────────────

    def test_detects_dockerfile_at_root(self, tmp_path: Path):
        """Dockerfile present → detected AND parsed (base image, stages, ports)."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.12-slim AS builder\n"
            "RUN pip install deps\n"
            "FROM python:3.12-slim AS runtime\n"
            "COPY --from=builder /app /app\n"
            "EXPOSE 8000\n"
            "EXPOSE 8443/tcp\n"
        )
        r = docker_status(tmp_path)
        # Existence
        assert "has_dockerfile" in r
        assert r["has_dockerfile"] is True
        assert "dockerfiles" in r
        assert "Dockerfile" in r["dockerfiles"]
        # Parsed details
        assert "dockerfile_details" in r
        assert len(r["dockerfile_details"]) >= 1
        df = r["dockerfile_details"][0]
        assert df["path"] == "Dockerfile"
        assert df["base_images"] == ["python:3.12-slim", "python:3.12-slim"]
        assert df["stage_count"] == 2
        assert df["stages"] == ["builder", "runtime"]
        assert 8000 in df["ports"]
        assert 8443 in df["ports"]
        assert "warnings" in df
        assert df["warnings"] == []

    def test_detects_no_dockerfile(self, tmp_path: Path):
        """No Dockerfile → has_dockerfile False, details empty."""
        from src.core.services.docker_detect import docker_status
        r = docker_status(tmp_path)
        assert r["has_dockerfile"] is False
        assert r["dockerfiles"] == []
        assert r["dockerfile_details"] == []

    def test_detects_dockerfile_in_subdirectory(self, tmp_path: Path):
        """Dockerfile in subdirectory → detected with relative path, parsed."""
        from src.core.services.docker_detect import docker_status
        subdir = tmp_path / "services" / "api"
        subdir.mkdir(parents=True)
        (subdir / "Dockerfile").write_text(
            "FROM node:20-alpine\n"
            "EXPOSE 3000\n"
        )
        r = docker_status(tmp_path)
        assert r["has_dockerfile"] is True
        assert "services/api/Dockerfile" in r["dockerfiles"]
        # Parsed details for the subdirectory Dockerfile
        assert len(r["dockerfile_details"]) >= 1
        df = [d for d in r["dockerfile_details"] if d["path"] == "services/api/Dockerfile"]
        assert len(df) == 1
        assert df[0]["base_images"] == ["node:20-alpine"]
        assert df[0]["stage_count"] == 1
        assert 3000 in df[0]["ports"]

    def test_detects_dockerignore(self, tmp_path: Path):
        """.dockerignore present → detected, patterns parsed."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / ".dockerignore").write_text(
            "node_modules\n"
            ".git\n"
            "*.pyc\n"
            "# comment line\n"
            "\n"
        )
        r = docker_status(tmp_path)
        assert "has_dockerignore" in r
        assert r["has_dockerignore"] is True
        assert "dockerignore_patterns" in r
        assert isinstance(r["dockerignore_patterns"], list)
        assert len(r["dockerignore_patterns"]) == 3  # excludes comments and blanks
        assert "node_modules" in r["dockerignore_patterns"]
        assert ".git" in r["dockerignore_patterns"]
        assert "*.pyc" in r["dockerignore_patterns"]

    # ── Malformed files ─────────────────────────────────────────

    def test_malformed_dockerfile_detected_with_warnings(self, tmp_path: Path):
        """Malformed Dockerfile → detected, parsed with warnings.

        A Dockerfile with no FROM instruction should still be detected
        (has_dockerfile=True) but dockerfile_details should have warnings
        and empty base_images.
        """
        from src.core.services.docker_detect import docker_status
        (tmp_path / "Dockerfile").write_text(
            "# No FROM here\n"
            "RUN echo hello\n"
            "EXPOSE 8080\n"
            "GIBBERISH line that makes no sense\n"
        )
        r = docker_status(tmp_path)
        assert r["has_dockerfile"] is True
        assert "Dockerfile" in r["dockerfiles"]
        assert len(r["dockerfile_details"]) == 1
        df = r["dockerfile_details"][0]
        # All 6 fields present (path, base_images, stages, stage_count, ports, warnings)
        assert df["path"] == "Dockerfile"
        assert df["base_images"] == []
        assert df["stages"] == []
        assert df["stage_count"] == 0
        assert df["ports"] == [8080]  # EXPOSE still parsed
        assert "warnings" in df
        assert isinstance(df["warnings"], list)
        assert len(df["warnings"]) >= 1
        # At least one warning about missing FROM
        assert any("FROM" in w for w in df["warnings"])

    def test_empty_dockerfile_detected_with_warnings(self, tmp_path: Path):
        """Empty Dockerfile → detected, warnings include 'empty'."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "Dockerfile").write_text("")
        r = docker_status(tmp_path)
        assert r["has_dockerfile"] is True
        df = r["dockerfile_details"][0]
        assert df["base_images"] == []
        assert df["stage_count"] == 0
        assert "warnings" in df
        assert any("empty" in w.lower() for w in df["warnings"])

    def test_malformed_compose_detected_with_warnings(self, tmp_path: Path):
        """Malformed compose file → detected, services empty, warning present."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(
            "this: is: not: valid: yaml: [[\n"
        )
        r = docker_status(tmp_path)
        # File detected
        assert r["has_compose"] is True
        assert r["compose_file"] == "docker-compose.yml"
        # But parsing failed gracefully
        assert r["compose_services"] == []
        assert r["compose_service_details"] == []
        assert r["services_count"] == 0

    # ── Empty project ───────────────────────────────────────────

    def test_empty_project_clean_result(self, tmp_path: Path):
        """Empty project → every file-detection key present and negative."""
        from src.core.services.docker_detect import docker_status
        r = docker_status(tmp_path)
        # Must be a dict with consistent shape regardless of CLI
        assert isinstance(r, dict)
        # File detection keys — all must be present, not hidden behind .get()
        assert "has_dockerfile" in r
        assert r["has_dockerfile"] is False
        assert "has_compose" in r
        assert r["has_compose"] is False
        assert "compose_file" in r
        assert r["compose_file"] is None
        assert "dockerfiles" in r
        assert r["dockerfiles"] == []
        assert "compose_services" in r
        assert r["compose_services"] == []
        assert "compose_service_details" in r
        assert r["compose_service_details"] == []
        assert "dockerfile_details" in r
        assert r["dockerfile_details"] == []
        assert "services_count" in r
        assert r["services_count"] == 0
        assert "has_dockerignore" in r
        assert r["has_dockerignore"] is False
        assert "dockerignore_patterns" in r
        assert r["dockerignore_patterns"] == []

    # ── Coexistence ─────────────────────────────────────────────

    def test_both_dockerfile_and_compose_detected(self, tmp_path: Path):
        """Both Dockerfile and compose → both detected, both fully parsed."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            "EXPOSE 8000\n"
        )
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n"
            "  app:\n"
            "    build: .\n"
            "    image: myapp:latest\n"
            "    ports:\n"
            "      - '8000:8000'\n"
        )
        r = docker_status(tmp_path)

        # Both flags true simultaneously
        assert r["has_dockerfile"] is True
        assert r["has_compose"] is True

        # Dockerfile detection + parsing
        assert "Dockerfile" in r["dockerfiles"]
        assert len(r["dockerfile_details"]) >= 1
        df = r["dockerfile_details"][0]
        assert df["path"] == "Dockerfile"
        assert df["base_images"] == ["python:3.12-slim"]
        assert df["stage_count"] == 1
        assert df["stages"] == []
        assert 8000 in df["ports"]

        # Compose detection + parsing
        assert r["compose_file"] == "docker-compose.yml"
        assert r["compose_services"] == ["app"]
        assert r["services_count"] == 1
        assert len(r["compose_service_details"]) == 1
        svc = r["compose_service_details"][0]
        assert svc["name"] == "app"
        assert svc["image"] == "myapp:latest"
        # All 42 keys present
        expected_keys = {
            "name", "image", "build", "ports", "environment", "volumes",
            "depends_on", "command", "entrypoint", "restart", "healthcheck",
            "deploy", "networks", "labels",
            "container_name", "hostname", "domainname", "platform", "profiles",
            "user", "working_dir", "stdin_open", "tty", "privileged", "init",
            "read_only", "pid", "shm_size",
            "network_mode", "dns", "dns_search", "extra_hosts", "expose",
            "env_file", "configs", "secrets", "tmpfs", "devices",
            "logging",
            "stop_signal", "stop_grace_period", "pull_policy",
        }
        assert expected_keys.issubset(set(svc.keys())), (
            f"Missing keys: {expected_keys - set(svc.keys())}"
        )

# ═══════════════════════════════════════════════════════════════════
#  2. SERVICE PARSING — extract full service details from compose
# ═══════════════════════════════════════════════════════════════════


class TestDockerServiceParsing:
    """Compose services must be parsed with ALL configuration details."""

    FULL_COMPOSE = textwrap.dedent("""\
        version: "3.8"
        services:
          web:
            build:
              context: ./web
              dockerfile: Dockerfile.prod
            image: myapp-web:latest
            ports:
              - "3000:3000"
              - "3001:3001"
            volumes:
              - ./web/src:/app/src
              - web-data:/app/data
            environment:
              NODE_ENV: production
              API_URL: http://api:8000
            depends_on:
              - api
              - db
            healthcheck:
              test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
              interval: 30s
              timeout: 10s
              retries: 3
            restart: unless-stopped
            networks:
              - frontend
              - backend
            labels:
              app.tier: frontend

          api:
            build: ./api
            ports:
              - "8000:8000"
            environment:
              - DATABASE_URL=postgres://db:5432/app
              - SECRET_KEY=changeme
            depends_on:
              - db
            restart: always
            networks:
              - backend

          db:
            image: postgres:15
            ports:
              - "5432:5432"
            volumes:
              - pg-data:/var/lib/postgresql/data
            environment:
              POSTGRES_PASSWORD: secret
              POSTGRES_DB: app
            restart: always
            networks:
              - backend

          redis:
            image: redis:7-alpine
            ports:
              - "6379:6379"
            restart: always

        volumes:
          web-data:
          pg-data:

        networks:
          frontend:
          backend:
    """)

    def _write_compose(self, tmp_path: Path) -> Path:
        f = tmp_path / "docker-compose.yml"
        f.write_text(self.FULL_COMPOSE)
        return f

    def test_counts_all_services(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        assert r["services_count"] == 4

    def test_service_names(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        names = [s["name"] for s in r["services"]]
        assert set(names) == {"web", "api", "db", "redis"}

    def test_service_ports_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        assert len(web["ports"]) >= 2

    def test_service_volumes_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        assert len(web.get("volumes", [])) >= 2

    def test_service_environment_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        env = web.get("environment", {})
        assert "NODE_ENV" in env or any("NODE_ENV" in str(e) for e in env)

    def test_service_depends_on_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        deps = web.get("depends_on", [])
        assert "api" in deps
        assert "db" in deps

    def test_service_build_context_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        assert web.get("build") is not None

    def test_service_image_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        db = next(s for s in r["services"] if s["name"] == "db")
        assert "postgres" in db.get("image", "")

    def test_service_healthcheck_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        assert web.get("healthcheck") is not None

    def test_service_restart_policy_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        assert web.get("restart") in ("unless-stopped", "always", "no", "on-failure")

    def test_service_networks_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        nets = web.get("networks", [])
        assert "frontend" in nets
        assert "backend" in nets

    def test_service_labels_parsed(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        self._write_compose(tmp_path)
        r = docker_status(tmp_path)
        web = next(s for s in r["services"] if s["name"] == "web")
        labels = web.get("labels", {})
        assert "app.tier" in labels or len(labels) > 0

    # ── Environment variable formats ────────────────────────────

    def test_env_dict_format(self, tmp_path: Path):
        """KEY: value format → parsed correctly."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                environment:
                  FOO: bar
                  BAZ: qux
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        env = app.get("environment", {})
        assert env.get("FOO") == "bar" or "FOO" in str(env)

    def test_env_list_format(self, tmp_path: Path):
        """KEY=value list format → parsed correctly."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                environment:
                  - FOO=bar
                  - BAZ=qux
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        env = app.get("environment", {})
        assert env.get("FOO") == "bar" or "FOO" in str(env)

    # ── Port formats ────────────────────────────────────────────

    def test_string_port_mapping(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                ports:
                  - "8080:80"
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        assert len(app.get("ports", [])) >= 1

    def test_long_port_mapping(self, tmp_path: Path):
        """Long-form port syntax → parsed."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                ports:
                  - target: 80
                    published: 8080
                    protocol: tcp
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        assert len(app.get("ports", [])) >= 1

    # ── Volume formats ──────────────────────────────────────────

    def test_bind_mount_volume(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                volumes:
                  - ./data:/app/data
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        assert len(app.get("volumes", [])) >= 1

    def test_named_volume(self, tmp_path: Path):
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              app:
                image: app
                volumes:
                  - mydata:/app/data
            volumes:
              mydata:
        """))
        r = docker_status(tmp_path)
        app = r["services"][0]
        assert len(app.get("volumes", [])) >= 1


# ═══════════════════════════════════════════════════════════════════
#  3. CONTAINER MANAGEMENT — lifecycle of individual containers
# ═══════════════════════════════════════════════════════════════════


class TestDockerContainerManagement:
    """Container operations — all require Docker daemon.
    These define WHAT must work, mocking the daemon."""

    @patch("src.core.services.docker_containers.run_docker")
    def test_list_containers(self, mock_run, tmp_path: Path):
        """List running containers → structured result with id, name, status, ports."""
        from src.core.services.docker_containers import list_containers

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"ID":"abc123","Names":"web","State":"running","Ports":"0.0.0.0:3000->3000/tcp","Image":"myapp:latest"}]'
        )
        result = list_containers(tmp_path)
        assert result["ok"] is True
        assert len(result["containers"]) >= 1
        c = result["containers"][0]
        assert "id" in c or "ID" in c
        assert "name" in c or "Names" in c

    @patch("src.core.services.docker_containers.run_docker")
    def test_list_images(self, mock_run, tmp_path: Path):
        """List images → id, repo, tag, size."""
        from src.core.services.docker_containers import list_images

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"ID":"sha256:abc","Repository":"myapp","Tag":"latest","Size":"150MB"}]'
        )
        result = list_images(tmp_path)
        assert result["ok"] is True
        assert len(result["images"]) >= 1

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_inspect(self, mock_run, tmp_path: Path):
        """Inspect container → full config, state, network."""
        from src.core.services.docker_containers import container_inspect

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"State":{"Status":"running"},"Config":{"Image":"myapp:latest"}}]'
        )
        result = container_inspect("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_logs(self, mock_run, tmp_path: Path):
        """Get container logs → log lines returned."""
        from src.core.services.docker_containers import container_logs

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="2024-01-01 Server started\n2024-01-01 Listening on :3000\n"
        )
        result = container_logs("abc123", tmp_path, tail=100)
        assert result["ok"] is True
        assert "logs" in result

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_stats(self, mock_run, tmp_path: Path):
        """Get container stats → CPU, memory, network I/O."""
        from src.core.services.docker_containers import container_stats

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"CPUPerc":"2.5%","MemUsage":"150MiB / 8GiB","NetIO":"1.2kB / 3.4kB"}]'
        )
        result = container_stats("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_start(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import container_start
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = container_start("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_stop(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import container_stop
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = container_stop("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_restart(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import container_restart
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = container_restart("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_container_remove(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import container_remove
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = container_remove("abc123", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_image_pull(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import image_pull
        mock_run.return_value = MagicMock(returncode=0, stdout="Pull complete\n")
        result = image_pull("nginx:latest", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_image_remove(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import image_remove
        mock_run.return_value = MagicMock(returncode=0, stdout="Deleted\n")
        result = image_remove("sha256:abc", tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_prune_resources(self, mock_run, tmp_path: Path):
        """Prune unused containers, images, volumes."""
        from src.core.services.docker_containers import docker_prune
        mock_run.return_value = MagicMock(returncode=0, stdout="Deleted\n")
        result = docker_prune(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_list_networks(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import list_networks
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name":"bridge","Driver":"bridge"}]'
        )
        result = list_networks(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_docker")
    def test_list_volumes(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import list_volumes
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name":"mydata","Driver":"local"}]'
        )
        result = list_volumes(tmp_path)
        assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════
#  4. COMPOSE OPERATIONS — build, up, down, restart
# ═══════════════════════════════════════════════════════════════════


class TestDockerComposeOperations:
    """Compose operations manage multi-service Docker applications."""

    def _write_compose(self, tmp_path: Path):
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              web:
                image: nginx:alpine
                ports:
                  - "8080:80"
        """))

    @patch("src.core.services.docker_containers.run_compose")
    def test_compose_build(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import compose_build
        self._write_compose(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="Building...\n")
        result = compose_build(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_compose")
    def test_compose_up(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import compose_up
        self._write_compose(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="Started\n")
        result = compose_up(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_compose")
    def test_compose_down(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import compose_down
        self._write_compose(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="Stopped\n")
        result = compose_down(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_compose")
    def test_compose_restart(self, mock_run, tmp_path: Path):
        from src.core.services.docker_containers import compose_restart
        self._write_compose(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="Restarted\n")
        result = compose_restart(tmp_path)
        assert result["ok"] is True

    @patch("src.core.services.docker_containers.run_compose")
    def test_compose_status(self, mock_run, tmp_path: Path):
        """Compose status → running/stopped per service."""
        from src.core.services.docker_containers import compose_status
        self._write_compose(tmp_path)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='NAME  IMAGE         COMMAND  SERVICE  CREATED  STATUS  PORTS\nweb   nginx:alpine  ""       web      1h ago   Up      0.0.0.0:8080->80/tcp\n'
        )
        result = compose_status(tmp_path)
        assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════
#  5. FILE GENERATION — Dockerfile, .dockerignore, compose
# ═══════════════════════════════════════════════════════════════════


class TestDockerFileGeneration:
    """Generation must produce valid, production-ready files."""

    # ── Dockerfile per stack ────────────────────────────────────

    def test_dockerfile_all_stacks(self, tmp_path: Path):
        """Every supported stack must generate a Dockerfile."""
        from src.core.services.generators.dockerfile import generate_dockerfile, supported_stacks
        for stack in supported_stacks():
            r = generate_dockerfile(tmp_path, stack)
            assert r is not None, f"No Dockerfile for {stack}"
            assert "FROM" in r.content, f"No FROM in {stack}"
            assert "EXPOSE" in r.content, f"No EXPOSE in {stack}"
            assert "USER" in r.content, f"No non-root USER in {stack}"

    def test_dockerfile_multi_stage(self, tmp_path: Path):
        """Compiled stacks must use multi-stage builds."""
        from src.core.services.generators.dockerfile import generate_dockerfile
        for stack in ("go", "rust", "java-maven", "dotnet"):
            r = generate_dockerfile(tmp_path, stack)
            from_count = r.content.count("FROM ")
            assert from_count >= 2, f"{stack} should be multi-stage, got {from_count} FROM"

    def test_dockerfile_layer_caching(self, tmp_path: Path):
        """Dependencies must be copied before source for layer caching."""
        from src.core.services.generators.dockerfile import generate_dockerfile
        r = generate_dockerfile(tmp_path, "python")
        lines = r.content.splitlines()
        # requirements/pyproject copied before full COPY .
        req_idx = next((i for i, l in enumerate(lines) if "requirements" in l or "pyproject" in l), -1)
        copy_all_idx = next((i for i, l in enumerate(lines) if l.strip() == "COPY . ."), -1)
        assert req_idx < copy_all_idx, "Dependencies should be copied before source code"

    # ── Dockerignore per stack ──────────────────────────────────

    def test_dockerignore_all_stacks(self, tmp_path: Path):
        """Every stack produces a .dockerignore with relevant patterns."""
        from src.core.services.generators.dockerignore import generate_dockerignore
        from src.core.services.generators.dockerfile import supported_stacks
        for stack in supported_stacks():
            r = generate_dockerignore(tmp_path, [stack])
            assert ".git" in r.content, f"Missing .git for {stack}"
            assert len(r.content) > 50

    def test_dockerignore_no_duplicate_sections(self, tmp_path: Path):
        """python + python-flask → python patterns only once."""
        from src.core.services.generators.dockerignore import generate_dockerignore
        r = generate_dockerignore(tmp_path, ["python", "python-flask"])
        assert r.content.count("__pycache__") == 1

    # ── Compose from wizard ─────────────────────────────────────

    def test_compose_from_modules(self, tmp_path: Path):
        """Multiple modules → compose with correct services and ports."""
        from src.core.services.generators.compose import generate_compose
        modules = [
            {"name": "api", "path": "api", "stack_name": "python"},
            {"name": "web", "path": "web", "stack_name": "node"},
            {"name": "worker", "path": "worker", "stack_name": "go"},
        ]
        r = generate_compose(tmp_path, modules)
        assert r is not None
        assert "api" in r.content
        assert "web" in r.content
        assert "worker" in r.content
        assert "8000" in r.content  # python
        assert "3000" in r.content  # node
        assert "8080" in r.content  # go

    def test_compose_from_wizard_services(self, tmp_path: Path):
        """Wizard-defined services → compose with user-specified config."""
        from src.core.services.docker_generate import generate_compose_from_wizard
        services = [
            {
                "name": "api",
                "image": "myapp-api:latest",
                "build": {"context": "./api"},
                "ports": [{"host": 8000, "container": 8000}],
                "environment": {"DATABASE_URL": "postgres://db:5432/app"},
                "volumes": [{"source": "./data", "target": "/app/data"}],
                "depends_on": ["db"],
            },
            {
                "name": "db",
                "image": "postgres:15",
                "ports": [{"host": 5432, "container": 5432}],
                "environment": {"POSTGRES_PASSWORD": "secret"},
                "volumes": [{"source": "pgdata", "target": "/var/lib/postgresql/data", "type": "volume"}],
            },
        ]
        result = generate_compose_from_wizard(services, tmp_path)
        assert result["ok"] is True
        content = result["content"]
        assert "api" in content
        assert "db" in content
        assert "postgres" in content
        assert "8000" in content
        assert "5432" in content

    # ── Write generated file ────────────────────────────────────

    def test_write_generated_file(self, tmp_path: Path):
        """write_generated_file writes content to disk."""
        from src.core.services.docker_generate import write_generated_file
        from src.core.models.template import GeneratedFile

        gf = GeneratedFile(
            path="Dockerfile",
            content="FROM python:3.12\nRUN echo hello\n",
            overwrite=False,
            reason="test",
        )
        result = write_generated_file(gf, tmp_path)
        assert result["ok"] is True
        assert (tmp_path / "Dockerfile").exists()
        assert "python:3.12" in (tmp_path / "Dockerfile").read_text()

    def test_write_generated_file_no_overwrite(self, tmp_path: Path):
        """Existing file + overwrite=False → not overwritten."""
        from src.core.services.docker_generate import write_generated_file
        from src.core.models.template import GeneratedFile

        (tmp_path / "Dockerfile").write_text("ORIGINAL\n")
        gf = GeneratedFile(path="Dockerfile", content="REPLACED\n", overwrite=False)
        write_generated_file(gf, tmp_path)
        assert "ORIGINAL" in (tmp_path / "Dockerfile").read_text()

    def test_write_generated_file_overwrite(self, tmp_path: Path):
        """Existing file + overwrite=True → overwritten."""
        from src.core.services.docker_generate import write_generated_file
        from src.core.models.template import GeneratedFile

        (tmp_path / "Dockerfile").write_text("ORIGINAL\n")
        gf = GeneratedFile(path="Dockerfile", content="REPLACED\n", overwrite=True)
        write_generated_file(gf, tmp_path)
        assert "REPLACED" in (tmp_path / "Dockerfile").read_text()


# ═══════════════════════════════════════════════════════════════════
#  6. WIZARD SETUP — full orchestration
# ═══════════════════════════════════════════════════════════════════


class TestDockerWizardSetup:
    """Wizard setup must orchestrate the full flow:
    accept user choices → generate files → write to disk."""

    def test_setup_creates_all_files(self, tmp_path: Path):
        """setup_docker → Dockerfile + compose + dockerignore on disk."""
        from src.core.services.wizard_setup import setup_docker
        result = setup_docker(
            project_root=tmp_path,
            stack="python-flask",
            services=[{"name": "api", "path": ".", "port": 8000}],
        )
        assert result["ok"] is True
        assert (tmp_path / "Dockerfile").exists()
        assert (tmp_path / "docker-compose.yml").exists()
        assert (tmp_path / ".dockerignore").exists()

    def test_setup_preserves_existing(self, tmp_path: Path):
        """Existing Dockerfile not overwritten."""
        from src.core.services.wizard_setup import setup_docker
        original = "FROM custom:v1\n"
        (tmp_path / "Dockerfile").write_text(original)
        setup_docker(
            project_root=tmp_path,
            stack="python",
            services=[{"name": "api", "path": ".", "port": 8000}],
        )
        assert (tmp_path / "Dockerfile").read_text() == original

    def test_setup_returns_generated_files_list(self, tmp_path: Path):
        """Result includes list of files that were generated."""
        from src.core.services.wizard_setup import setup_docker
        result = setup_docker(
            project_root=tmp_path,
            stack="node",
            services=[{"name": "web", "path": ".", "port": 3000}],
        )
        assert "files" in result or "generated" in result
        files = result.get("files", result.get("generated", []))
        assert len(files) >= 2

    def test_setup_multi_service(self, tmp_path: Path):
        """Multiple services → compose has all of them."""
        from src.core.services.wizard_setup import setup_docker
        result = setup_docker(
            project_root=tmp_path,
            stack="python",
            services=[
                {"name": "api", "path": "api", "port": 8000},
                {"name": "worker", "path": "worker", "port": 8001},
            ],
        )
        assert result["ok"] is True
        compose_content = (tmp_path / "docker-compose.yml").read_text()
        assert "api" in compose_content
        assert "worker" in compose_content


# ═══════════════════════════════════════════════════════════════════
#  7. ROUND-TRIP — generate → detect must be consistent
# ═══════════════════════════════════════════════════════════════════


class TestDockerRoundTrip:
    def test_generated_compose_detected(self, tmp_path: Path):
        """Generate compose → write → detect → same services found."""
        from src.core.services.generators.compose import generate_compose
        from src.core.services.docker_detect import docker_status

        compose = generate_compose(tmp_path, [
            {"name": "api", "path": "api", "stack_name": "python"},
            {"name": "web", "path": "web", "stack_name": "node"},
        ])
        (tmp_path / "docker-compose.yml").write_text(compose.content)

        status = docker_status(tmp_path)
        assert status["compose_file"] is not None
        assert status["services_count"] >= 2
        names = [s["name"] for s in status["services"]]
        assert "api" in names
        assert "web" in names

    def test_wizard_setup_then_detect(self, tmp_path: Path):
        """Wizard setup → detect → consistent results."""
        from src.core.services.wizard_setup import setup_docker
        from src.core.services.docker_detect import docker_status

        setup_docker(
            project_root=tmp_path,
            stack="python",
            services=[{"name": "api", "path": ".", "port": 8000}],
        )

        status = docker_status(tmp_path)
        assert status["compose_file"] is not None
        assert status.get("has_dockerfile") is True


# ═══════════════════════════════════════════════════════════════════
#  8. ERROR HANDLING — graceful failures
# ═══════════════════════════════════════════════════════════════════


class TestDockerErrorHandling:
    def test_detect_unreadable_compose(self, tmp_path: Path):
        """Corrupt compose file → error, not crash."""
        from src.core.services.docker_detect import docker_status
        (tmp_path / "docker-compose.yml").write_text("{{invalid yaml")
        result = docker_status(tmp_path)
        assert isinstance(result, dict)
        # Must not raise

    @patch("src.core.services.docker_containers.run_docker")
    def test_daemon_not_available(self, mock_run, tmp_path: Path):
        """Docker daemon unreachable → ok=False with clear error."""
        from src.core.services.docker_containers import list_containers
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = list_containers(tmp_path)
        assert result["ok"] is False

    def test_generate_unknown_stack(self, tmp_path: Path):
        """Unknown stack → None, not crash."""
        from src.core.services.generators.dockerfile import generate_dockerfile
        assert generate_dockerfile(tmp_path, "fortran-77") is None
