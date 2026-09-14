# FraudLatch

FraudLatch is a Terraform-first, event-driven fraud risk platform. It is designed to run locally with Docker and to be deployable to AWS without changing the application contract.

The repository is intentionally being built in small vertical slices. The current foundation contains the Python quality gates, local-development conventions, and CI contract. Application services, Terraform roots, and the BankSim replay pipeline will be added incrementally.

The dependency-aware implementation roadmap and status board are maintained in [`milestones/0.md`](milestones/0.md).
The dated architecture and scope baseline is [`milestones/00-proposal.md`](milestones/00-proposal.md).

## Development

Requirements: Python 3.12+, Terraform, Docker, and Make.

```bash
cp .env.example .env
make setup
make quality
```

`make setup` creates a repository-local `.venv` and installs the project with
its development dependencies. The Make targets use that environment directly,
so activating a shell environment is optional and the system Python remains
unchanged.

## Make command contract

Run commands from the repository root. Service commands use `.venv` directly;
the Makefile loads `.env` when present. Copy `.env.example` to `.env` first and
provide a reachable PostgreSQL instance for `make api`. The API listens on
`127.0.0.1:8000`.

```text
make setup              Create the local virtual environment
make quality            Run format, lint, type checks, and tests
make format             Format Python code
make format-check       Check Python formatting
make lint               Run Ruff lint checks
make typecheck          Run mypy
make test               Run pytest
make terraform-fmt      Check Terraform formatting
make terraform-validate Validate available Terraform roots
make infra-init         Initialize local Terraform infrastructure
make infra-plan         Plan local Terraform infrastructure
make infra-up           Apply local Terraform infrastructure
make infra-down         Destroy local Terraform infrastructure
make data-check         Validate manually acquired BankSim data
make data-prepare       Prepare canonical BankSim data
make api                Run the API locally
make dispatcher         Run the outbox dispatcher locally
make worker             Run the risk worker locally
make replay             Replay canonical transactions locally
make docker-build       Build local release/demo images
```

`infra-down` is explicitly destructive and is never run automatically. The
infrastructure, data pipeline, dispatcher, worker, replay, and Docker image
commands fail with a milestone-specific message until their implementation is
available. The dispatcher is available once PostgreSQL and Redis are running;
the worker, replay, and Docker image commands remain milestone-gated. No
command downloads BankSim, creates cloud resources, or fetches credentials
automatically.

BankSim raw and processed data is excluded from Git. See [`milestones/00-proposal.md`](milestones/00-proposal.md), [`milestones/7.1.md`](milestones/7.1.md), and [`milestones/7.2.md`](milestones/7.2.md) for the acquisition and preprocessing contract.

## Dataset acquisition

The BankSim CSV is a manual local prerequisite because the dataset is licensed and must not be committed or downloaded by CI.

The command targets below are defined by Milestones 7.1–7.2 and become executable when those milestones are implemented.

1. Download the dataset from the [BankSim Kaggle page](https://www.kaggle.com/datasets/ealaxi/banksim1) and accept its `CC BY-NC-SA 4.0` terms for this non-commercial project.
2. If Kaggle provides an archive, extract it locally and place only `bs140513_032310.csv` at `data/raw/bs140513_032310.csv`.
3. Run `make data-check`.
4. Run `make data-prepare`.

Keep Kaggle credentials outside this repository. The validation command records the source hash and provenance metadata; it does not upload or fetch the raw file.

## Repository conventions

- All source code, documentation, issues, and pull requests are written in English.
- Secrets and licensed raw datasets never enter the repository.
- Terraform state and variable files containing values are local or remote-managed artifacts.
- Changes merge through pull requests after CI succeeds.

## Planned CI/CD boundary

Pull requests run Python quality checks, tests, Terraform formatting/validation, and Docker builds when images exist. AWS plans and applies are manual, environment-protected operations; CI will use short-lived AWS credentials through OIDC rather than static access keys.
