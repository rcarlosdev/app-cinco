from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from apps.ia_dev.infrastructure.ai.model_routing import resolve_model_name


class CauseDiagnosticsService:
    """
    Generador hibrido de diagnosticos:
    - Heuristico determinista (fallback seguro)
    - OpenAI con contrato JSON + validacion de evidencia
    """

    def __init__(self):
        self.model = resolve_model_name("cause_diagnostics")

    @staticmethod
    def _flag_enabled(name: str, default: str = "1") -> bool:
        return str(os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _get_openai_api_key() -> str:
        return str(os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or "").strip()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def generate(
        self,
        *,
        message: str,
        rows: list[dict[str, Any]],
        group_label: str,
        metric_key: str = "total_ausentismos",
        observability=None,
        run_id: str | None = None,
        trace_id: str | None = None,
        domain_code: str | None = None,
        capability_id: str | None = None,
    ) -> dict[str, Any]:
        evidence_rows = self._build_evidence_rows(rows=rows, metric_key=metric_key)
        top_group, top_pct = self._extract_top_group(evidence_rows=evidence_rows)
        prompt_hash = self._build_prompt_hash(
            message=message,
            group_label=group_label,
            evidence_rows=evidence_rows,
        )
        policy_inputs = self._build_policy_inputs()
        base_policy_decision = self._build_policy_decision(
            selected_generator="heuristic",
            allowed=False,
            reason="default_heuristic",
            policy_inputs=policy_inputs,
        )

        if not evidence_rows:
            insights = self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label)
            meta = {
                "generator": "heuristic",
                "evidence_rows": evidence_rows,
                "top_group": top_group,
                "top_pct": top_pct,
                "confidence": 0.35,
                "fallback_reason": "insufficient_evidence_rows",
                "validated": True,
                "prompt_hash": prompt_hash,
                "validation_errors": ["insufficient_evidence_rows"],
                "policy_decision": base_policy_decision,
            }
            self._record_result_event(
                observability=observability,
                run_id=run_id,
                trace_id=trace_id,
                domain_code=domain_code,
                capability_id=capability_id,
                meta=meta,
            )
            return {
                "insights": insights,
                "meta": meta,
            }

        runtime_enabled = bool(policy_inputs.get("runtime_enabled"))
        openai_enabled = bool(policy_inputs.get("openai_enabled"))
        if not runtime_enabled or not openai_enabled:
            insights = self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label)
            reason = "openai_disabled_by_flag"
            meta = {
                "generator": "heuristic",
                "evidence_rows": evidence_rows,
                "top_group": top_group,
                "top_pct": top_pct,
                "confidence": 0.55,
                "fallback_reason": reason,
                "validated": True,
                "prompt_hash": prompt_hash,
                "validation_errors": [reason],
                "policy_decision": self._build_policy_decision(
                    selected_generator="heuristic",
                    allowed=False,
                    reason=reason,
                    policy_inputs=policy_inputs,
                ),
            }
            self._record_result_event(
                observability=observability,
                run_id=run_id,
                trace_id=trace_id,
                domain_code=domain_code,
                capability_id=capability_id,
                meta=meta,
            )
            return {
                "insights": insights,
                "meta": meta,
            }

        api_key = self._get_openai_api_key()
        if not api_key:
            insights = self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label)
            reason = "openai_api_key_missing"
            meta = {
                "generator": "heuristic",
                "evidence_rows": evidence_rows,
                "top_group": top_group,
                "top_pct": top_pct,
                "confidence": 0.55,
                "fallback_reason": reason,
                "validated": True,
                "prompt_hash": prompt_hash,
                "validation_errors": [reason],
                "policy_decision": self._build_policy_decision(
                    selected_generator="heuristic",
                    allowed=False,
                    reason=reason,
                    policy_inputs=policy_inputs,
                ),
            }
            self._record_result_event(
                observability=observability,
                run_id=run_id,
                trace_id=trace_id,
                domain_code=domain_code,
                capability_id=capability_id,
                meta=meta,
            )
            return {
                "insights": insights,
                "meta": meta,
            }

        try:
            payload = self._generate_openai_payload(
                message=message,
                group_label=group_label,
                evidence_rows=evidence_rows,
                api_key=api_key,
            )
            validation = self._validate_openai_payload(payload=payload, evidence_rows=evidence_rows)
            if validation["valid"]:
                insights = self._openai_payload_to_insights(payload=payload)
                confidence = self._safe_float(payload.get("confidence"), 0.8)
                self._record_event(
                    observability=observability,
                    event_type="cause_diagnostics_generated",
                    source="CauseDiagnosticsService",
                    meta={
                        "run_id": run_id,
                        "trace_id": trace_id,
                        "generator": "openai",
                        "confidence": confidence,
                        "model": self.model,
                        "prompt_hash": prompt_hash,
                    },
                )
                meta = {
                    "generator": "openai",
                    "evidence_rows": evidence_rows,
                    "top_group": top_group,
                    "top_pct": top_pct,
                    "confidence": confidence,
                    "validated": True,
                    "validation_reason": str(validation.get("reason") or "ok"),
                    "model": self.model,
                    "prompt_hash": prompt_hash,
                    "validation_errors": [],
                    "policy_decision": self._build_policy_decision(
                        selected_generator="openai",
                        allowed=True,
                        reason="openai_payload_validated",
                        policy_inputs=policy_inputs,
                    ),
                }
                self._record_result_event(
                    observability=observability,
                    run_id=run_id,
                    trace_id=trace_id,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    meta=meta,
                )
                return {
                    "insights": insights or self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label),
                    "meta": meta,
                }

            insights = self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label)
            invalid_reason = str(validation.get("reason") or "openai_payload_invalid")
            meta = {
                "generator": "heuristic",
                "evidence_rows": evidence_rows,
                "top_group": top_group,
                "top_pct": top_pct,
                "confidence": 0.55,
                "fallback_reason": f"openai_payload_invalid:{invalid_reason}",
                "validated": False,
                "model": self.model,
                "prompt_hash": prompt_hash,
                "validation_errors": [invalid_reason],
                "policy_decision": self._build_policy_decision(
                    selected_generator="heuristic",
                    allowed=False,
                    reason=f"openai_payload_invalid:{invalid_reason}",
                    policy_inputs=policy_inputs,
                ),
            }
            self._record_result_event(
                observability=observability,
                run_id=run_id,
                trace_id=trace_id,
                domain_code=domain_code,
                capability_id=capability_id,
                meta=meta,
            )
            return {
                "insights": insights,
                "meta": meta,
            }
        except Exception as exc:
            insights = self._heuristic_insights(evidence_rows=evidence_rows, group_label=group_label)
            self._record_event(
                observability=observability,
                event_type="cause_diagnostics_fallback_heuristic",
                source="CauseDiagnosticsService",
                meta={
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "generator": "heuristic",
                    "fallback_reason": f"openai_exception:{type(exc).__name__}",
                    "prompt_hash": prompt_hash,
                },
            )
            meta = {
                "generator": "heuristic",
                "evidence_rows": evidence_rows,
                "top_group": top_group,
                "top_pct": top_pct,
                "confidence": 0.55,
                "fallback_reason": f"openai_exception:{type(exc).__name__}",
                "validated": False,
                "model": self.model,
                "prompt_hash": prompt_hash,
                "validation_errors": [f"openai_exception:{type(exc).__name__}"],
                "policy_decision": self._build_policy_decision(
                    selected_generator="heuristic",
                    allowed=False,
                    reason=f"openai_exception:{type(exc).__name__}",
                    policy_inputs=policy_inputs,
                ),
            }
            self._record_result_event(
                observability=observability,
                run_id=run_id,
                trace_id=trace_id,
                domain_code=domain_code,
                capability_id=capability_id,
                meta=meta,
            )
            return {
                "insights": insights,
                "meta": meta,
            }

    def _record_result_event(
        self,
        *,
        observability,
        run_id: str | None,
        trace_id: str | None,
        domain_code: str | None,
        capability_id: str | None,
        meta: dict[str, Any],
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        payload = dict(meta or {})
        policy_decision = dict(payload.get("policy_decision") or {})
        fallback_reason = str(payload.get("fallback_reason") or "").strip()
        validation_errors = [
            str(item or "").strip()
            for item in list(payload.get("validation_errors") or [])
            if str(item or "").strip()
        ]
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        try:
            top_pct = float(payload.get("top_pct") or 0.0)
        except Exception:
            top_pct = 0.0

        self._record_event(
            observability=observability,
            event_type="cause_diagnostics_result",
            source="CauseDiagnosticsService",
            meta={
                "run_id": run_id,
                "trace_id": trace_id,
                "domain_code": str(domain_code or "").strip().lower(),
                "capability_id": str(capability_id or "").strip(),
                "generator": str(payload.get("generator") or "heuristic"),
                "confidence": confidence,
                "validated": bool(payload.get("validated")),
                "fallback_reason": fallback_reason,
                "validation_error_count": len(validation_errors),
                "validation_errors": validation_errors[:5],
                "policy_reason": str(policy_decision.get("reason") or ""),
                "policy_selected_generator": str(policy_decision.get("selected_generator") or ""),
                "policy_allowed": bool(policy_decision.get("allowed")),
                "model": str(payload.get("model") or self.model),
                "prompt_hash": str(payload.get("prompt_hash") or ""),
                "evidence_rows_count": len(list(payload.get("evidence_rows") or [])),
                "top_group": str(payload.get("top_group") or ""),
                "top_pct": top_pct,
            },
        )

    @staticmethod
    def _build_prompt_hash(*, message: str, group_label: str, evidence_rows: list[dict[str, Any]]) -> str:
        canonical = json.dumps(
            {
                "message": str(message or "").strip().lower(),
                "group_label": str(group_label or "").strip().lower(),
                "evidence_rows": list(evidence_rows or []),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _build_policy_inputs(self) -> dict[str, Any]:
        min_confidence = self._safe_float(
            os.getenv("IA_DEV_CAUSE_DIAGNOSTICS_MIN_CONFIDENCE", "0.60"),
            0.60,
        )
        return {
            "runtime_enabled": self._flag_enabled("IA_DEV_CAUSE_DIAGNOSTICS_ENABLED", "1"),
            "openai_enabled": self._flag_enabled("IA_DEV_CAUSE_DIAGNOSTICS_OPENAI_ENABLED", "1"),
            "api_key_present": bool(self._get_openai_api_key()),
            "min_confidence": min_confidence,
            "model": self.model,
        }

    @staticmethod
    def _build_policy_decision(
        *,
        selected_generator: str,
        allowed: bool,
        reason: str,
        policy_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "selected_generator": str(selected_generator or "heuristic"),
            "allowed": bool(allowed),
            "reason": str(reason or ""),
            "runtime_enabled": bool(policy_inputs.get("runtime_enabled")),
            "openai_enabled": bool(policy_inputs.get("openai_enabled")),
            "api_key_present": bool(policy_inputs.get("api_key_present")),
            "min_confidence": float(policy_inputs.get("min_confidence") or 0.0),
            "model": str(policy_inputs.get("model") or ""),
        }

    @staticmethod
    def _build_evidence_rows(*, rows: list[dict[str, Any]], metric_key: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for row in list(rows or [])[:5]:
            if not isinstance(row, dict):
                continue
            group_value = str(
                row.get("grupo")
                or row.get("group")
                or row.get("area")
                or row.get("supervisor")
                or row.get("cargo")
                or row.get("carpeta")
                or "N/D"
            ).strip()
            pct = CauseDiagnosticsService._safe_float(row.get("porcentaje"), 0.0)
            count = int(CauseDiagnosticsService._safe_float(row.get(metric_key), 0.0))
            evidence.append(
                {
                    "group": group_value,
                    "count": count,
                    "pct": round(pct, 2),
                }
            )
        return evidence

    @staticmethod
    def _extract_top_group(*, evidence_rows: list[dict[str, Any]]) -> tuple[str, float]:
        if not evidence_rows:
            return "", 0.0
        first = dict(evidence_rows[0] or {})
        return str(first.get("group") or "").strip(), CauseDiagnosticsService._safe_float(first.get("pct"), 0.0)

    @staticmethod
    def _heuristic_insights(*, evidence_rows: list[dict[str, Any]], group_label: str) -> list[str]:
        if not evidence_rows:
            return ["No hay datos suficientes en el periodo para sugerir causas probables."]
        top = dict(evidence_rows[0] or {})
        top_group = str(top.get("group") or "N/D")
        top_pct = CauseDiagnosticsService._safe_float(top.get("pct"), 0.0)
        return [
            f"Mayor concentracion por {str(group_label or 'grupo').strip().lower()}: {top_group} ({top_pct:.1f}%).",
            "Posibles causas a validar: sobrecarga operativa, picos de incapacidades y cobertura insuficiente de reemplazos.",
            "Recomendacion: cruza ausentismo con turnos, novedades medicas y dotacion por equipo para confirmar causa raiz.",
        ]

    def _generate_openai_payload(
        self,
        *,
        message: str,
        group_label: str,
        evidence_rows: list[dict[str, Any]],
        api_key: str,
    ) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Eres analista senior de ausentismo. Responde SOLO JSON valido.\n"
                        "Contrato JSON obligatorio:\n"
                        "{"
                        "\"diagnostics\":[{\"finding\":\"...\",\"suggestion\":\"...\",\"evidence_groups\":[\"...\"],\"confidence\":0.0}],"
                        "\"confidence\":0.0"
                        "}\n"
                        "Reglas:\n"
                        "- No inventes cifras.\n"
                        "- Usa exclusivamente evidence_groups presentes en la evidencia.\n"
                        "- Maximo 3 diagnostics.\n"
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        f"Contexto:\nmessage={message}\n"
                        f"group_label={group_label}\n"
                        f"evidence_rows={json.dumps(evidence_rows, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": message},
            ],
        )
        raw = str(getattr(response, "output_text", "") or "").strip()
        return self._safe_json(raw)

    @staticmethod
    def _safe_json(raw_text: str) -> dict[str, Any]:
        if not raw_text:
            return {}
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        candidate = raw_text[start : end + 1] if start >= 0 and end > start else raw_text
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _validate_openai_payload(self, *, payload: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            return {"valid": False, "reason": "empty_payload"}
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, list) or not diagnostics:
            return {"valid": False, "reason": "missing_diagnostics"}
        valid_groups = {
            str(item.get("group") or "").strip().lower()
            for item in list(evidence_rows or [])
            if isinstance(item, dict) and str(item.get("group") or "").strip()
        }
        if not valid_groups:
            return {"valid": False, "reason": "missing_valid_groups"}

        accepted = 0
        for item in diagnostics[:3]:
            if not isinstance(item, dict):
                continue
            finding = str(item.get("finding") or "").strip()
            suggestion = str(item.get("suggestion") or "").strip()
            evidence_groups = item.get("evidence_groups")
            if not finding or not suggestion or not isinstance(evidence_groups, list):
                continue
            normalized_groups = {str(group or "").strip().lower() for group in evidence_groups if str(group or "").strip()}
            if not normalized_groups or not normalized_groups.intersection(valid_groups):
                continue
            confidence = self._safe_float(item.get("confidence"), 0.0)
            if confidence < 0.45:
                continue
            accepted += 1

        overall_confidence = self._safe_float(payload.get("confidence"), 0.0)
        min_overall = self._safe_float(os.getenv("IA_DEV_CAUSE_DIAGNOSTICS_MIN_CONFIDENCE", "0.60"), 0.60)
        if accepted <= 0:
            return {"valid": False, "reason": "diagnostics_not_evidence_grounded"}
        if overall_confidence < min_overall:
            return {"valid": False, "reason": "overall_confidence_below_threshold"}
        return {"valid": True, "reason": "ok"}

    @staticmethod
    def _openai_payload_to_insights(*, payload: dict[str, Any]) -> list[str]:
        diagnostics = [item for item in list(payload.get("diagnostics") or []) if isinstance(item, dict)][:3]
        insights: list[str] = []
        for item in diagnostics:
            finding = str(item.get("finding") or "").strip()
            suggestion = str(item.get("suggestion") or "").strip()
            groups = [str(group).strip() for group in list(item.get("evidence_groups") or []) if str(group).strip()]
            if finding:
                if groups:
                    insights.append(f"{finding} (evidencia: {', '.join(groups)}).")
                else:
                    insights.append(finding)
            if suggestion:
                insights.append(f"Accion sugerida: {suggestion}")
        return insights

    @staticmethod
    def _record_event(*, observability, event_type: str, source: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source=source,
            meta=dict(meta or {}),
        )
