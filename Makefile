.DEFAULT_GOAL := help

PYTHON ?= python3
TERRAFORM ?= terraform
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_RUFF := $(VENV)/bin/ruff
VENV_MYPY := $(VENV)/bin/mypy
VENV_PYTEST := $(VENV)/bin/pytest

-include .env
export APP_ENV LOG_LEVEL DATABASE_URL REDIS_URL QUEUE_BACKEND

.PHONY: help setup lint format format-check typecheck test quality \
	terraform-fmt terraform-validate infra-init infra-plan infra-up infra-down \
	data-check data-prepare api dispatcher worker replay docker-build

INFRA_ROOT := infra/terraform/local
DATASET := data/raw/bs140513_032310.csv

define require_target_file
	@if [ ! -e "$(1)" ]; then \
		echo "error: $(2)" >&2; \
		exit 1; \
	fi
endef

define require_env
	@if [ -z "$(value $(1))" ]; then \
		echo "error: $(1) must be set; copy .env.example to .env or export it" >&2; \
		exit 1; \
	fi
endef

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
		'make terraform-validate Validate Terraform roots when present' \
		'make infra-init         Initialize local Terraform infrastructure' \
		'make infra-plan         Plan local Terraform infrastructure' \
		'make infra-up           Start local Terraform infrastructure' \
		'make infra-down         Stop local Terraform infrastructure' \
		'make data-check         Validate the manually acquired BankSim file' \
		'make data-prepare       Prepare canonical BankSim data' \
		'make api                Run the API locally' \
		'make dispatcher         Run the outbox dispatcher locally' \
		'make worker             Run the risk worker locally' \
		'make replay             Replay canonical transactions locally' \
		'make docker-build       Build local release/demo images'

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

infra-init:
	$(call require_target_file,$(INFRA_ROOT),local Terraform root is not implemented yet; see Milestone 9.1)
	$(TERRAFORM) -chdir=$(INFRA_ROOT) init -input=false

infra-plan:
	$(call require_target_file,$(INFRA_ROOT),local Terraform root is not implemented yet; see Milestone 9.1)
	$(TERRAFORM) -chdir=$(INFRA_ROOT) plan -input=false

infra-up:
	$(call require_target_file,$(INFRA_ROOT),local Terraform root is not implemented yet; see Milestone 9.1)
	$(TERRAFORM) -chdir=$(INFRA_ROOT) apply -input=false

infra-down:
	$(call require_target_file,$(INFRA_ROOT),local Terraform root is not implemented yet; see Milestone 9.1)
	$(TERRAFORM) -chdir=$(INFRA_ROOT) destroy -input=false

data-check:
	$(call require_target_file,$(DATASET),$(DATASET) is missing; acquire BankSim manually before running this command)
	@echo "error: dataset validation is not implemented yet; see Milestone 7.1" >&2
	@exit 1

data-prepare:
	@echo "error: data preparation is not implemented yet; see Milestone 7.2" >&2
	@exit 1

api:
	$(call require_env,DATABASE_URL)
	$(VENV_PYTHON) -m uvicorn fraudlatch.api.app:create_app --factory --host 127.0.0.1 --port 8000

dispatcher:
	$(call require_env,DATABASE_URL)
	$(call require_env,REDIS_URL)
	@echo "error: dispatcher is not implemented yet; see Milestone 3.2" >&2
	@exit 1

worker:
	$(call require_env,DATABASE_URL)
	$(call require_env,REDIS_URL)
	@echo "error: worker is not implemented yet; see Milestone 6.1" >&2
	@exit 1

replay:
	$(call require_env,DATABASE_URL)
	$(call require_env,REDIS_URL)
	@echo "error: replay is not implemented yet; see Milestone 7.3" >&2
	@exit 1

docker-build:
	$(call require_target_file,Dockerfile,Dockerfile is not present; image packaging belongs to Milestone 9.4)
	@echo "error: Docker image build configuration is not implemented yet; see Milestone 9.4" >&2
	@exit 1
