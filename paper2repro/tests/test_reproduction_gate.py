from workflows.artifact_contract import ArtifactContract
from workflows.claim_contract import ClaimContract
from workflows.reproduction_gate import run_reproduction_gate


def test_reproduction_gate_times_out_hanging_demo(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text("while True:\n    pass\n", encoding="utf-8")
    contract = ArtifactContract(project_root=".", entrypoint="main.py", smoke_commands=["python main.py"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=1,
    )

    assert result["status"] == "error"
    assert any(check["status"] == "timeout" for check in result["checks"])


def test_reproduction_gate_runs_minimal_demo(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text(
        "import argparse\nparser=argparse.ArgumentParser(); parser.parse_args(); print('ok')\n",
        encoding="utf-8",
    )
    contract = ArtifactContract(project_root=".", entrypoint="main.py", smoke_commands=["python main.py --help"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=2,
    )

    assert result["status"] == "success"


def test_reproduction_gate_sets_pytest_plugin_autoload_disabled(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text(
        "import os\n"
        "assert os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1'\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    contract = ArtifactContract(project_root=".", entrypoint="main.py", smoke_commands=["python main.py"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=2,
    )

    assert result["status"] == "success"


def test_reproduction_gate_blocks_pytest_smoke_commands(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    contract = ArtifactContract(
        project_root=".",
        entrypoint="main.py",
        smoke_commands=["python -m pytest tests/ -v"],
    )

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=2,
    )

    assert result["status"] == "error"
    assert result["checks"][-1]["name"] == "smoke"
    assert "Blocked pytest" in result["checks"][-1]["stderr"]
