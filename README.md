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
