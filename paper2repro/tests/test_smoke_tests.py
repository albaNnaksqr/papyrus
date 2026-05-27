from workflows.artifact_contract import ArtifactContract
from workflows.smoke_tests import run_smoke_checks


def test_smoke_checks_compile_python_project(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            smoke_commands=[],
        ),
        timeout_seconds=10,
    )

    assert result["status"] == "success"
    assert result["checks"][0]["name"] == "compileall"


def test_smoke_checks_fail_on_syntax_error(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("def broken(:\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
        timeout_seconds=10,
    )

    assert result["status"] == "error"


def test_smoke_checks_run_contract_commands_after_compile(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text(
        "import argparse\n"
        "\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.parse_args()\n",
        encoding="utf-8",
    )

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            smoke_commands=["python src/main.py --help"],
        ),
        timeout_seconds=10,
    )

    assert result["status"] == "success"
    assert [check["name"] for check in result["checks"]] == [
        "compileall",
        "contract_smoke_command",
    ]


def test_smoke_checks_return_error_for_missing_code_directory(tmp_path):
    result = run_smoke_checks(
        str(tmp_path / "missing"),
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
        timeout_seconds=10,
    )

    assert result["status"] == "error"
    assert result["checks"][0]["name"] == "code_directory"


def test_smoke_checks_return_error_for_missing_smoke_executable(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            smoke_commands=["definitely-not-a-real-command-xyz"],
        ),
        timeout_seconds=10,
    )

    assert result["status"] == "error"
    assert result["checks"][-1]["name"] == "contract_smoke_command"


def test_smoke_checks_block_pytest_smoke_commands(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            smoke_commands=["python -m pytest tests/ -v"],
        ),
        timeout_seconds=10,
    )

    assert result["status"] == "error"
    assert result["checks"][-1]["status"] == "error"
    assert "Blocked pytest" in result["checks"][-1]["stderr"]
