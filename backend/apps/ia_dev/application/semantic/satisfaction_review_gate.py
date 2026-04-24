from __future__ import annotations

import re
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    SatisfactionReviewGateResult,
    StructuredQueryIntent,
)
from apps.ia_dev.application.taxonomia_dominios import (
    dominio_desde_capacidad,
    intenciones_son_compatibles,
    normalizar_codigo_dominio,
    normalizar_intencion_comparable,
)


class SatisfactionReviewGate:
    """
    Revisor deterministic-first de satisfaccion semantica.
    En esta fase no introduce loop propio ni invocacion GPT.
    """

    _TECHNICAL_LEAK_PATTERNS = (
        r"\bselect\s+.+\s+from\b",
        r"\bjoin\b",
        r"\bwhere\b",
        r"\btraceback\b",
        r"\bexception\b",
        r"\bsql\b",
        r"\bstack trace\b",
    )

    def evaluate(
        self,
        *,
        raw_query: str,
        canonical_resolution: dict[str, Any] | None,
        runtime_intent: StructuredQueryIntent | None,
        resolved_query: ResolvedQuerySpec | None,
        execution_result: dict[str, Any] | None,
        candidate_response: dict[str, Any] | None,
        strategy: str,
        planned_capability: dict[str, Any] | None,
        loop_metadata: dict[str, Any] | None,
        legacy_validation: dict[str, Any] | None,
        runtime_flags: dict[str, Any] | None = None,
    ) -> SatisfactionReviewGateResult:
        canonical = dict(canonical_resolution or {})
        execution = dict(execution_result or {})
        response = dict(candidate_response or {})
        planned = dict(planned_capability or {})
        legacy = dict(legacy_validation or {})
        flags = dict(runtime_flags or {})
        loop_meta = dict(loop_metadata or {})

        canonical_domain = normalizar_codigo_dominio(canonical.get("domain_code"))
        canonical_capability = str(canonical.get("capability_code") or "").strip()
        canonical_confidence = float(canonical.get("confidence") or 0.0)
        canonical_intent = normalizar_intencion_comparable(
            canonical.get("intent_code"),
            domain=canonical_domain,
            capability_id=canonical_capability,
        )

        runtime_capability = str(planned.get("capability_id") or "").strip()
        runtime_domain = self._capability_domain(runtime_capability)
        if not runtime_domain:
            runtime_domain = normalizar_codigo_dominio(
                resolved_query.intent.domain_code if resolved_query else ""
            )
        runtime_intent_code = normalizar_intencion_comparable(
            runtime_intent.operation if runtime_intent else "",
            domain=runtime_domain,
            capability_id=runtime_capability,
        )
        if not runtime_intent_code:
            runtime_intent_code = normalizar_intencion_comparable(
                resolved_query.intent.operation if resolved_query else "",
                domain=runtime_domain,
                capability_id=runtime_capability,
            )

        domain_alignment = bool(
            not canonical_domain
            or canonical_domain in {"general", "legacy"}
            or canonical_domain == runtime_domain
        )
        intent_alignment = intenciones_son_compatibles(
            canonical_intent,
            runtime_intent_code,
            expected_capability_id=canonical_capability,
            actual_capability_id=runtime_capability,
            domain=canonical_domain or runtime_domain,
        )
        capability_alignment = bool(not canonical_capability or canonical_capability == runtime_capability)

        data = dict(response.get("data") or {})
        table = dict(data.get("table") or {})
        rows = list(table.get("rows") or [])
        kpis = dict(data.get("kpis") or {})
        labels = list(data.get("labels") or [])
        series = list(data.get("series") or [])
        charts = list(data.get("charts") or [])
        chart = dict(data.get("chart") or {})
        has_kpi = any(isinstance(value, (int, float)) for value in kpis.values())
        has_rows = bool(rows)
        has_series = bool(labels and series)
        has_chart = bool(chart or charts)
        evidence_sufficient = bool(has_kpi or has_rows or has_series or has_chart)

        technical_leak_detected = self._technical_leak_detected(response=response, execution=execution)
        response_safe = not technical_leak_detected

        used_legacy = bool(execution.get("used_legacy"))
        fallback_reason = str(execution.get("fallback_reason") or "").strip().lower()
        fallback_justified = True
        if used_legacy:
            fallback_justified = bool(
                canonical_domain in {"", "general", "legacy"}
                or canonical_confidence < 0.72
                or "policy_" in fallback_reason
                or "capability_" in fallback_reason
                or "routing_mode" in fallback_reason
            )

        legacy_satisfied = bool(legacy.get("satisfied", True))
        legacy_reason = str(legacy.get("reason") or "")
        semantic_alignment = bool(domain_alignment and intent_alignment and capability_alignment and legacy_satisfied)

        issues: list[dict[str, Any]] = []
        if canonical_domain not in {"", "general", "legacy"} and runtime_domain in {"", "general", "legacy"}:
            issues.append(
                {
                    "code": "unjustified_fall_to_general",
                    "severity": "high",
                    "detail": f"canonical_domain={canonical_domain} runtime_domain={runtime_domain or 'general'}",
                }
            )
        if canonical_domain not in {"", "general", "legacy"} and runtime_domain not in {"", "general", "legacy"} and canonical_domain != runtime_domain:
            issues.append(
                {
                    "code": "wrong_domain",
                    "severity": "high",
                    "detail": f"canonical_domain={canonical_domain} runtime_domain={runtime_domain}",
                }
            )
        if canonical_capability and runtime_capability and canonical_capability != runtime_capability:
            issues.append(
                {
                    "code": "wrong_capability",
                    "severity": "high",
                    "detail": f"canonical_capability={canonical_capability} runtime_capability={runtime_capability}",
                }
            )
        if not semantic_alignment:
            issues.append(
                {
                    "code": "semantic_mismatch",
                    "severity": "medium",
                    "detail": legacy_reason or "semantic_alignment_false",
                }
            )
        if technical_leak_detected:
            issues.append(
                {
                    "code": "technical_leak",
                    "severity": "high",
                    "detail": "response contains technical internals",
                }
            )
        if not evidence_sufficient:
            issues.append(
                {
                    "code": "low_evidence",
                    "severity": "medium",
                    "detail": "response payload lacks kpis/table/chart evidence",
                }
            )
        if not fallback_justified:
            issues.append(
                {
                    "code": "fallback_unjustified",
                    "severity": "high",
                    "detail": f"fallback_reason={fallback_reason or 'unknown'}",
                }
            )

        answered_user_goal = bool(
            execution.get("ok")
            and semantic_alignment
            and evidence_sufficient
            and response_safe
        )

        satisfaction_score = self._compute_score(
            answered_user_goal=answered_user_goal,
            semantic_alignment=semantic_alignment,
            domain_alignment=domain_alignment,
            intent_alignment=intent_alignment,
            capability_alignment=capability_alignment,
            evidence_sufficient=evidence_sufficient,
            response_safe=response_safe,
            fallback_justified=fallback_justified,
            issues=issues,
        )
        has_high_issue = any(str((item or {}).get("severity") or "") == "high" for item in issues)
        approved = bool(answered_user_goal and not has_high_issue and satisfaction_score >= 0.65)

        retry_reason = ""
        next_action = "approve"
        if not approved:
            retry_reason = str((issues[0] if issues else {}).get("code") or legacy_reason or "review_required")
            next_action = "retry_with_next_candidate"
            if used_legacy and not fallback_justified:
                next_action = "review_legacy_fallback"

        return SatisfactionReviewGateResult(
            approved=approved,
            answered_user_goal=answered_user_goal,
            semantic_alignment=semantic_alignment,
            domain_alignment=domain_alignment,
            intent_alignment=intent_alignment,
            capability_alignment=capability_alignment,
            evidence_sufficient=evidence_sufficient,
            response_safe=response_safe,
            technical_leak_detected=technical_leak_detected,
            fallback_justified=fallback_justified,
            satisfaction_score=satisfaction_score,
            issues=issues,
            retry_reason=retry_reason,
            next_action=next_action,
            review_meta={
                "strategy": str(strategy or ""),
                "runtime_domain": runtime_domain,
                "runtime_intent": runtime_intent_code,
                "runtime_capability": runtime_capability,
                "canonical_confidence": canonical_confidence,
                "legacy_reason": legacy_reason,
                "legacy_satisfied": legacy_satisfied,
                "loop_iteration": int(loop_meta.get("iteration") or 0),
                "llm_reviewer_enabled": bool(flags.get("llm_reviewer_enabled")),
            },
        )

    @classmethod
    def _technical_leak_detected(cls, *, response: dict[str, Any], execution: dict[str, Any]) -> bool:
        reply = str(response.get("reply") or "").strip().lower()
        if any(re.search(pattern, reply) for pattern in cls._TECHNICAL_LEAK_PATTERNS):
            return True
        trace = list(response.get("trace") or [])
        for row in trace:
            if not isinstance(row, dict):
                continue
            detail_text = str(row.get("detail") or "").lower()
            if any(re.search(pattern, detail_text) for pattern in cls._TECHNICAL_LEAK_PATTERNS):
                return True
        error_text = str(execution.get("error") or "").strip().lower()
        if any(token in error_text for token in ("traceback", "sql", "exception")):
            return True
        return False

    @staticmethod
    def _capability_domain(capability_id: str) -> str:
        return dominio_desde_capacidad(capability_id)

    @staticmethod
    def _compute_score(
        *,
        answered_user_goal: bool,
        semantic_alignment: bool,
        domain_alignment: bool,
        intent_alignment: bool,
        capability_alignment: bool,
        evidence_sufficient: bool,
        response_safe: bool,
        fallback_justified: bool,
        issues: list[dict[str, Any]],
    ) -> float:
        weighted = [
            (answered_user_goal, 2.0),
            (semantic_alignment, 1.6),
            (domain_alignment, 1.2),
            (intent_alignment, 1.1),
            (capability_alignment, 1.1),
            (evidence_sufficient, 1.2),
            (response_safe, 2.0),
            (fallback_justified, 1.0),
        ]
        achieved = sum(weight for passed, weight in weighted if passed)
        total = sum(weight for _, weight in weighted)
        score = achieved / total if total else 0.0
        high_issues = sum(1 for item in issues if str((item or {}).get("severity") or "") == "high")
        medium_issues = sum(1 for item in issues if str((item or {}).get("severity") or "") == "medium")
        score -= min(0.35, high_issues * 0.12 + medium_issues * 0.05)
        return max(0.0, min(1.0, round(score, 4)))

