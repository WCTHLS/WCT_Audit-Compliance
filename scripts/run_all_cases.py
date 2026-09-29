"""
Batch runner script to execute AI Summary Service against Cases 001 to 006.
Loads mock event fixtures, runs summarization, saves JSON responses to eval-output/,
and prints an execution summary table.
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

# Workspace and service paths setup
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data" / "fwa-mock"
EVAL_OUTPUT_DIR = WORKSPACE_ROOT / "eval-output"

for path in [
    WORKSPACE_ROOT / "libs" / "event-contracts",
    WORKSPACE_ROOT / "libs" / "evidence-lookup",
    WORKSPACE_ROOT / "libs" / "auth-middleware",
    WORKSPACE_ROOT / "services" / "ai-summary-svc",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.summarizer import CaseSummarizer, SummarizeRequest, SummarizeResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_all_cases")


async def evaluate_case(
    summarizer: CaseSummarizer,
    fixture_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    """Evaluates a single case fixture and persists output JSON."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        event_data = json.load(f)

    case_id = event_data.get("case_id", fixture_path.stem)
    claim_ref = event_data.get("claim_ref", "UNKNOWN")

    request = SummarizeRequest(
        case_id=case_id,
        claim_ref=claim_ref,
        risk_score=event_data.get("risk_score", 850),
        flagged_reason=event_data.get("flagged_reason"),
        evidence_pointers=event_data.get("evidence_pointers", {}),
        service_date=event_data.get("service_date"),
    )

    start_time = time.perf_counter()
    try:
        response: SummarizeResponse = await summarizer.summarize_case(request)
        elapsed = time.perf_counter() - start_time

        output_data = response.model_dump(mode="json")
        output_data["_meta"] = {
            "elapsed_seconds": round(elapsed, 3),
            "fixture_file": fixture_path.name,
        }

        # Save output JSON
        output_file = output_dir / f"{case_id}.json"
        with open(output_file, "w", encoding="utf-8") as out:
            json.dump(output_data, out, indent=2)

        return {
            "case_id": case_id,
            "claim_ref": claim_ref,
            "model": response.model_version,
            "releasable": "YES" if response.releasable else "NO",
            "validation_result": response.validation_result,
            "warnings_count": len(response.validation_warnings),
            "length_chars": len(response.clinical_summary),
            "latency_s": f"{elapsed:.2f}s",
            "status": "OK",
            "error": None,
        }

    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        logger.error(f"Error evaluating {case_id} ({fixture_path.name}): {exc}", exc_info=True)

        error_data = {
            "case_id": case_id,
            "claim_ref": claim_ref,
            "error": str(exc),
            "_meta": {
                "elapsed_seconds": round(elapsed, 3),
                "fixture_file": fixture_path.name,
            },
        }
        output_file = output_dir / f"{case_id}_error.json"
        with open(output_file, "w", encoding="utf-8") as out:
            json.dump(error_data, out, indent=2)

        return {
            "case_id": case_id,
            "claim_ref": claim_ref,
            "model": "N/A",
            "releasable": "NO",
            "validation_result": "ERROR",
            "warnings_count": 0,
            "length_chars": 0,
            "latency_s": f"{elapsed:.2f}s",
            "status": "FAILED",
            "error": str(exc),
        }


def print_summary_table(results: List[Dict[str, Any]]) -> None:
    """Formats and prints summary results table to stdout."""
    headers = [
        ("Case ID", 15),
        ("Claim Ref", 20),
        ("Model", 32),
        ("Releasable", 12),
        ("Validation Result", 20),
        ("Warnings", 10),
        ("Length", 10),
        ("Latency", 10),
    ]

    header_line = " | ".join(f"{name:<{w}}" for name, w in headers)
    separator_line = "-+-".join("-" * w for _, w in headers)

    print("\n" + "=" * len(header_line))
    print("  AI SUMMARY EVALUATION RESULTS")
    print("=" * len(header_line))
    print(header_line)
    print(separator_line)

    for r in results:
        row = [
            f"{r['case_id']:<15}",
            f"{r['claim_ref']:<20}",
            f"{r['model']:<32}",
            f"{r['releasable']:<12}",
            f"{r['validation_result']:<20}",
            f"{str(r['warnings_count']):<10}",
            f"{str(r['length_chars']) + 'c':<10}",
            f"{r['latency_s']:<10}",
        ]
        print(" | ".join(row))

    print(separator_line)
    total_cases = len(results)
    releasable_count = sum(1 for r in results if r["releasable"] == "YES")
    passed_count = sum(1 for r in results if r["status"] == "OK")
    print(f"Summary: {total_cases} evaluated | {passed_count}/{total_cases} completed | {releasable_count}/{total_cases} releasable")
    print("=" * len(header_line) + "\n")


async def main_async(case_filter: List[str], output_dir: Path) -> None:
    """Main async orchestrator."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summarizer = CaseSummarizer()

    # Discover fixture files
    fixture_files = sorted(MOCK_DATA_DIR.glob("case_*_event.json"))
    if not fixture_files:
        logger.error(f"No case event fixtures found in {MOCK_DATA_DIR}")
        return

    if case_filter:
        fixture_files = [
            f for f in fixture_files
            if any(cf in f.name for cf in case_filter)
        ]

    logger.info(f"Running batch summarization on {len(fixture_files)} case(s)...")
    results = []
    for fixture in fixture_files:
        logger.info(f"--> Processing fixture: {fixture.name}")
        res = await evaluate_case(summarizer, fixture, output_dir)
        results.append(res)

    print_summary_table(results)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run AI Summary Service across mock cases 001-006.")
    parser.add_argument(
        "--cases",
        type=str,
        default="",
        help="Comma-separated list of case numbers to evaluate (e.g. '001,002,005'). Defaults to all.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(EVAL_OUTPUT_DIR),
        help=f"Directory to save evaluation JSON artifacts. Default: '{EVAL_OUTPUT_DIR}'",
    )
    args = parser.parse_args()

    filter_list = [c.strip() for c in args.cases.split(",") if c.strip()]
    asyncio.run(main_async(filter_list, Path(args.output_dir)))


if __name__ == "__main__":
    main()
