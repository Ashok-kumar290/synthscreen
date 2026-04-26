from __future__ import annotations

from typing import Any


def risk_level_from_score(score: float) -> str:
    """Return the BioLens risk tier for a normalized score."""
    if score >= 0.72:
        return "HIGH"
    if score >= 0.42:
        return "REVIEW"
    return "SAFE"


def apply_intelligence_adjustment(result: dict[str, Any], intel_modifier: float) -> dict[str, Any]:
    """
    Preserve raw model output while making hazard_score/risk_level operational.

    The returned result keeps the raw model score in model_* fields and stores
    intelligence-aware triage in effective_* plus the legacy operational fields.
    """
    adjusted = dict(result)
    modifier = round(max(0.0, float(intel_modifier or 0.0)), 3)

    model_score_value = result.get("model_hazard_score")
    if model_score_value is None:
        model_score_value = result["hazard_score"]
    model_score = float(model_score_value)
    model_risk = str(result.get("model_risk_level") or result["risk_level"])
    effective_score = round(min(1.0, model_score + modifier), 3)
    effective_risk = risk_level_from_score(effective_score)

    adjusted["model_hazard_score"] = model_score
    adjusted["model_risk_level"] = model_risk
    adjusted["intel_modifier"] = modifier
    adjusted["effective_hazard_score"] = effective_score
    adjusted["effective_risk_level"] = effective_risk
    adjusted["hazard_score"] = effective_score
    adjusted["risk_level"] = effective_risk

    explanation = str(result.get("explanation") or "")
    if modifier > 0 and "Intelligence context added" not in explanation:
        adjusted["explanation"] = (
            f"{explanation} Intelligence context added +{modifier:.3f} to model score "
            f"({model_score:.3f} -> {effective_score:.3f}); "
            f"triage tier {model_risk} -> {effective_risk}."
        ).strip()

    return adjusted
