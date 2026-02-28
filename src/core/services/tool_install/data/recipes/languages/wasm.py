"""
L0 Data — WebAssembly tools.

Categories: wasm
Pure data, no logic.
"""

from __future__ import annotations


_WASM_RECIPES: dict[str, dict] = {

    "wasmtime": {
        "label": "Wasmtime (Wasm runtime)",
        "category": "wasm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://wasmtime.dev/install.sh -sSf | bash",
            ],
            "brew": ["brew", "install", "wasmtime"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.wasmtime/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.wasmtime/bin:$PATH" && wasmtime --version'],
    },
    "wasmer": {
        "label": "Wasmer (Wasm runtime)",
        "category": "wasm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://get.wasmer.io -sSfL | sh",
            ],
            "brew": ["brew", "install", "wasmer"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.wasmer/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.wasmer/bin:$PATH" && wasmer --version'],
    },
    "wasm-pack": {
        "label": "wasm-pack (Rust → Wasm)",
        "category": "wasm",
        "install": {
            "_default": ["cargo", "install", "wasm-pack"],
            "brew": ["brew", "install", "wasm-pack"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "cargo"},
        "requires": {"binaries": ["cargo"]},
        "verify": ["wasm-pack", "--version"],
    },
}
