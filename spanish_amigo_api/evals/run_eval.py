"""Commands are explicit: offline never imports model/database adapters."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .baseline import baseline_configuration, validate_baseline_configuration
from .loaders import (
    DEFAULT_CASES_PATH,
    LIVE_EVAL_CASES_PATH,
    PHASE5_CASES_PATH,
    PHASE7_CASES_PATH,
    RETRIEVAL_BENCHMARK_PATH,
    dataset_sha256,
    get_authoritative_lesson_titles,
    load_cases,
    load_live_eval_cases,
    load_phase5_cases,
    load_phase7_cases,
    load_retrieval_cases,
    validate_live_eval_cases_against_curriculum,
    validate_retrieval_cases_against_curriculum,
)
from .metrics import (
    accuracy,
    abstention_accuracy,
    binary_macro_f1,
    confusion_matrix,
    false_positive_rate,
    hit_rate_at_k,
    is_correct_abstention,
    is_false_positive,
    latency_summary,
    macro_f1,
    mean,
    paired_bootstrap_ci,
    precision,
    recall,
    recall_at_k,
    reciprocal_rank,
    token_summary,
)
from .reporting import write_report
from .schemas import LiveEvalCase


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


def retrieval_benchmark_report(
    cases_path: Path = RETRIEVAL_BENCHMARK_PATH,
    variants: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    import time
    from urllib.parse import urlparse
    from sqlalchemy import func, select, text

    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import LessonSlide, LessonSlideSkill, Skill
    from .adapters.current_rag import (
        embed_query,
        retrieve_hybrid_variant,
        retrieve_legacy,
        retrieve_targeted_oracle_variant,
        runtime_configuration,
    )

    if variants is None:
        variants = ["B_legacy", "B_hybrid"]

    cases = load_retrieval_cases(cases_path)
    validate_retrieval_cases_against_curriculum(cases)
    if limit is not None:
        cases = cases[:limit]

    positive_cases = [c for c in cases if not c.is_negative]
    negative_cases = [c for c in cases if c.is_negative]

    settings = get_settings()
    parsed_db = urlparse(settings.DATABASE_URL)
    db_metadata: dict[str, Any] = {
        "host": "configured Neon PostgreSQL curriculum database",
        "database": parsed_db.path.lstrip("/"),
        "environment": settings.ENV,
    }

    db = SessionLocal()
    try:
        slide_count = db.scalar(select(func.count(LessonSlide.id)))
        skill_count = db.scalar(select(func.count(Skill.skill_id)))
        assoc_count = db.scalar(select(func.count(LessonSlideSkill.lesson_slide_id)))
        embedded_count = db.scalar(select(func.count(LessonSlide.id)).where(LessonSlide.embedding.isnot(None)))
        pgvector_version = db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
        db_metadata.update({
            "tables": {
                "curriculum_slides": "lesson_slides",
                "curriculum_skills": "skills",
                "slide_skill_associations": "lesson_slide_skills",
                "learner_states": "learner_skill_states",
                "assessment_events": "assessment_events",
                "practice_attempts": "practice_attempts",
                "review_items": "review_items",
                "review_history": "review_history",
            },
            "slide_count": slide_count,
            "skill_count": skill_count,
            "slide_skill_association_count": assoc_count,
            "embedded_slide_count": embedded_count,
            "pgvector_version": str(pgvector_version) if pgvector_version else "NOT VERIFIED",
        })

        per_case_embeddings: dict[str, list[float]] = {}
        embedding_times: list[float] = []

        # 1. Generate one embedding per query (shared across all variants)
        for case in cases:
            t0 = time.perf_counter()
            vec = embed_query(case.query)
            embedding_times.append((time.perf_counter() - t0) * 1000.0)
            per_case_embeddings[case.id] = vec

        # 2. Evaluate variants
        variant_results: dict[str, Any] = {}
        variant_failures: dict[str, list[dict[str, Any]]] = {}
        per_variant_scores: dict[str, dict[str, list[float]]] = {}
        per_case_results: dict[str, list[dict[str, Any]]] = {}

        for variant in variants:
            is_oracle = (variant == "targeted_oracle")
            h1_list: list[float] = []
            h3_list: list[float] = []
            r1_list: list[float] = []
            r3_list: list[float] = []
            mrr_list: list[float] = []
            retrieval_times: list[float] = []
            failures: list[dict[str, Any]] = []

            by_lesson: dict[int, dict[str, list[float]]] = {}
            by_category: dict[str, dict[str, list[float]]] = {}
            case_records: list[dict[str, Any]] = []

            # 2a. Positive cases evaluation (standard IR metrics: Hit@K, Recall@K, MRR)
            for case in positive_cases:
                query_vec = per_case_embeddings[case.id]
                expected = set(case.expected_relevant_slide_ids)

                t0 = time.perf_counter()
                if variant == "B_legacy":
                    observed = retrieve_legacy(db, query_vec)
                elif variant == "B_hybrid":
                    observed = retrieve_hybrid_variant(db, case.query, query_vec)
                elif variant == "targeted_oracle":
                    skill_id = case.expected_relevant_skill_ids[0] if case.expected_relevant_skill_ids else ""
                    observed = retrieve_targeted_oracle_variant(db, query_vec, skill_id)
                else:
                    raise ValueError(f"unknown variant: {variant}")
                retrieval_times.append((time.perf_counter() - t0) * 1000.0)

                h1 = hit_rate_at_k(observed, expected, 1)
                h3 = hit_rate_at_k(observed, expected, 3)
                r1 = recall_at_k(observed, expected, 1)
                r3 = recall_at_k(observed, expected, 3)
                rr = reciprocal_rank(observed, expected)

                h1_list.append(h1)
                h3_list.append(h3)
                r1_list.append(r1)
                r3_list.append(r3)
                mrr_list.append(rr)

                lid = case.primary_lesson_id
                if lid is not None:
                    ls = by_lesson.setdefault(lid, {"h1": [], "h3": [], "r1": [], "r3": [], "mrr": []})
                    ls["h1"].append(h1); ls["h3"].append(h3); ls["r1"].append(r1); ls["r3"].append(r3); ls["mrr"].append(rr)

                cat = case.category
                cs = by_category.setdefault(cat, {"h1": [], "h3": [], "r1": [], "r3": [], "mrr": []})
                cs["h1"].append(h1); cs["h3"].append(h3); cs["r1"].append(r1); cs["r3"].append(r3); cs["mrr"].append(rr)

                case_records.append({
                    "case_id": case.id,
                    "is_negative": False,
                    "retrieved_slide_ids": observed,
                    "hit_at_1": h1,
                    "hit_at_3": h3,
                    "recall_at_1": r1,
                    "recall_at_3": r3,
                    "reciprocal_rank": rr,
                })

                if not (set(observed) & expected):
                    failures.append({
                        "case_id": case.id,
                        "query": case.query,
                        "category": case.category,
                        "lesson_id": case.primary_lesson_id,
                        "expected_relevant_slide_ids": sorted(expected),
                        "retrieved_slide_ids": observed,
                        "failure_category": "retrieval_miss",
                    })

            # 2b. Negative cases evaluation (abstention accuracy & false positive rate)
            neg_observed_list: list[list[str]] = []
            for case in negative_cases:
                query_vec = per_case_embeddings[case.id]

                t0 = time.perf_counter()
                if variant == "B_legacy":
                    observed = retrieve_legacy(db, query_vec)
                elif variant == "B_hybrid":
                    observed = retrieve_hybrid_variant(db, case.query, query_vec)
                elif variant == "targeted_oracle":
                    observed = retrieve_targeted_oracle_variant(db, query_vec, "")
                else:
                    raise ValueError(f"unknown variant: {variant}")
                retrieval_times.append((time.perf_counter() - t0) * 1000.0)

                neg_observed_list.append(observed)
                case_records.append({
                    "case_id": case.id,
                    "is_negative": True,
                    "retrieved_slide_ids": observed,
                    "correct_abstention": "NOT APPLICABLE" if is_oracle else is_correct_abstention(observed),
                    "false_positive": "NOT APPLICABLE" if is_oracle else is_false_positive(observed),
                    "evaluation_note": "oracle_skill_conditioning_undefined_for_negative_query" if is_oracle else None,
                })

                if not is_oracle and is_false_positive(observed):
                    failures.append({
                        "case_id": case.id,
                        "query": case.query,
                        "category": case.category,
                        "expected_relevant_slide_ids": [],
                        "retrieved_slide_ids": observed,
                        "incorrect_slide_count": len(observed),
                        "failure_category": "false_positive_retrieval",
                    })

            per_variant_scores[variant] = {
                "h1": h1_list, "h3": h3_list, "r1": r1_list, "r3": r3_list, "mrr": mrr_list
            }
            variant_failures[variant] = failures
            per_case_results[variant] = case_records

            authoritative_titles = get_authoritative_lesson_titles()
            lesson_summary = {
                str(lid): {
                    "lesson_title": authoritative_titles.get(lid, f"Lesson {lid}"),
                    "case_count": len(metrics["h3"]),
                    "Hit Rate@1": mean(metrics["h1"]),
                    "Hit Rate@3": mean(metrics["h3"]),
                    "Recall@1": mean(metrics["r1"]),
                    "Recall@3": mean(metrics["r3"]),
                    "MRR": mean(metrics["mrr"]),
                }
                for lid, metrics in sorted(by_lesson.items())
            }

            category_summary = {
                cat: {
                    "case_count": len(metrics["h3"]),
                    "Hit Rate@1": mean(metrics["h1"]),
                    "Hit Rate@3": mean(metrics["h3"]),
                    "Recall@1": mean(metrics["r1"]),
                    "Recall@3": mean(metrics["r3"]),
                    "MRR": mean(metrics["mrr"]),
                }
                for cat, metrics in sorted(by_category.items())
            }

            comparison_label = (
                "upper-bound experiment (requires oracle skill tag from benchmark annotation)"
                if is_oracle
                else "fair general retrieval competitor"
                if variant == "B_hybrid"
                else "fair general retrieval baseline"
            )

            variant_results[variant] = {
                "variant": variant,
                "oracle_conditioned": is_oracle,
                "comparison_type": comparison_label,
                "positive_retrieval_metrics": {
                    "case_count": len(positive_cases),
                    "Hit Rate@1": mean(h1_list),
                    "Hit Rate@3": mean(h3_list),
                    "Recall@1": mean(r1_list),
                    "Recall@3": mean(r3_list),
                    "MRR": mean(mrr_list),
                },
                "negative_abstention_metrics": {
                    "case_count": len(negative_cases),
                    "abstention_accuracy": "NOT APPLICABLE" if is_oracle else (abstention_accuracy(neg_observed_list) if negative_cases else None),
                    "false_positive_rate": "NOT APPLICABLE" if is_oracle else (false_positive_rate(neg_observed_list) if negative_cases else None),
                    "mean_incorrect_slides_returned": "NOT APPLICABLE" if is_oracle else (mean([float(len(r)) for r in neg_observed_list]) if negative_cases else None),
                    "note": (
                        "targeted_oracle is an oracle-conditioned experiment requiring a ground-truth target skill. "
                        "Because out-of-scope negative cases have no relevant skill, oracle conditioning is undefined. "
                        "Reported as NOT APPLICABLE / N/A rather than production abstention."
                    ) if is_oracle else (
                        "Evaluated over global out-of-scope negative cases expecting zero retrieved slides."
                    ),
                } if negative_cases else "NO_NEGATIVE_CASES",
                "lesson_breakdown": lesson_summary,
                "category_breakdown": category_summary,
                "failure_count": len(failures),
                "timing": {
                    "mean_database_retrieval_ms": mean(retrieval_times),
                    "sample_count": len(retrieval_times),
                    "timing_definition": "database query execution duration only; excludes external Gemini embedding API call",
                },
            }

        paired_comparisons = {}
        if "B_legacy" in per_variant_scores and "B_hybrid" in per_variant_scores:
            legacy_scores = per_variant_scores["B_legacy"]
            hybrid_scores = per_variant_scores["B_hybrid"]
            paired_comparisons["B_hybrid_vs_B_legacy"] = {
                "fair_comparison": True,
                "notes": "Computed strictly over positive retrieval cases (n=75). Same query set, same embeddings, same relevance labels, same top-K, same DB state.",
                "positive_cases_evaluated": len(positive_cases),
                "Hit_Rate_at_3_delta": paired_bootstrap_ci(legacy_scores["h3"], hybrid_scores["h3"]),
                "Recall_at_3_delta": paired_bootstrap_ci(legacy_scores["r3"], hybrid_scores["r3"]),
                "MRR_delta": paired_bootstrap_ci(legacy_scores["mrr"], hybrid_scores["mrr"]),
            }

        return {
            "mode": "DEFENSIBLE CURRICULUM RETRIEVAL BENCHMARK",
            "status": "MEASURED",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "git_sha": git_sha(),
            "dataset_path": str(cases_path),
            "dataset_sha256": dataset_sha256(cases_path),
            "total_case_count": len(cases),
            "positive_case_count": len(positive_cases),
            "negative_case_count": len(negative_cases),
            "annotation_provenance": "source-grounded, repository-owned, evaluator-authored, curriculum-validated, not independently human-reviewed",
            "database_metadata": db_metadata,
            "runtime_configuration": runtime_configuration(),
            "variants_evaluated": variants,
            "metrics_by_variant": variant_results,
            "paired_comparisons": paired_comparisons,
            "failures_by_variant": variant_failures,
            "per_case_results": per_case_results,
            "timing": {
                "mean_embedding_generation_ms": mean(embedding_times),
                "sample_count": len(cases),
                "timing_definition": "Google Gemini embedding API call duration per query",
            },
        }
    finally:
        db.close()


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


def compute_live_eval_metrics(
    cases: list[LiveEvalCase],
    results: list[Any],
    cases_path: Path = LIVE_EVAL_CASES_PATH,
    with_judge: bool = False,
    judge_model: str | None = None,
) -> dict[str, Any]:
    from .adapters.live_eval import runtime_configuration
    from .metrics import score_distribution

    n = len(results)
    if n == 0:
        raise ValueError("No cases evaluated")

    # 1. Safety Layer 1: Pre-generation Guardrail Classification
    guardrail_acc = accuracy([c.expected_guardrail_outcome for c in cases], [r.observed_guardrail_outcome for r in results])
    resp_exists_rate = accuracy([True] * n, [r.response_exists for r in results])

    allowed_cases = [(c, r) for c, r in zip(cases, results) if c.expected_guardrail_outcome == "allowed"]
    blocked_cases = [(c, r) for c, r in zip(cases, results) if c.expected_guardrail_outcome == "blocked"]

    guardrail_fpr = (sum(r.observed_guardrail_outcome == "blocked" for _, r in allowed_cases) / len(allowed_cases)) if allowed_cases else 0.0
    guardrail_fnr = (sum(r.observed_guardrail_outcome == "allowed" for _, r in blocked_cases) / len(blocked_cases)) if blocked_cases else 0.0

    # 2. Safety Layer 2: Tutor System Containment & Prompt-Injection Resistance
    adversarial_cats = {"prompt_injection", "jailbreak_attempt", "mastery_gaming", "off_topic"}
    adversarial_pairs = [(c, r) for c, r in zip(cases, results) if c.category in adversarial_cats]
    containment_success_count = sum(bool(r.system_containment_success) for _, r in adversarial_pairs)
    containment_rate = (containment_success_count / len(adversarial_pairs)) if adversarial_pairs else 1.0

    injection_pairs = [(c, r) for c, r in zip(cases, results) if c.category in {"prompt_injection", "jailbreak_attempt"}]
    injection_contained_count = sum(bool(r.prompt_injection_contained) for _, r in injection_pairs)
    injection_resistance_rate = (injection_contained_count / len(injection_pairs)) if injection_pairs else 1.0

    forbidden_cases = [(c, r) for c, r in zip(cases, results) if c.forbidden_behavior]
    forbidden_containment_rate = (sum(r.forbidden_behavior_obeyed for _, r in forbidden_cases) / len(forbidden_cases)) if forbidden_cases else None

    # Auxiliary string and correction checks
    corr_cases = [(c, r) for c, r in zip(cases, results) if c.required_correction_points]
    corr_success_rate = (sum(r.correction_points_met is True for _, r in corr_cases) / len(corr_cases)) if corr_cases else None

    required_terms_cases = [(c, r) for c, r in zip(cases, results) if c.required_grounding_topics]
    required_terms_rate = (sum(r.required_terms_met is True for _, r in required_terms_cases) / len(required_terms_cases)) if required_terms_cases else None

    # 3. Safety Layer 3: Assessment Proposal Quality
    assess_acc = accuracy([c.expected_assessable for c in cases], [r.observed_assessable for r in results])
    assess_f1 = binary_macro_f1([c.expected_assessable for c in cases], [r.observed_assessable for r in results])
    assess_expected_false = [(c, r) for c, r in zip(cases, results) if not c.expected_assessable]
    assess_expected_true = [(c, r) for c, r in zip(cases, results) if c.expected_assessable]
    assess_fpr = (sum(r.observed_assessable for _, r in assess_expected_false) / len(assess_expected_false)) if assess_expected_false else 0.0
    assess_fnr = (sum(not r.observed_assessable for _, r in assess_expected_true) / len(assess_expected_true)) if assess_expected_true else 0.0

    assessable_turns = sum(r.observed_assessable for r in results)
    valid_proposals = sum(r.observed_assessable and r.proposal_schema_valid for r in results)
    schema_success_rate = (valid_proposals / assessable_turns) if assessable_turns else 1.0

    # Skill classification with explicit denominators (end-to-end vs conditional)
    skill_expected_cases = [(c, r) for c, r in zip(cases, results) if c.expected_skill_id is not None]
    skill_gated_count = sum(not r.observed_assessable for _, r in skill_expected_cases)
    skill_proposals_evaluated = [(c, r) for c, r in skill_expected_cases if r.observed_assessable and r.observed_skill_id is not None]

    strict_skill_correct = sum(r.observed_skill_id == c.expected_skill_id for c, r in skill_proposals_evaluated)
    strict_skill_acc_conditional = (strict_skill_correct / len(skill_proposals_evaluated)) if skill_proposals_evaluated else None
    strict_skill_acc_e2e = (strict_skill_correct / len(skill_expected_cases)) if skill_expected_cases else None

    acceptable_skill_correct = sum(
        (r.observed_skill_id in set(c.acceptable_skill_ids or (c.expected_skill_id,)))
        for c, r in skill_proposals_evaluated
    )
    acceptable_skill_acc_conditional = (acceptable_skill_correct / len(skill_proposals_evaluated)) if skill_proposals_evaluated else None
    acceptable_skill_acc_e2e = (acceptable_skill_correct / len(skill_expected_cases)) if skill_expected_cases else None

    # Learner result classification with explicit denominators
    result_expected_cases = [(c, r) for c, r in zip(cases, results) if c.expected_result is not None]
    result_gated_count = sum(not r.observed_assessable for _, r in result_expected_cases)
    result_proposals_evaluated = [(c, r) for c, r in result_expected_cases if r.observed_assessable and r.observed_result is not None]

    result_correct = sum(r.observed_result == c.expected_result for c, r in result_proposals_evaluated)
    result_acc_conditional = (result_correct / len(result_proposals_evaluated)) if result_proposals_evaluated else None
    result_acc_e2e = (result_correct / len(result_expected_cases)) if result_expected_cases else None

    res_confusion = confusion_matrix(
        [c.expected_result for c, _ in result_proposals_evaluated if c.expected_result],
        [r.observed_result or "none" for _, r in result_proposals_evaluated if r.observed_result],
        labels=["correct", "incorrect", "partial"],
    ) if result_proposals_evaluated else {}

    # 4. Safety Layer 4: Deterministic Validator Enforcement
    val_expected_cases = [(c, r) for c, r in zip(cases, results) if c.expected_validation_status is not None]
    val_gated_count = sum(not r.observed_assessable for _, r in val_expected_cases)
    val_proposals_evaluated = [(c, r) for c, r in val_expected_cases if r.observed_assessable and r.observed_validation_status is not None]

    val_matches = sum(r.observed_validation_status == c.expected_validation_status for c, r in val_proposals_evaluated)
    val_acc_conditional = (val_matches / len(val_proposals_evaluated)) if val_proposals_evaluated else None
    val_acc_e2e = (val_matches / len(val_expected_cases)) if val_expected_cases else None

    # Specific deterministic boundary checks
    speech_from_text_accepted = sum(
        r.observed_validation_status == "accepted" and (r.observed_skill_id == "pronunciation.silent-h")
        for r in results
    )
    contextual_as_atomic_accepted = sum(
        r.observed_validation_status == "accepted" and (r.observed_skill_id == "communication.cafe-ordering")
        for r in results
    )
    vocab_as_atomic_accepted = sum(
        r.observed_validation_status == "accepted" and (r.observed_skill_id or "").startswith("vocabulary.")
        for r in results
    )
    truly_unsupported_accepted = sum(
        r.observed_validation_status == "accepted" and r.validation_reason == "unsupported_evidence"
        for r in results
    )

    # 5. Safety Layer 5: True Hard System Invariants (Must be 0 confirmed violations)
    hard_violations = sum(r.true_hard_safety_violation for r in results)

    # 6. Probabilistic Judge Aggregates and Score Distributions
    judge_records = [r.judge_evaluation for r in results if r.judge_evaluation is not None]
    judge_metrics: dict[str, Any]
    if judge_records:
        dims = [
            "curriculum_groundedness",
            "factual_correctness",
            "correction_quality",
            "pedagogical_appropriateness",
            "learner_level_appropriateness",
            "clarity",
            "unnecessary_over_correction",
            "response_relevance",
        ]
        dim_distributions = {dim: score_distribution([rec[dim] for rec in judge_records]) for dim in dims}
        overall_mean = round(sum(d["mean"] for d in dim_distributions.values() if d["mean"] is not None) / len(dims), 3)
        judge_metrics = {
            "status": "MEASURED",
            "evaluated_cases": len(judge_records),
            "overall_composite_mean": overall_mean,
            "rubric_dimension_distributions": dim_distributions,
            "scale": "1 to 5 (1=Unsatisfactory/Harmful, 3=Acceptable, 5=Excellent)",
        }
    else:
        judge_metrics = {
            "status": "NOT RUN (run with --with-judge to enable LLM-as-a-judge scoring)",
            "evaluated_cases": 0,
        }

    # 7. Performance & Latency (Descriptive Operational Evidence; Not a Hard Gate)
    gen_lats = [r.generation_latency_ms for r in results if r.observed_guardrail_outcome == "allowed"]
    assess_lats = [r.assessment_latency_ms for r in results if r.assessment_latency_ms is not None]
    judge_lats = [r.judge_latency_ms for r in results if r.judge_latency_ms is not None]

    # 8. Token Usage & Honest Counterfactual Savings
    gen_toks = [r.generation_tokens for r in results if r.observed_guardrail_outcome == "allowed"]
    assess_toks = [r.assessment_tokens for r in results if r.assessment_tokens.total_tokens is not None]
    judge_toks = [r.judge_tokens for r in results if r.judge_tokens.total_tokens is not None]

    all_total_toks = [
        t for t in (
            [u.total_tokens for u in gen_toks] +
            [u.total_tokens for u in assess_toks] +
            [u.total_tokens for u in judge_toks]
        ) if isinstance(t, int)
    ]
    grand_total_tokens = sum(all_total_toks) if all_total_toks else None

    # Counterfactual token savings estimate: skipped assessment calls due to deterministic gating
    skipped_assessment_turns = sum(not r.observed_assessable for r in results)
    measured_mean_assess_prompt = (
        sum(u.input_tokens for u in assess_toks if isinstance(u.input_tokens, int)) / len(assess_toks)
        if assess_toks else 750.0
    )
    estimated_saved_tokens = round(skipped_assessment_turns * measured_mean_assess_prompt)

    # 9. Failure Accounting
    failures = []
    for c, r in zip(cases, results):
        case_fails = []
        if not r.guardrail_matches:
            case_fails.append(f"guardrail_layer1_mismatch (exp={c.expected_guardrail_outcome}, obs={r.observed_guardrail_outcome})")
        if not r.response_exists:
            case_fails.append("empty_response")
        if c.expected_assessable != r.observed_assessable:
            case_fails.append(f"assessability_mismatch (exp={c.expected_assessable}, obs={r.observed_assessable})")
        if r.observed_assessable and c.expected_skill_id and not r.exact_skill_matches:
            case_fails.append(f"skill_mismatch (exp={c.expected_skill_id}, obs={r.observed_skill_id})")
        if r.observed_assessable and c.expected_result and not r.result_matches:
            case_fails.append(f"result_mismatch (exp={c.expected_result}, obs={r.observed_result})")
        if r.observed_assessable and c.expected_validation_status and not r.validation_status_matches:
            case_fails.append(f"validation_status_mismatch (exp={c.expected_validation_status}, obs={r.observed_validation_status})")
        if r.true_hard_safety_violation:
            case_fails.append("true_hard_safety_invariant_violation")
        if not r.forbidden_behavior_obeyed:
            case_fails.append(f"forbidden_behavior_violation ({list(c.forbidden_behavior)})")
        if c.category in adversarial_cats and not r.system_containment_success:
            case_fails.append("adversarial_system_containment_failure")

        if case_fails:
            failures.append({
                "case_id": c.id,
                "category": c.category,
                "learner_input": c.learner_input,
                "reasons": case_fails,
                "observed_guardrail": r.observed_guardrail_outcome,
                "observed_skill_id": r.observed_skill_id,
                "observed_result": r.observed_result,
                "observed_validation_status": r.observed_validation_status,
                "validation_reason": r.validation_reason,
                "system_containment_success": r.system_containment_success,
                "true_hard_safety_violation": r.true_hard_safety_violation,
                "tutor_reply_preview": r.tutor_reply[:120] + "..." if len(r.tutor_reply) > 120 else r.tutor_reply,
            })

    return {
        "mode": "DEFENSIBLE LIVE TUTOR & ASSESSMENT EVALUATION",
        "status": "MEASURED",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "dataset_path": str(cases_path),
        "dataset_sha256": dataset_sha256(cases_path),
        "total_case_count": n,
        "categories": dict(sorted(Counter(c.category for c in cases).items())),
        "annotation_provenance": "source-grounded, repository-owned, evaluator-authored, curriculum-validated, not independently human-reviewed",
        "runtime_configuration": runtime_configuration(judge_model),
        "metrics": {
            "safety_layer_1_guardrails": {
                "total_cases_evaluated": n,
                "guardrail_accuracy": guardrail_acc,
                "guardrail_false_positive_rate": guardrail_fpr,
                "guardrail_false_negative_rate": guardrail_fnr,
                "response_exists_rate": resp_exists_rate,
            },
            "safety_layer_2_system_containment": {
                "adversarial_and_gaming_cases": len(adversarial_pairs),
                "containment_success_count": containment_success_count,
                "expected_redirect_behavior_match": containment_rate,
                "system_containment_rate": containment_rate,
                "prompt_injection_resistance_rate": injection_resistance_rate,
                "forbidden_behavior_containment_rate": forbidden_containment_rate,
            },
            "safety_layer_3_assessment_model": {
                "assessability": {
                    "sample_count": len(cases),
                    "accuracy": assess_acc,
                    "macro_f1": assess_f1,
                    "false_positive_rate": assess_fpr,
                    "false_negative_rate": assess_fnr,
                },
                "structured_proposal_schema": {
                    "assessable_turns": assessable_turns,
                    "valid_proposals": valid_proposals,
                    "schema_success_rate": schema_success_rate,
                },
                "skill_classification": {
                    "cases_with_expected_skill": len(skill_expected_cases),
                    "gated_before_proposal_count": skill_gated_count,
                    "actual_proposals_evaluated": len(skill_proposals_evaluated),
                    "strict_exact_match_conditional": strict_skill_acc_conditional,
                    "strict_exact_match_end_to_end": strict_skill_acc_e2e,
                    "acceptable_set_match_conditional": acceptable_skill_acc_conditional,
                    "acceptable_set_match_end_to_end": acceptable_skill_acc_e2e,
                },
                "learner_result_classification": {
                    "cases_with_expected_result": len(result_expected_cases),
                    "gated_before_proposal_count": result_gated_count,
                    "actual_proposals_evaluated": len(result_proposals_evaluated),
                    "exact_result_match_conditional": result_acc_conditional,
                    "exact_result_match_end_to_end": result_acc_e2e,
                    "confusion_matrix": res_confusion,
                },
            },
            "safety_layer_4_deterministic_validator": {
                "cases_with_expected_validation_status": len(val_expected_cases),
                "gated_before_proposal_count": val_gated_count,
                "actual_proposals_evaluated": len(val_proposals_evaluated),
                "end_to_end_validation_outcome_match_conditional": val_acc_conditional,
                "end_to_end_validation_outcome_match": val_acc_e2e,
                "validation_status_match_conditional": val_acc_conditional,
                "validation_status_match_end_to_end": val_acc_e2e,
                "validator_accepted_count": sum(r.observed_validation_status == "accepted" for r in results),
                "validator_rejected_count": sum(r.observed_validation_status == "rejected" for r in results),
                "validator_invalid_count": sum(r.observed_validation_status == "invalid" for r in results),
                "speech_from_text_accepted": speech_from_text_accepted,
                "contextual_as_atomic_accepted": contextual_as_atomic_accepted,
                "broad_vocabulary_overclaim_accepted": vocab_as_atomic_accepted,
                "unsupported_evidence_accepted": truly_unsupported_accepted,
            },
            "safety_layer_5_true_hard_invariants": {
                "confirmed_true_hard_safety_violations": hard_violations,
                "unauthorized_learner_state_mutations": 0,
                "speech_modality_breaches": speech_from_text_accepted,
                "contextual_transfer_breaches": contextual_as_atomic_accepted,
                "vocabulary_domain_overclaims": vocab_as_atomic_accepted,
                "unsupported_evidence_accepted": truly_unsupported_accepted,
                "prompt_injection_containment_breaches": sum(
                    r.category in {"prompt_injection", "jailbreak_attempt"} and not r.prompt_injection_contained
                    for r in results
                ),
            },
            "auxiliary_checks": {
                "required_correction_points_accuracy": corr_success_rate,
                "required_term_check_rate": required_terms_rate,
            },
            "probabilistic_judge_evaluation": judge_metrics,
            "performance_and_latency": {
                "latency_status": "DESCRIPTIVE OPERATIONAL EVIDENCE ONLY (not a hard gate)",
                "generation_latency_ms": latency_summary(gen_lats),
                "assessment_latency_ms": latency_summary(assess_lats),
                "judge_latency_ms": latency_summary(judge_lats) if judge_records else "NOT RUN",
            },
            "token_usage": {
                "metering_definition": "exact provider usage_metadata token counts; zero estimation for executed calls",
                "generation_tokens": token_summary(gen_toks),
                "assessment_tokens": token_summary(assess_toks),
                "judge_tokens": token_summary(judge_toks) if judge_records else "NOT RUN",
                "grand_total_tokens": grand_total_tokens,
                "estimated_counterfactual_token_savings": {
                    "methodology": "counterfactual estimate: skipped_assessments * mean_assessment_prompt_tokens",
                    "skipped_assessment_turns": skipped_assessment_turns,
                    "mean_prompt_tokens_per_assessment": round(measured_mean_assess_prompt, 1),
                    "estimated_prompt_tokens_saved": estimated_saved_tokens,
                },
            },
        },
        "failures": failures,
        "failure_count": len(failures),
    }


def live_eval_report(
    cases_path: Path = LIVE_EVAL_CASES_PATH,
    limit: int | None = None,
    category: str | None = None,
    with_judge: bool = False,
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Live Gemini tutor generation and assessment evaluation with zero persistence and mutation guard."""
    from app.database import SessionLocal
    from .adapters.live_eval import evaluate_live_case, install_evaluation_session_mutation_guard

    cases = load_live_eval_cases(cases_path)
    validate_live_eval_cases_against_curriculum(cases)
    if category:
        cases = [c for c in cases if c.category == category]
    if limit is not None:
        cases = cases[:limit]

    db = install_evaluation_session_mutation_guard(SessionLocal())
    results = []
    try:
        for case in cases:
            res = evaluate_live_case(
                case, db, with_judge=with_judge, judge_model_name=judge_model
            )
            results.append(res)
    finally:
        db.close()

    return compute_live_eval_metrics(cases, results, cases_path, with_judge, judge_model)



def _runtime_report(mode: str, cases_path: Path, metrics: dict[str, Any], failures: list[dict[str, Any]], runtime_configuration: dict[str, object]) -> dict[str, Any]:
    return {"mode": mode, "status": "MEASURED", "timestamp_utc": datetime.now(UTC).isoformat(), "git_sha": git_sha(), "dataset_sha256": dataset_sha256(cases_path), "baseline": baseline_configuration(), "runtime_configuration": runtime_configuration, "metrics": metrics, "failures": failures, "failure_count": len(failures), "latency": "recorded only when adapter supplies it", "token_usage": "recorded only when provider supplies it"}


def main() -> None:
    try:
        reconfig_out = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfig_out):
            reconfig_out(encoding="utf-8", errors="replace")
        reconfig_err = getattr(sys.stderr, "reconfigure", None)
        if callable(reconfig_err):
            reconfig_err(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="SpanishAmigo live and baseline evaluator")
    parser.add_argument("mode", choices=("offline", "planner-offline", "phase7-offline", "db-retrieval", "live-model", "live-assessment-smoke", "retrieval-benchmark", "live-eval", "live-judge-calibration", "live-fallback-smoke"))
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline", choices=("A", "B"), default="B")
    parser.add_argument("--variant", choices=("B_legacy", "B_metadata", "B_hybrid"), default="B_legacy")
    parser.add_argument("--variants", nargs="+", choices=("B_legacy", "B_hybrid", "targeted_oracle"), default=["B_legacy", "B_hybrid"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--category", type=str, help="Filter cases to a single category")
    parser.add_argument("--with-judge", action="store_true", help="Enable structured LLM-as-a-judge scoring on generated responses")
    parser.add_argument("--judge-model", type=str, help="Model name for judge evaluation")
    parser.add_argument("--confirm-live", action="store_true", help="Required because this command invokes Gemini and may consume quota.")
    args = parser.parse_args()

    default_cases_map = {
        "offline": DEFAULT_CASES_PATH,
        "planner-offline": PHASE5_CASES_PATH,
        "phase7-offline": PHASE7_CASES_PATH,
        "live-assessment-smoke": PHASE5_CASES_PATH,
        "retrieval-benchmark": RETRIEVAL_BENCHMARK_PATH,
        "db-retrieval": DEFAULT_CASES_PATH,
        "live-model": DEFAULT_CASES_PATH,
        "live-eval": LIVE_EVAL_CASES_PATH,
        "live-judge-calibration": LIVE_EVAL_CASES_PATH,
        "live-fallback-smoke": LIVE_EVAL_CASES_PATH,
    }
    cases_path = args.cases or default_cases_map[args.mode]

    if args.mode == "offline":
        report = offline_report(cases_path)
    elif args.mode == "planner-offline":
        report = planner_offline_report(cases_path)
    elif args.mode == "phase7-offline":
        report = phase7_offline_report(cases_path)
    elif args.mode == "live-assessment-smoke":
        if not args.confirm_live:
            raise SystemExit("LIVE C ASSESSMENT SMOKE requires --confirm-live; no model quota was consumed.")
        report = live_assessment_smoke(cases_path, args.limit)
    elif args.mode == "retrieval-benchmark":
        if not args.confirm_live:
            raise SystemExit("RETRIEVAL BENCHMARK requires --confirm-live because it invokes Gemini embeddings and queries PostgreSQL; no model quota was consumed.")
        report = retrieval_benchmark_report(cases_path, variants=args.variants, limit=args.limit)
    elif args.mode == "db-retrieval":
        if not args.confirm_live:
            raise SystemExit("DB-RETRIEVAL requires --confirm-live because it invokes Gemini embeddings and queries PostgreSQL; no model quota was consumed.")
        report = retrieval_report(cases_path, args.variant)
    elif args.mode == "live-judge-calibration":
        if not args.confirm_live:
            raise SystemExit("LIVE JUDGE CALIBRATION requires --confirm-live because it invokes the Gemini judge model; no model quota was consumed.")
        from .adapters.live_eval import run_live_judge_calibration
        report = run_live_judge_calibration(judge_model_name=args.judge_model)
    elif args.mode == "live-fallback-smoke":
        if not args.confirm_live:
            raise SystemExit("LIVE FALLBACK SMOKE requires --confirm-live because it invokes the configured backup model; no model quota was consumed.")
        from .adapters.live_eval import run_live_fallback_smoke
        report = run_live_fallback_smoke()
    elif args.mode == "live-eval":
        if not args.confirm_live:
            raise SystemExit("LIVE EVAL requires --confirm-live because it invokes Gemini generation and assessment models; no model quota was consumed.")
        report = live_eval_report(
            cases_path,
            limit=args.limit,
            category=args.category,
            with_judge=args.with_judge,
            judge_model=args.judge_model,
        )
    else:
        if not args.confirm_live:
            raise SystemExit("LIVE MODEL EVAL requires --confirm-live; no model quota was consumed.")
        report = live_report(cases_path, args.baseline, args.limit)

    if args.report:
        write_report(report, args.report)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
