.PHONY: help install lint format test types check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install package in editable mode with dev deps
	pip install -e ".[dev]"

lint: ## Run ruff linter
	ruff check src/ tests/

format: ## Run ruff formatter
	ruff format src/ tests/

test: ## Run tests with pytest
	pytest

test-cov: ## Run tests with coverage report
	pytest --cov=src --cov-report=term-missing

types: ## Run mypy type checker
	mypy src/

check: lint types test ## Run all checks (lint + types + test)
	@echo ""
	@echo "  ✅ All checks passed"
	@echo ""

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
