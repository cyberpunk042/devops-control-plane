"""
L0 Data — Data pack recipes.

Categories: data_pack
Pure data, no logic.
"""

from __future__ import annotations


_DATA_PACKS_RECIPES: dict[str, dict] = {
    #
    # Spec: domain-data-packs §Recipes.
    # These produce `type: "download"` steps with disk check,
    # resume, checksums, and freshness tracking.

    "trivy-db": {
        "type": "data_pack",
        "label": "Trivy Vulnerability DB",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-trivy-db",
                "type": "download",
                "label": "Download Trivy vulnerability database",
                "url": "https://github.com/aquasecurity/trivy-db/releases/"
                       "latest/download/db.tar.gz",
                "dest": "~/.cache/trivy/db/trivy.db",
                "size_bytes": 150_000_000,
                "freshness_days": 7,
            },
        ],
        "requires": {
            "binaries": ["trivy"],
        },
    },
    "geoip-db": {
        "type": "data_pack",
        "label": "MaxMind GeoIP Database",
        "category": "data_pack",
        "risk": "low",
        "inputs": [
            {
                "id": "license_key",
                "label": "MaxMind License Key",
                "type": "password",
                "required": True,
                "help_text": "Get a free key from https://www.maxmind.com",
            },
        ],
        "steps": [
            {
                "id": "download-geoip",
                "type": "download",
                "label": "Download GeoLite2 City database",
                "url": "https://download.maxmind.com/app/geoip_download"
                       "?edition_id=GeoLite2-City&license_key="
                       "{license_key}&suffix=tar.gz",
                "dest": "~/.local/share/GeoIP/GeoLite2-City.mmdb",
                "freshness_days": 30,
            },
        ],
    },
    "wordlists": {
        "type": "data_pack",
        "label": "Security Wordlists (rockyou)",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-rockyou",
                "type": "download",
                "label": "Download rockyou.txt wordlist",
                "url": "https://github.com/brannondorsey/naive-hashcat/"
                       "releases/download/data/rockyou.txt",
                "dest": "~/.local/share/wordlists/rockyou.txt",
                "size_bytes": 139_921_497,
            },
        ],
    },
    "spacy-en": {
        "type": "data_pack",
        "label": "spaCy English Model",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-spacy-en",
                "type": "post_install",
                "label": "Download spaCy English NLP model",
                "command": [
                    "python3", "-m", "spacy", "download", "en_core_web_sm",
                ],
            },
        ],
        "requires": {
            "binaries": ["python3"],
        },
    },
    "hf-model": {
        "type": "data_pack",
        "label": "HuggingFace Model (gated)",
        "category": "data_pack",
        "risk": "low",
        "inputs": [
            {
                "id": "model_id",
                "label": "Model ID",
                "type": "text",
                "default": "meta-llama/Llama-2-7b-hf",
                "required": True,
            },
            {
                "id": "hf_token",
                "label": "HuggingFace Token",
                "type": "password",
                "required": True,
                "help_text": "Get a token from https://huggingface.co/settings/tokens",
            },
        ],
        "steps": [
            {
                "id": "download-hf-model",
                "type": "post_install",
                "label": "Download HuggingFace model",
                "command": [
                    "python3", "-c",
                    "from huggingface_hub import snapshot_download; "
                    "snapshot_download('{model_id}', token='{hf_token}')",
                ],
            },
        ],
        "requires": {
            "binaries": ["python3"],
            "network": ["https://huggingface.co"],
        },
    },
}
