import json
import os
from datetime import date, datetime
from typing import Any, Callable
from urllib import error, request

from django.core.management.base import BaseCommand, CommandError

from apps.ia_dev.application.runtime.service_runtime_bootstrap import (
    SERVICE_RUNTIME_DEFAULTS,
    apply_service_runtime_bootstrap,
)
from apps.ia_dev.services.orchestrator_service import IADevOrchestratorService


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
            help="service: llama IADevOrchestratorService directo. http: llama POST /ia-dev/chat/.",
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
            choices=["auto", "off", "compact", "full"],
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

        message = str(options.get("message") or "").strip()
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
        self._print_payload(payload, raw=raw, flow_mode=flow_mode)

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
        self.stdout.write("Comandos: /exit, /reset, /session <id>, /flow <off|compact|full>, /live <off|compact|full>")

        current_session = session_id
        current_flow_mode = flow_mode
        current_live_mode = live_mode
        while True:
            try:
                message = input("tu> ").strip()
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
                self._print_payload(payload, raw=raw, flow_mode=current_flow_mode)
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
                if requested_live in {"off", "compact", "full"}:
                    current_live_mode = requested_live
                    self.stdout.write(f"live_mode={current_live_mode}")
                else:
                    self.stdout.write(self.style.WARNING("live invalido. Usa: off | compact | full"))
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
            self._print_payload(payload, raw=raw, flow_mode=current_flow_mode)

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
        service = IADevOrchestratorService()
        if live_mode in {"compact", "full"}:
            service.observability = _RealtimeObservabilityProxy(
                base=service.observability,
                on_event=lambda event: self._emit_live_event(event=event, live_mode=live_mode),
            )
            self.stdout.write(self.style.WARNING(f"live> observability en tiempo real ({live_mode})"))
        return service.run(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
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

    def _print_payload(self, payload: dict, *, raw: bool, flow_mode: str = "off"):
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
        if flow_mode in {"compact", "full"}:
            self._print_flow_summary(payload=payload, flow_mode=flow_mode)

    def _print_flow_summary(self, *, payload: dict, flow_mode: str) -> None:
        orchestrator = dict(payload.get("orchestrator") or {})
        capability_shadow = dict(orchestrator.get("capability_shadow") or {})
        route = dict(capability_shadow.get("route") or {})
        qi_payload = dict(capability_shadow.get("query_intelligence") or {})
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
                f"capability={str(route.get('selected_capability_id') or '-')}"
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
        return "compact" if interactive else "off"

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
        if capability_resolved.startswith("attendance.") and orchestrator_domain == "attendance":
            codigo_dominio = "attendance"
        elif capability_resolved.startswith("empleados.") and orchestrator_domain == "empleados":
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
