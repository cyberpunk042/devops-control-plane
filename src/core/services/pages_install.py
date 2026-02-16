"""
Pages install — SSE streaming for builder installation.

Handles installing page builders (pip, npm, Hugo binary) with
real-time SSE event streaming.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.core.services.pages_builders import get_builder


def install_builder_stream(name: str) -> dict | None:
    """Install a builder's dependencies, yielding SSE events.

    Args:
        name: Builder name (e.g. 'mkdocs', 'hugo', 'docusaurus').

    Returns:
        None if builder not found or no install command.
        Otherwise returns an iterator yielding SSE-formatted lines.
        Use ``{"error": ...}`` dict to signal pre-flight errors.
    """
    builder = get_builder(name)
    if builder is None:
        return {"ok": False, "error": f"Builder '{name}' not found"}

    info = builder.info()
    if not info.install_cmd:
        return {"ok": False, "error": f"Builder '{name}' has no auto-install command"}

    if builder.detect():
        return {"ok": True, "already_installed": True}

    # Return None to signal "use the generator"
    return None


def install_builder_events(name: str):
    """Generator that yields SSE events for builder installation.

    Caller must verify install_builder_stream() returned None first.
    """
    import os
    import platform
    import tarfile
    import tempfile
    import urllib.request

    builder = get_builder(name)
    info = builder.info()

    def _pip_install():
        cmd = list(info.install_cmd)
        cmd[0] = str(Path(sys.executable).parent / "pip")
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield {"type": "log", "line": line.rstrip()}
        proc.wait()

        if proc.returncode == 0:
            yield {"type": "done", "ok": True, "message": f"{info.label} installed in venv"}
        else:
            yield {"type": "done", "ok": False, "error": f"pip install failed (exit {proc.returncode})"}

    def _glibc_version() -> str:
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.gnu_get_libc_version.restype = ctypes.c_char_p
            return libc.gnu_get_libc_version().decode()
        except Exception:
            return "unknown"

    def _hugo_binary_install():
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)

        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        else:
            yield {"type": "done", "ok": False, "error": f"Unsupported arch: {machine}"}
            return

        system_name = platform.system().lower()
        if system_name != "linux":
            yield {"type": "done", "ok": False, "error": f"Hugo binary download only supports Linux, got {system_name}"}
            return

        yield {"type": "log", "line": f"Detecting latest Hugo release for linux/{arch}..."}

        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/gohugoio/hugo/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "devops-cp"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read().decode())

            version = release["tag_name"].lstrip("v")
            yield {"type": "log", "line": f"Latest version: {version}  (GLIBC: {_glibc_version()})"}

            candidates = [
                f"hugo_{version}_linux-{arch}.tar.gz",
                f"hugo_extended_{version}_linux-{arch}.tar.gz",
            ]
            dl_url = None
            tarball_name = None
            for candidate in candidates:
                for asset in release.get("assets", []):
                    if asset["name"] == candidate:
                        dl_url = asset["browser_download_url"]
                        tarball_name = candidate
                        break
                if dl_url:
                    break

            if not dl_url:
                yield {"type": "done", "ok": False, "error": f"Could not find release asset for linux/{arch}"}
                return

            yield {"type": "log", "line": f"Downloading {tarball_name}..."}

            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                urllib.request.urlretrieve(dl_url, tmp.name)
                tmp_path = tmp.name

            yield {"type": "log", "line": "Extracting..."}

            with tarfile.open(tmp_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name == "hugo" or member.name.endswith("/hugo"):
                        member.name = "hugo"
                        tar.extract(member, path=str(local_bin))
                        break

            os.unlink(tmp_path)

            hugo_path = local_bin / "hugo"
            hugo_path.chmod(0o755)

            path_dirs = os.environ.get("PATH", "").split(":")
            if str(local_bin) not in path_dirs:
                os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

            r = subprocess.run([str(hugo_path), "version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                yield {"type": "log", "line": r.stdout.strip()}
                yield {"type": "done", "ok": True, "message": f"Hugo {version} installed to {hugo_path}"}
            else:
                err_detail = (r.stderr or r.stdout or "unknown error").strip()
                yield {"type": "log", "line": f"Execution failed: {err_detail}"}
                yield {"type": "done", "ok": False, "error": f"Hugo binary failed: {err_detail}"}

        except Exception as e:
            yield {"type": "done", "ok": False, "error": f"Download failed: {e}"}

    def _npm_install():
        cmd = list(info.install_cmd)
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout:
            for line in proc.stdout:
                yield {"type": "log", "line": line.rstrip()}
        proc.wait()

        if proc.returncode == 0:
            yield {"type": "done", "ok": True, "message": f"{info.label} installed"}
        else:
            yield {"type": "done", "ok": False, "error": f"npm install failed (exit {proc.returncode})"}

    yield {"type": "log", "line": f"Installing {info.label}..."}

    cmd = info.install_cmd
    if cmd[0] == "pip":
        yield from _pip_install()
    elif cmd[0] == "__hugo_binary__":
        yield from _hugo_binary_install()
    elif cmd[0] in ("npm", "npx"):
        yield from _npm_install()
    else:
        cmd_str = ' '.join(cmd)
        yield {"type": "log", "line": f"▶ {cmd_str}"}
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            if proc.stdout:
                for line in proc.stdout:
                    yield {"type": "log", "line": line.rstrip()}
            proc.wait()
            ok = proc.returncode == 0
            if ok:
                yield {"type": "done", "ok": True, "message": f"{info.label} installed"}
            else:
                yield {"type": "done", "ok": False, "error": f"Install failed (exit {proc.returncode})"}
        except Exception as e:
            yield {"type": "done", "ok": False, "error": str(e)}
