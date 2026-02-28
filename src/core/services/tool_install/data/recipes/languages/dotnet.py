"""
L0 Data — .NET ecosystem tools.

Categories: dotnet
Pure data, no logic.
"""

from __future__ import annotations


_DOTNET_RECIPES: dict[str, dict] = {

    "dotnet-sdk": {
        "label": ".NET SDK",
        "category": "dotnet",
        "cli": "dotnet",
        "install": {
            "apt": ["apt-get", "install", "-y", "dotnet-sdk-8.0"],
            "dnf": ["dnf", "install", "-y", "dotnet-sdk-8.0"],
            "brew": ["brew", "install", "dotnet"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://dot.net/v1/dotnet-install.sh | bash",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "verify": ["dotnet", "--version"],
    },
    "omnisharp": {
        "label": "OmniSharp (C# language server)",
        "category": "dotnet",
        "install": {
            "_default": ["dotnet", "tool", "install", "-g", "csharp-ls"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["dotnet"]},
        "cli": "csharp-ls",
        "verify": ["csharp-ls", "--version"],
    },
    "nuget": {
        "label": "NuGet CLI",
        "category": "dotnet",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL -o /usr/local/bin/nuget.exe"
                " https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"
                " && chmod +x /usr/local/bin/nuget.exe",
            ],
            "brew": ["brew", "install", "nuget"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["nuget", "help"],
        "cli": "nuget",
    },
    "dotnet-ef": {
        "label": "Entity Framework CLI",
        "category": "dotnet",
        "install": {
            "_default": ["dotnet", "tool", "install", "-g", "dotnet-ef"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["dotnet"]},
        "verify": ["dotnet", "ef", "--version"],
        "cli": "dotnet",
    },
}
