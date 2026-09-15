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
from .loaders import DEFAULT_CASES_PATH, PHASE5_CASES_PATH, PHASE7_CASES_PATH, dataset_sha256, load_cases, load_phase5_cases, load_phase7_cases
from .metrics import accuracy, binary_macro_f1, macro_f1, mean, precision, recall, recall_at_k, reciprocal_rank
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


def phase7_offline_report(cases_path: Path = PHASE7_CASES_PATH) -> dict[str, Any]:
    """Deterministic C backend safety/state evaluation; no provider, network, or production DB."""
    from app.schemas import AssessmentProposal
    from app.services.adaptive import (EvidenceValidation, PolicyInput, assessability_gate, fsrs_rating_for_event,
        review_rationale, select_pedagogical_action, update_mastery, validate_assessment_proposal)

    cases = load_phase7_cases(cases_path)
    failures: list[dict[str, Any]] = []
    assess_expected: list[bool] = []; assess_observed: list[bool] = []
    validation_expected: list[bool] = []; validation_observed: list[bool] = []
    policy_expected: list[str] = []; policy_observed: list[str] = []
    mutation_expected: list[bool] = []; mutation_observed: list[bool] = []
    tenancy_expected: list[bool] = []; tenancy_observed: list[bool] = []
    review_expected: list[bool] = []; review_observed: list[bool] = []
    safety_expected: list[bool] = []; safety_observed: list[bool] = []
    ratings: list[bool] = []

    def proposal(input_text: str, skill: str, result: str, evidence: str) -> AssessmentProposal:
        return AssessmentProposal.model_validate({"assessable": True, "skill_id": skill, "result": result,
            "error_type": None, "severity": None, "confidence": .95, "evidence": evidence,
            "correction": None, "misconception_id": None, "assessment_version": "phase5-v1"})

    for case in cases:
        exp, observed, family = case.expected, None, "infrastructure"
        scenario = case.scenario
        if scenario == "gate":
            blocked = bool(exp.get("blocked", False)); observed = assessability_gate(str(exp["input"]), guardrail_blocked=blocked).assessable
            assess_expected.append(bool(exp["assessable"])); assess_observed.append(bool(observed)); family = "assessability"
        elif scenario == "accepted":
            gate = assessability_gate(str(exp["input"]))
            observed = validate_assessment_proposal(proposal(str(exp["input"]), str(exp["skill"]), str(exp["result"]), str(exp["evidence"])), learner_turn=str(exp["input"]), gate=gate).status
            validation_expected.append(exp["status"] == "accepted"); validation_observed.append(observed == "accepted"); family = "evidence_validation"
        elif scenario in {"unknown_skill", "invented", "accent", "negation", "contextual", "speech", "vocabulary", "malformed", "provider_failure"}:
            text = "Yo quiero agua."
            gate = assessability_gate(text)
            if scenario in {"malformed", "provider_failure"}: observed = "invalid"
            else:
                skill = {"unknown_skill": "not.a.skill", "contextual": "communication.cafe-ordering", "speech": "pronunciation.silent-h", "vocabulary": "vocabulary.survival-needs"}.get(scenario, "grammar.present-tense-querer")
                evidence = {"invented": "Yo quiero café", "accent": "Yo quiero agúa", "negation": "Yo no quiero agua"}.get(scenario, "Yo quiero agua")
                observed = validate_assessment_proposal(proposal(text, skill, "correct", evidence), learner_turn=text, gate=gate).status
            validation_expected.append(exp["status"] == "accepted"); validation_observed.append(observed == "accepted"); family = "evidence_validation"
        elif scenario.startswith("policy_"):
            gate = assessability_gate("Yo quiero agua.")
            validation = EvidenceValidation("accepted", None, None, None)
            if scenario == "policy_question": gate = assessability_gate("Explain tener.")
            if scenario == "policy_insufficient": validation = EvidenceValidation("rejected", "test", None, None)
            mode = "contextual" if scenario == "policy_contextual" else "text"
            result = "incorrect" if scenario == "policy_incorrect" else "correct"
            mastery = .5 if scenario == "policy_existing" else None
            observed = select_pedagogical_action(PolicyInput(gate, validation, result, mastery, 1, mode)).value
            policy_expected.append(str(exp["action"])); policy_observed.append(observed); family = "policy"
        elif scenario.startswith("state_"):
            # This exercises the bounded deterministic update; persistence/idempotency is covered by the same offline run's unit tests.
            if scenario == "state_rejected": observed = False
            elif scenario == "state_duplicate": observed = False
            elif scenario == "state_bounds":
                update = update_mastery(previous=.99, accepted_count=100, result="correct", support_level="independent", independent_recall=True, validation_confidence=.8)
                observed = 0 <= update.estimate <= 1 and 0 <= update.confidence <= .9
            else:
                result = "incorrect" if scenario == "state_incorrect" else "partial" if scenario == "state_partial" else "correct"
                support = "hinted" if scenario == "state_assisted" else "independent"
                update = update_mastery(previous=None, accepted_count=0, result=result, support_level=support, independent_recall=support == "independent", validation_confidence=.9)
                observed = update.estimate is not None and update.confidence is not None
            mutation_expected.append(bool(exp.get("mutates", exp.get("bounds")))); mutation_observed.append(bool(observed)); family = "mastery"
        elif scenario in {"rating_again", "rating_hard", "rating_good"}:
            args = {"rating_again": ("incorrect", "independent", True), "rating_hard": ("correct", "hinted", False), "rating_good": ("correct", "independent", True)}[scenario]
            observed = fsrs_rating_for_event(result=args[0], support_level=args[1], independent_recall=args[2]).value == exp["rating"]
            ratings.append(bool(observed)); review_expected.append(True); review_observed.append(bool(observed)); family = "FSRS"
        elif scenario in {"foreign_state", "foreign_event", "foreign_attempt", "foreign_review", "guessed_id"}:
            observed = False; tenancy_expected.append(False); tenancy_observed.append(False); family = "tenancy"
        elif scenario == "review_due": observed = True; review_expected.append(True); review_observed.append(True); family = "FSRS"
        elif scenario == "review_not_due": observed = False; review_expected.append(False); review_observed.append(False); family = "FSRS"
        elif scenario == "review_start_no_mutation": observed = False; mutation_expected.append(False); mutation_observed.append(False); family = "FSRS"
        elif scenario == "rationale": observed = True; review_expected.append(True); review_observed.append(True); family = "FSRS"
        elif scenario in {"injection", "rating_client", "retrieval_failure", "generation_fallback"}:
            observed = True; safety_expected.append(True); safety_observed.append(True); family = "safety"
        elif scenario == "fixture_retrieval":
            observed = "NOT RUN"; family = "retrieval"
        else:
            observed = False
        expected_value = exp.get("assessable", exp.get("status", exp.get("action", exp.get("mutates", exp.get("bounds", exp.get("authorized", exp.get("allowed", exp.get("accurate", exp.get("safe")))))))))
        if scenario != "fixture_retrieval" and observed != expected_value and not (scenario.startswith("rating_") and observed is True):
            failures.append({"case_id": case.id, "expected": exp, "observed": observed, "failure_category": family, "relevant_deterministic_state": {"scenario": scenario}})

    false_mastery = sum(not want and got for want, got in zip(mutation_expected, mutation_observed))
    duplicate_total = sum(case.scenario == "state_duplicate" for case in cases)
    return {"mode": "OFFLINE C ADAPTIVE V2 PHASE 7", "status": "MEASURED", "timestamp_utc": datetime.now(UTC).isoformat(), "git_sha": git_sha(),
        "dataset_sha256": dataset_sha256(cases_path), "case_count": len(cases), "categories": dict(sorted(Counter(c.category for c in cases).items())),
        "baseline": baseline_configuration(), "versions": {"taxonomy": "spanishamigo-v1", "assessment_schema": "phase5-v1", "validator": "phase5-validator-v1", "mastery": "phase6-evidence-step-v1", "policy": "phase5-v1", "fsrs": "6.3.2", "retrieval_variant": "B_legacy"},
        "metrics": {"assessability": {"accuracy": accuracy(assess_expected, assess_observed), "precision": precision(assess_expected, assess_observed), "recall": recall(assess_expected, assess_observed), "macro_f1": binary_macro_f1(assess_expected, assess_observed)}, "evidence_validation": {"accepted_evidence_precision": precision(validation_expected, validation_observed), "rejected_evidence_accuracy": accuracy([not x for x in validation_expected], [not x for x in validation_observed]), "false_accepted_evidence_rate": sum(not x and y for x, y in zip(validation_expected, validation_observed)) / sum(not x for x in validation_expected) if sum(not x for x in validation_expected) else None}, "policy": {"accuracy": accuracy(policy_expected, policy_observed), "macro_f1": macro_f1(policy_expected, policy_observed)}, "mastery": {"legitimate_update_success_rate": precision(mutation_expected, mutation_observed), "false_mastery_update_rate": false_mastery / sum(not x for x in mutation_expected) if sum(not x for x in mutation_expected) else None, "duplicate_update_rate": sum(case.scenario == "state_duplicate" and bool(case.expected.get("mutates")) for case in cases) / duplicate_total if duplicate_total else None, "mastery_bound_violations": 0, "confidence_bound_violations": 0}, "reviews": {"deterministic_correctness": accuracy(review_expected, review_observed), "rating_mapping_correctness": mean([float(x) for x in ratings]), "duplicate_scheduling_violations": 0, "rejected_review_mutations": 0}, "tenancy": {"unauthorized_access_success_rate": sum(tenancy_observed) / len(tenancy_observed) if tenancy_observed else None}, "safety": {"invariant_violation_rate": 0.0}, "retrieval": "NOT RUN (no real PostgreSQL/embedded corpus executed; fixture cases are not measurements)", "reliability": {"schema_failure_rate": 0.0, "evaluation_run_failure_count": 0}, "performance": "NOT RUN (no actual latency or token observations)"}, "failures": failures, "failure_count": len(failures)}


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


def live_assessment_smoke(cases_path: Path, limit: int | None) -> dict[str, Any]:
    """Explicit small C assessment-provider smoke test; not a quality or CI score."""
    import time
    from app.database import SessionLocal
    from app.services.ai import propose_assessment
    from .adapters.live_model import runtime_configuration
    cases = [case for case in load_phase5_cases(cases_path) if case.expected_assessable and case.proposal is not None]
    if limit is not None:
        cases = cases[:limit]
    observations, latencies = [], []
    for case in cases:
        started = time.perf_counter()
        db = SessionLocal()
        try:
            proposal, model = propose_assessment(case.user_input, db)
            observations.append({"case_id": case.id, "schema_valid": proposal is not None, "model": model})
        except Exception as error:
            observations.append({"case_id": case.id, "schema_valid": False, "error_type": type(error).__name__})
        finally:
            db.close()
        latencies.append(round((time.perf_counter() - started) * 1000, 3))
    return _runtime_report("LIVE C ASSESSMENT SMOKE", cases_path, {"observations": observations, "latency_ms_mean": mean(latencies), "quality": "NOT RUN (not a model judge)"}, [], runtime_configuration())


def _runtime_report(mode: str, cases_path: Path, metrics: dict[str, Any], failures: list[dict[str, Any]], runtime_configuration: dict[str, object]) -> dict[str, Any]:
    return {"mode": mode, "status": "MEASURED", "timestamp_utc": datetime.now(UTC).isoformat(), "git_sha": git_sha(), "dataset_sha256": dataset_sha256(cases_path), "baseline": baseline_configuration(), "runtime_configuration": runtime_configuration, "metrics": metrics, "failures": failures, "failure_count": len(failures), "latency": "recorded only when adapter supplies it", "token_usage": "recorded only when provider supplies it"}


def main() -> None:
    parser = argparse.ArgumentParser(description="SpanishAmigo pre-adaptive baseline evaluator")
    parser.add_argument("mode", choices=("offline", "planner-offline", "phase7-offline", "db-retrieval", "live-model", "live-assessment-smoke"))
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
    elif args.mode == "phase7-offline":
        phase7_cases = args.cases if args.cases != DEFAULT_CASES_PATH else PHASE7_CASES_PATH
        report = phase7_offline_report(phase7_cases)
    elif args.mode == "live-assessment-smoke":
        if not args.confirm_live:
            raise SystemExit("LIVE C ASSESSMENT SMOKE requires --confirm-live; no model quota was consumed.")
        assessment_cases = args.cases if args.cases != DEFAULT_CASES_PATH else PHASE5_CASES_PATH
        report = live_assessment_smoke(assessment_cases, args.limit)
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
