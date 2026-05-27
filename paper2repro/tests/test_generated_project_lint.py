from workflows.claim_contract import ClaimContract, ClaimRequirement
from workflows.generated_project_lint import lint_generated_project


def test_lint_rejects_missing_required_symbol(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "pipeline.py").write_text("def other():\n    return 1\n")

    contract = ClaimContract(
        claims=[ClaimRequirement("claim_1", "stability", ["compute_stability_signal"])],
        required_symbols=["compute_stability_signal"],
        limitations=[],
    )

    result = lint_generated_project(str(code_dir), contract)

    assert result["status"] == "error"
    assert "missing required symbols: compute_stability_signal" in result["failures"]


def test_lint_rejects_placeholder_function_body(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "pipeline.py").write_text(
        "def compute_stability_signal():\n    pass\n",
        encoding="utf-8",
    )
    contract = ClaimContract(claims=[], required_symbols=["compute_stability_signal"], limitations=[])

    result = lint_generated_project(str(code_dir), contract)

    assert result["status"] == "error"
    assert any("placeholder" in failure for failure in result["failures"])
