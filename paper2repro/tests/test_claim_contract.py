from workflows.claim_contract import build_claim_contract


def test_claim_contract_extracts_required_symbols_from_plan():
    plan = """
implementation_components:
  - stability-based reward signal: implement compute_stability_signal
  - parallel rollout: implement sample_with_temperature
  - skill library retrieval: implement retrieve_skills and merge_skills
validation_approach:
  required_api:
    - compute_stability_signal
    - sample_with_temperature
    - retrieve_skills
    - merge_skills
"""

    contract = build_claim_contract(plan_text=plan, critique_text="")

    assert contract.required_symbols == [
        "compute_stability_signal",
        "merge_skills",
        "retrieve_skills",
        "sample_with_temperature",
    ]
    assert any("stability" in claim.description.lower() for claim in contract.claims)
    assert any("rollout" in claim.description.lower() for claim in contract.claims)


def test_claim_contract_is_json_serializable():
    contract = build_claim_contract(
        plan_text="implementation_components:\n  - inference pipeline: implement run_inference\n",
        critique_text="risk: dataset unavailable",
    )

    payload = contract.to_dict()

    assert payload["required_symbols"] == ["run_inference"]
    assert payload["limitations"] == ["dataset unavailable"]
