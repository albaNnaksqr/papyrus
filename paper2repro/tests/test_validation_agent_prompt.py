"""Validation agent's LLM prompt construction.

paper_09fffdd3 (LoRA) generated validate_paper_claims.py with
`from src.lora import ...`, but pytest ran from `cwd=generate_code/`
where the actual code lives at `lora_implementation/src/lora.py`.
The implementation-phase prompt had the import convention via
ArtifactContract.to_prompt_block(), but the validation_agent (which
generates validate_paper_claims.py separately) didn't see it.

These tests verify that the validation_agent's user prompt now embeds
the contract's import-convention block so the LLM uses the correct
`from {project_root}.src.X` shape.
"""

from workflows.artifact_contract import ArtifactContract
from workflows.agents.validation_agent import _build_user_prompt


def test_user_prompt_embeds_import_convention_for_nested_project():
    contract = ArtifactContract(
        project_root="lora_implementation",
        entrypoint="lora_implementation/main.py",
        package_name="lora_implementation",
    )
    prompt = _build_user_prompt(
        must_implement="- claim 1\n- claim 2",
        plan="file_structure: ...",
        file_list="lora_implementation/src/lora.py",
        code_sample="def f(): pass",
        contract=contract,
    )
    # Contract block is embedded so the LLM sees the import convention.
    assert "AUTHORITATIVE PROJECT LAYOUT" in prompt
    # The from-real-root shape (what validate_paper_claims.py needs).
    assert "from lora_implementation.src." in prompt


def test_user_prompt_works_without_contract():
    """Backcompat: contract is optional. None still produces a valid prompt."""
    prompt = _build_user_prompt(
        must_implement="- claim",
        plan="file_structure: ...",
        file_list="src/main.py",
        code_sample="x = 1",
        contract=None,
    )
    assert "claim" in prompt
    assert "src/main.py" in prompt
    # No contract → no AUTHORITATIVE PROJECT LAYOUT block.
    assert "AUTHORITATIVE PROJECT LAYOUT" not in prompt


def test_user_prompt_flat_project_embeds_convention():
    contract = ArtifactContract(project_root=".", entrypoint="main.py")
    prompt = _build_user_prompt(
        must_implement="- claim",
        plan="file_structure: ...",
        file_list="src/main.py",
        code_sample="x = 1",
        contract=contract,
    )
    assert "AUTHORITATIVE PROJECT LAYOUT" in prompt
    assert "flat" in prompt.lower()
