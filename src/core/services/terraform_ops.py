"""Terraform operations — backward-compat re-export hub.

All implementation has moved to ``src.core.services.terraform/``.
This file re-exports everything so existing ``from src.core.services.terraform_ops import X``
continues to work.
"""

from src.core.services.terraform import *  # noqa: F401, F403
