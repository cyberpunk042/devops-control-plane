"""
L0 Data — Media, docs & messaging tools.

Categories: media, docs, messaging, logging, api, protobuf
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_MEDIA_DOCS_RECIPES: dict[str, dict] = {
    "ffmpeg": {
        "label": "FFmpeg",
        "category": "media",
        "install": {
            "apt":    ["apt-get", "install", "-y", "ffmpeg"],
            "dnf":    ["dnf", "install", "-y", "ffmpeg-free"],
            "apk":    ["apk", "add", "ffmpeg"],
            "pacman": ["pacman", "-S", "--noconfirm", "ffmpeg"],
            "zypper": ["zypper", "install", "-y", "ffmpeg"],
            "brew":   ["brew", "install", "ffmpeg"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["ffmpeg", "-version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "ffmpeg"],
            "dnf":    ["dnf", "upgrade", "-y", "ffmpeg-free"],
            "apk":    ["apk", "upgrade", "ffmpeg"],
            "pacman": ["pacman", "-S", "--noconfirm", "ffmpeg"],
            "zypper": ["zypper", "update", "-y", "ffmpeg"],
            "brew":   ["brew", "upgrade", "ffmpeg"],
        },
    },

    "rabbitmqctl": {
        "label": "RabbitMQ tools",
        "category": "messaging",
        "cli": "rabbitmqctl",
        "install": {
            "apt": ["apt-get", "install", "-y", "rabbitmq-server"],
            "dnf": ["dnf", "install", "-y", "rabbitmq-server"],
            "brew": ["brew", "install", "rabbitmq"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["rabbitmqctl", "version"],
    },
    "nats-cli": {
        "label": "NATS CLI",
        "category": "messaging",
        "cli": "nats",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/nats-io/"
                "natscli/main/install.sh | sh",
            ],
            "brew": ["brew", "install", "nats-io/nats-tools/nats"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["nats", "--version"],
    },
    "kafkacat": {
        "label": "kcat (Kafka CLI)",
        "category": "messaging",
        "cli": "kcat",
        "install": {
            "apt": ["apt-get", "install", "-y", "kafkacat"],
            "dnf": ["dnf", "install", "-y", "kafkacat"],
            "brew": ["brew", "install", "kcat"],
            "_default": [
                "bash", "-c",
                "git clone https://github.com/edenhill/kcat.git /tmp/kcat"
                " && cd /tmp/kcat && ./configure && make"
                " && sudo make install && rm -rf /tmp/kcat",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": True},
        "verify": ["kcat", "-V"],
    },

    "sphinx": {
        "label": "Sphinx (Python docs)",
        "category": "docs",
        "cli": "sphinx-build",
        "install": {"_default": _PIP + ["install", "sphinx"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["sphinx-build", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "sphinx"]},
    },
    "mdbook": {
        "label": "mdBook (Rust doc generator)",
        "category": "docs",
        "install": {
            "_default": ["cargo", "install", "mdbook"],
            "brew": ["brew", "install", "mdbook"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "cargo"},
        "verify": ["mdbook", "--version"],
    },
    "asciidoctor": {
        "label": "Asciidoctor",
        "category": "docs",
        "install": {
            "apt": ["apt-get", "install", "-y", "asciidoctor"],
            "dnf": ["dnf", "install", "-y", "rubygem-asciidoctor"],
            "brew": ["brew", "install", "asciidoctor"],
            "_default": ["gem", "install", "asciidoctor"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": False},
        "install_via": {"_default": "gem"},
        "verify": ["asciidoctor", "--version"],
    },

    "protoc": {
        "label": "Protocol Buffers compiler",
        "category": "protobuf",
        "install": {
            "apt": ["apt-get", "install", "-y", "protobuf-compiler"],
            "dnf": ["dnf", "install", "-y", "protobuf-compiler"],
            "apk": ["apk", "add", "protobuf"],
            "pacman": ["pacman", "-S", "--noconfirm", "protobuf"],
            "zypper": ["zypper", "install", "-y", "protobuf-devel"],
            "brew": ["brew", "install", "protobuf"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["protoc", "--version"],
    },
    "grpcurl": {
        "label": "grpcurl (gRPC CLI)",
        "category": "protobuf",
        "install": {
            "_default": ["go", "install",
                         "github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"],
            "brew": ["brew", "install", "grpcurl"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "go"},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && grpcurl --version'],
    },
    "buf": {
        "label": "Buf (protobuf tooling)",
        "category": "protobuf",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSL https://github.com/bufbuild/buf/releases/latest/"
                    "download/buf-Linux-x86_64"
                    " -o /usr/local/bin/buf && chmod +x /usr/local/bin/buf",
                ],
            },
            "brew": ["brew", "install", "bufbuild/buf/buf"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["buf", "--version"],
    },

    "postman-cli": {
        "label": "Postman CLI (newman)",
        "category": "api",
        "cli": "newman",
        "install": {
            "_default": ["npm", "install", "-g", "newman"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["newman", "--version"],
        "update": {"_default": ["npm", "update", "-g", "newman"]},
    },
    "insomnia-cli": {
        "label": "Inso CLI (Insomnia)",
        "category": "api",
        "cli": "inso",
        "install": {
            "_default": ["npm", "install", "-g", "insomnia-inso"],
            "brew": ["brew", "install", "inso"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["inso", "--version"],
    },
    "swagger-cli": {
        "label": "Swagger CLI",
        "category": "api",
        "cli": "swagger-cli",
        "install": {
            "_default": ["npm", "install", "-g", "@apidevtools/swagger-cli"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["swagger-cli", "--version"],
    },
    "openapi-generator": {
        "label": "OpenAPI Generator CLI",
        "category": "api",
        "install": {
            "_default": ["npm", "install", "-g",
                         "@openapitools/openapi-generator-cli"],
            "brew": ["brew", "install", "openapi-generator"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "cli": "openapi-generator-cli",
        "verify": ["openapi-generator-cli", "version"],
    },

    "vector": {
        "label": "Vector (log pipeline)",
        "category": "logging",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSfL"
                " https://sh.vector.dev | bash -s -- -y",
            ],
            "brew": ["brew", "install", "vectordotdev/brew/vector"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["vector", "--version"],
    },
    "fluentbit": {
        "label": "Fluent Bit",
        "category": "logging",
        "cli": "fluent-bit",
        "install": {
            "apt": ["apt-get", "install", "-y", "fluent-bit"],
            "dnf": ["dnf", "install", "-y", "fluent-bit"],
            "brew": ["brew", "install", "fluent-bit"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["fluent-bit", "--version"],
    },
    "stern-log": {
        "label": "stern (K8s multi-pod log tailing)",
        "category": "logging",
        "cli": "stern",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/stern/stern/releases/"
                    "latest/download/stern_linux_amd64.tar.gz"
                    " | tar xz -C /usr/local/bin stern",
                ],
            },
            "brew": ["brew", "install", "stern"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["stern", "--version"],
    },

    "imagemagick": {
        "label": "ImageMagick",
        "category": "media",
        "cli": "magick",
        "install": {
            "apt": ["apt-get", "install", "-y", "imagemagick"],
            "dnf": ["dnf", "install", "-y", "ImageMagick"],
            "apk": ["apk", "add", "imagemagick"],
            "pacman": ["pacman", "-S", "--noconfirm", "imagemagick"],
            "zypper": ["zypper", "install", "-y", "ImageMagick"],
            "brew": ["brew", "install", "imagemagick"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["magick", "--version"],
    },
    "gifsicle": {
        "label": "Gifsicle (GIF optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "gifsicle"],
            "dnf": ["dnf", "install", "-y", "gifsicle"],
            "brew": ["brew", "install", "gifsicle"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["gifsicle", "--version"],
    },
    "jpegoptim": {
        "label": "jpegoptim (JPEG optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "jpegoptim"],
            "dnf": ["dnf", "install", "-y", "jpegoptim"],
            "apk": ["apk", "add", "jpegoptim"],
            "pacman": ["pacman", "-S", "--noconfirm", "jpegoptim"],
            "brew": ["brew", "install", "jpegoptim"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["jpegoptim", "--version"],
    },
    "optipng": {
        "label": "OptiPNG (PNG optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "optipng"],
            "dnf": ["dnf", "install", "-y", "optipng"],
            "apk": ["apk", "add", "optipng"],
            "pacman": ["pacman", "-S", "--noconfirm", "optipng"],
            "zypper": ["zypper", "install", "-y", "optipng"],
            "brew": ["brew", "install", "optipng"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["optipng", "--version"],
    },
    "svgo": {
        "label": "SVGO (SVG optimizer)",
        "category": "media",
        "install": {
            "_default": ["npm", "install", "-g", "svgo"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["svgo", "--version"],
    },
}
