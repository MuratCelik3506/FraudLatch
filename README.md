# FraudStream

FraudStream is a Terraform-first, event-driven fraud risk platform. It is designed to run locally with Docker and to be deployable to AWS without changing the application contract.

The repository is intentionally being built in small vertical slices. The current foundation contains the Python quality gates, local-development conventions, and CI contract. Application services, Terraform roots, and the BankSim replay pipeline will be added incrementally.

## Development

Requirements: Python 3.12+, Terraform, Docker, and Make.

```bash
cp .env.example .env
make setup
make quality
```

BankSim raw and processed data is excluded from Git. See `fraudstream_project_proposal.md` for the acquisition and preprocessing contract.

## Repository conventions

- All source code, documentation, issues, and pull requests are written in English.
- Secrets and licensed raw datasets never enter the repository.
- Terraform state and variable files containing values are local or remote-managed artifacts.
- Changes merge through pull requests after CI succeeds.

## Planned CI/CD boundary

Pull requests run Python quality checks, tests, Terraform formatting/validation, and Docker builds when images exist. AWS plans and applies are manual, environment-protected operations; CI will use short-lived AWS credentials through OIDC rather than static access keys.
