# Security policy

Please do not report security vulnerabilities in public issues. Use a private security advisory or contact the repository maintainer directly.

Never commit credentials, `.env` files, Terraform state, or raw BankSim data. CI is expected to use short-lived AWS credentials through GitHub Actions OIDC.
