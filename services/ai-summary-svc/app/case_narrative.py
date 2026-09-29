"""
Case narrative generation — replaces audit_summary_v6.py.

Flattens whatever JSON exists for a case into readable text, asks the model for
a narrative summary, and optionally checks that numbers in the output came from
the source.

No schemas, no status enums, no manifest, no span grounding, no validators that
need a CPT profile table. If a case is missing a file or a field, it just
doesn't appear in the text.
"""

import json
import re
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# 1. Flatten arbitrary JSON into readable labelled text
# ---------------------------------------------------------------------------

RENDER_SKIP_KEYS = {
    "distribution_histogram",
    "shap_waterfall",
    "extracted_entities",
    "source_module",
    "is_synthetic",
    "event_id",
    "event_type",
    "timestamp",
    "evaluated_at",
    "evaluation_timestamp",
    "fixture_ref",
    "address",
    "pos_code",
    "evidence_pointers",
    "collected",
    "other_components",
    "facility_npi",
    "doctor_npi",
}

PEER_STATS_ALLOWED_KEYS = {
    "median",
    "p95",
    "p99",
    "max",
    "computed_percentile",
    "ratio_to_median",
}

EVENT_DEDUP_KEYS = {
    "case_id",
    "claim_ref",
    "risk_score",
    "flagged_reason",
    "total_claim_amount",
}


def flatten(obj: Any, indent: int = 0, parent_key: str = "") -> List[str]:
    """Turn any nested JSON into indented label: value lines with filtering."""
    pad = "  " * indent
    lines: List[str] = []

    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in RENDER_SKIP_KEYS:
                continue
            if parent_key == "statistics" and key not in PEER_STATS_ALLOWED_KEYS:
                continue
            label = key.replace("_", " ")
            if isinstance(val, (dict, list)):
                if not val:
                    continue
                nested = flatten(val, indent + 1, parent_key=key)
                if nested:
                    lines.append(f"{pad}{label}:")
                    lines.extend(nested)
            elif val is not None and val != "":
                lines.append(f"{pad}{label}: {val}")

    elif isinstance(obj, list):
        for i, item in enumerate(obj, 1):
            if isinstance(item, (dict, list)):
                nested = flatten(item, indent + 1, parent_key=parent_key)
                if nested:
                    lines.append(f"{pad}({i})")
                    lines.extend(nested)
            else:
                lines.append(f"{pad}- {item}")

    else:
        lines.append(f"{pad}{obj}")

    return lines


def build_case_text(case: Dict[str, Any]) -> str:
    """
    Render the whole case as readable text. Sections with no data are skipped
    automatically, so a sparse case just produces a shorter block.
    """
    # Pre-compute totals in Python so the model never does arithmetic
    if case.get("clinical") and case["clinical"].get("claim_lines"):
        lines = case["clinical"]["claim_lines"]
        case["clinical"]["TOTALS"] = {
            "total_billed": sum(float(l.get("billed_amount") or 0.0) for l in lines),
            "total_allowed": sum(float(l.get("allowed_amount") or 0.0) for l in lines),
        }

    # Authoritative dates block
    clinical = case.get("clinical") or {}
    event = case.get("event") or {}

    auth_service_date = (
        clinical.get("service_date")
        or clinical.get("admission_date")
        or event.get("service_date")
    )
    admission_date = clinical.get("admission_date")
    discharge_date = clinical.get("discharge_date")

    date_lines: List[str] = []
    if auth_service_date:
        date_lines.append(f"CLAIM SERVICE DATE (authoritative): {auth_service_date}")
    if admission_date and discharge_date:
        date_lines.append(f"CLAIM ADMISSION DATE (authoritative): {admission_date}")
        date_lines.append(f"CLAIM DISCHARGE DATE (authoritative): {discharge_date}")

    labels = {
        "clinical": "CLINICAL EVIDENCE",
        "flags": "PAYMENT INTEGRITY FLAGS",
        "risk": "FWA RISK MODEL",
        "peer": "PEER COMPARISON",
        "event": "CASE EVENT",
        "drg_validation": "DRG VALIDATION",
    }
    out: List[str] = []
    if date_lines:
        out.extend(date_lines)
        out.append("")

    for key in ("event", "clinical", "flags", "risk", "peer", "drg_validation"):
        data = case.get(key)
        if not data:
            continue

        # Deduplicate event section when clinical evidence exists
        if key == "event" and isinstance(data, dict):
            event_data = {k: v for k, v in data.items() if k in EVENT_DEDUP_KEYS}
            body = flatten(event_data)
        elif isinstance(data, dict):
            # Deduplicate case_id / claim_ref already present in CASE EVENT
            sec_data = {k: v for k, v in data.items() if k not in ("case_id", "claim_ref")}
            body = flatten(sec_data)
        else:
            body = flatten(data)

        if not body:
            continue
        out.append(f"--- {labels[key]} ---")
        out.extend(body)
        out.append("")
    return "\n".join(out)



# ---------------------------------------------------------------------------
# 2. Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You write case briefs for healthcare claim auditors, using only the CASE DATA provided.

Rules:
1. Use only facts in CASE DATA. Never invent or infer a code, amount, date, diagnosis, procedure, medication, result, finding, or recommendation. If something is absent, omit it.
2. Describe the claim using the coding actually present (CPT/HCPCS lines, DRGs, ICD-10-CM/PCS). Do not assume the claim is outpatient or inpatient.
3. Report upstream findings (flags, medical necessity reviews, DRG validation, risk model) exactly as supplied. Do not make your own coding or clinical determination, and do not add recommendations.
4. Distinguish a service that is documented but does not support the billed level from a service that is absent from the record.
5. A risk score is a signal, not proof. If the claim-level review found the documentation meets policy, state that clearly.
6. If a review is pending or inconclusive, say so. Do not guess the outcome.
7. Use amounts and totals exactly as given; do not calculate new ones. Keep each value's meaning: rates as percentages, counts as counts, binary indicators as yes/no conditions.
8. Write plain professional prose. Do not output JSON."""

USER_PROMPT = """CASE DATA
{case_text}

Rules for this brief:
- When a claim has multiple lines, give each line its own sentence with its own code, billed amount, allowed amount, and diagnosis codes. Use codes, not descriptions, for diagnoses. Never merge two or more lines into one statement or use "respectively".
- If a claim line has an allowed amount in CASE DATA, you must state it. Only write that a line has no allowed amount when the field is genuinely absent for that line. Check each line individually before making that statement.
- Label every monetary amount with exactly what CASE DATA calls it: billed amount, allowed amount, reimbursement amount, overpayment variance, or questioned amount. Never substitute one label for another.
- State each monetary amount only in the section where CASE DATA defines it. Do not attach a claim-level or validation-level amount to an individual diagnosis, code, or line.
- Report an allowed amount only where CASE DATA supplies one. If a claim has no allowed amount, omit it rather than repeating the billed amount.
- Never subtract allowed from billed, or perform any other arithmetic, to produce a questioned amount. Use only a questioned amount, overpayment variance, or questioned allowed amount total that appears verbatim in CASE DATA. If none appears, write "No questioned amount has been determined."
- State only diagnosis codes present in CASE DATA. If a line or claim has no diagnoses, say so; never supply a code or description from general knowledge.
- List only the diagnoses actually billed on the claim. A code proposed as a correction or reassignment is not a billed diagnosis — describe it as a proposed change, not as part of the claim.
- When fraud ring analysis reports flagged as false, state that no fraud ring was identified, regardless of the connected entity count.
- If the review found the documentation meets policy, say so first in the Auditor Takeaway, before describing any provider-level pattern. Do not ask for documentation that the review did not identify as missing.
- Use the authoritative claim service date exactly as given at the top of CASE DATA. Never infer or adjust the claim's service date from any other record's admission, discharge, or evaluation dates.

Write a 300-380 word case brief. Use a short plain-text heading for each
section below, then prose. Do not use markdown, bold, or numbered lists.
Keep each section to 2-4 sentences. Skip any section with no data.
The Auditor Takeaway section is required and must be the last thing you
write — reach it before you run out of space:
Case Overview: patient, claim, provider, facility, dates, billed and allowed amounts.
Clinical Course: reason for care, key findings, vitals, results, medications with doses, treatment, outcome.
Claim and Coding: each billed item with its code, amounts, and linked diagnoses.
Review Findings: flags and review results, with citations and recommended actions.
Risk and Peer Context: risk score, typology, key risk factors, peer comparison, fraud ring findings.
Auditor Takeaway: the main issues to review, missing documentation, and any questioned amount supplied in CASE DATA."""


def build_prompt(case: Dict[str, Any]) -> str:
    return USER_PROMPT.format(case_text=build_case_text(case))



# ---------------------------------------------------------------------------
# 3. Light fact check (optional, ~40 lines, no CPT tables)
# ---------------------------------------------------------------------------

def check_numbers(summary: str, case: Dict[str, Any]) -> List[str]:
    """
    Confirm every code and dollar amount in the summary appears in the source
    JSON. Catches transposed digits and invented codes without needing any
    knowledge of what the codes mean.
    """
    source = json.dumps(case)
    warnings: List[str] = []

    # CPT codes (5 digits)
    for code in sorted(set(re.findall(r"\b\d{5}\b", summary))):
        if code not in source:
            warnings.append(f"CPT/code {code} is not in the case data.")

    # HCPCS Level II codes (e.g. K0823, E2365, L1851)
    for code in sorted(set(re.findall(r"\b[A-V]\d{4}\b", summary))):
        if code not in source:
            warnings.append(f"HCPCS code {code} is not in the case data.")

    # DRG codes (e.g. DRG 469, MS-DRG 470)
    for code in sorted(set(re.findall(r"\b(?:MS-)?DRG\s*(\d{1,3})\b", summary, re.IGNORECASE))):
        if code not in source:
            warnings.append(f"DRG code {code} is not in the case data.")

    # ICD-10 codes
    for code in sorted(set(re.findall(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b", summary))):
        if code not in source:
            warnings.append(f"ICD-10 code {code} is not in the case data.")

    # Dollar amounts ($1,250.00, $420) and standalone decimal numbers (e.g. 943.31)
    found_tokens = re.findall(r"\$\s?([\d,]+(?:\.\d{2})?)", summary)
    # Also capture standalone decimal numbers not preceded by $ and not part of a comma-separated number
    summary_without_dollars = re.sub(r"\$\s?[\d,]+(?:\.\d{2})?", "", summary)
    for m in re.findall(r"(?<![\d,])\b(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}\b", summary_without_dollars):
        found_tokens.append(m)

    amounts = {
        float(m.replace(",", ""))
        for m in found_tokens
    }
    source_nums = {
        float(n) for n in re.findall(r"-?\d+\.?\d*", source)
    }
    # Totals are legitimate, so allow any sum of source amounts up to the total.
    lines = (case.get("clinical") or {}).get("claim_lines", [])
    for field in ("billed_amount", "allowed_amount"):
        vals = [float(l[field]) for l in lines if l.get(field) is not None]
        if vals:
            source_nums.add(sum(vals))
    for amt in sorted(amounts):
        if amt not in source_nums:
            warnings.append(f"Dollar amount ${amt:,.2f} is not in the case data.")

    return warnings


# ---------------------------------------------------------------------------
# 4. Entry point
# ---------------------------------------------------------------------------

def summarize(case: Dict[str, Any], call_llm) -> Tuple[str, List[str]]:
    """
    call_llm(system, user) -> str
    Returns (summary_text, warnings).
    """
    meaningful_keys = ("clinical", "risk", "peer", "flags", "drg_validation")
    if not any(bool(case.get(k)) for k in meaningful_keys):
        return (
            "No usable evidence was available for this case, so no summary "
            "could be produced. Manual review is required.",
            ["No usable evidence resolved."],
        )

    summary = call_llm(SYSTEM_PROMPT, build_prompt(case)).strip()
    return summary, check_numbers(summary, case)

