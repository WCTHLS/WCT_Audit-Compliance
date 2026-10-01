## AI Summary Service (services/ai-summary-svc/)

Microservice providing automated, LLM-driven case brief generation and numeric grounding verification for healthcare audit and compliance workflows.

### 1. Overview & Architecture

The AI Summary Service ingests structured case event data and upstream evidence bundles (clinical charts, SHAP explainability, peer distributions, DRG validations, and claim edit flags) and produces a clinical audit brief.

- **Engine:** Single-call prompt-driven LLM synthesis with strict grounding rules, plus code-built sections for facts that must be exact.
- **Default LLM Provider:** Microsoft Foundry Local with OpenVINO GPU acceleration (`qwen2.5-7b-instruct-openvino-gpu`).
- **Context Window:** 32,768 tokens (effective prompt budget: 32,668 with a 100-token safety margin).
- **Alternative Provider:** Ollama (`qwen2.5:3b` or compatible). This is **not** an automatic fallback. Switch to it explicitly with `LLM_PROVIDER=ollama`. If the configured provider fails, the service returns `LLM_ERROR` and `releasable=false`; it never substitutes canned text.
- **Grounding Verification:** `check_numbers()` confirms that every code (CPT, HCPCS, ICD-10, DRG) and every monetary or decimal value in the LLM text exists in the case data. Any value not found makes the summary non-releasable. It does not check that a real value is used in the right place (see Known Limitations C).

**Pipeline**

```
case.created event (from FWA)
  -> evidence_pointers -> _load_case()        load each evidence file that exists
  -> build_case_text()                        flatten JSON + authoritative header
  -> token budget check                       INPUT_TOO_LARGE if over limit
  -> LLM call (Foundry)                       temperature 0.2, 1000 output tokens
  -> check_numbers()                          on LLM text only
  -> build_risk_peer_section()                deterministic, inserted before Auditor Takeaway
  -> SummarizeResponse                        releasable = no warnings
```

**Validation results**

| validation_result |                         Meaning                                | releasable |
|      ---          |                           ---                                  |    ---     |
| PASSED            | No warnings                                                    |    true    |
| N WARNING(S)      | Ungrounded value found, or output truncated                    |    false   |
| NO DATA           | No usable evidence resolved; LLM not called                    |    false   |
| INPUT_TOO_LARGE   | Input + output tokens exceed the context limit; LLM not called |    false   |
| LLM_ERROR         | Provider failed (HTTP error, timeout, empty reply)             |    false   |

### 2. Configuration & Environment Variables

|      Variable       |                Default           |                                   Description                                                                   |
|        ---          |                   ---            |                                      ---                                                                        |
| LLM_PROVIDER        | foundry                          | LLM backend: foundry or ollama                                                                                  |
| FOUNDRY_BASE_URL    | set from `foundry server status` | OpenAI-compatible endpoint for Foundry Local. The default in `config.py` is a placeholder and is usually stale. |
| FOUNDRY_MODEL       | qwen2.5-7b-instruct-openvino-gpu | Loaded model identifier                                                                                         |
| MODEL_CONTEXT_LIMIT | 32768                            | Maximum context length of the loaded model (the NPU variant is limited to 4224)                                 |
| OUTPUT_TOKENS       | 1000                             | Max tokens generated per summary (650 caused truncation)                                                        |
| OLLAMA_BASE_URL     | http://127.0.0.1:11434           | Endpoint for Ollama                                                                                             |
| OLLAMA_MODEL        | qwen2.5:3b                       | Model name when running under Ollama                                                                            |

**Dynamic Port Notice:** Foundry Local assigns a new port each time it restarts (observed: 51664, 51840, 63904, 55343). After every restart, run `foundry server status` and set `FOUNDRY_BASE_URL` in your `.env` or container environment to match.

### 3. Known Limitations & Production Hardening Roadmap

#### A. Lenient Schema Parsing (extra="allow" with Optional fields)
- **Current Behavior:** All evidence models in `libs/evidence-lookup/` configure `model_config = ConfigDict(extra="allow")` and treat all fields as `Optional[...] = None`. This allows the service to ingest varied mock fixtures and partial evidence bundles without failing schema validation.
- **Production Risk:** If an upstream producer sends a misspelled key (e.g. `billed_ammount` instead of `billed_amount`, or `allowed_amt` instead of `allowed_amount`), Pydantic stores it in `__pydantic_extra__` and leaves the canonical field as `None`. Summary generation silently proceeds and may report *"No questioned amount has been determined"*, which could hide valid billing discrepancies from the auditor.
- **Hardening Requirement:**
  - Enforce strict JSONSchema validation at the event-bus ingestion boundary (`case.created`).
  - Implement Pydantic `AliasChoices` or validation pre-hooks to normalize known naming discrepancies.
  - Emit observability warnings/alerts when canonical monetary fields evaluate to `None` while unexpected fields are present in raw payloads.

#### B. Single-Prompt Summarization
- For very complex inpatient cases with multi-week hospital stays, 50+ claim lines, or dense surgical records, single-prompt generation may encounter token limits or lose nuance on secondary lines. Multi-stage map-reduce or hierarchical claim-line evaluation should be introduced if claim line count exceeds 30 lines.

#### C. Grounding Check Scope
- `check_numbers()` blocks any code or amount not found in the case data.
- It does **not** catch a real value placed in the wrong slot, or a real value left out. Observed in the final POC run:
  - CASE-2026-003: lines 3-5 reported as "no allowed amount" (actual: $5.00, $6.50, $6.00).
  - CASE-2026-004: "questioned amount of $0.00" in the overview vs "no questioned amount has been determined" in the takeaway.

#### D. Residual Wording Errors (7B Local Model)
None of these invent a number or reverse a key finding; the correct fact appears elsewhere in the same summary.
- CASE-2026-002: says the claim "was reassigned to MS-DRG 470"; the data only recommends reassignment.
- CASE-2026-004: adds "no further action is required", which is not in the data.
- CASE-2026-006: says "the documentation does not support the billed service" although no medical necessity review exists for this case.

#### E. Deterministic Sections
Facts the model repeatedly got wrong are rendered by code, not the LLM, and are exact by construction:
- Authoritative header: claim service date, admission/discharge dates, questioned amount, fraud ring status, medical necessity review status.
- Pre-computed totals (total billed, total allowed).
- Compact one-line claim rendering: `Line N | CPT | billed | allowed | dx`.
- The full **Risk and Peer Context** section (risk score, typology, ranked SHAP factors with value types, fraud ring, payment action, peer comparison). Also returned separately in `risk_factors_summary` and `peer_comparison_narrative`.

#### F. Model & Environment
- Qwen2.5-7B (local, GPU). re-validate all cases after switching.
- The tokenizer path points to the local Foundry cache. On other machines token counting falls back to a chars / 3.8 estimate.
- Legacy response fields (`bottom_line`, `encounter_as_documented`, `line_by_line_assessment`, `evidence_required`, `line_status_map`) are empty and kept only for frontend compatibility.
- Every summary must be reviewed by an auditor before any decision.

### 4. Running

```powershell
# Start the model and get the current endpoint
foundry model load qwen2.5-7b-instruct-openvino-gpu
foundry server status            # set FOUNDRY_BASE_URL from this output

# Run unit and integration tests (LLM is mocked; ~2 seconds)
pytest services/ai-summary-svc/tests

# Run all mock cases against the real model; writes eval-output/<case_id>.json
python scripts/run_all_cases.py

# Run the API
cd services/ai-summary-svc
python -m uvicorn src.main:app --port 8001
# Swagger UI: http://localhost:8001/docs
```

Run pytest before the batch. If tests fail, the pipeline itself is broken and the batch output is not meaningful.

### 5. Final POC Results

|      Case     |                       Scenario                    |      Result        | Latency |
|      ---      |                        ---                        |       ---          |   ---   |
| CASE-2026-001 | Outpatient cardiology, modifier 25 / E&M upcoding | PASSED, releasable |   ~33s  |
| CASE-2026-002 | Inpatient DRG 469 unsupported MCC                 | PASSED, releasable |   ~40s  |
| CASE-2026-003 | Lab panel unbundling                              | PASSED, releasable |   ~51s  |
| CASE-2026-004 | Upcoding pattern, claim documentation supported   | PASSED, releasable |   ~45s  |
| CASE-2026-005 | DME supplier, fraud ring, records pending         | PASSED, releasable |   ~35s  |
| CASE-2026-006 | Identity misuse, FWA evidence only                | PASSED, releasable |   ~24s  | 

All latencies are within the PRD's 60-second target.
