from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext


class ReasoningLedgerService:
    VERSION = "ia_dev.reasoning.v1"

    @staticmethod
    def enabled() -> bool:
        raw = str(os.getenv("IA_DEV_REASONING_LEDGER_ENABLED", "1") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def start_run(
        self,
        *,
        run_context: RunContext,
        message: str,
        user_key: str | None,
        session_context: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled():
            return
        session = dict(session_context or {})
        run_context.metadata["reasoning"] = {
            "version": self.VERSION,
            "started_at": run_context.started_at_iso,
            "working_goal": self._build_goal(message=message),
            "status": "running",
            "current_next_step": "clasificar la consulta y cargar contexto util",
            "entries": [],
            "hypotheses": [],
            "evidence": [],
            "diagnostics": [],
            "memory_summary": {
                "user_key": str(user_key or "").strip(),
                "session_context": {
                    "last_domain": str(session.get("last_domain") or ""),
                    "last_intent": str(session.get("last_intent") or ""),
                    "last_output_mode": str(session.get("last_output_mode") or ""),
                },
            },
            "final_outcome": {},
        }
        self.record_progress(
            run_context=run_context,
            stage="intake",
            status="completed",
            summary="Consulta recibida y lista para analisis.",
            details={
                "message_excerpt": str(message or "").strip()[:160],
                "session_id": str(run_context.session_id or ""),
            },
            next_step="clasificar dominio e intencion base",
            confidence=0.4,
        )

    def record_progress(
        self,
        *,
        run_context: RunContext,
        stage: str,
        summary: str,
        status: str = "in_progress",
        details: dict[str, Any] | None = None,
        next_step: str | None = None,
        confidence: float | None = None,
        user_visible: bool = True,
    ) -> None:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return
        entry = {
            "id": f"step_{len(list(ledger.get('entries') or [])) + 1}",
            "stage": str(stage or "").strip().lower() or "unknown",
            "status": str(status or "").strip().lower() or "in_progress",
            "summary": str(summary or "").strip(),
            "details": dict(details or {}),
            "next_step": str(next_step or "").strip(),
            "confidence": self._normalize_confidence(confidence),
            "user_visible": bool(user_visible),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        entries = list(ledger.get("entries") or [])
        entries.append(entry)
        ledger["entries"] = entries[-30:]
        if entry["next_step"]:
            ledger["current_next_step"] = entry["next_step"]
        run_context.metadata["reasoning"] = ledger

    def attach_memory_hints(
        self,
        *,
        run_context: RunContext,
        memory_hints: dict[str, Any] | None,
        phase: str,
    ) -> None:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return
        hints = dict(memory_hints or {})
        memory_summary = dict(ledger.get("memory_summary") or {})
        memory_summary[str(phase or "memory")] = {
            "query_patterns": len(list(hints.get("query_patterns") or [])),
            "reasoning_patterns": len(list(hints.get("reasoning_patterns") or [])),
            "output_mode": str(hints.get("output_mode") or ""),
            "personal_status": str(hints.get("personal_status") or ""),
        }
        ledger["memory_summary"] = memory_summary
        run_context.metadata["reasoning"] = ledger
        if any(
            [
                int(memory_summary[str(phase or "memory")].get("query_patterns") or 0) > 0,
                int(memory_summary[str(phase or "memory")].get("reasoning_patterns") or 0) > 0,
                bool(memory_summary[str(phase or "memory")].get("output_mode")),
                bool(memory_summary[str(phase or "memory")].get("personal_status")),
            ]
        ):
            self.record_progress(
                run_context=run_context,
                stage="memory",
                status="completed",
                summary="Memorias utiles cargadas para orientar la consulta.",
                details=memory_summary[str(phase or "memory")],
                next_step="resolver la consulta con señales semanticas y patrones previos",
                confidence=0.7,
                user_visible=(str(phase or "").strip().lower() == "pre_query"),
            )

    def record_hypothesis(
        self,
        *,
        run_context: RunContext,
        key: str,
        text: str,
        status: str = "open",
        confidence: float | None = None,
        evidence_refs: list[str] | None = None,
    ) -> None:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return
        hypotheses = list(ledger.get("hypotheses") or [])
        normalized_key = str(key or "").strip().lower()
        payload = {
            "key": normalized_key,
            "text": str(text or "").strip(),
            "status": str(status or "").strip().lower() or "open",
            "confidence": self._normalize_confidence(confidence),
            "evidence_refs": [str(item or "").strip() for item in list(evidence_refs or []) if str(item or "").strip()],
        }
        replaced = False
        for idx, item in enumerate(hypotheses):
            if str((item or {}).get("key") or "").strip().lower() == normalized_key:
                hypotheses[idx] = payload
                replaced = True
                break
        if not replaced:
            hypotheses.append(payload)
        ledger["hypotheses"] = hypotheses[-20:]
        run_context.metadata["reasoning"] = ledger

    def record_evidence(
        self,
        *,
        run_context: RunContext,
        source: str,
        finding: str,
        stage: str = "",
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return ""
        evidence = list(ledger.get("evidence") or [])
        evidence_id = f"ev_{len(evidence) + 1}"
        evidence.append(
            {
                "id": evidence_id,
                "source": str(source or "").strip().lower(),
                "stage": str(stage or "").strip().lower(),
                "finding": str(finding or "").strip(),
                "confidence": self._normalize_confidence(confidence),
                "metadata": dict(metadata or {}),
            }
        )
        ledger["evidence"] = evidence[-30:]
        run_context.metadata["reasoning"] = ledger
        return evidence_id

    def record_diagnostics(
        self,
        *,
        run_context: RunContext,
        diagnostics: dict[str, Any] | None,
    ) -> None:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return
        payload = dict(diagnostics or {})
        items = [
            dict(item)
            for item in list(payload.get("items") or [])
            if isinstance(item, dict)
        ]
        if not items:
            return
        ledger["diagnostics"] = items[:10]
        run_context.metadata["reasoning"] = ledger
        for item in items[:5]:
            evidence_refs: list[str] = []
            for evidence in list(item.get("evidence") or []):
                if not isinstance(evidence, dict):
                    continue
                evidence_refs.append(
                    self.record_evidence(
                        run_context=run_context,
                        source=str(evidence.get("source") or "diagnostic"),
                        finding=str(evidence.get("finding") or ""),
                        stage=str(item.get("stage") or "diagnostics"),
                        confidence=float(evidence.get("confidence") or item.get("confidence") or 0.0),
                        metadata=dict(evidence.get("metadata") or {}),
                    )
                )
            for hypothesis in list(item.get("hypotheses") or []):
                if not isinstance(hypothesis, dict):
                    continue
                self.record_hypothesis(
                    run_context=run_context,
                    key=str(hypothesis.get("key") or item.get("signature") or ""),
                    text=str(hypothesis.get("text") or ""),
                    status=str(hypothesis.get("status") or "supported"),
                    confidence=float(hypothesis.get("confidence") or item.get("confidence") or 0.0),
                    evidence_refs=evidence_refs,
                )
        top = dict(items[0])
        self.record_progress(
            run_context=run_context,
            stage="diagnostics",
            status="completed",
            summary=str(top.get("summary") or "Se detectaron hallazgos de diagnostico."),
            details={
                "signatures": [str(item.get("signature") or "") for item in items[:5]],
                "severity": str(top.get("severity") or ""),
                "recommended_actions": [
                    str(item or "").strip()
                    for item in list(payload.get("recommended_actions") or [])
                    if str(item or "").strip()
                ][:3],
            },
            next_step="persistir aprendizajes utiles para futuras ejecuciones",
            confidence=float(top.get("confidence") or 0.0),
        )

    def finalize(
        self,
        *,
        run_context: RunContext,
        status: str,
        outcome: dict[str, Any] | None = None,
    ) -> None:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return
        ledger["status"] = str(status or "").strip().lower() or "completed"
        ledger["final_outcome"] = dict(outcome or {})
        if not str(ledger.get("current_next_step") or "").strip():
            ledger["current_next_step"] = "respuesta lista"
        run_context.metadata["reasoning"] = ledger

    def build_public_payload(self, *, run_context: RunContext) -> dict[str, Any]:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return {
                "enabled": False,
                "version": self.VERSION,
                "status": "disabled",
                "working_goal": "",
                "current_next_step": "",
                "hypotheses": [],
                "diagnostics": [],
                "memory_summary": {},
                "duration_ms": 0,
            }
        return {
            "enabled": True,
            "version": self.VERSION,
            "status": str(ledger.get("status") or "running"),
            "working_goal": str(ledger.get("working_goal") or ""),
            "current_next_step": str(ledger.get("current_next_step") or ""),
            "hypotheses": [dict(item or {}) for item in list(ledger.get("hypotheses") or []) if isinstance(item, dict)],
            "diagnostics": [dict(item or {}) for item in list(ledger.get("diagnostics") or []) if isinstance(item, dict)],
            "memory_summary": dict(ledger.get("memory_summary") or {}),
            "duration_ms": max(0, int(datetime.now(timezone.utc).timestamp() * 1000) - int(run_context.started_at_ms or 0)),
        }

    def build_working_updates(self, *, run_context: RunContext, limit: int = 8) -> list[dict[str, Any]]:
        ledger = self._get_ledger(run_context)
        if ledger is None:
            return []
        updates = []
        for item in list(ledger.get("entries") or []):
            if not isinstance(item, dict) or not bool(item.get("user_visible", True)):
                continue
            updates.append(
                {
                    "stage": str(item.get("stage") or ""),
                    "stage_label": self._build_stage_label(stage=str(item.get("stage") or "")),
                    "status": str(item.get("status") or ""),
                    "summary": str(item.get("summary") or ""),
                    "display_text": self._build_display_text(entry=item),
                    "next_step": str(item.get("next_step") or ""),
                    "confidence": self._normalize_confidence(item.get("confidence")),
                    "at": str(item.get("at") or ""),
                }
            )
        return updates[-max(1, int(limit)) :]

    @staticmethod
    def _build_goal(*, message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return "Resolver la consulta del usuario con evidencia suficiente."
        excerpt = text[:160]
        if len(text) > 160:
            excerpt = f"{excerpt}..."
        return f'Resolver la consulta "{excerpt}" con la mejor evidencia disponible.'

    @staticmethod
    def _normalize_confidence(value: Any) -> float | None:
        if value in {None, ""}:
            return None
        try:
            normalized = float(value)
        except Exception:
            return None
        return max(0.0, min(normalized, 1.0))

    @staticmethod
    def _get_ledger(run_context: RunContext) -> dict[str, Any] | None:
        payload = run_context.metadata.get("reasoning")
        if not isinstance(payload, dict):
            return None
        return dict(payload)

    @staticmethod
    def _build_stage_label(*, stage: str) -> str:
        labels = {
            "intake": "Consulta",
            "bootstrap": "Lectura",
            "memory": "Memoria",
            "query_intelligence": "Resolucion",
            "planning": "Ruta",
            "diagnostics": "Hallazgo",
            "response": "Aprendizaje",
        }
        normalized = str(stage or "").strip().lower()
        return labels.get(normalized, normalized or "Paso")

    def _build_display_text(self, *, entry: dict[str, Any]) -> str:
        stage = str(entry.get("stage") or "").strip().lower()
        details = dict(entry.get("details") or {})
        summary = str(entry.get("summary") or "").strip()

        if stage == "bootstrap":
            domain = str(details.get("domain") or "").strip().lower()
            agent = str(details.get("selected_agent") or "").strip()
            if domain:
                if agent:
                    return f"Ubique la consulta en {domain} y asigne {agent}."
                return f"Ubique la consulta en {domain}."
        if stage == "memory":
            query_patterns = int(details.get("query_patterns") or 0)
            reasoning_patterns = int(details.get("reasoning_patterns") or 0)
            if query_patterns or reasoning_patterns:
                parts: list[str] = []
                if query_patterns:
                    parts.append(f"{query_patterns} patrones de consulta")
                if reasoning_patterns:
                    parts.append(f"{reasoning_patterns} aprendizajes previos")
                return f"Recupere {', '.join(parts)} para orientar la respuesta."
            output_mode = str(details.get("output_mode") or "").strip()
            if output_mode:
                return f"Recupere preferencias previas de salida {output_mode}."
        if stage == "query_intelligence":
            strategy = str(details.get("strategy") or "").strip().lower()
            domain_code = str(details.get("domain_code") or "").strip().lower()
            template_id = str(details.get("template_id") or "").strip().lower()
            status_value = str(details.get("status_value") or "").strip().lower()
            temporal_column_hint = str(details.get("temporal_column_hint") or "").strip().lower()
            period_label = str(details.get("period_label") or "").strip().replace("_", " ")
            if domain_code and status_value and temporal_column_hint:
                if period_label:
                    return (
                        f"Resolvi {domain_code} con estado {status_value}, "
                        f"periodo {period_label} y columna {temporal_column_hint}."
                    )
                return f"Resolvi {domain_code} con estado {status_value} usando {temporal_column_hint}."
            if domain_code and strategy:
                if template_id:
                    return f"Resolvi {domain_code} con estrategia {strategy} y plantilla {template_id}."
                return f"Resolvi {domain_code} con estrategia {strategy}."
        if stage == "planning":
            capability_id = str(details.get("top_capability_id") or "").strip()
            if capability_id:
                return f"Elegi {capability_id} como mejor ruta de ejecucion."
        if stage == "diagnostics":
            signatures = [
                str(item or "").strip().replace("_", " ")
                for item in list(details.get("signatures") or [])
                if str(item or "").strip()
            ]
            if signatures:
                return f"Detecte {signatures[0]} y ajuste el razonamiento para no repetirlo."
        if stage == "response":
            pending = int(details.get("pending_proposals") or 0)
            if pending > 0:
                return f"Genere la respuesta y guarde {pending} aprendizajes para futuras consultas."
            if bool(details.get("diagnostics_activated")):
                return "Genere la respuesta y deje trazado el aprendizaje detectado."
        return summary
