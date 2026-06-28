"""Regression tests for Alice Tier-0 selection robustness (Story 16.14).

Guards against the partial-benchmark-migration bug where a stale-seeded
``inference-qwen3-vl-235b-GRC`` row (reasoning 87 / vision 95 / instruction 86 /
coding 78), left behind by the 273 refresh, hijacked Tier-0 for every agent on UAT.
Tier-0 now (a) ignores non-positive scores and (b) de-prioritizes ``-GRC`` duplicates
when a non-GRC sibling is also scored.
"""

from ai_qa.agents.alice import _select_model_for


def test_grc_duplicate_does_not_win_over_non_grc_sibling() -> None:
    # The stale -GRC row carries the highest score, but a non-GRC model must win.
    pool = [
        {"id": "inference-qwen3-vl-235b", "supports_vision": True},
        {"id": "inference-qwen3-vl-235b-GRC", "supports_vision": True},
        {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
    ]
    scores = {
        "inference-qwen3-vl-235b-GRC": 95.0,  # stale; must not win
        "inference-qwen3-vl-235b": 20.0,
        "inference-glm-51-754b": 50.0,
    }
    pick = _select_model_for("alice", pool, scores)
    assert pick is not None
    assert "grc" not in pick["model"].lower()
    # With -GRC excluded, glm-51 (50) outranks the non-GRC qwen (20).
    assert pick["model"] == "inference-glm-51-754b"
    assert pick["source"] == "admin"


def test_only_grc_scored_still_selectable() -> None:
    # If a -GRC variant is the ONLY scored eligible model, it may still be chosen
    # (the guard de-prioritizes, it does not hard-ban).
    pool = [{"id": "inference-qwen3-vl-235b-GRC", "supports_vision": True}]
    pick = _select_model_for("bob", pool, {"inference-qwen3-vl-235b-GRC": 80.0})
    assert pick is not None
    assert pick["model"] == "inference-qwen3-vl-235b-GRC"
    assert pick["source"] == "admin"


def test_zero_score_is_treated_as_unscored() -> None:
    # A 0.0 admin row must NOT let a model win Tier-0 over the curated pick.
    pool = [
        {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
        {"id": "inference-zero-9-700b", "name": "Zero"},
    ]
    pick = _select_model_for("sarah", pool, {"inference-zero-9-700b": 0.0})
    assert pick is not None
    # Falls through to the curated tier (glm-5.1 is the coding flagship).
    assert pick["model"] == "inference-glm-51-754b"
    assert pick["source"] == "curated"


def test_positive_non_grc_admin_score_still_overrides_curated() -> None:
    # Sanity: a legitimate positive non-GRC admin score still wins outright.
    pool = [
        {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
        {"id": "inference-newcomer-9-700b", "name": "Newcomer"},
    ]
    pick = _select_model_for("sarah", pool, {"inference-newcomer-9-700b": 80.0})
    assert pick is not None
    assert pick["model"] == "inference-newcomer-9-700b"
    assert pick["source"] == "admin"
