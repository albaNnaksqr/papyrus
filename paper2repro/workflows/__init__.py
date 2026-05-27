"""Workflow package exports for research-to-code automation.

Keep this module lightweight: importing small helper modules such as
``workflows.claim_contract`` must not eagerly import the full agent stack.
"""

__all__ = [
    "CodeImplementationWorkflow",
    "acquire_input_artifact",
    "execute_multi_agent_research_pipeline",
    "github_repo_download",
    "paper_code_preparation",
    "paper_reference_analyzer",
    "run_code_analyzer",
]


def __getattr__(name):
    if name == "CodeImplementationWorkflow":
        from .code_implementation_workflow import CodeImplementationWorkflow

        return CodeImplementationWorkflow

    if name in {
        "acquire_input_artifact",
        "run_code_analyzer",
        "github_repo_download",
        "paper_reference_analyzer",
        "execute_multi_agent_research_pipeline",
        "paper_code_preparation",
    }:
        from . import agent_orchestration_engine

        return getattr(agent_orchestration_engine, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
