# WCT Mock Data Fixtures (mock-data/)

Synthetic fixtures for Module 5 (Audit & Compliance) POC. Every case is **triggered by FWA
Detection (Module 2)**. Payment Integrity (Module 3) never triggers a case; it only supplies
enrichment evidence. All files carry `source_module` and `is_synthetic: true`.

- `fwa-mock/` = Module 2 outputs: `case.created` event, risk factors (SHAP, typology, fraud ring,
  suspension recommendation), peer comparison.
- `pi-mock/`  = Module 3 outputs: clinical evidence (incl. medical necessity review), claim flags,
  DRG validation.

## Case matrix

| Case | Claim type | FWA typology | Risk | How PI evidence relates to the FWA flag | Evidence present |
|---|---|---|---|---|---|
| 001 | 837P outpatient cardiology | UNBUNDLING (+UPCODING) | 850 | Supports: E&M thin, echo undocumented | event, clinical, risk, peer, flags |
| 002 | 837I inpatient ortho | UPCODING (DRG) | 920 | Supports: MCC not validated, DRG 469 -> 470 | event, clinical, risk, peer, flags, drg_validation |
| 003 | 837P internal medicine labs | UNBUNDLING | 780 | Supports: CMP components billed separately | event, clinical, risk, peer, flags |
| 004 | 837P family medicine | UPCODING | 810 | **Contradicts**: this 99215 is well documented, 0 flags | event, clinical, risk, peer, flags (empty) |
| 005 | 837P DME supplier | PHANTOM_BILLING, fraud ring | 890 | **Partial**: PI status PARTIAL, records pending, no flags file | event, clinical, risk, peer |
| 006 | 837P behavioral health | IDENTITY_FRAUD | 940 | **None**: FWA-only, no PI evidence | event, risk |

## What each case tests in the summarizer

- **001/002**: regression for the two cases already validated.
- **003**: a third typology and many small-dollar lines; supplied questioned amount $17.50.
- **004**: the model must NOT treat a high risk score as proof. It must report the provider-level
  pattern AND that this claim's documentation was found to meet policy. Also has a negative
  (mitigating) SHAP factor.
- **005**: must report pending documents and inconclusive review without inventing a verdict;
  must describe the fraud ring from supplied data only.
- **006**: no clinical course exists; the summary must not invent one.

## Changes from the previous fixture set

1. Clinical evidence moved from `fwa-mock/` to `pi-mock/` (it is Module 3 output). Event pointers updated.
2. Case 001 claim_ref renamed `CLM-99214-8841` -> `CLM-2026-8841` (old ID contained an unbilled CPT code).
3. Case 002 `flagged_reason` no longer states the DRG 470 conclusion (that belongs to DRG validation).
4. Added `typology`, `fraud_ring_analysis`, `suspension_recommendation` to all risk factor files.
5. Added `value_type` to every risk factor (rate, binary, count, days, currency, score, ...) so binary
   features are not rendered as percentages.
6. Added `claim_type`, `processing_status`, `medical_necessity_review`, `extracted_entities` to clinical evidence.
7. Added `flag_type` to every flag, and questioned-amount totals to claim flags.
8. Case 001 gained a third flag for the undocumented echocardiogram (line 3).
9. Case 002 gained POA indicators, `hac_flag`, `poa_verified`.
