.DEFAULT_GOAL := help

PYTHON ?= python3
TERRAFORM ?= terraform
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_RUFF := $(VENV)/bin/ruff
VENV_MYPY := $(VENV)/bin/mypy
VENV_PYTEST := $(VENV)/bin/pytest

.PHONY: help setup lint format format-check typecheck test quality terraform-fmt terraform-validate

help:
	@printf '%s\n' \
		'make setup               Create .venv and install development dependencies' \
		'make quality             Run formatting, linting, typing, and tests' \
		'make format              Format Python code' \
		'make format-check        Check Python formatting' \
		'make lint                Check Python code' \
		'make typecheck           Run mypy' \
		'make test                Run tests' \
		'make terraform-fmt      Check Terraform formatting' \
		'make terraform-validate Validate Terraform roots when present'

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e '.[dev]'

format:
	$(VENV_RUFF) format .

lint:
	$(VENV_RUFF) check .

format-check:
	$(VENV_RUFF) format --check .

typecheck:
	$(VENV_MYPY) fraudlatch

test:
	$(VENV_PYTEST)

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
