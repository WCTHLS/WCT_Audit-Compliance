# AI Summary Service (`services/ai-summary-svc/`)

Microservice providing automated, LLM-driven case brief generation and numeric grounding verification for healthcare audit and compliance workflows.

---

## 1. Overview & Architecture

The AI Summary Service ingests structured case event data and upstream evidence bundles (clinical charts, SHAP explainability, peer distributions, DRG validations, and claim edit flags) and produces a clinical audit brief.

- **Engine:** Single-call prompt-driven LLM synthesis with strict grounding rules.
- **Default LLM Provider:** Microsoft Foundry Local with OpenVINO GPU acceleration (`qwen2.5-7b-instruct-openvino-gpu`).
- **Context Window:** 32,768 tokens (effective prompt budget: 32,668 with safety margin).
- **Fallback Provider:** Ollama (`qwen2.5:3b` or compatible).
- **Grounding Verification:** Validates that numeric claims in the output correspond to source evidence.

---

## 2. Configuration & Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `foundry` | LLM backend: `foundry`, `ollama`, `mock`, or `openai` |
| `FOUNDRY_BASE_URL` | `http://127.0.0.1:51840/v1` | OpenAI-compatible endpoint for Foundry Local |
| `FOUNDRY_MODEL` | `qwen2.5-7b-instruct-openvino-gpu` | Loaded model identifier |
| `MODEL_CONTEXT_LIMIT` | `32768` | Maximum context length supported by the loaded model |
| `OUTPUT_TOKENS` | `1000` | Max tokens generated per summary response |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Endpoint for Ollama fallback |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model name when running under Ollama |

> [!NOTE]
> **Dynamic Port Notice:** Foundry Local assigns dynamic ports upon restart (e.g. `51840`, `63904`, `55343`). Always set `FOUNDRY_BASE_URL` in your `.env` or container environment to match the currently running Foundry instance.

---

## 3. Known Limitations & Production Hardening Roadmap

### A. Lenient Schema Parsing (`extra="allow"` with `Optional` fields)
- **Current Behavior:** All evidence models in `libs/evidence-lookup/` configure `model_config = ConfigDict(extra="allow")` and treat all fields as `Optional[...] = None`. This allows the service to ingest varied mock fixtures and partial evidence bundles without failing schema validation.
- **Production Risk:** If an upstream producer sends a misspelled key (e.g. `billed_ammount` instead of `billed_amount` or `allowed_amt` instead of `allowed_amount`), Pydantic stores it in `__pydantic_extra__` and leaves the canonical field as `None`. The summary generation will silently proceed and report *"No questioned amount has been determined"*, which could hide valid billing discrepancies from the auditor.
- **Hardening Requirement:**
  1. Enforce strict JSONSchema validation at the event-bus ingestion boundary (`case.created`).
  2. Implement Pydantic `AliasChoices` or validation pre-hooks to normalize known naming discrepancies.
  3. Emit observability warnings/alerts when canonical monetary fields evaluate to `None` while unexpected fields are present in raw payloads.

### B. Single-Prompt Summarization
- For very complex inpatient cases with multi-week hospital stays, 50+ claim lines, or dense surgical records, single-prompt generation may encounter token limits or lose nuance on secondary lines. Multi-stage map-reduce or hierarchical claim line evaluation should be introduced if claim line count exceeds 30 lines.
