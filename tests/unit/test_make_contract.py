from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_makefile_exposes_the_documented_command_contract() -> None:
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    commands = (
        "setup",
        "quality",
        "format",
        "format-check",
        "lint",
        "typecheck",
        "test",
        "terraform-fmt",
        "terraform-validate",
        "infra-init",
        "infra-plan",
        "infra-up",
        "infra-down",
        "data-check",
        "data-prepare",
        "api",
        "dispatcher",
        "worker",
        "replay",
        "docker-build",
    )

    for command in commands:
        assert f"{command}:" in makefile
        assert f"make {command}" in readme


def test_makefile_keeps_future_commands_explicitly_unimplemented() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "-include .env" in makefile
    assert "export APP_ENV LOG_LEVEL DATABASE_URL REDIS_URL QUEUE_BACKEND" in makefile
    assert "does not fetch" not in makefile
    assert "scripts/prepare_banksim.py" in makefile
    assert "$(VENV_PYTHON) -m fraudlatch.dispatcher" in makefile
    assert "worker is not implemented yet" in makefile
    assert "scripts/replay_banksim.py" in makefile
