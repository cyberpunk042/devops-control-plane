# ADR-001: Python 3.12 with pyenv

**Status:** Accepted  
**Date:** 2026-02-10

## Context

The system Python on this machine is 3.8.10. The control plane requires
Python 3.11+ for modern type syntax, Pydantic v2, and structural pattern
matching.

## Decision

Use Python 3.12.8 via pyenv. The `.venv` is created from the pyenv-managed
Python, not the system Python.

## Consequences

- All contributors need either pyenv or a system Python >= 3.11
- The `manage.sh` script (MS-8) should detect and activate the correct Python
- CI uses `actions/setup-python` which handles this automatically
