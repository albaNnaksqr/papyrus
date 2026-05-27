from workflows.repair_planner import build_repair_prompt


def test_repair_prompt_lists_empty_files_and_missing_imports():
    prompt = build_repair_prompt(
        {
            "status": "error",
            "empty_python_files": ["src/main.py"],
            "missing_local_imports": [
                {"file": "validate_paper_claims.py", "module": "src.skills.library"}
            ],
            "source_roots": ["hyper_kggen/src", "src"],
            "failures": ["Detected multiple source roots: hyper_kggen/src, src"],
        }
    )

    assert "src/main.py" in prompt
    assert "src.skills.library" in prompt
    assert "single project root" in prompt


def test_repair_prompt_lists_syntax_errors_and_advertised_file_failures():
    prompt = build_repair_prompt(
        {
            "status": "error",
            "syntax_errors": [
                {"file": "src/model.py", "error": "expected ':' on line 12"}
            ],
            "missing_advertised_files": ["src/training.py"],
            "empty_advertised_files": ["src/evaluate.py"],
        }
    )

    assert "src/model.py" in prompt
    assert "expected ':' on line 12" in prompt
    assert "src/training.py" in prompt
    assert "src/evaluate.py" in prompt


def test_repair_prompt_lists_smoke_and_validation_failures():
    prompt = build_repair_prompt(
        {
            "status": "error",
            "smoke": {
                "status": "error",
                "checks": [
                    {
                        "name": "contract_smoke_command",
                        "command": ["python", "src/main.py", "--help"],
                        "stderr": "ModuleNotFoundError: No module named 'src'",
                        "status": "error",
                    }
                ],
            },
            "validation": {
                "status": "error",
                "raw_output": "ImportError: cannot import name 'compute_stability_signal'",
            },
        }
    )

    assert "python src/main.py --help" in prompt
    assert "ModuleNotFoundError: No module named 'src'" in prompt
    assert "compute_stability_signal" in prompt


def test_repair_prompt_lists_reproduction_gate_failures():
    prompt = build_repair_prompt(
        {
            "status": "error",
            "failures": [],
            "reproduction_gate": {
                "status": "error",
                "checks": [
                    {
                        "name": "claim_contract_lint",
                        "failures": ["missing required symbols: compute_stability_signal"],
                        "status": "error",
                    },
                    {
                        "name": "smoke",
                        "stderr": "ModuleNotFoundError: No module named 'src'",
                        "status": "error",
                    },
                ],
            },
        }
    )

    assert "missing required symbols: compute_stability_signal" in prompt
    assert "ModuleNotFoundError: No module named 'src'" in prompt


def test_build_repair_prompt_includes_type_check_section_on_errors():
    quality_result = {
        "failures": [],
        "type_check_gate": {
            "status": "errors",
            "raw_error_count": 5,
            "filtered_count": 3,
            "symbol_count": 1,
            "duration_seconds": 1.2,
            "rendered_prompt": (
                "# Type-check failures (mypy attr-defined + call-arg)\n"
                "\n"
                "## 1. Node.node_id (3 处调用)\n"
                "**根因**：Node 在 model.py:1 定义...\n"
            ),
        },
    }
    out = build_repair_prompt(quality_result)
    assert "Type-check failures" in out
    assert "Node.node_id" in out


def test_build_repair_prompt_omits_type_check_section_on_success():
    quality_result = {
        "failures": [],
        "type_check_gate": {
            "status": "success",
            "raw_error_count": 0,
            "filtered_count": 0,
            "symbol_count": 0,
            "duration_seconds": 0.5,
            "rendered_prompt": "",
        },
    }
    out = build_repair_prompt(quality_result)
    assert "Type-check failures" not in out


def test_build_repair_prompt_handles_missing_type_check_gate_field():
    """No regression: existing callers without the new field still work."""
    quality_result = {"failures": ["something"]}
    out = build_repair_prompt(quality_result)
    assert "Repair the generated code" in out
