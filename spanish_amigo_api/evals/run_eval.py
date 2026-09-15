"""Commands are explicit: offline never imports model/database adapters."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .baseline import baseline_configuration, validate_baseline_configuration
from .loaders import DEFAULT_CASES_PATH, PHASE5_CASES_PATH, dataset_sha256, load_cases, load_phase5_cases
from .metrics import accuracy, binary_macro_f1, mean, recall_at_k, reciprocal_rank
from .reporting import write_report


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=Path(__file__).resolve().parents[2]).strip()
    except (OSError, subprocess.CalledProcessError):
        return "NOT AVAILABLE"


def offline_report(cases_path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    cases = load_cases(cases_path)
    config = baseline_configuration()
    validate_baseline_configuration(config)
    return {"mode": "OFFLINE METRIC TEST", "status": "MEASURED", "dataset_sha256": dataset_sha256(cases_path), "case_count": len(cases), "categories": dict(sorted(Counter(case.category for case in cases).items())), "baseline": config, "metrics": {"retrieval": "NOT RUN (fixture metric unit tests only)", "safety": "NOT RUN (no live guardrail adapter in offline runner)", "reliability": {"case_load_failures": 0, "evaluation_run_failures": 0}, "latency": "NOT RUN", "token_usage": "NOT RUN"}, "failures": []}


def retrieval_report(cases_path: Path, variant: str = "B_legacy") -> dict[str, Any]:
    from .adapters.current_rag import retrieve_variant, runtime_configuration  # Explicit only: may call Gemini and PostgreSQL.
    cases = load_cases(cases_path)
    failures, recalls, recall_ones, ranks = [], [], [], []
    for case in cases:
        if not case.expected_relevant_slide_ids:
            continue
        observed = retrieve_variant(case.user_input, variant)
        expected = set(case.expected_relevant_slide_ids)
        recall_ones.append(recall_at_k(observed, expected, 1))
        recalls.append(recall_at_k(observed, expected, 3))
        ranks.append(reciprocal_rank(observed, expected))
        if not set(observed) & expected:
            failures.append({"case_id": case.id, "expected_behavior": case.expected_behavior, "expected_relevant_slide_ids": sorted(expected), "retrieved_slide_ids": observed, "rank_positions": [], "failure_category": "retrieval_miss"})
    return _runtime_report("LOCAL/INTEGRATION RETRIEVAL EVAL", cases_path, {"variant": variant, "Recall@1": mean(recall_ones), "Recall@3": mean(recalls), "MRR": mean(ranks)}, failures, runtime_configuration())


def planner_offline_report(cases_path: Path = PHASE5_CASES_PATH) -> dict[str, Any]:
    """No model, network, or DB: run curated proposals through Phase-5 application policy."""
    from app.schemas import AssessmentProposal
    from app.services.adaptive import PolicyInput, assessability_gate, select_pedagogical_action, validate_assessment_proposal

    cases = load_phase5_cases(cases_path)
    expected_assessable, observed_assessable = [], []
    expected_validation, observed_validation = [], []
    expected_actions, observed_actions = [], []
    false_accepts = 0
    negative_validation_cases = 0
    failures = []
    for case in cases:
        gate = assessability_gate(case.user_input, guardrail_blocked=case.guardrail_blocked)
        validation = None
        parsed_proposal = None
        if case.proposal is not None:
            try:
                parsed_proposal = AssessmentProposal.model_validate(case.proposal)
                validation = validate_assessment_proposal(parsed_proposal, learner_turn=case.user_input, gate=gate)
            except Exception:
                from app.services.adaptive import EvidenceValidation
                validation = EvidenceValidation("invalid", "malformed_proposal", None, None)
        action = select_pedagogical_action(PolicyInput(gate, validation, parsed_proposal.result if parsed_proposal else None, None, 0, validation.skill.assessment_mode if validation and validation.skill else None))
        expected_assessable.append(case.expected_assessable)
        observed_assessable.append(gate.assessable)
        expected_actions.append(case.expected_action)
        observed_actions.append(action.value)
        if case.expected_validation_status is not None:
            expected_validation.append(case.expected_validation_status)
            observed_validation.append(validation.status if validation else None)
            if case.expected_validation_status != "accepted":
                negative_validation_cases += 1
                false_accepts += int(validation is not None and validation.status == "accepted")
        if gate.assessable != case.expected_assessable or action.value != case.expected_action or (case.expected_validation_status is not None and (validation is None or validation.status != case.expected_validation_status)):
            failures.append({"case_id": case.id, "failure_category": "planner_mismatch"})
    return {
        "mode": "OFFLINE C_planner METRIC TEST", "status": "MEASURED",
        "dataset_sha256": dataset_sha256(cases_path), "case_count": len(cases),
        "baseline": baseline_configuration(),
        "metrics": {
            "assessability_accuracy": accuracy(expected_assessable, observed_assessable),
            "assessability_macro_f1": binary_macro_f1(expected_assessable, observed_assessable),
            "validation_accuracy": accuracy(expected_validation, observed_validation),
            "policy_action_accuracy": accuracy(expected_actions, observed_actions),
            "false_accepted_evidence_rate": false_accepts / negative_validation_cases if negative_validation_cases else None,
            "skill_classification_accuracy": "NOT RUN (requires model predictions; fixture proposals are inputs)",
            "mastery_update_metrics": "NOT IMPLEMENTED",
        },
        "failures": failures, "failure_count": len(failures),
    }


def live_report(cases_path: Path, baseline: str, limit: int | None) -> dict[str, Any]:
    from .adapters.live_model import evaluate_live_case, runtime_configuration  # Explicit only: invokes the configured Gemini generation model.
    cases = load_cases(cases_path)
    if limit is not None:
        cases = cases[:limit]
    failures, latencies, token_usages = [], [], []
    for case in cases:
        observed = evaluate_live_case(case, baseline)
        if observed["latency_ms"] is not None:
            latencies.append(observed["latency_ms"])
        if observed["token_usage"] is not None:
            token_usages.append(observed["token_usage"])
        if observed["behavior"] != case.expected_behavior:
            failures.append({"case_id": case.id, "expected_behavior": case.expected_behavior, "observed_behavior": observed["behavior"], "retrieved_slide_ids": observed["retrieved_slide_ids"], "rank_positions": [], "failure_category": "guardrail_mismatch"})
    return _runtime_report("LIVE MODEL EVAL", cases_path, {"baseline": baseline, "safety_success_rate": (len(cases) - len(failures)) / len(cases) if cases else None, "latency_ms_mean": mean(latencies), "provider_token_usage_total": sum(token_usages) if token_usages else None}, failures, runtime_configuration())


def _runtime_report(mode: str, cases_path: Path, metrics: dict[str, Any], failures: list[dict[str, Any]], runtime_configuration: dict[str, object]) -> dict[str, Any]:
    return {"mode": mode, "status": "MEASURED", "timestamp_utc": datetime.now(UTC).isoformat(), "git_sha": git_sha(), "dataset_sha256": dataset_sha256(cases_path), "baseline": baseline_configuration(), "runtime_configuration": runtime_configuration, "metrics": metrics, "failures": failures, "failure_count": len(failures), "latency": "recorded only when adapter supplies it", "token_usage": "recorded only when provider supplies it"}


def main() -> None:
    parser = argparse.ArgumentParser(description="SpanishAmigo pre-adaptive baseline evaluator")
    parser.add_argument("mode", choices=("offline", "planner-offline", "db-retrieval", "live-model"))
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline", choices=("A", "B"), default="B")
    parser.add_argument("--variant", choices=("B_legacy", "B_metadata", "B_hybrid"), default="B_legacy")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--confirm-live", action="store_true", help="Required because this command invokes Gemini and may consume quota.")
    args = parser.parse_args()
    if args.mode == "offline":
        report = offline_report(args.cases)
    elif args.mode == "planner-offline":
        planner_cases = args.cases if args.cases != DEFAULT_CASES_PATH else PHASE5_CASES_PATH
        report = planner_offline_report(planner_cases)
    elif args.mode == "db-retrieval":
        report = retrieval_report(args.cases, args.variant)
    else:
        if not args.confirm_live:
            raise SystemExit("LIVE MODEL EVAL requires --confirm-live; no model quota was consumed.")
        report = live_report(args.cases, args.baseline, args.limit)
    if args.report:
        write_report(report, args.report)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
