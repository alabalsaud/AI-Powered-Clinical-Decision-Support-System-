"""
app/agents/medication_agent.py — Agent 4: Medication

Uses the evidence-based drug_suggest service, then gates every suggested drug
through the existing drug-drug and drug-allergy safety checkers.

Classifies each drug as:
  safe    — no interactions, no allergy conflicts
  warning — moderate interaction or minor allergy risk
  blocked — Contraindicated / Major interaction or confirmed allergy conflict

Only safe / warning drugs are included in the final recommendations.
Blocked drugs are surfaced with the reason so the UI can show them as red.

Adds to PipelineContext:
  medication_groups     : list[{matched_on, rationale, drugs_safe, drugs_warned, drugs_blocked}]
  total_safe_drugs      : int
  total_warned_drugs    : int
  total_blocked_drugs   : int
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent, PipelineContext
from app.services.drug_suggest import suggest_medications
from app.safety.drug_drug import check_drug_interactions
from app.safety.drug_allergy import check_drug_allergy


_BLOCK_SEVERITIES = frozenset({"Contraindicated", "Major", "High"})
_WARN_SEVERITIES  = frozenset({"Moderate", "Minor", "Low"})


def _safety_classify(
    drug_name: str,
    current_meds: List[str],
    allergies: List[str],
) -> Dict[str, Any]:
    """
    Run DDI + allergy checks for a single drug.
    Returns {status, ddi_issues, allergy_issues, block_reason}.
    """
    ddi_results     = check_drug_interactions(drug_name, current_meds)
    allergy_results = check_drug_allergy(
        drug_name,
        [{"allergen": a} for a in allergies],
    )

    block_reasons: List[str] = []
    warn_reasons:  List[str] = []

    for r in ddi_results:
        sev = str(r.get("severity") or "")
        if sev in _BLOCK_SEVERITIES:
            block_reasons.append(
                f"DDI: {r.get('drug_b', drug_name)} ({sev})"
            )
        elif sev in _WARN_SEVERITIES:
            warn_reasons.append(
                f"DDI: {r.get('drug_b', drug_name)} ({sev})"
            )

    for r in allergy_results:
        risk = str(r.get("risk_level") or "")
        if risk in _BLOCK_SEVERITIES or risk == "Contraindicated":
            block_reasons.append(
                f"Allergy: {r.get('allergen', '')} ({risk})"
            )
        elif risk in _WARN_SEVERITIES:
            warn_reasons.append(
                f"Allergy: {r.get('allergen', '')} ({risk})"
            )

    if block_reasons:
        status = "blocked"
    elif warn_reasons:
        status = "warning"
    else:
        status = "safe"

    return {
        "status":          status,
        "ddi_issues":      ddi_results,
        "allergy_issues":  allergy_results,
        "block_reasons":   block_reasons,
        "warn_reasons":    warn_reasons,
    }


class MedicationAgent(BaseAgent):
    name = "MedicationAgent"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        self.log("Generating evidence-based medication recommendations…")

        verified     = ctx.get("verified_diagnoses") or []
        allergies    = ctx.get("normalised_allergies") or []
        current_meds = ctx.get("current_meds") or []
        conditions   = ctx.get("medical_history") or []
        symptoms     = ctx.get("symptoms") or ""

        # Build diagnosis name list for drug_suggest
        dx_names = [d.get("name", "") for d in verified[:5]]

        # Query evidence-based drug suggestion engine
        suggestion_result = suggest_medications(
            diagnoses=dx_names,
            symptoms=symptoms,
            allergies=allergies,
            conditions=conditions,
        )

        output_groups:  List[Dict[str, Any]] = []
        total_safe    = 0
        total_warned  = 0
        total_blocked = 0

        for group in suggestion_result.get("suggestions") or []:
            drugs_safe:    List[Dict[str, Any]] = []
            drugs_warned:  List[Dict[str, Any]] = []
            drugs_blocked: List[Dict[str, Any]] = []

            for drug in group.get("drugs") or []:
                safety = _safety_classify(
                    drug["name"],
                    current_meds,
                    allergies,
                )
                enriched = {**drug, **safety}

                if safety["status"] == "blocked":
                    drugs_blocked.append(enriched)
                    total_blocked += 1
                elif safety["status"] == "warning":
                    drugs_warned.append(enriched)
                    total_warned += 1
                else:
                    drugs_safe.append(enriched)
                    total_safe += 1

            output_groups.append({
                "matched_on":    group.get("matched_on", ""),
                "rationale":     group.get("rationale", ""),
                "drugs_safe":    drugs_safe,
                "drugs_warned":  drugs_warned,
                "drugs_blocked": drugs_blocked,
            })

        self.log(
            f"Medications: {total_safe} safe, {total_warned} warned, "
            f"{total_blocked} blocked across {len(output_groups)} condition groups"
        )

        ctx["medication_groups"]    = output_groups
        ctx["total_safe_drugs"]     = total_safe
        ctx["total_warned_drugs"]   = total_warned
        ctx["total_blocked_drugs"]  = total_blocked
        return ctx
