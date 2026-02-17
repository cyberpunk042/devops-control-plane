"""
Tests for docker_detect — compose file parsing, port normalization, env parsing.

Pure unit tests: compose YAML file on disk → parsed dicts.
No Docker daemon required.
"""

from pathlib import Path

from src.core.services.docker_detect import (
    _parse_compose_service_details,
    _normalise_ports,
    _env_list_to_dict,
    find_compose_file,
)


# ═══════════════════════════════════════════════════════════════════
#  find_compose_file
# ═══════════════════════════════════════════════════════════════════


class TestFindComposeFile:
    def test_finds_docker_compose_yml(self, tmp_path: Path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        result = find_compose_file(tmp_path)
        assert result is not None
        assert result.name == "docker-compose.yml"

    def test_finds_compose_yml(self, tmp_path: Path):
        (tmp_path / "compose.yml").write_text("services: {}\n")
        result = find_compose_file(tmp_path)
        assert result is not None
        assert result.name == "compose.yml"

    def test_returns_none_if_missing(self, tmp_path: Path):
        result = find_compose_file(tmp_path)
        assert result is None

    def test_priority_order(self, tmp_path: Path):
        """docker-compose.yml is found first even if compose.yml exists."""
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")
        (tmp_path / "compose.yml").write_text("services: {}\n")
        result = find_compose_file(tmp_path)
        assert result.name == "docker-compose.yml"


# ═══════════════════════════════════════════════════════════════════
#  _normalise_ports
# ═══════════════════════════════════════════════════════════════════


class TestNormalisePorts:
    def test_string_host_container(self):
        """'8080:80' → host=8080, container=80."""
        result = _normalise_ports(["8080:80"])
        assert len(result) == 1
        assert result[0]["host"] == 8080
        assert result[0]["container"] == 80
        assert result[0]["protocol"] == "tcp"

    def test_string_single_port(self):
        """'8080' → host=8080, container=8080."""
        result = _normalise_ports(["8080"])
        assert result[0]["host"] == 8080
        assert result[0]["container"] == 8080

    def test_string_with_protocol(self):
        """'53:53/udp' → protocol=udp."""
        result = _normalise_ports(["53:53/udp"])
        assert result[0]["protocol"] == "udp"

    def test_string_with_host_ip(self):
        """'127.0.0.1:8080:80' → host=8080, container=80."""
        result = _normalise_ports(["127.0.0.1:8080:80"])
        assert result[0]["host"] == 8080
        assert result[0]["container"] == 80

    def test_integer_port(self):
        """Integer port → same host and container."""
        result = _normalise_ports([8080])
        assert result[0]["host"] == 8080
        assert result[0]["container"] == 8080

    def test_dict_long_form(self):
        """Long-form dict → target, published."""
        result = _normalise_ports([
            {"target": 80, "published": 8080, "protocol": "tcp"},
        ])
        assert result[0]["host"] == 8080
        assert result[0]["container"] == 80

    def test_empty_input(self):
        assert _normalise_ports(None) == []
        assert _normalise_ports([]) == []


# ═══════════════════════════════════════════════════════════════════
#  _env_list_to_dict
# ═══════════════════════════════════════════════════════════════════


class TestEnvListToDict:
    def test_key_value_pairs(self):
        result = _env_list_to_dict(["DB_HOST=localhost", "DB_PORT=5432"])
        assert result == {"DB_HOST": "localhost", "DB_PORT": "5432"}

    def test_value_with_equals(self):
        """Value containing '=' is preserved."""
        result = _env_list_to_dict(["CONN=host=db;port=5432"])
        assert result["CONN"] == "host=db;port=5432"

    def test_key_without_value(self):
        """Key without '=' → empty value."""
        result = _env_list_to_dict(["DEBUG"])
        assert result["DEBUG"] == ""


# ═══════════════════════════════════════════════════════════════════
#  _parse_compose_service_details
# ═══════════════════════════════════════════════════════════════════


class TestParseComposeServiceDetails:
    def test_simple_service(self, tmp_path: Path):
        """Single service with image and ports."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  web:\n"
            "    image: nginx:alpine\n"
            "    ports:\n"
            "      - '80:80'\n"
        )
        result = _parse_compose_service_details(compose)
        assert len(result) == 1
        svc = result[0]
        assert svc["name"] == "web"
        assert svc["image"] == "nginx:alpine"
        assert svc["ports"][0]["container"] == 80

    def test_service_with_build(self, tmp_path: Path):
        """Service with build context and dockerfile."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile.prod\n"
        )
        result = _parse_compose_service_details(compose)
        svc = result[0]
        assert svc["build"]["context"] == "."
        assert svc["build"]["dockerfile"] == "Dockerfile.prod"

    def test_service_with_env_list(self, tmp_path: Path):
        """Service with environment as list → parsed to dict."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    image: myapp:latest\n"
            "    environment:\n"
            "      - DB_HOST=localhost\n"
            "      - DB_PORT=5432\n"
        )
        result = _parse_compose_service_details(compose)
        env = result[0]["environment"]
        assert env["DB_HOST"] == "localhost"
        assert env["DB_PORT"] == "5432"

    def test_service_with_env_dict(self, tmp_path: Path):
        """Service with environment as dict."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    image: myapp:latest\n"
            "    environment:\n"
            "      DB_HOST: localhost\n"
            "      DB_PORT: 5432\n"
        )
        result = _parse_compose_service_details(compose)
        env = result[0]["environment"]
        assert env["DB_HOST"] == "localhost"
        assert env["DB_PORT"] == "5432"

    def test_depends_on(self, tmp_path: Path):
        """depends_on as list of service names."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    image: myapp:latest\n"
            "    depends_on:\n"
            "      - db\n"
            "      - redis\n"
            "  db:\n"
            "    image: postgres:16\n"
            "  redis:\n"
            "    image: redis:7\n"
        )
        result = _parse_compose_service_details(compose)
        api = next(s for s in result if s["name"] == "api")
        assert api["depends_on"] == ["db", "redis"]

    def test_invalid_file_returns_empty(self, tmp_path: Path):
        """Invalid YAML → empty list."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("not: valid: yaml: {{{\n")
        result = _parse_compose_service_details(compose)
        assert result == []

    def test_no_services_key_returns_empty(self, tmp_path: Path):
        """YAML without 'services' key → empty list."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\nfoo: bar\n")
        result = _parse_compose_service_details(compose)
        assert result == []

    def test_volumes_and_networks(self, tmp_path: Path):
        """Volumes and networks are extracted."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  db:\n"
            "    image: postgres:16\n"
            "    volumes:\n"
            "      - pgdata:/var/lib/postgresql/data\n"
            "    networks:\n"
            "      - backend\n"
        )
        result = _parse_compose_service_details(compose)
        svc = result[0]
        assert "pgdata:/var/lib/postgresql/data" in svc["volumes"]
        assert "backend" in svc["networks"]
