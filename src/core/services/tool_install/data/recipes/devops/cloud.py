"""
L0 Data — Cloud & IaC tools.

Categories: cloud, iac, hashicorp
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_CLOUD_RECIPES: dict[str, dict] = {

    "terraform": {
        "cli": "terraform",
        "label": "Terraform (infrastructure as code)",
        "category": "iac",
        "install": {
            "apt": [
                "bash", "-c",
                "wget -O- https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o"
                " /usr/share/keyrings/hashicorp-archive-keyring.gpg"
                " && echo \"deb [arch=$(dpkg --print-architecture)"
                " signed-by=/usr/share/keyrings/"
                "hashicorp-archive-keyring.gpg]"
                " https://apt.releases.hashicorp.com"
                " $(lsb_release -cs) main\""
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update"
                " && sudo apt-get install -y terraform",
            ],
            "dnf": [
                "bash", "-c",
                "sudo dnf install -y dnf-plugins-core"
                " && sudo dnf config-manager addrepo"
                " --from-repofile="
                "https://rpm.releases.hashicorp.com/fedora/"
                "hashicorp.repo"
                " && sudo dnf -y install terraform",
            ],
            "pacman": ["pacman", "-S", "--noconfirm", "terraform"],
            "snap": ["snap", "install", "terraform", "--classic"],
            "brew": [
                "bash", "-c",
                "brew tap hashicorp/tap"
                " && brew install hashicorp/tap/terraform",
            ],
            "_default": [
                "bash", "-c",
                "TF_VERSION=$(curl -sSf"
                " https://checkpoint.hashicorp.com/v1/check/terraform"
                " | python3 -c"
                " \"import sys,json;"
                "print(json.load(sys.stdin)['current_version'])\")"
                " && curl -sSfL -o /tmp/terraform.zip"
                " \"https://releases.hashicorp.com/terraform/"
                "${TF_VERSION}/terraform_${TF_VERSION}"
                "_{os}_{arch}.zip\""
                " && sudo unzip -o /tmp/terraform.zip"
                " -d /usr/local/bin"
                " && rm /tmp/terraform.zip",
            ],
        },
        "needs_sudo": {
            "apt": True,
            "dnf": True,
            "pacman": True,
            "snap": True,
            "brew": False,
            "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl", "unzip"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
        "prefer": ["apt", "dnf", "pacman", "snap", "brew"],
        "verify": ["terraform", "--version"],
        "update": {
            "apt": [
                "bash", "-c",
                "sudo apt-get update"
                " && sudo apt-get install -y --only-upgrade terraform",
            ],
            "dnf": ["dnf", "upgrade", "-y", "terraform"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "terraform"],
            "snap": ["snap", "refresh", "terraform"],
            "brew": ["brew", "upgrade", "hashicorp/tap/terraform"],
            "_default": [
                "bash", "-c",
                "TF_VERSION=$(curl -sSf"
                " https://checkpoint.hashicorp.com/v1/check/terraform"
                " | python3 -c"
                " \"import sys,json;"
                "print(json.load(sys.stdin)['current_version'])\")"
                " && curl -sSfL -o /tmp/terraform.zip"
                " \"https://releases.hashicorp.com/terraform/"
                "${TF_VERSION}/terraform_${TF_VERSION}"
                "_{os}_{arch}.zip\""
                " && sudo unzip -o /tmp/terraform.zip"
                " -d /usr/local/bin"
                " && rm /tmp/terraform.zip",
            ],
        },
    },

    "aws-cli": {
        "cli": "aws",
        "label": "AWS CLI v2 (Amazon Web Services command-line interface)",
        "category": "cloud",
        # Written in Python but v2 ships as a self-contained installer.
        # Official installer is bundled zip with embedded Python — no pip deps.
        # brew formula: awscli. snap: aws-cli --classic.
        # pip has `awscli` but AWS discourages for v2 — use official installer.
        # NOT in apt (v1 only), dnf (v1 only), pacman, zypper.
        # apk has it in community repo but may lag versions.
        # _default uses $(uname -m) for runtime arch detection.
        # AWS URLs: awscli-exe-linux-x86_64.zip / awscli-exe-linux-aarch64.zip
        # uname -m outputs x86_64 or aarch64 — matches AWS naming exactly.
        "install": {
            "brew": ["brew", "install", "awscli"],
            "snap": ["snap", "install", "aws-cli", "--classic"],
            "_default": [
                "bash", "-c",
                'ARCH=$(uname -m) && '
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
        },
        "needs_sudo": {"brew": False, "snap": True, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["brew", "snap"],
        "verify": ["aws", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "awscli"],
            "snap": ["snap", "refresh", "aws-cli"],
            "_default": [
                "bash", "-c",
                'ARCH=$(uname -m) && '
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
        },
    },
    "gcloud": {
        "cli": "gcloud",
        "label": "Google Cloud SDK (gcloud CLI)",
        "category": "cloud",
        # Written in Python. Google provides official apt/dnf repos but
        # they require adding Google's signing key and repo — complex setup.
        # snap is simpler (google-cloud-cli --classic), brew works too.
        # _default installer pipes to bash — installs to $HOME.
        # NOT in apk, pacman, zypper.
        # apt/dnf methods omitted because they need repo setup (not simple apt install).
        "install": {
            "snap": ["snap", "install", "google-cloud-cli", "--classic"],
            "brew": ["brew", "install", "google-cloud-sdk"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://sdk.cloud.google.com | bash -s -- "
                "--disable-prompts --install-dir=$HOME",
            ],
        },
        "needs_sudo": {"snap": True, "brew": False, "_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/google-cloud-sdk/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/google-cloud-sdk/bin:$PATH" && gcloud --version'],
        "prefer": ["snap", "brew"],
        "update": {
            "snap": ["snap", "refresh", "google-cloud-cli"],
            "brew": ["brew", "upgrade", "google-cloud-sdk"],
            "_default": ["bash", "-c",
                         'export PATH="$HOME/google-cloud-sdk/bin:$PATH" '
                         '&& gcloud components update --quiet'],
        },
    },
    "az-cli": {
        "cli": "az",
        "label": "Azure CLI (Microsoft Azure command-line interface)",
        "category": "cloud",
        # Written in Python. `pip install azure-cli` is the cross-platform
        # method Microsoft recommends for any Linux/macOS.
        # brew formula: azure-cli.
        # Microsoft also has distro-specific repo setup scripts
        # (InstallAzureCLIDeb for Debian, RPM repo for Fedora, etc.)
        # but those require repo + key setup and are distro-locked.
        # pip is the true universal fallback — works everywhere Python runs.
        # NOT in snap, apk, pacman.
        "install": {
            "brew": ["brew", "install", "azure-cli"],
            "_default": _PIP + ["install", "azure-cli"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "pip"},
        "prefer": ["brew"],
        "verify": ["az", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "azure-cli"],
            "_default": _PIP + ["install", "--upgrade", "azure-cli"],
        },
    },

    "ansible": {
        "cli": "ansible",
        "label": "Ansible (configuration management & automation)",
        "category": "iac",
        "install": {
            "_default": _PIP + ["install", "ansible"],
            "apt": ["apt-get", "install", "-y", "ansible"],
            "dnf": ["dnf", "install", "-y", "ansible"],
            "apk": ["apk", "add", "ansible"],
            "pacman": ["pacman", "-S", "--noconfirm", "ansible"],
            "zypper": ["zypper", "install", "-y", "ansible"],
            "brew": ["brew", "install", "ansible"],
        },
        "needs_sudo": {
            "_default": False, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "zypper": True,
            "brew": False,
        },
        "install_via": {"_default": "pip"},
        "requires": {"binaries": ["python3"]},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["ansible", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "ansible"],
            "apt": [
                "bash", "-c",
                "sudo apt-get update"
                " && sudo apt-get install -y --only-upgrade ansible",
            ],
            "dnf": ["dnf", "upgrade", "-y", "ansible"],
            "apk": ["apk", "upgrade", "ansible"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "ansible"],
            "zypper": ["zypper", "update", "-y", "ansible"],
            "brew": ["brew", "upgrade", "ansible"],
        },
    },

    "pulumi": {
        "cli": "pulumi",
        "label": "Pulumi (infrastructure as code SDK)",
        "category": "iac",
        # Written in Go. IaC using real programming languages (Python, TS, Go, etc.).
        # brew: pulumi. Official installer: get.pulumi.com — auto-detects arch.
        # Installs to $HOME/.pulumi/bin — NO sudo needed.
        # NOT in apt, dnf, apk, pacman (official), zypper, snap.
        # AUR has pulumi-bin but that's yay, not pacman -S.
        # Verify: `pulumi version` (NOT --version).
        "install": {
            "brew": ["brew", "install", "pulumi"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pulumi.com | sh",
            ],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.pulumi/bin:$PATH"',
        "prefer": ["brew"],
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.pulumi/bin:$PATH" && pulumi version'],
        "update": {
            "brew": ["brew", "upgrade", "pulumi"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pulumi.com | sh",
            ],
        },
    },
    "cdktf": {
        "cli": "cdktf",
        "label": "CDK for Terraform (infrastructure as code with programming languages)",
        "category": "iac",
        # Written in TypeScript. By HashiCorp.
        # ⚠️  DEPRECATED by HashiCorp — archived December 10, 2025.
        # npm: cdktf-cli (global install). brew: cdktf.
        # Requires terraform CLI (>= 1.2.0) and Node.js at runtime.
        # NOT in apt, dnf, apk, pacman, zypper, snap.
        "install": {
            "brew": ["brew", "install", "cdktf"],
            "_default": ["npm", "install", "-g", "cdktf-cli"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["brew"],
        "verify": ["cdktf", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "cdktf"],
            "_default": ["npm", "update", "-g", "cdktf-cli"],
        },
    },

    "vault": {
        "label": "HashiCorp Vault",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y vault",
            ],
            "brew": ["brew", "install", "vault"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["vault", "--version"],
    },
    "consul": {
        "label": "HashiCorp Consul",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y consul",
            ],
            "brew": ["brew", "install", "consul"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["consul", "--version"],
    },
    "nomad": {
        "label": "HashiCorp Nomad",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y nomad",
            ],
            "brew": ["brew", "install", "nomad"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["nomad", "--version"],
    },
    "boundary": {
        "label": "HashiCorp Boundary",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y boundary",
            ],
            "brew": ["brew", "install", "boundary"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "verify": ["boundary", "version"],
    },

    "doctl": {
        "label": "DigitalOcean CLI",
        "category": "cloud",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSL https://github.com/digitalocean/doctl/releases/"
                    "latest/download/doctl-linux-amd64.tar.gz"
                    " | tar xz -C /usr/local/bin",
                ],
            },
            "brew": ["brew", "install", "doctl"],
            "snap": ["snap", "install", "doctl"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["doctl", "version"],
    },
    "linode-cli": {
        "label": "Linode CLI",
        "category": "cloud",
        "install": {
            "_default": _PIP + ["install", "linode-cli"],
            "brew": ["brew", "install", "linode-cli"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "pip"},
        "verify": ["linode-cli", "--version"],
    },
    "flyctl": {
        "label": "Fly.io CLI",
        "category": "cloud",
        "cli": "fly",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -L https://fly.io/install.sh | sh",
            ],
            "brew": ["brew", "install", "flyctl"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.fly/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.fly/bin:$PATH" && fly version'],
    },
    "wrangler": {
        "label": "Wrangler (Cloudflare Workers)",
        "category": "cloud",
        "install": {
            "_default": ["npm", "install", "-g", "wrangler"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["wrangler", "--version"],
        "update": {"_default": ["npm", "update", "-g", "wrangler"]},
    },
    "vercel": {
        "label": "Vercel CLI",
        "category": "cloud",
        "install": {
            "_default": ["npm", "install", "-g", "vercel"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["vercel", "--version"],
        "update": {"_default": ["npm", "update", "-g", "vercel"]},
    },
    "netlify-cli": {
        "label": "Netlify CLI",
        "category": "cloud",
        "cli": "netlify",
        "install": {
            "_default": ["npm", "install", "-g", "netlify-cli"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["netlify", "--version"],
        "update": {"_default": ["npm", "update", "-g", "netlify-cli"]},
    },
}
