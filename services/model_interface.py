from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from urllib import error, request

from services.constants import RISK_LEVELS


DNA_ALPHABET = set("ACGTN")
PROTEIN_ALPHABET = set("ABCDEFGHIKLMNPQRSTVWXYZ*")

CATEGORY_BANK = {
    "DNA": {
        "SAFE": (
            "Routine metabolic gene signature",
            "Common structural cassette",
            "Low-concern regulatory context",
        ),
        "REVIEW": (
            "Ambiguous host-interaction signal",
            "Regulatory activity worth analyst review",
            "Unresolved functional control pattern",
        ),
        "HIGH": (
            "Elevated host-interaction signature",
            "Escalation-priority functional signal",
            "High-concern regulation-linked pattern",
        ),
    },
    "PROTEIN": {
        "SAFE": (
            "Routine enzyme-like profile",
            "Low-concern scaffold signature",
            "Common cellular maintenance pattern",
        ),
        "REVIEW": (
            "Ambiguous membrane-associated profile",
            "Unresolved signaling-like pattern",
            "Review-level interaction motif cluster",
        ),
        "HIGH": (
            "Elevated interaction-associated profile",
            "Escalation-priority effector-like pattern",
            "High-concern modulation signature",
        ),
    },
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize_sequence(sequence: str) -> str:
    return "".join(sequence.split()).upper()


def _hash_unit(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _longest_run(sequence: str) -> int:
    if not sequence:
        return 0

    longest = 1
    current = 1
    for index in range(1, len(sequence)):
        if sequence[index] == sequence[index - 1]:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _error_response(model_name: str, error_text: str) -> dict[str, Any]:
    return {
        "ok": False,
        "hazard_score": None,
        "risk_level": None,
        "confidence": None,
        "category": None,
        "explanation": None,
        "baseline_result": None,
        "model_name": model_name,
        "error": error_text,
    }


def _validate_sequence(sequence: str, seq_type: str) -> tuple[str | None, str | None]:
    normalized = _normalize_sequence(sequence)
    if not normalized:
        return None, "empty_sequence_input"

    if seq_type not in {"DNA", "PROTEIN"}:
        return None, "unsupported_sequence_type"

    allowed = DNA_ALPHABET if seq_type == "DNA" else PROTEIN_ALPHABET
    invalid = sorted({character for character in normalized if character not in allowed})
    if invalid:
        return None, f"invalid_{seq_type.lower()}_characters:{''.join(invalid[:8])}"

    return normalized, None


def _risk_level_from_score(score: float) -> str:
    if score >= 0.72:
        return "HIGH"
    if score >= 0.42:
        return "REVIEW"
    return "SAFE"


def _pick_category(seq_type: str, risk_level: str, sequence: str) -> str:
    bank = CATEGORY_BANK[seq_type][risk_level]
    index = int(_hash_unit(seq_type, risk_level, sequence) * len(bank)) % len(bank)
    return bank[index]


def _baseline_result(risk_level: str) -> str:
    if risk_level == "SAFE":
        return "Baseline similarity mock: routine profile, no alert."
    if risk_level == "REVIEW":
        return "Baseline similarity mock: partial signal overlap, manual review recommended."
    return "Baseline similarity mock: inconclusive; function-aware adapter retained a high-priority flag."


def _mock_explanation(seq_type: str, risk_level: str) -> str:
    display_type = "DNA" if seq_type == "DNA" else "protein"
    if risk_level == "SAFE":
        return f"Mock {display_type} screening found a low-concern functional profile with no elevated review signals."
    if risk_level == "REVIEW":
        return f"Mock {display_type} screening found ambiguous functional cues, so the case should be reviewed by an analyst."
    return f"Mock {display_type} screening found multiple elevated functional cues relative to the baseline mock, so the case should be escalated."


def _screen_mock(sequence: str, seq_type: str, model_name: str) -> dict[str, Any]:
    length = len(sequence)
    hash_factor = _hash_unit(sequence, seq_type)

    if seq_type == "DNA":
        gc_fraction = (sequence.count("G") + sequence.count("C")) / length
        unknown_fraction = sequence.count("N") / length
        motif_hits = sum(sequence.count(motif) for motif in ("ATG", "TATA", "CGCG", "GGG"))
        repeat_factor = min(max(_longest_run(sequence) - 3, 0) * 0.018, 0.18)
        score = _clamp(
            0.12
            + min(length / 1800, 0.22)
            + abs(gc_fraction - 0.5) * 0.30
            + min(motif_hits * 0.028, 0.18)
            + repeat_factor
            + min(unknown_fraction * 0.45, 0.12)
            + hash_factor * 0.15
        )
        confidence = _clamp(0.58 + min(length / 900, 0.20) + (1 - abs(gc_fraction - 0.5)) * 0.15 + hash_factor * 0.07)
    else:
        hydrophobic_fraction = sum(character in "AVILMFWYC" for character in sequence) / length
        charged_fraction = sum(character in "KRDEH" for character in sequence) / length
        motif_hits = sum(sequence.count(motif) for motif in ("KK", "RR", "KR", "GP", "GG"))
        low_complexity = 1 - (len(set(sequence)) / max(1, min(20, length)))
        repeat_factor = min(max(_longest_run(sequence) - 2, 0) * 0.022, 0.20)
        score = _clamp(
            0.14
            + min(length / 1200, 0.20)
            + abs(hydrophobic_fraction - 0.34) * 0.38
            + abs(charged_fraction - 0.22) * 0.24
            + min(motif_hits * 0.024, 0.16)
            + min(low_complexity * 0.22, 0.18)
            + repeat_factor
            + hash_factor * 0.15
        )
        confidence = _clamp(
            0.56 + min(length / 700, 0.20) + (1 - abs(charged_fraction - 0.22)) * 0.12 + hash_factor * 0.08
        )

    risk_level = _risk_level_from_score(score)
    category = _pick_category(seq_type, risk_level, sequence)

    return {
        "ok": True,
        "hazard_score": round(score, 3),
        "risk_level": risk_level,
        "confidence": round(confidence, 3),
        "category": category,
        "explanation": _mock_explanation(seq_type, risk_level),
        "baseline_result": _baseline_result(risk_level),
        "model_name": model_name,
        "error": None,
    }


def _coerce_integrated_response(payload: dict[str, Any], fallback_model_name: str) -> dict[str, Any]:
    try:
        if not payload.get("ok"):
            return _error_response(
                str(payload.get("model_name") or fallback_model_name),
                str(payload.get("error") or "integration_failure"),
            )

        risk_level = str(payload.get("risk_level"))
        if risk_level not in RISK_LEVELS:
            raise ValueError("invalid_risk_level")

        hazard_score = _clamp(float(payload.get("hazard_score")))
        confidence = _clamp(float(payload.get("confidence")))
        return {
            "ok": True,
            "hazard_score": round(hazard_score, 3),
            "risk_level": risk_level,
            "confidence": round(confidence, 3),
            "category": str(payload.get("category") or "Unspecified"),
            "explanation": str(payload.get("explanation") or "No explanation provided."),
            "baseline_result": str(payload.get("baseline_result")) if payload.get("baseline_result") else None,
            "model_name": str(payload.get("model_name") or fallback_model_name),
            "error": None,
        }
    except (TypeError, ValueError) as exc:
        return _error_response(fallback_model_name, f"invalid_integrated_response:{exc}")


def _screen_integrated(sequence: str, seq_type: str, model_name: str) -> dict[str, Any]:
    endpoint = os.getenv("SYNTHSCREEN_ENDPOINT")
    if not endpoint:
        return _error_response(model_name, "missing_synthscreen_endpoint")

    payload = json.dumps({"sequence": sequence, "seq_type": seq_type}).encode("utf-8")
    timeout_seconds = float(os.getenv("SYNTHSCREEN_TIMEOUT_SECONDS", "15"))
    request_object = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(request_object, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return _coerce_integrated_response(json.loads(body), model_name)
    except error.HTTPError as exc:
        return _error_response(model_name, f"integration_http_error:{exc.code}")
    except error.URLError as exc:
        return _error_response(model_name, f"integration_connection_error:{exc.reason}")
    except (TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return _error_response(model_name, f"integration_parse_error:{exc}")


def screen_sequence(sequence: str, seq_type: str) -> dict[str, Any]:
    """
    Screen a DNA or protein sequence through the BioLens adapter contract.
    """

    mode = os.getenv("BIOLENS_MODE", "mock").strip().lower() or "mock"
    model_name = f"biolens-{mode}-adapter"
    normalized, validation_error = _validate_sequence(sequence, seq_type)

    if validation_error:
        return _error_response(model_name, validation_error)

    if mode in {"mock", "demo"}:
        return _screen_mock(normalized or "", seq_type, model_name)

    if mode == "integrated":
        return _screen_integrated(normalized or "", seq_type, model_name)

    return _error_response(model_name, f"unsupported_runtime_mode:{mode}")
