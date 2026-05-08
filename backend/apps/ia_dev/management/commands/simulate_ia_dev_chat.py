import json
import os
import sys
from datetime import date, datetime
from typing import Any, Callable
from urllib import error, request

from django.core.management.base import BaseCommand, CommandError

from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.runtime.service_runtime_bootstrap import (
    SERVICE_RUNTIME_DEFAULTS,
    apply_service_runtime_bootstrap,
)
from apps.ia_dev.services.observability_service import ObservabilityService
from apps.ia_dev.services.orchestrator_legacy_runtime import LegacyOrchestratorRuntime


class RuntimeEventHumanizer:
    _PHASE_LABELS = {
        "inicio": "Inicio",
        "memoria": "Memoria/contexto",
        "intencion": "Comprension de intencion",
        "diccionario": "Consulta a ai_dictionary",
        "decision": "Decision de ejecucion",
        "sql": "Ejecucion SQL assisted",
        "handler": "Ejecucion por handler moderno",
        "fallback": "Fallback seguro",
        "respuesta": "Construccion de respuesta",
        "hallazgo": "Hallazgo/recomendacion",
    }

    def __init__(self, *, message: str = ""):
        self.message = str(message or "").strip()
        self._summary_steps: list[str] = []
        self._seen_summary_steps: set[str] = set()

    def record_question_received(self) -> None:
        if self.message:
            self._append_summary_step("Se recibio la pregunta.")

    def humanize_event(self, event: dict[str, Any]) -> dict[str, str] | None:
        event_type = str(event.get("event_type") or "").strip().lower()
        meta = dict(event.get("meta") or {})
        if event_type == "memory_used_in_chat":
            total = int(meta.get("user_memory_count") or 0) + int(meta.get("business_memory_count") or 0)
            support = []
            if int(meta.get("business_memory_count") or 0) > 0:
                support.append(f"{int(meta.get('business_memory_count') or 0)} pistas del negocio")
            if int(meta.get("user_memory_count") or 0) > 0:
                support.append(f"{int(meta.get('user_memory_count') or 0)} preferencias previas")
            detail = ", ".join(support) if support else "sin memoria previa relevante"
            self._append_summary_step("Se reviso memoria y contexto previo del negocio.")
            return {
                "phase": self._PHASE_LABELS["memoria"],
                "status": "info",
                "message": f"📚 Consultando memoria y contexto del negocio... Encontramos {detail}.",
                "key": f"memory:{total}",
            }
        if event_type == "query_pattern_candidates_loaded":
            count = int(meta.get("candidate_count") or 0)
            ranking = list(meta.get("ranking") or [])
            top = ""
            if ranking:
                first = ranking[0]
                if isinstance(first, dict):
                    top = str(first.get("pattern_key") or first.get("domain_code") or "").strip()
            suffix = f" Referencias encontradas: {count}." if count else " No hubo patrones previos fuertes."
            if top:
                suffix += f" La mejor pista fue {top}."
            self._append_summary_step("Se contrasto la pregunta con patrones historicos de consulta.")
            return {
                "phase": self._PHASE_LABELS["intencion"],
                "status": "info",
                "message": f"🧠 Entendiendo la pregunta...{suffix}",
                "key": f"patterns:{count}:{top}",
            }
        if event_type == "intent_arbitration_resolved":
            final_intent = str(meta.get("arbitrated_intent") or meta.get("final_intent") or "").strip()
            domain = str(meta.get("domain") or meta.get("domain_code") or meta.get("final_domain") or "").strip()
            summary = str(meta.get("arbitration_reason") or "").strip()
            decision = "Se resolvio la intencion de la consulta."
            if final_intent:
                decision = f"Se resolvio la intencion principal como {final_intent}."
            if domain:
                decision += f" Dominio orientado: {domain}."
            if summary:
                decision += f" Motivo: {summary}"
            self._append_summary_step("Se resolvio la intencion y el dominio de la consulta.")
            return {
                "phase": self._PHASE_LABELS["decision"],
                "status": "ok",
                "message": f"🧭 Resolviendo intencion con OpenAI/GPT... {decision}",
                "key": f"intent:{final_intent}:{domain}",
            }
        if event_type == "query_intelligence_resolved":
            strategy = str(meta.get("strategy") or "").strip()
            capability_id = str(meta.get("capability_id") or "").strip()
            detail = "La metadata disponible fue suficiente para elegir una ruta de ejecucion."
            if strategy == "sql_assisted":
                detail = "La consulta puede resolverse con una consulta inteligente sobre datos reales."
            elif strategy == "fallback":
                detail = "La metadata no alcanza para una consulta inteligente y se preparara una salida segura."
            elif strategy:
                detail = f"Se eligio la estrategia {strategy} para responder."
            if capability_id:
                detail += f" Capacidad objetivo: {capability_id}."
            self._append_summary_step("Se definio la ruta de ejecucion para responder.")
            return {
                "phase": self._PHASE_LABELS["diccionario"],
                "status": "info",
                "message": f"🗂️ Revisando ai_dictionary y metadata operativa... {detail}",
                "key": f"qi:{strategy}:{capability_id}",
            }
        if event_type == "query_sql_assisted_executed":
            rowcount = int(meta.get("rowcount") or 0)
            duration_ms = int(meta.get("duration_ms") or 0)
            domain = str(meta.get("domain_code") or "").strip()
            detail = f"Se consultaron datos reales del dominio {domain or 'operativo'}."
            if rowcount:
                detail += f" Filas recuperadas: {rowcount}."
            if duration_ms:
                detail += f" Tiempo estimado: {duration_ms} ms."
            self._append_summary_step("Se ejecuto una consulta inteligente sobre datos reales.")
            return {
                "phase": self._PHASE_LABELS["sql"],
                "status": "ok",
                "message": f"📊 Ejecutando una consulta inteligente sobre datos reales... {detail}",
                "key": f"sql:{domain}:{rowcount}",
            }
        if event_type == "query_intelligence_error":
            self._append_summary_step(
                "No se pudo usar la ruta inteligente de consulta y se activo una alternativa segura."
            )
            return {
                "phase": self._PHASE_LABELS["fallback"],
                "status": "warning",
                "message": (
                    "⚠️ No se pudo usar la ruta inteligente de consulta para esta pregunta. "
                    "El sistema usara una ruta segura alternativa."
                ),
                "key": "query_intelligence_error",
            }
        if event_type == "runtime_fallback_used":
            reason = str(meta.get("reason") or meta.get("fallback_reason") or "").strip()
            extra = (
                f" Motivo observado: {reason}."
                if reason
                else " No hubo suficiente metadata para una consulta inteligente confiable."
            )
            self._append_summary_step("Se utilizo un fallback seguro para mantener la respuesta controlada.")
            return {
                "phase": self._PHASE_LABELS["fallback"],
                "status": "warning",
                "message": (
                    "⚠️ No hubo suficiente metadata para ejecutar SQL assisted. "
                    f"Se usara fallback seguro sin legacy silencioso.{extra}"
                ),
                "key": f"fallback:{reason}",
            }
        if event_type.endswith("_handler_executed"):
            capability_id = str(meta.get("capability_id") or "").strip()
            capability_domain = str(meta.get("capability_domain") or event_type.replace("_handler_executed", "")).strip()
            detail = f"Se ejecuto la ruta moderna segura para {capability_domain or 'el dominio solicitado'}."
            if capability_id:
                detail += f" Capacidad: {capability_id}."
            self._append_summary_step("Se uso un handler moderno y seguro para resolver la consulta.")
            return {
                "phase": self._PHASE_LABELS["handler"],
                "status": "ok",
                "message": f"🛡️ Ejecutando handler moderno seguro... {detail}",
                "key": f"handler:{capability_domain}:{capability_id}",
            }
        if event_type == "runtime_response_resolved":
            flow = str(meta.get("response_flow") or "").strip()
            domain = str(meta.get("domain_resolved") or "").strip()
            dimensions = [str(item).strip() for item in list(meta.get("dimensions_used") or []) if str(item).strip()]
            detail = "La respuesta final ya fue construida con datos y reglas del sistema."
            if domain:
                detail += f" Dominio resuelto: {domain}."
            if dimensions:
                detail += f" Dimensiones usadas: {', '.join(dimensions[:3])}."
            if flow:
                detail += f" Ruta final: {flow}."
            self._append_summary_step("Se genero la respuesta final del asistente.")
            return {
                "phase": self._PHASE_LABELS["respuesta"],
                "status": "ok",
                "message": f"✅ Respuesta construida con datos reales. {detail}",
                "key": f"response:{flow}:{domain}",
            }
        if event_type == "knowledge_proposal_created":
            self._append_summary_step("Se detecto una propuesta de conocimiento para revision posterior.")
            return {
                "phase": self._PHASE_LABELS["hallazgo"],
                "status": "info",
                "message": (
                    "💡 Se genero una propuesta de conocimiento para revisar o enriquecer la base del asistente."
                ),
                "key": "knowledge_proposal_created",
            }
        return None

    def build_explained_flow(self, payload: dict[str, Any]) -> list[str]:
        steps: list[str] = list(self._summary_steps)
        if not steps:
            steps.append("Se recibio la pregunta.")
        domain = self._resolve_domain(payload)
        if domain:
            steps.append(f"Se identifico el dominio: {domain}.")
        period = self._resolve_period(payload)
        if period:
            steps.append(f"Se resolvio el periodo: {period}.")
        route = self._resolve_route(payload)
        if route:
            steps.append(route)
        if self._response_uses_real_data(payload):
            steps.append("Se consultaron datos reales o metadata operativa trazable.")
        steps.append("Se genero una respuesta con explicacion y siguiente accion sugerida.")
        return self._dedupe_steps(steps)

    def build_business_sections(self, payload: dict[str, Any]) -> list[tuple[str, str]]:
        reply = str(payload.get("reply") or payload.get("message") or "").strip()
        insights = [
            str(item).strip()
            for item in list(((payload.get("data") or {}).get("insights") or []))
            if str(item).strip()
        ]
        actions = [
            str((item or {}).get("label") or (item or {}).get("text") or item).strip()
            for item in list(payload.get("actions") or [])
            if str((item or {}).get("label") or (item or {}).get("text") or item).strip()
        ]
        main_data = self._resolve_main_data_point(payload)
        hallazgo = insights[0] if insights else ""
        riesgo = self._infer_risk(payload=payload, main_data=main_data, hallazgo=hallazgo)
        recomendacion = actions[0] if actions else ""
        if not recomendacion:
            suggestion = self._resolve_followup_suggestion(payload)
            if suggestion:
                recomendacion = suggestion
        siguiente_accion = self._resolve_next_action(payload)

        sections: list[tuple[str, str]] = []
        if main_data or reply:
            sections.append(("Dato principal", main_data or reply))
        if hallazgo:
            sections.append(("Hallazgo", hallazgo))
        if riesgo:
            sections.append(("Riesgo o interpretacion", riesgo))
        if recomendacion:
            sections.append(("Recomendacion", recomendacion))
        if siguiente_accion:
            sections.append(("Siguiente accion sugerida", siguiente_accion))
        return sections

    def _append_summary_step(self, step: str) -> None:
        normalized = str(step or "").strip()
        if not normalized:
            return
        token = normalized.lower()
        if token in self._seen_summary_steps:
            return
        self._seen_summary_steps.add(token)
        self._summary_steps.append(normalized)

    @staticmethod
    def _dedupe_steps(steps: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for step in steps:
            normalized = str(step or "").strip()
            if not normalized:
                continue
            token = normalized.lower()
            if token in seen:
                continue
            seen.add(token)
            result.append(normalized)
        return result

    @staticmethod
    def _resolve_domain(payload: dict[str, Any]) -> str:
        orchestrator = dict(payload.get("orchestrator") or {})
        qi = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})
        resolved_query = dict(qi.get("resolved_query") or {})
        intent = dict(resolved_query.get("intent") or qi.get("intent") or {})
        return str(
            orchestrator.get("final_domain")
            or orchestrator.get("domain")
            or intent.get("domain_code")
            or ""
        ).strip()

    @staticmethod
    def _resolve_period(payload: dict[str, Any]) -> str:
        qi = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})
        resolved_query = dict(qi.get("resolved_query") or {})
        normalized_period = dict(resolved_query.get("normalized_period") or {})
        start = str(normalized_period.get("start_date") or "").strip()
        end = str(normalized_period.get("end_date") or "").strip()
        if start and end and start == end:
            return start
        if start and end:
            return f"del {start} al {end}"
        return ""

    @staticmethod
    def _resolve_route(payload: dict[str, Any]) -> str:
        orchestrator = dict(payload.get("orchestrator") or {})
        runtime_flow = str(orchestrator.get("runtime_flow") or "").strip().lower()
        qi = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})
        execution_plan = dict(qi.get("execution_plan") or {})
        strategy = str(execution_plan.get("strategy") or "").strip().lower()
        if runtime_flow == "sql_assisted" or strategy == "sql_assisted":
            return "Se decidio usar SQL assisted para resolver la consulta con datos reales."
        if runtime_flow == "handler":
            return "Se decidio usar un handler moderno porque era la ruta mas segura para esta consulta."
        if runtime_flow == "legacy_fallback" or strategy == "fallback":
            return "Se eligio una ruta segura alternativa para evitar una ejecucion insegura."
        return ""

    @staticmethod
    def _response_uses_real_data(payload: dict[str, Any]) -> bool:
        sources = dict(payload.get("data_sources") or {})
        runtime = dict(sources.get("runtime") or {})
        qi = dict(sources.get("query_intelligence") or {})
        if bool(qi.get("ok")):
            return True
        return str(runtime.get("runtime_authority") or "").strip() == "query_execution_planner"

    @staticmethod
    def _resolve_main_data_point(payload: dict[str, Any]) -> str:
        data = dict(payload.get("data") or {})
        kpis = dict(data.get("kpis") or {})
        reply = str(payload.get("reply") or payload.get("message") or "").strip()
        if "total_ausentismos_injustificados" in kpis:
            return f"Hoy se registran {kpis['total_ausentismos_injustificados']} ausentismos injustificados."
        if "total_ausencias" in kpis:
            return f"Se registran {kpis['total_ausencias']} ausencias en el resultado consultado."
        if "total_grupos" in kpis:
            return f"Se identificaron {kpis['total_grupos']} grupos relevantes en la consulta."
        if reply:
            return reply
        return ""

    @staticmethod
    def _infer_risk(*, payload: dict[str, Any], main_data: str, hallazgo: str) -> str:
        text = " ".join(part for part in [main_data, hallazgo, str(payload.get('reply') or '').strip()] if part).lower()
        if "injustific" in text or "ausent" in text:
            return (
                "Puede existir afectacion operativa si no se revisan las areas o empleados con mayor concentracion."
            )
        if "fallback" in text:
            return "La respuesta es segura, pero podria requerir una pregunta mas especifica para profundizar."
        return ""

    def _resolve_followup_suggestion(self, payload: dict[str, Any]) -> str:
        qi = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})
        summary = self._build_resolution_summary(payload=payload, qi=qi)
        return str(summary.get("sugerencia_continuacion") or "").strip()

    def _resolve_next_action(self, payload: dict[str, Any]) -> str:
        suggestion = self._resolve_followup_suggestion(payload)
        if suggestion:
            return f'Pregunta: "{suggestion}"'
        actions = list(payload.get("actions") or [])
        if actions:
            first = actions[0]
            text = str((first or {}).get("text") or (first or {}).get("label") or first).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _build_resolution_summary(payload: dict[str, Any], qi: dict[str, Any]) -> dict[str, Any]:
        orchestrator = dict(payload.get("orchestrator") or {})
        execution_plan = dict(qi.get("execution_plan") or {})
        intent = dict((qi.get("resolved_query") or {}).get("intent") or qi.get("intent") or {})
        route = {
            "selected_capability_id": str(orchestrator.get("selected_capability_id") or ""),
            "execute_capability": str(orchestrator.get("runtime_flow") or "") == "handler",
            "use_legacy": str(orchestrator.get("runtime_flow") or "") == "legacy_fallback",
            "reason": str(orchestrator.get("fallback_reason") or ""),
        }
        semantic_norm = dict(qi.get("semantic_normalization") or {})
        canonical_resolution = dict(qi.get("canonical_resolution") or {})
        return Command()._build_resolucion_consulta_resumen(
            orchestrator=orchestrator,
            route=route,
            intent=intent,
            execution_plan=execution_plan,
            semantic_normalization=semantic_norm,
            canonical_resolution=canonical_resolution,
        )


class _RealtimeObservabilityProxy:
    def __init__(self, *, base, on_event: Callable[[dict[str, Any]], None]):
        self._base = base
        self._on_event = on_event
        self.enabled = bool(getattr(base, "enabled", True))

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        duration_ms: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        meta: dict | None = None,
    ):
        event = {
            "event_type": str(event_type or ""),
            "source": str(source or ""),
            "duration_ms": duration_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "meta": dict(meta or {}),
            "at": datetime.utcnow().isoformat() + "Z",
        }
        try:
            self._on_event(event)
        except Exception:
            # No bloquear la simulacion por fallos de visualizacion live.
            pass
        self._base.record_event(
            event_type=event_type,
            source=source,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            meta=meta,
        )

    def __getattr__(self, name: str):
        return getattr(self._base, name)


class Command(BaseCommand):
    help = "Simula consultas de /ia-dev/chat desde terminal (modo service u HTTP)."
    _TRACE_COMPACT_LIMIT = 12
    _SERVICE_RUNTIME_DEFAULTS = SERVICE_RUNTIME_DEFAULTS

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["service", "http"],
            default="service",
            help="service: llama ChatApplicationService directo. http: llama POST /ia-dev/chat/.",
        )
        parser.add_argument(
            "--skip-service-runtime-bootstrap",
            action="store_true",
            help=(
                "Solo mode=service. Evita forzar flags de runtime para capability/query intelligence "
                "durante la simulacion."
            ),
        )
        parser.add_argument("--message", type=str, help="Mensaje a consultar.")
        parser.add_argument("--session-id", type=str, default="cli-session")
        parser.add_argument("--reset-memory", action="store_true")
        parser.add_argument("--actor-user-key", type=str, default=None)
        parser.add_argument("--raw", action="store_true", help="Imprime JSON completo.")
        parser.add_argument(
            "--flow",
            choices=["auto", "off", "compact", "full"],
            default="auto",
            help=(
                "Nivel de trazabilidad visual en terminal. "
                "auto: compact en interactive, off en no-interactive."
            ),
        )
        parser.add_argument(
            "--live",
            choices=["auto", "off", "compact", "full", "human"],
            default="auto",
            help=(
                "Trazas en tiempo real durante la ejecucion (solo mode=service). "
                "auto: compact en interactive, off en no-interactive."
            ),
        )
        parser.add_argument("--interactive", action="store_true", help="Inicia modo conversacional.")
        parser.add_argument(
            "--base-url",
            type=str,
            default="http://127.0.0.1:8000",
            help="Base URL para modo http.",
        )
        parser.add_argument(
            "--auth-token",
            type=str,
            default=None,
            help="Bearer token para modo http.",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default=None,
            help="X-API-Key para modo http.",
        )
        parser.add_argument("--timeout", type=int, default=45)

    def handle(self, *args, **options):
        self._prepare_terminal_io()
        self._active_humanizer: RuntimeEventHumanizer | None = None
        mode = str(options.get("mode") or "service").strip().lower()
        interactive = bool(options.get("interactive"))
        raw = bool(options.get("raw"))
        session_id = str(options.get("session_id") or "cli-session").strip()
        flow_mode = self._resolve_flow_mode(
            requested_mode=str(options.get("flow") or "auto").strip().lower(),
            interactive=interactive,
        )
        live_mode = self._resolve_live_mode(
            requested_mode=str(options.get("live") or "auto").strip().lower(),
            interactive=interactive,
            mode=mode,
        )
        runtime_bootstrap = not bool(options.get("skip_service_runtime_bootstrap"))

        if mode == "service" and runtime_bootstrap:
            self._apply_service_runtime_bootstrap()

        if interactive:
            self._run_interactive(
                mode=mode,
                raw=raw,
                options=options,
                session_id=session_id,
                flow_mode=flow_mode,
                live_mode=live_mode,
                runtime_bootstrap=runtime_bootstrap,
            )
            return

        message = self._normalize_cli_message(str(options.get("message") or ""))
        if not message:
            raise CommandError("Debes enviar --message o usar --interactive.")

        payload = self._run_once(
            mode=mode,
            message=message,
            session_id=session_id,
            reset_memory=bool(options.get("reset_memory")),
            actor_user_key=options.get("actor_user_key"),
            options=options,
            live_mode=live_mode,
        )
        self._print_payload(payload, raw=raw, flow_mode=flow_mode, live_mode=live_mode)

    def _run_interactive(
        self,
        *,
        mode: str,
        raw: bool,
        options: dict[str, Any],
        session_id: str,
        flow_mode: str,
        live_mode: str,
        runtime_bootstrap: bool,
    ):
        self.stdout.write(self.style.SUCCESS("Simulador IA DEV interactivo"))
        self.stdout.write(f"mode={mode} | session_id={session_id}")
        if mode == "service":
            status = "on" if runtime_bootstrap else "off"
            self.stdout.write(f"service_runtime_bootstrap={status}")
        self.stdout.write(f"flow_mode={flow_mode}")
        self.stdout.write(f"live_mode={live_mode}")
        self.stdout.write(
            "Comandos: /exit, /reset, /session <id>, /flow <off|compact|full>, "
            "/live <off|compact|full|human>"
        )

        current_session = session_id
        current_flow_mode = flow_mode
        current_live_mode = live_mode
        while True:
            try:
                message = self._normalize_cli_message(input("tu> "))
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("")
                self.stdout.write("Fin de sesion.")
                return

            if not message:
                continue
            if message in {"/exit", "/quit"}:
                self.stdout.write("Fin de sesion.")
                return
            if message == "/reset":
                payload = self._run_once(
                    mode=mode,
                    message="reset",
                    session_id=current_session,
                    reset_memory=True,
                    actor_user_key=options.get("actor_user_key"),
                    options=options,
                    live_mode=current_live_mode,
                )
                self._print_payload(payload, raw=raw, flow_mode=current_flow_mode, live_mode=current_live_mode)
                continue
            if message.startswith("/session "):
                new_session = message.replace("/session ", "", 1).strip()
                if new_session:
                    current_session = new_session
                    self.stdout.write(f"session_id={current_session}")
                continue
            if message.startswith("/flow "):
                requested_flow = message.replace("/flow ", "", 1).strip().lower()
                if requested_flow in {"off", "compact", "full"}:
                    current_flow_mode = requested_flow
                    self.stdout.write(f"flow_mode={current_flow_mode}")
                else:
                    self.stdout.write(self.style.WARNING("flow invalido. Usa: off | compact | full"))
                continue
            if message.startswith("/live "):
                requested_live = message.replace("/live ", "", 1).strip().lower()
                if requested_live in {"off", "compact", "full", "human"}:
                    current_live_mode = requested_live
                    self.stdout.write(f"live_mode={current_live_mode}")
                else:
                    self.stdout.write(self.style.WARNING("live invalido. Usa: off | compact | full | human"))
                continue

            payload = self._run_once(
                mode=mode,
                message=message,
                session_id=current_session,
                reset_memory=False,
                actor_user_key=options.get("actor_user_key"),
                options=options,
                live_mode=current_live_mode,
            )
            self._print_payload(payload, raw=raw, flow_mode=current_flow_mode, live_mode=current_live_mode)

    def _run_once(
        self,
        *,
        mode: str,
        message: str,
        session_id: str,
        reset_memory: bool,
        actor_user_key: str | None,
        options: dict[str, Any],
        live_mode: str,
    ) -> dict:
        if mode == "http":
            return self._run_http(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                options=options,
            )
        return self._run_service(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
            actor_user_key=actor_user_key,
            live_mode=live_mode,
        )

    def _run_service(
        self,
        *,
        message: str,
        session_id: str,
        reset_memory: bool,
        actor_user_key: str | None,
        live_mode: str,
    ) -> dict:
        service = ChatApplicationService()
        legacy_runtime = LegacyOrchestratorRuntime()
        observability = ObservabilityService()
        self._active_humanizer = None
        if live_mode in {"compact", "full", "human"}:
            humanizer = RuntimeEventHumanizer(message=message) if live_mode == "human" else None
            if humanizer is not None:
                humanizer.record_question_received()
                self._active_humanizer = humanizer
            observability = _RealtimeObservabilityProxy(
                base=observability,
                on_event=lambda event: self._emit_live_event(event=event, live_mode=live_mode),
            )
            if live_mode == "human":
                self.stdout.write(self.style.WARNING("live> explicacion humana del flujo activada"))
            else:
                self.stdout.write(self.style.WARNING(f"live> observability en tiempo real ({live_mode})"))
        legacy_runtime.observability = observability
        return service.run(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
            legacy_runner=lambda **kwargs: legacy_runtime.run(**kwargs),
            observability=observability,
            actor_user_key=actor_user_key,
        )

    def _run_http(
        self,
        *,
        message: str,
        session_id: str,
        reset_memory: bool,
        options: dict[str, Any],
    ) -> dict:
        base_url = str(options.get("base_url") or "http://127.0.0.1:8000").rstrip("/")
        url = f"{base_url}/ia-dev/chat/"
        body = json.dumps(
            {
                "message": message,
                "session_id": session_id,
                "reset_memory": reset_memory,
            }
        ).encode("utf-8")
        req = request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        auth_token = str(options.get("auth_token") or "").strip()
        api_key = str(options.get("api_key") or "").strip()
        if auth_token:
            req.add_header("Authorization", f"Bearer {auth_token}")
        if api_key:
            req.add_header("X-API-Key", api_key)

        timeout = int(options.get("timeout") or 45)
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise CommandError(f"HTTP {exc.code}: {error_text}") from exc
        except error.URLError as exc:
            raise CommandError(f"No se pudo conectar a {url}: {exc.reason}") from exc

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Respuesta no-JSON desde {url}: {text[:300]}") from exc

    def _print_payload(self, payload: dict, *, raw: bool, flow_mode: str = "off", live_mode: str = "off"):
        if raw:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default))
            return

        reply = str(payload.get("reply") or payload.get("message") or "").strip()
        sid = str(payload.get("session_id") or "").strip()
        domain = str((payload.get("orchestrator") or {}).get("domain") or "").strip()
        route = str((payload.get("orchestrator") or {}).get("routing_mode") or "").strip()

        self.stdout.write("")
        if reply:
            self.stdout.write(self.style.SUCCESS(f"assistant> {reply}"))
        else:
            self.stdout.write(self.style.WARNING("assistant> (sin campo reply)"))
        if sid:
            self.stdout.write(f"session_id: {sid}")
        if domain:
            self.stdout.write(f"domain: {domain}")
        if route:
            self.stdout.write(f"routing_mode: {route}")
        if live_mode == "human":
            self._print_human_response_summary(payload=payload)
        if flow_mode in {"compact", "full"}:
            self._print_flow_summary(payload=payload, flow_mode=flow_mode)

    def _print_human_response_summary(self, *, payload: dict[str, Any]) -> None:
        humanizer = self._active_humanizer or RuntimeEventHumanizer(
            message=str(payload.get("message") or payload.get("reply") or "").strip()
        )
        sections = humanizer.build_business_sections(payload)
        if sections:
            self.stdout.write("")
            for title, content in sections:
                text = str(content or "").strip()
                if not text:
                    continue
                self.stdout.write(f"{title}:")
                self.stdout.write(text)
                self.stdout.write("")
        steps = humanizer.build_explained_flow(payload)
        if steps:
            self.stdout.write("Flujo explicado:")
            for idx, step in enumerate(steps, start=1):
                self.stdout.write(f"{idx}. {step}")

    def _print_flow_summary(self, *, payload: dict, flow_mode: str) -> None:
        orchestrator = dict(payload.get("orchestrator") or {})
        runtime_meta = dict((payload.get("data_sources") or {}).get("runtime") or {})
        route = {
            "selected_capability_id": str(orchestrator.get("selected_capability_id") or ""),
            "execute_capability": str(orchestrator.get("runtime_flow") or "") == "handler",
            "use_legacy": str(orchestrator.get("runtime_flow") or "") == "legacy_fallback",
            "reason": str(orchestrator.get("fallback_reason") or ""),
        }
        qi_payload = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})
        execution_plan = dict(qi_payload.get("execution_plan") or {})
        query_pattern_fastpath = dict(qi_payload.get("query_pattern_fastpath") or {})
        intent = dict(qi_payload.get("intent") or {})
        semantic_norm = dict(qi_payload.get("semantic_normalization") or {})
        canonical_resolution = dict(qi_payload.get("canonical_resolution") or {})
        semantic_diag = dict(((payload.get("data_sources") or {}).get("query_intelligence") or {}).get("semantic_diagnostics") or {})
        sources = dict(payload.get("data_sources") or {})
        trace = list(payload.get("trace") or [])

        self.stdout.write("flujo:")
        self.stdout.write(
            "  clasificacion: "
            f"intent={str(orchestrator.get('intent') or '') or '-'} | "
            f"domain={str(orchestrator.get('domain') or '') or '-'} | "
            f"agent={str(orchestrator.get('selected_agent') or '') or '-'} | "
            f"source={str(orchestrator.get('classifier_source') or '') or '-'}"
        )
        if route:
            self.stdout.write(
                "  route: "
                f"capability={str(route.get('selected_capability_id') or runtime_meta.get('task_state_key') or '-')}"
                f" | execute={bool(route.get('execute_capability'))}"
                f" | use_legacy={bool(route.get('use_legacy'))}"
                f" | reason={str(route.get('reason') or '-')}"
            )
        if qi_payload or semantic_diag:
            strategy = str(execution_plan.get("strategy") or semantic_diag.get("strategy") or "").strip() or "-"
            warnings = list(semantic_diag.get("warnings") or [])
            self.stdout.write(
                "  query_intelligence: "
                f"mode={str(qi_payload.get('mode') or '-')} | "
                f"enabled={bool(qi_payload.get('enabled'))} | "
                f"domain={str(intent.get('domain_code') or '-')} | "
                f"op={str(intent.get('operation') or '-')} | "
                f"strategy={strategy}"
            )
            if warnings:
                self.stdout.write(f"  qi_warnings: {', '.join(str(w) for w in warnings)}")
            if bool(query_pattern_fastpath.get("hit")):
                self.stdout.write(
                    "  qi_fastpath: "
                    f"hit=True | openai_avoided={bool(query_pattern_fastpath.get('openai_avoided'))} | "
                    f"estimated_saved_ms={int(query_pattern_fastpath.get('estimated_saved_ms') or 0)}"
                )
        resumen = self._build_resolucion_consulta_resumen(
            orchestrator=orchestrator,
            route=route,
            intent=intent,
            execution_plan=execution_plan,
            semantic_normalization=semantic_norm,
            canonical_resolution=canonical_resolution,
        )
        self.stdout.write("  resolucion_consulta:")
        self.stdout.write(
            json.dumps(
                resumen,
                ensure_ascii=False,
                indent=2,
                default=self._json_default,
            )
            .replace("\n", "\n  ")
        )
        if sources:
            entries: list[str] = []
            for source_name, source_payload in sorted(sources.items()):
                if not isinstance(source_payload, dict):
                    continue
                ok = source_payload.get("ok", None)
                if ok is True:
                    marker = "ok"
                elif ok is False:
                    marker = "fail"
                else:
                    marker = "info"
                extra = str(
                    source_payload.get("mode")
                    or source_payload.get("strategy")
                    or source_payload.get("table")
                    or source_payload.get("domain")
                    or ""
                ).strip()
                if extra:
                    entries.append(f"{source_name}:{marker}({extra})")
                else:
                    entries.append(f"{source_name}:{marker}")
            if entries:
                self.stdout.write(f"  fuentes: {', '.join(entries)}")

        if trace:
            self.stdout.write("  etapas:")
            limit = len(trace) if flow_mode == "full" else self._TRACE_COMPACT_LIMIT
            for idx, event in enumerate(trace[:limit], start=1):
                if not isinstance(event, dict):
                    continue
                phase = str(event.get("phase") or "unknown")
                status = str(event.get("status") or "info").strip().lower()
                prefix = self._status_prefix(status)
                line = f"    {idx:02d}. {prefix} {phase}"
                if flow_mode == "full":
                    detail_excerpt = self._detail_excerpt(event.get("detail"))
                    if detail_excerpt:
                        line += f" -> {detail_excerpt}"
                self.stdout.write(self._style_by_status(status=status, text=line))
            if len(trace) > limit:
                pending = len(trace) - limit
                self.stdout.write(f"    ... +{pending} etapas mas")

    @staticmethod
    def _prepare_terminal_io() -> None:
        for stream in (getattr(sys, "stdin", None), getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
            if stream is None or not hasattr(stream, "reconfigure"):
                continue
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                continue

    @classmethod
    def _normalize_cli_message(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        repaired = cls._repair_terminal_mojibake(text)
        return str(repaired or text).strip()

    @staticmethod
    def _repair_terminal_mojibake(value: str) -> str:
        text = str(value or "")
        if not text:
            return ""
        suspicious_markers = ("Ã", "Â", "â€™", "â€œ", "â€", "ðŸ")
        if not any(marker in text for marker in suspicious_markers):
            return text
        for source_encoding in ("cp1252", "latin-1"):
            try:
                repaired = text.encode(source_encoding, errors="strict").decode("utf-8", errors="strict")
            except Exception:
                continue
            if repaired and repaired != text:
                return repaired
        return text

    @staticmethod
    def _resolve_flow_mode(*, requested_mode: str, interactive: bool) -> str:
        mode = str(requested_mode or "auto").strip().lower()
        if mode != "auto":
            return mode
        return "compact" if interactive else "off"

    @staticmethod
    def _resolve_live_mode(*, requested_mode: str, interactive: bool, mode: str) -> str:
        value = str(requested_mode or "auto").strip().lower()
        if mode != "service":
            return "off"
        if value != "auto":
            return value
        return "human" if interactive else "off"

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _detail_excerpt(detail: Any) -> str:
        if isinstance(detail, str):
            return detail.strip()[:140]
        if isinstance(detail, dict):
            for key in ("reason", "reply_preview", "error", "action", "policy_id"):
                val = str(detail.get(key) or "").strip()
                if val:
                    return f"{key}={val[:140]}"
            parts: list[str] = []
            for key in ("domain", "selected_agent", "needs_database", "routing_mode", "selected_capability_id"):
                if key in detail:
                    parts.append(f"{key}={detail.get(key)}")
            return " | ".join(parts)[:180]
        return str(detail or "").strip()[:140]

    @staticmethod
    def _status_prefix(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == "ok":
            return "[OK]"
        if normalized in {"warning", "warn"}:
            return "[WARN]"
        if normalized in {"error", "failed", "fail"}:
            return "[ERR]"
        return "[INFO]"

    def _style_by_status(self, *, status: str, text: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == "ok":
            return self.style.SUCCESS(text)
        if normalized in {"warning", "warn"}:
            return self.style.WARNING(text)
        if normalized in {"error", "failed", "fail"}:
            return self.style.ERROR(text)
        return text

    def _emit_live_event(self, *, event: dict[str, Any], live_mode: str) -> None:
        if live_mode == "human":
            humanizer = self._active_humanizer or RuntimeEventHumanizer()
            rendered = humanizer.humanize_event(event)
            if rendered:
                text = f"{rendered.get('message') or ''}".strip()
                status = str(rendered.get("status") or "info").strip().lower()
                if text:
                    self.stdout.write(self._style_by_status(status=status, text=text))
            return
        event_type = str(event.get("event_type") or "").strip()
        source = str(event.get("source") or "").strip()
        duration_ms = event.get("duration_ms")
        meta = dict(event.get("meta") or {})

        if live_mode == "compact" and event_type in {"tool_latency"}:
            return

        stamp = datetime.utcnow().strftime("%H:%M:%S")
        parts = [f"live> [{stamp}] {event_type or '-'} @{source or '-'}"]

        for key in (
            "trace_id",
            "run_id",
            "domain",
            "domain_code",
            "intent",
            "operation",
            "selected_agent",
            "selected_capability_id",
            "capability_id",
            "strategy",
            "decision",
            "reason",
            "next_phase",
            "target_phase",
        ):
            value = str(meta.get(key) or "").strip()
            if value:
                parts.append(f"{key}={value}")

        if isinstance(duration_ms, int) and duration_ms >= 0:
            parts.append(f"duration_ms={duration_ms}")

        estimate = self._extract_live_estimate(meta=meta)
        if estimate:
            parts.append(f"respuesta~={estimate}")

        line = " | ".join(parts)
        if live_mode == "full":
            detail = self._detail_excerpt(meta)
            if detail:
                line = f"{line} | meta={detail}"
        self.stdout.write(line)

    @staticmethod
    def _extract_live_estimate(*, meta: dict[str, Any]) -> str:
        for key in (
            "reply_preview",
            "response_preview",
            "estimated_reply",
            "estimated_response",
            "message_preview",
            "assistant_reply_preview",
        ):
            value = str(meta.get(key) or "").strip()
            if value:
                return value[:160]
        return ""

    def _build_resolucion_consulta_resumen(
        self,
        *,
        orchestrator: dict[str, Any],
        route: dict[str, Any],
        intent: dict[str, Any],
        execution_plan: dict[str, Any],
        semantic_normalization: dict[str, Any],
        canonical_resolution: dict[str, Any],
    ) -> dict[str, Any]:
        consulta_canonica = str(
            canonical_resolution.get("canonical_query")
            or semantic_normalization.get("canonical_query")
            or intent.get("raw_query")
            or ""
        ).strip()
        codigo_dominio = str(
            canonical_resolution.get("domain_code")
            or semantic_normalization.get("domain_code")
            or intent.get("domain_code")
            or orchestrator.get("domain")
            or execution_plan.get("domain_code")
            or ""
        ).strip().lower()
        codigo_intencion = str(
            canonical_resolution.get("intent_code")
            or semantic_normalization.get("intent_code")
            or intent.get("operation")
            or orchestrator.get("intent")
            or ""
        ).strip().lower()
        capability_resolved = str(
            route.get("selected_capability_id")
            or execution_plan.get("capability_id")
            or semantic_normalization.get("capability_hint")
            or ""
        ).strip().lower()
        orchestrator_domain = str(orchestrator.get("domain") or "").strip().lower()
        final_runtime_domain = str(
            orchestrator.get("final_domain")
            or execution_plan.get("domain_code")
            or canonical_resolution.get("domain_code")
            or semantic_normalization.get("domain_code")
            or intent.get("domain_code")
            or ""
        ).strip().lower()
        runtime_flow = str(orchestrator.get("runtime_flow") or "").strip().lower()
        execution_strategy = str(execution_plan.get("strategy") or "").strip().lower()
        arbitrated_intent = str(
            orchestrator.get("arbitrated_intent")
            or orchestrator.get("final_intent")
            or ""
        ).strip().lower()
        execution_domain = str(execution_plan.get("domain_code") or "").strip().lower()
        sql_assisted_runtime = runtime_flow == "sql_assisted" or execution_strategy == "sql_assisted"
        if sql_assisted_runtime and final_runtime_domain not in {"", "general", "legacy"}:
            codigo_dominio = final_runtime_domain
        elif (
            runtime_flow == "sql_assisted"
            and arbitrated_intent == "analytics_query"
            and "ausentismo" in {orchestrator_domain, execution_domain}
        ):
            codigo_dominio = "ausentismo"
        if not sql_assisted_runtime and capability_resolved.startswith("attendance.") and orchestrator_domain == "attendance":
            codigo_dominio = "attendance"
        elif not sql_assisted_runtime and capability_resolved.startswith("empleados.") and orchestrator_domain == "empleados":
            codigo_dominio = "empleados"
        if codigo_dominio in {"", "general"}:
            if capability_resolved.startswith("empleados."):
                codigo_dominio = "empleados"
            elif capability_resolved.startswith("attendance."):
                codigo_dominio = "attendance"
            elif capability_resolved.startswith("transport."):
                codigo_dominio = "transport"
            elif orchestrator_domain and orchestrator_domain not in {"general", "legacy"}:
                codigo_dominio = orchestrator_domain
        if capability_resolved == "empleados.detail.v1":
            codigo_intencion = "detail"
        execution_filters = dict((execution_plan.get("constraints") or {}).get("filters") or {})
        if capability_resolved.startswith("attendance.") and execution_filters:
            filtros = dict(execution_filters)
        else:
            filtros = dict(semantic_normalization.get("normalized_filters") or {})
            filtros.update(dict(intent.get("filters") or {}))
            filtros.update(execution_filters)
        if capability_resolved.startswith("attendance."):
            motivo = str(filtros.get("motivo_justificacion") or filtros.get("justificacion") or "").strip()
            if motivo and "justificacion" not in filtros:
                filtros["justificacion"] = motivo
            if motivo:
                for key in ("estado", "estado_empleado"):
                    if str(filtros.get(key) or "").strip().upper() == "ACTIVO":
                        filtros.pop(key, None)
        if capability_resolved in {"attendance.unjustified.table.v1", "attendance.unjustified.table_with_personal.v1"}:
            codigo_intencion = "detail"
        elif capability_resolved.startswith("attendance.summary.by_"):
            codigo_intencion = "aggregate"
        elif capability_resolved.startswith("attendance.unjustified.summary"):
            codigo_intencion = "summary"
        alias_detectados = self._extract_aliases_detectados(
            semantic_normalization=semantic_normalization,
            canonical_resolution=canonical_resolution,
        )
        sugerencia_capacidad = str(
            semantic_normalization.get("capability_hint")
            or canonical_resolution.get("capability_code")
            or execution_plan.get("capability_id")
            or route.get("selected_capability_id")
            or ""
        ).strip()
        confianza = self._safe_float(
            canonical_resolution.get("confidence"),
            semantic_normalization.get("confidence"),
            intent.get("confidence"),
            default=0.0,
        )
        ambiguedades = [
            dict(item or {})
            for item in list(semantic_normalization.get("ambiguities") or [])
            if isinstance(item, dict)
        ]
        conflictos = [
            dict(item or {})
            for item in list(canonical_resolution.get("conflicts") or [])
            if isinstance(item, dict)
        ]
        if conflictos and not ambiguedades:
            ambiguedades = conflictos
        sugerencia_continuacion = self._build_followup_suggestion(
            codigo_dominio=codigo_dominio,
            codigo_intencion=codigo_intencion,
            filtros=filtros,
            route=route,
            execution_plan=execution_plan,
            semantic_normalization=semantic_normalization,
        )

        return {
            "consulta_canonica": consulta_canonica,
            "codigo_dominio": codigo_dominio,
            "codigo_intencion": codigo_intencion,
            "filtros": filtros,
            "alias_detectados": alias_detectados,
            "sugerencia_capacidad": sugerencia_capacidad,
            "confianza": confianza,
            "ambiguedades": ambiguedades,
            "agente_seleccionado": str(orchestrator.get("selected_agent") or "").strip(),
            "estrategia_ejecucion": str(execution_plan.get("strategy") or "").strip(),
            "capacidad_enrutada": str(route.get("selected_capability_id") or "").strip(),
            "ejecuta_capacidad": bool(route.get("execute_capability")),
            "sugerencia_continuacion": sugerencia_continuacion,
        }

    @staticmethod
    def _extract_aliases_detectados(
        *,
        semantic_normalization: dict[str, Any],
        canonical_resolution: dict[str, Any],
    ) -> list[str]:
        aliases: list[str] = []
        for item in list(semantic_normalization.get("semantic_aliases") or []):
            if not isinstance(item, dict):
                continue
            requested = str(item.get("requested_term") or item.get("raw") or "").strip().lower()
            canonical = str(item.get("canonical_term") or item.get("canonical") or "").strip().lower()
            if requested:
                aliases.append(requested if not canonical else f"{requested}->{canonical}")
        for item in list(canonical_resolution.get("resolution_evidence") or []):
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() not in {"alias", "synonym", "sinonimo"}:
                continue
            raw_value = str(item.get("value") or item.get("raw") or "").strip().lower()
            canonical = str(item.get("canonical") or "").strip().lower()
            if raw_value:
                aliases.append(raw_value if not canonical else f"{raw_value}->{canonical}")
        deduped: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            token = str(alias or "").strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    @staticmethod
    def _safe_float(*values: Any, default: float = 0.0) -> float:
        for value in values:
            try:
                return float(value)
            except Exception:
                continue
        return float(default)

    @staticmethod
    def _build_followup_suggestion(
        *,
        codigo_dominio: str,
        codigo_intencion: str,
        filtros: dict[str, Any],
        route: dict[str, Any],
        execution_plan: dict[str, Any],
        semantic_normalization: dict[str, Any],
    ) -> str:
        capability_id = str(
            route.get("selected_capability_id")
            or execution_plan.get("capability_id")
            or semantic_normalization.get("capability_hint")
            or ""
        ).strip()
        normalized_filters = dict(semantic_normalization.get("normalized_filters") or {})
        merged_filters = {**normalized_filters, **dict(filtros or {})}
        if capability_id == "empleados.detail.v1" or (
            codigo_dominio == "empleados" and codigo_intencion == "detail"
        ):
            movil = str(merged_filters.get("movil") or "").strip()
            if movil:
                return (
                    f'Si deseas conocer algo especifico adicional de esta movil, continua con: '
                    f'"ausentismos de la movil {movil}" o "empleados de la movil {movil} por cargo".'
                )
            identifier = str(
                merged_filters.get("cedula")
                or merged_filters.get("codigo_sap")
                or merged_filters.get("search")
                or ""
            ).strip()
            if identifier:
                return (
                    f'Si quieres, continua con: "ausentismos de {identifier}" '
                    'o "detalle del empleado por cargo y area".'
                )
            return 'Si quieres, continua con: "empleados por cargo" o "ausentismos del empleado".'
        if capability_id.startswith("empleados.count.active"):
            return 'Puedes ampliar con: "empleados activos por cargo" o "detalle del empleado por cedula".'
        if capability_id.startswith("attendance.summary.by_"):
            return 'Puedes ampliar con: "detalle por empleado" o cambiar la agrupacion a area, cargo o supervisor.'
        if codigo_dominio == "attendance":
            return 'Puedes ampliar con: "ausentismos por area" o "detalle por empleado".'
        return 'Puedes ampliar con una dimension, un filtro o pidiendo detalle de un registro especifico.'

    def _apply_service_runtime_bootstrap(self) -> None:
        apply_service_runtime_bootstrap(force=True)
