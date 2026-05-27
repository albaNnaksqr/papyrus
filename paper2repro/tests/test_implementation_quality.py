from workflows.implementation_quality import assess_generated_code_quality


def test_quality_gate_rejects_empty_python_implementation_files(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("", encoding="utf-8")

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "error"
    assert "src/main.py" in result["empty_python_files"]
    assert any("empty Python" in failure for failure in result["failures"])


def test_quality_gate_rejects_duplicate_source_roots(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('root')\n", encoding="utf-8")
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text(
        "print('nested')\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "error"
    assert result["source_roots"] == ["hyper_kggen/src", "src"]
    assert any("multiple project roots" in failure for failure in result["failures"])


def test_quality_gate_rejects_readme_python_commands_that_do_not_exist(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "model.py").write_text("class Model: pass\n", encoding="utf-8")
    (code_dir / "README.md").write_text(
        "## Usage\n\n```bash\npython src/main.py --config config.yaml\n```\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "error"
    assert "src/main.py" in result["missing_advertised_files"]


def test_quality_gate_rejects_missing_generated_local_imports(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src" / "skill_acquisition").mkdir(parents=True)
    (code_dir / "src" / "__init__.py").write_text("", encoding="utf-8")
    (code_dir / "src" / "skill_acquisition" / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (code_dir / "validate_paper_claims.py").write_text(
        "from src.skill_acquisition.parallel_rollout import ParallelRollout\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "error"
    assert {
        "file": "validate_paper_claims.py",
        "module": "src.skill_acquisition.parallel_rollout",
    } in result["missing_local_imports"]


def test_quality_gate_allows_simple_valid_python_project(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "README.md").write_text(
        "## Usage\n\n```bash\npython src/main.py\n```\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "success"
    assert result["failures"] == []


def test_quality_gate_allows_empty_init_files_in_readme_tree(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "pkg" / "src").mkdir(parents=True)
    (code_dir / "pkg" / "src" / "__init__.py").write_text("", encoding="utf-8")
    (code_dir / "pkg" / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "README.md").write_text(
        "# Project\n\n"
        "```text\n"
        "pkg/\n"
        "├── src/\n"
        "│   ├── __init__.py\n"
        "│   └── main.py\n"
        "```\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "success"
    assert result["empty_advertised_files"] == []


def test_quality_gate_strips_code_directory_root_from_readme_tree(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "tests").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "src" / "pipeline.py").write_text("class Pipeline: pass\n", encoding="utf-8")
    (code_dir / "tests" / "test_pipeline.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (code_dir / "README.md").write_text(
        "# Project\n\n"
        "```text\n"
        "generate_code/\n"
        "├── README.md\n"
        "├── src/\n"
        "│   ├── main.py\n"
        "│   └── pipeline.py\n"
        "└── tests/\n"
        "    └── test_pipeline.py\n"
        "```\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["status"] == "success"
    assert result["missing_advertised_files"] == []


def test_quality_gate_accepts_readme_files_resolved_by_basename(tmp_path):
    """Plan A: README says hyper_kggen/main.py but file is at
    hyper_kggen/src/main.py — accept (find by basename)."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text(
        "def main(): pass\n", encoding="utf-8"
    )
    (code_dir / "hyper_kggen" / "src" / "utils.py").write_text(
        "def helper(): pass\n", encoding="utf-8"
    )
    (code_dir / "hyper_kggen" / "__init__.py").write_text("", encoding="utf-8")
    (code_dir / "hyper_kggen" / "src" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    (code_dir / "README.md").write_text(
        "## Usage\n\n```bash\npython hyper_kggen/main.py --help\n```\n",
        encoding="utf-8",
    )

    result = assess_generated_code_quality(str(code_dir))

    assert result["missing_advertised_files"] == []
