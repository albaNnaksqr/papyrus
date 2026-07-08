from __future__ import annotations

from pathlib import Path

from trajectory.scorecard import DIMENSIONS, score_run


ROOT = Path(__file__).resolve().parents[1]
WAVE2 = ROOT / "output" / "scale_up_wave2" / "codex"
WAVE1 = ROOT / "output" / "scale_up_wave1" / "codex"


def test_clean_wave2_run_has_full_mechanical_scores_and_hybrid_ceilings() -> None:
    result = score_run(WAVE2 / "nucleus_sampling_repro")

    for dim, (_name, _weight, kind) in DIMENSIONS.items():
        score = result["dimensions"][dim]["score"]
        if kind == "mechanical":
            assert score == 2
        else:
            assert result["dimensions"][dim]["ceiling"] == 2
            assert score is None

    assert result["points_if_ceilings"] == 100.0


def test_d2_override_below_ceiling_lowers_final_points() -> None:
    run = WAVE2 / "nucleus_sampling_repro"
    all_ceilings = score_run(run)["points_if_ceilings"]

    overridden = score_run(
        run,
        {
            "1": {"score": 2, "note": "confirmed"},
            "2": {"score": 1, "note": "contract proxy weakened"},
            "6": {"score": 2, "note": "confirmed"},
        },
    )

    assert overridden["points"] < all_ceilings


def test_galore_is_band_capped_to_portfolio_ready() -> None:
    result = score_run(
        WAVE1 / "galore_repro",
        {
            "1": {"score": 2, "note": "confirmed"},
            "2": {"score": 2, "note": "confirmed"},
            "6": {"score": 2, "note": "confirmed"},
        },
    )

    assert result["band_cap"] == "portfolio-ready"
    assert result["band"] == "portfolio-ready"
