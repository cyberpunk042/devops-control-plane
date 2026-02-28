"""
L0 Data — Monitoring & observability tools.

Categories: monitoring
Pure data, no logic.
"""

from __future__ import annotations


_MONITORING_RECIPES: dict[str, dict] = {

    "prometheus": {
        "cli": "prometheus",
        "label": "Prometheus (metrics monitoring and alerting toolkit)",
        "category": "monitoring",
        # Written in Go. By the CNCF (Cloud Native Computing Foundation).
        # brew: prometheus. snap: not available.
        # GitHub releases: prometheus-VERSION.OS-ARCH.tar.gz
        # Version is in BOTH the tag (v2.x.x) and filename (2.x.x).
        # Tag has 'v' prefix, filename does not.
        # Arch: amd64, arm64, armv7. OS: linux, darwin.
        # NOT in apt, dnf, apk (via community), pacman, zypper as standard.
        # pacman has prometheus in community but it includes the server service.
        # Archive contains: prometheus, promtool, config, consoles — we extract
        # just the binaries.
        "install": {
            "brew": ["brew", "install", "prometheus"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/prometheus/"
                "prometheus/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/prometheus/prometheus/releases/"
                "download/v${VERSION}/prometheus-${VERSION}.{os}-{arch}.tar.gz"
                " | sudo tar -xz --strip-components=1 -C /usr/local/bin"
                " prometheus-${VERSION}.{os}-{arch}/prometheus"
                " prometheus-${VERSION}.{os}-{arch}/promtool",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7",
        },
        "prefer": ["brew"],
        "verify": ["prometheus", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "prometheus"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/prometheus/"
                "prometheus/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/prometheus/prometheus/releases/"
                "download/v${VERSION}/prometheus-${VERSION}.{os}-{arch}.tar.gz"
                " | sudo tar -xz --strip-components=1 -C /usr/local/bin"
                " prometheus-${VERSION}.{os}-{arch}/prometheus"
                " prometheus-${VERSION}.{os}-{arch}/promtool",
            ],
        },
    },
    "grafana-cli": {
        "label": "Grafana CLI",
        "category": "monitoring",
        "cli": "grafana-cli",
        "install": {
            "apt": ["apt-get", "install", "-y", "grafana"],
            "dnf": ["dnf", "install", "-y", "grafana"],
            "brew": ["brew", "install", "grafana"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["grafana-cli", "--version"],
    },
    "loki": {
        "label": "Grafana Loki",
        "category": "monitoring",
        "cli": "loki",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/loki"
                    " https://github.com/grafana/loki/releases/latest/download/"
                    "loki-linux-amd64.zip && chmod +x /usr/local/bin/loki",
                ],
            },
            "brew": ["brew", "install", "loki"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["loki", "--version"],
    },
    "promtail": {
        "label": "Promtail (Loki agent)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/promtail"
                    " https://github.com/grafana/loki/releases/latest/download/"
                    "promtail-linux-amd64.zip && chmod +x /usr/local/bin/promtail",
                ],
            },
            "brew": ["brew", "install", "promtail"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["promtail", "--version"],
    },
    "jaeger": {
        "label": "Jaeger (distributed tracing)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/jaegertracing/jaeger/releases/"
                    "latest/download/jaeger-all-in-one-linux-amd64.tar.gz"
                    " | tar xz -C /usr/local/bin",
                ],
            },
            "brew": ["brew", "install", "jaeger"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["jaeger-all-in-one", "version"],
        "cli": "jaeger-all-in-one",
    },
    "vegeta": {
        "label": "Vegeta (HTTP load testing)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/tsenart/vegeta/releases/"
                    "latest/download/vegeta_linux_amd64.tar.gz"
                    " | tar xz -C /usr/local/bin vegeta",
                ],
            },
            "brew": ["brew", "install", "vegeta"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["vegeta", "--version"],
    },
}
