# ── Backward-compatibility shim ─────────────────────────────────────
# Real implementation lives in src/core/services/vault/
# This file exists so old ``from src.core.services.vault import X``
# paths keep working.  New code should import from the package.
#
# NOTE: With the vault/ package directory present, Python already
# resolves ``from src.core.services.vault import ...`` to
# ``vault/__init__.py``.  This file is kept as documentation of
# the migration — Python will prefer the package over this file.
