from workflows.artifact_contract import ArtifactContract
from workflows.code_acceptance import accept_written_file
from workflows.code_implementation_workflow import CodeImplementationWorkflow


def test_acceptance_rejects_empty_implementation_file(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "empty implementation file" in result["reason"]


def test_acceptance_allows_empty_init_file(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "__init__.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/__init__.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is True


def test_acceptance_rejects_python_syntax_error(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("def broken(:\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "syntax error" in result["reason"]


def test_acceptance_rejects_python_file_outside_contract_source_root(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "other_root" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("print('wrong root')\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "other_root/main.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "outside project root" in result["reason"]


def test_acceptance_allows_flat_project_files_when_source_root_is_current_directory(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "utils.py"
    code_dir.mkdir(parents=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "utils.py",
        ArtifactContract(project_root=".", entrypoint="main.py"),
    )

    assert result["accepted"] is True


def test_rejected_write_file_does_not_count_progress_and_records_error(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    workflow = CodeImplementationWorkflow()
    workflow.progress_tracker.set_total_files(1)
    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")

    completed_first_time = workflow._accept_write_file_for_progress(
        str(code_dir),
        "src/main.py",
        "src/main.py",
        contract,
    )

    assert completed_first_time is False
    assert workflow.progress_tracker.completed_files == 0
    assert workflow.loop_detector.consecutive_errors == 1


# Run16 (paper_4c51bf57) showed: acceptance rejected utils/llm_client.py and
# similar out-of-root writes, but the files stayed on disk. Then
# _active_source_roots scanned the directory later and reported "multiple
# source roots: ., hyper_kggen, src, utils" — a ghost failure. Solution:
# on the source-root reject path, unlink the file so disk reflects only
# accepted writes.


def test_acceptance_unlinks_rejected_out_of_root_file(tmp_path):
    """Source-root reject should delete the offending file to keep disk clean."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "utils" / "llm_client.py"
    path.parent.mkdir(parents=True)
    path.write_text("def x(): pass\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "utils/llm_client.py",
        ArtifactContract(project_root="hyper_kggen", entrypoint="hyper_kggen/main.py"),
    )

    assert result["accepted"] is False
    assert "outside project root" in result["reason"]
    # File should be gone from disk so downstream gates don't see a ghost root.
    assert not path.exists()


def test_acceptance_does_not_unlink_empty_file_on_rejection(tmp_path):
    """Empty-file rejection should not delete (agent should fix content)."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "empty implementation file" in result["reason"]
    # File preserved so agent can see and re-write it.
    assert path.exists()


def test_acceptance_does_not_unlink_syntax_error_file(tmp_path):
    """Syntax-error rejection should not delete (agent should fix content)."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("def x(:\n", encoding="utf-8")  # syntax error

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "syntax error" in result["reason"]
    assert path.exists()


def test_acceptance_unlink_handles_missing_file_gracefully(tmp_path):
    """If something else removed the file before we get there, no crash."""
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir(parents=True)
    # File never existed — accept will return early on 'file does not exist'.
    result = accept_written_file(
        str(code_dir),
        "utils/llm_client.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )
    assert result["accepted"] is False
    assert "does not exist" in result["reason"]


# End-of-implementation sweep. Run17/Run18 showed: even with per-write
# unlink, the agent's final batch re-writes files that get rejected but
# never re-checked, so the disk ends up with multi-root leftovers.
# prune_out_of_root_py_files() does a final pass and removes them.


def test_prune_removes_files_outside_source_root(tmp_path):
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "lora_implementation" / "src").mkdir(parents=True)
    (code_dir / "lora_implementation" / "src" / "lora.py").write_text(
        "def x(): pass\n", encoding="utf-8"
    )
    # Leftover outside contract source root
    (code_dir / "src").mkdir()
    (code_dir / "src" / "lora.py").write_text("ghost\n", encoding="utf-8")
    (code_dir / "utils").mkdir()
    (code_dir / "utils" / "llm.py").write_text("ghost2\n", encoding="utf-8")

    contract = ArtifactContract(
        project_root="lora_implementation/src",
        entrypoint="lora_implementation/main.py",
    )

    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "lora_implementation" / "src" / "lora.py").exists()
    assert not (code_dir / "src" / "lora.py").exists()
    assert not (code_dir / "utils" / "llm.py").exists()
    assert sorted(result["pruned"]) == ["src/lora.py", "utils/llm.py"]


def test_prune_keeps_allowlisted_paths(tmp_path):
    """tests/, validate_paper_claims.py, entrypoint should survive."""
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("x=1\n", encoding="utf-8")
    (code_dir / "tests").mkdir()
    (code_dir / "tests" / "test_x.py").write_text("def test(): pass\n", encoding="utf-8")
    (code_dir / "validate_paper_claims.py").write_text(
        "print(1)\n", encoding="utf-8"
    )

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "src" / "main.py").exists()
    assert (code_dir / "tests" / "test_x.py").exists()
    assert (code_dir / "validate_paper_claims.py").exists()
    assert result["pruned"] == []


def test_prune_removes_scripts_dir_now_that_allowlist_dropped(tmp_path):
    """scripts/ allowlist dropped: scripts/*.py at root is pruned."""
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("x=1\n", encoding="utf-8")
    (code_dir / "scripts").mkdir()
    (code_dir / "scripts" / "launch.py").write_text("print(1)\n", encoding="utf-8")

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "src" / "main.py").exists()
    assert not (code_dir / "scripts" / "launch.py").exists()
    assert "scripts/launch.py" in result["pruned"]


def test_prune_ignores_caches_and_pycache(tmp_path):
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("x=1\n", encoding="utf-8")
    # Non-contract pycache files that look like .py — should not be pruned
    (code_dir / "__pycache__").mkdir()
    (code_dir / "__pycache__" / "x.cpython-313.py").write_text(
        "compiled", encoding="utf-8"
    )
    (code_dir / ".mypy_cache").mkdir()
    (code_dir / ".mypy_cache" / "ghost.py").write_text("stale", encoding="utf-8")

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "__pycache__" / "x.cpython-313.py").exists()
    assert (code_dir / ".mypy_cache" / "ghost.py").exists()
    assert result["pruned"] == []


def test_prune_handles_missing_code_directory(tmp_path):
    from workflows.code_acceptance import prune_out_of_root_py_files

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(
        str(tmp_path / "does_not_exist"), contract
    )
    assert result["pruned"] == []


# Run19 (LoRA) showed the over-restriction: contract.project_root was
# lora_reproduction/src, but the plan tree puts the experiment driver at
# lora_reproduction/experiments/run_gpt2_nlg.py — sibling to src/ under the
# same package root. Acceptance rejected it and prune deleted it, leaving
# the contract's expected entrypoint with no file anywhere on disk. Fix:
# accept anything under the same top-level package root as source_root.


def test_acceptance_allows_sibling_subdir_under_same_package_root(tmp_path):
    """project_root=pkg should accept pkg/experiments/run.py."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "lora_reproduction" / "experiments" / "run_glue.py"
    path.parent.mkdir(parents=True)
    path.write_text("def main(): pass\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "lora_reproduction/experiments/run_glue.py",
        ArtifactContract(
            project_root="lora_reproduction",
            entrypoint="lora_reproduction/run_glue.py",
        ),
    )

    assert result["accepted"] is True
    assert path.exists()


def test_acceptance_still_rejects_unrelated_top_level_package(tmp_path):
    """src/foo.py is NOT under lora_reproduction/ → still reject."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "foo.py"
    path.parent.mkdir(parents=True)
    path.write_text("ghost\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/foo.py",
        ArtifactContract(
            project_root="lora_reproduction",
            entrypoint="lora_reproduction/main.py",
        ),
    )

    assert result["accepted"] is False
    assert "outside project root" in result["reason"]
    assert not path.exists()  # unlinked


def test_acceptance_flat_source_root_unchanged(tmp_path):
    """project_root=src (no package) — only src/* accepted, not random root."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "other" / "foo.py"
    path.parent.mkdir(parents=True)
    path.write_text("ghost\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "other/foo.py",
        ArtifactContract(project_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert not path.exists()


def test_prune_keeps_sibling_package_root_files(tmp_path):
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "lora_reproduction" / "src").mkdir(parents=True)
    (code_dir / "lora_reproduction" / "src" / "lora.py").write_text(
        "x=1\n", encoding="utf-8"
    )
    (code_dir / "lora_reproduction" / "experiments").mkdir()
    (code_dir / "lora_reproduction" / "experiments" / "run.py").write_text(
        "x=1\n", encoding="utf-8"
    )

    contract = ArtifactContract(
        project_root="lora_reproduction",
        entrypoint="lora_reproduction/main.py",
    )
    result = prune_out_of_root_py_files(str(code_dir), contract)

    # Sibling under the same package root preserved
    assert (code_dir / "lora_reproduction" / "experiments" / "run.py").exists()
    assert result["pruned"] == []


# ----- accept_written_file simplification (Task 6) -----


def test_acceptance_rejects_scripts_dir_now_that_allowlist_dropped(tmp_path):
    """scripts/ allowlist removed. Agent must put scripts inside project_root."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "scripts" / "launch.py"
    path.parent.mkdir(parents=True)
    path.write_text("print('launch')\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "scripts/launch.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is False
    assert "outside" in result["reason"] or "project" in result["reason"]
    assert not path.exists()


def test_acceptance_accepts_entrypoint_inside_project_root(tmp_path):
    """No longer needs special-case rel == contract.entrypoint."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "pkg" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("def main(): pass\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "pkg/main.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is True


def test_acceptance_accepts_validate_paper_claims_at_root(tmp_path):
    """Explicit allowlist for the paper2code-specific validation script."""
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "validate_paper_claims.py").write_text(
        "def test(): pass\n", encoding="utf-8"
    )

    result = accept_written_file(
        str(code_dir),
        "validate_paper_claims.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is True
