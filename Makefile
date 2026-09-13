.DEFAULT_GOAL := help

PYTHON ?= python3
TERRAFORM ?= terraform

.PHONY: help setup lint format format-check typecheck test quality terraform-fmt terraform-validate

help:
	@printf '%s\n' \
		'make setup               Install development dependencies' \
		'make quality             Run formatting, linting, typing, and tests' \
		'make format              Format Python code' \
		'make format-check        Check Python formatting' \
		'make lint                Check Python code' \
		'make typecheck           Run mypy' \
		'make test                Run tests' \
		'make terraform-fmt      Check Terraform formatting' \
		'make terraform-validate Validate Terraform roots when present'

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

format:
	ruff format .

lint:
	ruff check .

format-check:
	ruff format --check .

typecheck:
	mypy fraudlatch

test:
	pytest

quality: format-check lint typecheck test

terraform-fmt:
	@roots=$$(find infra/terraform -type f -name '*.tf' -exec dirname {} \; 2>/dev/null | sort -u); \
	if [ -z "$$roots" ]; then echo 'No Terraform roots found'; exit 0; fi; \
	$(TERRAFORM) fmt -check -recursive infra/terraform

terraform-validate:
	@roots=$$(find infra/terraform -type f -name '*.tf' -exec dirname {} \; 2>/dev/null | sort -u); \
	if [ -z "$$roots" ]; then echo 'No Terraform roots found'; exit 0; fi; \
	for root in $$roots; do \
		echo "Validating $$root"; \
		(cd "$$root" && $(TERRAFORM) init -backend=false -input=false && $(TERRAFORM) validate); \
	done
