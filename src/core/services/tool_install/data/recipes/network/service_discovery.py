"""
L0 Data — Service discovery & mesh tools.

Categories: service_discovery
Pure data, no logic.
"""

from __future__ import annotations


_SERVICE_DISCOVERY_RECIPES: dict[str, dict] = {

    "etcd": {
        "label": "etcd",
        "category": "service_discovery",
        "cli": "etcdctl",
        "install": {
            "apt": ["apt-get", "install", "-y", "etcd-client"],
            "brew": ["brew", "install", "etcd"],
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/etcd-io/etcd/releases/"
                    "latest/download/etcd-linux-amd64.tar.gz"
                    " | tar xz --strip-components=1 -C /usr/local/bin"
                    " etcdctl etcd",
                ],
            },
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "verify": ["etcdctl", "version"],
    },
    "linkerd": {
        "label": "Linkerd CLI",
        "category": "service_discovery",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSfL"
                " https://run.linkerd.io/install | sh",
            ],
            "brew": ["brew", "install", "linkerd"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.linkerd2/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.linkerd2/bin:$PATH" && linkerd version --client'],
    },
}
