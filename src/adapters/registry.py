"""
Adapter registry — central dispatch for all adapter operations.

The registry is the single point of adapter management. It handles
registration, lookup, mock mode, and action execution. The engine
never talks to adapters directly — always through the registry.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Action, Receipt
from src.core.reliability.circuit_breaker import CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Central registry and dispatcher for adapters.

    Features:
        - Register/unregister adapters by name
        - Mock mode: swap all adapters for a mock that always succeeds
        - Execute actions through the appropriate adapter
        - Query adapter availability
    """

    def __init__(
        self,
        mock_mode: bool = False,
        circuit_breakers: CircuitBreakerRegistry | None = None,
    ):
        self._adapters: dict[str, Adapter] = {}
        self._mock_mode = mock_mode
        self._mock_adapter: Adapter | None = None
        self._circuit_breakers = circuit_breakers

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def set_mock_mode(self, enabled: bool, mock_adapter: Adapter | None = None) -> None:
        """Enable or disable mock mode.

        Args:
            enabled: Whether to use mock mode.
            mock_adapter: Optional custom mock adapter. If None, uses default.
        """
        self._mock_mode = enabled
        self._mock_adapter = mock_adapter

    def register(self, adapter: Adapter) -> None:
        """Register an adapter.

        Args:
            adapter: The adapter instance to register.
        """
        name = adapter.name
        if name in self._adapters:
            logger.warning("Overwriting existing adapter: %s", name)
        self._adapters[name] = adapter
        logger.debug("Registered adapter: %s", name)

    def unregister(self, name: str) -> None:
        """Remove an adapter from the registry."""
        self._adapters.pop(name, None)

    def get(self, name: str) -> Adapter | None:
        """Look up an adapter by name."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())

    def adapter_status(self) -> dict[str, dict[str, Any]]:
        """Get availability status of all registered adapters."""
        status = {}
        for name, adapter in self._adapters.items():
            try:
                available = adapter.is_available()
            except Exception:
                available = False
            status[name] = {
                "name": name,
                "available": available,
                "type": adapter.__class__.__name__,
            }
        return status

    def execute_action(
        self,
        action: Action,
        project_root: str = ".",
        environment: str = "dev",
        module_path: str | None = None,
        dry_run: bool = False,
    ) -> Receipt:
        """Execute an action through the appropriate adapter.

        This is the main dispatch method. It:
        1. Resolves the adapter (or mock)
        2. Builds the execution context
        3. Validates the action
        4. Executes (or dry-runs)
        5. Returns a Receipt (never raises)

        Args:
            action: The action to execute.
            project_root: Project root directory.
            environment: Target environment name.
            module_path: Module path (relative to project root).
            dry_run: If True, validate but don't execute.

        Returns:
            Receipt with execution results.
        """
        start_time = time.monotonic()

        context = ExecutionContext(
            action=action,
            project_root=project_root,
            environment=environment,
            module_path=module_path,
            dry_run=dry_run,
            params=action.params,
        )

        # Resolve adapter
        adapter: Adapter | None = None
        if self._mock_mode and self._mock_adapter:
            adapter = self._mock_adapter
        elif self._mock_mode:
            # Default mock behavior: return success
            return Receipt.success(
                adapter=action.adapter,
                action_id=action.id,
                output=f"[mock] {action.adapter}:{action.id} executed",
                metadata={"mock": True, "dry_run": dry_run},
            )
        else:
            adapter = self._adapters.get(action.adapter)

        if adapter is None:
            return Receipt.failure(
                adapter=action.adapter,
                action_id=action.id,
                error=f"No adapter registered for '{action.adapter}'",
            )

        # Validate
        try:
            is_valid, error_msg = adapter.validate(context)
            if not is_valid:
                return Receipt.failure(
                    adapter=action.adapter,
                    action_id=action.id,
                    error=f"Validation failed: {error_msg}",
                )
        except Exception as e:
            return Receipt.failure(
                adapter=action.adapter,
                action_id=action.id,
                error=f"Validation error: {e}",
            )

        # Dry run — validated but not executed
        if dry_run:
            return Receipt.skip(
                adapter=action.adapter,
                action_id=action.id,
                reason=f"[dry-run] Would execute {action.adapter}:{action.id}",
                metadata={"dry_run": True},
            )

        # ── Circuit breaker check ────────────────────────────────
        if self._circuit_breakers and not dry_run:
            cb = self._circuit_breakers.get_or_create(action.adapter)
            if not cb.allow_request():
                return Receipt.failure(
                    adapter=action.adapter,
                    action_id=action.id,
                    error=f"Circuit breaker OPEN for adapter '{action.adapter}'",
                    metadata={"circuit_state": cb.state.value},
                )

        # Execute
        try:
            receipt = adapter.execute(context)
        except Exception as e:
            # Adapters should never raise, but defense in depth
            logger.error("Adapter %s raised during execution: %s", action.adapter, e)
            receipt = Receipt.failure(
                adapter=action.adapter,
                action_id=action.id,
                error=f"Unexpected error: {e}",
            )

        # ── Circuit breaker record ───────────────────────────────
        if self._circuit_breakers:
            cb = self._circuit_breakers.get_or_create(action.adapter)
            if receipt.ok:
                cb.record_success()
            elif receipt.failed:
                cb.record_failure()

        # Add timing
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        receipt.duration_ms = elapsed_ms

        return receipt
