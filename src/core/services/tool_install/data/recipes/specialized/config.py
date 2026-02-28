"""
L0 Data — Config template recipes.

Categories: config
Pure data, no logic.
"""

from __future__ import annotations


_CONFIG_RECIPES: dict[str, dict] = {
    #
    # Spec: domain-config-files §Examples.
    # These produce `action: "template"` config steps.

    "docker-daemon-config": {
        "type": "config",
        "label": "Docker daemon.json",
        "category": "config",
        "config_templates": [{
            "id": "docker_config",
            "file": "/etc/docker/daemon.json",
            "format": "json",
            "template": '{\n'
                        '  "storage-driver": "{docker_storage_driver}",\n'
                        '  "log-driver": "json-file",\n'
                        '  "log-opts": {\n'
                        '    "max-size": "{log_max_size}",\n'
                        '    "max-file": "{log_max_files}"\n'
                        '  }\n'
                        '}',
            "inputs": [
                {"id": "docker_storage_driver", "label": "Storage Driver",
                 "type": "select",
                 "options": ["overlay2", "btrfs", "devicemapper"],
                 "default": "overlay2"},
                {"id": "log_max_size",
                 "label": "Max log size per container",
                 "type": "select",
                 "options": ["10m", "50m", "100m", "500m"],
                 "default": "50m"},
                {"id": "log_max_files",
                 "label": "Max log files per container",
                 "type": "select",
                 "options": ["1", "3", "5", "10"],
                 "default": "3"},
            ],
            "needs_sudo": True,
            "post_command": ["systemctl", "restart", "docker"],
            "condition": "has_systemd",
            "backup": True,
        }],
        # No install — this is a config-only recipe.
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c", "test -f /etc/docker/daemon.json"],
    },
    "journald-config": {
        "type": "config",
        "label": "journald configuration",
        "category": "config",
        "config_templates": [{
            "id": "journald_config",
            "file": "/etc/systemd/journald.conf.d/custom.conf",
            "format": "ini",
            "template": (
                "[Journal]\n"
                "SystemMaxUse={journal_max_size}\n"
                "Compress=yes\n"
                "RateLimitBurst={rate_limit}\n"
            ),
            "inputs": [
                {"id": "journal_max_size", "label": "Max journal size",
                 "type": "select",
                 "options": ["100M", "500M", "1G", "2G"],
                 "default": "500M"},
                {"id": "rate_limit", "label": "Rate limit burst",
                 "type": "number", "default": 1000,
                 "validation": {"min": 100, "max": 100000}},
            ],
            "needs_sudo": True,
            "post_command": ["systemctl", "restart", "systemd-journald"],
            "condition": "has_systemd",
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c",
                   "test -f /etc/systemd/journald.conf.d/custom.conf"],
    },
    "logrotate-docker": {
        "type": "config",
        "label": "Docker logrotate config",
        "category": "config",
        "config_templates": [{
            "id": "logrotate_docker",
            "file": "/etc/logrotate.d/docker-containers",
            "format": "raw",
            "template": (
                "/var/lib/docker/containers/*/*.log {\n"
                "    daily\n"
                "    rotate {rotate_count}\n"
                "    compress\n"
                "    delaycompress\n"
                "    missingok\n"
                "    notifempty\n"
                "    copytruncate\n"
                "}\n"
            ),
            "inputs": [
                {"id": "rotate_count", "label": "Days to keep",
                 "type": "number", "default": 14,
                 "validation": {"min": 1, "max": 365}},
            ],
            "needs_sudo": True,
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c",
                   "test -f /etc/logrotate.d/docker-containers"],
    },
    "nginx-vhost": {
        "type": "config",
        "label": "nginx virtual host",
        "category": "config",
        "config_templates": [{
            "id": "nginx_vhost",
            "file": "/etc/nginx/sites-available/{site_name}",
            "format": "raw",
            "template": (
                "server {\n"
                "    listen {port};\n"
                "    server_name {server_name};\n"
                "    root {document_root};\n"
                "\n"
                "    location / {\n"
                "        try_files $uri $uri/ =404;\n"
                "    }\n"
                "}\n"
            ),
            "inputs": [
                {"id": "site_name", "label": "Site name",
                 "type": "text", "default": "default"},
                {"id": "port", "label": "Listen port",
                 "type": "number", "default": 80,
                 "validation": {"min": 1, "max": 65535}},
                {"id": "server_name", "label": "Server name",
                 "type": "text", "default": "_"},
                {"id": "document_root", "label": "Document root",
                 "type": "path", "default": "/var/www/html"},
            ],
            "needs_sudo": True,
            "post_command": [
                "bash", "-c",
                "ln -sf /etc/nginx/sites-available/{site_name} "
                "/etc/nginx/sites-enabled/ && nginx -t && "
                "systemctl reload nginx",
            ],
            "condition": "has_systemd",
            "backup": True,
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["nginx", "-t"],
    },
}
