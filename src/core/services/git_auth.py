"""
BACKWARD COMPATIBILITY SHIM — imports have moved to ``src.core.services.git.auth``.

This file exists only so existing ``from src.core.services.git_auth import X``
statements continue to work.  New code should import from
``src.core.services.git.auth`` directly.
"""

from src.core.services.git.auth import (  # noqa: F401
    detect_remote_type,
    get_remote_url,
    find_ssh_key,
    key_has_passphrase,
    check_auth,
    add_ssh_key,
    add_https_credentials,
    git_env,
    is_auth_ok,
    is_auth_tested,
)
