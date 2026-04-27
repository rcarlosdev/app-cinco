import json
import logging
import os
import re
import unicodedata

from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService
from apps.ia_dev.infrastructure.ai.model_routing import resolve_model_name


logger = logging.getLogger(__name__)


class IntentClassifierService:
    def __init__(self):
        self.enable_openai = os.getenv("IA_DEV_USE_OPENAI_CLASSIFIER", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.model = resolve_model_name("intent_classifier")

    @staticmethod
    def _get_openai_api_key() -> str:
        return (
            os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or ""
        ).strip()

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = (text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _contains_unjustified_focus(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return "injustific" in msg or "sin justificar" in msg

    def _contains_attendance_domain(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(token in msg for token in ("ausent", "asistenc", "injustific", "justific"))

    def _contains_count_request(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(token in msg for token in ("cantidad", "cuantos", "cuantas", "total", "numero")) or bool(
            re.search(r"\bcantid[a-z]*\b", msg)
        )

    def _contains_employee_domain(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(
            token in msg
            for token in (
                "rrhh",
                "emplead",
                "colaborador",
                "personal",
                "persona",
                "cedula",
                "supervisor",
                "cargo",
                "area",
                "carpeta",
            )
        ) or bool(re.search(r"\bmovil\b", msg))

    def _contains_employee_status_focus(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(
            token in msg
            for token in (
                "activ",
                "vigent",
                "habilitad",
                "inactiv",
            )
        )

    def _is_employee_status_count_request(self, message: str) -> bool:
        msg = self._normalize_text(message)
        if not self._contains_employee_status_focus(message):
            return False
        if self._contains_count_request(message):
            return True
        return bool(re.search(r"\bhay\b", msg))

    def _looks_like_employee_lookup_request(self, message: str) -> bool:
        msg = self._normalize_text(message)
        if self._contains_attendance_domain(message):
            return False
        if any(token in msg for token in ("transporte", "ruta", "movilidad", "vehicul")):
            return False
        if EmployeeIdentifierService.has_movil_identifier(msg):
            return True
        match = re.search(
            r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+([a-z0-9_-]{3,40})\b",
            msg,
        )
        if not match:
            match = re.search(
                r"^\s*(?:info|informacion|detalle|datos|ficha)\s+([a-z0-9_-]{3,40})\s*$",
                msg,
            )
        if not match:
            return False
        candidate = str(match.group(1) or "").strip()
        if re.fullmatch(r"\d{6,13}", candidate):
            return True
        return bool(re.search(r"[a-z]", candidate) and re.search(r"\d", candidate))

    def _contains_group_dimension_request(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(
            token in msg
            for token in (
                "por supervisor",
                "por area",
                "por cargo",
                "por carpeta",
                "por justificacion",
                "por causa",
                "por motivo",
                "por tipo",
                "por estado",
            )
        )

    def _contains_missing_personal_focus(self, message: str) -> bool:
        msg = self._normalize_text(message)
        return any(
            token in msg
            for token in (
                "sin homologar",
                "sin personal",
                "sin nombre",
                "faltan datos de personal",
                "cedulas sin homologar",
            )
        )

    @staticmethod
    def _is_recurrence_request(msg: str) -> bool:
        if "reincid" not in msg:
            return False
        return bool(
            re.search(
                r"\b(semana|dias?|mes|anio|ultimo|ultimos|ultima|ultimas|anterior|pasad[oa])\b",
                msg,
            )
        )

    def _apply_deterministic_overrides(self, classification: dict, message: str) -> dict:
        result = dict(classification)
        if self._contains_attendance_domain(message) and self._contains_count_request(message) and self._contains_group_dimension_request(message):
            result.update(
                {
                    "domain": "ausentismo",
                    "intent": "ausentismo_query",
                    "selected_agent": "ausentismo_agent",
                    "needs_database": True,
                    "output_mode": "summary",
                    "needs_personal_join": True,
                }
            )
            return result
        if self._is_employee_status_count_request(message):
            result.update(
                {
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "selected_agent": "empleados_agent",
                    "needs_database": True,
                    "output_mode": "summary",
                }
            )
            return result
        if self._looks_like_employee_lookup_request(message):
            result.update(
                {
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "selected_agent": "empleados_agent",
                    "needs_database": True,
                    "output_mode": "table",
                }
            )
            return result
        if self._contains_missing_personal_focus(message):
            result.update(
                {
                    "domain": "ausentismo",
                    "intent": "ausentismo_query",
                    "selected_agent": "ausentismo_agent",
                    "needs_database": True,
                    "focus": "missing_personal",
                    "output_mode": "table",
                }
            )
            return result
        if self._contains_unjustified_focus(message):
            result.update(
                {
                    "domain": "ausentismo",
                    "intent": "ausentismo_query",
                    "selected_agent": "ausentismo_agent",
                    "needs_database": True,
                    "focus": "unjustified",
                }
            )
            if result.get("output_mode") == "summary":
                result["output_mode"] = "table"
        return result

    def classify(self, message: str) -> dict:
        fallback = self._classify_rules(message)
        hard_override = self._hard_rule_overrides(message)

        if not self.enable_openai:
            if hard_override:
                fallback.update(hard_override)
            fallback = self._apply_deterministic_overrides(fallback, message)
            fallback["classifier_source"] = "rules"
            return fallback

        openai_api_key = self._get_openai_api_key()
        if not openai_api_key:
            if hard_override:
                fallback.update(hard_override)
            fallback = self._apply_deterministic_overrides(fallback, message)
            fallback["classifier_source"] = "rules_no_api_key"
            return fallback

        try:
            llm_result = self._classify_openai(message, openai_api_key)
            merged = {
                **fallback,
                **{k: v for k, v in llm_result.items() if v not in (None, "")},
                "classifier_source": "openai",
            }
            if "selected_agent" not in merged or not merged["selected_agent"]:
                merged["selected_agent"] = self._agent_for_domain(merged.get("domain"))
            merged.setdefault("output_mode", fallback.get("output_mode", "summary"))
            merged.setdefault("needs_personal_join", fallback.get("needs_personal_join", False))
            merged.setdefault("focus", fallback.get("focus", "all"))
            if hard_override:
                merged.update(hard_override)
            merged = self._apply_deterministic_overrides(merged, message)
            return merged
        except Exception:
            logger.exception("Intent classifier fallback to rules")
            if hard_override:
                fallback.update(hard_override)
            fallback = self._apply_deterministic_overrides(fallback, message)
            fallback["classifier_source"] = "rules_on_error"
            return fallback

    def _classify_openai(self, message: str, openai_api_key: str) -> dict:
        # Lazy import to keep service running if dependency is missing.
        from openai import OpenAI

        client = OpenAI(api_key=openai_api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Classify user intent for an enterprise multi-agent system. "
                        "Return strict JSON with keys: intent, domain, selected_agent, needs_database, "
                        "output_mode, needs_personal_join, focus, confidence. "
                        "intent can also be knowledge_change_request when user asks to create/update business rules. "
                        "output_mode must be one of: summary, table, list. "
                        "focus must be one of: all, unjustified, missing_personal. "
                        "Domains: empleados, ausentismo, general, knowledge. "
                        "Agents: empleados_agent, ausentismo_agent, analista_agent."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )

        text = getattr(response, "output_text", "") or ""
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        raw = json_match.group(0) if json_match else text
        data = json.loads(raw)

        if "selected_agent" not in data or not data.get("selected_agent"):
            data["selected_agent"] = self._agent_for_domain(data.get("domain"))

        return data

    def _classify_rules(self, message: str) -> dict:
        msg = self._normalize_text(message)

        domain = "general"
        intent = "general_question"
        needs_database = False
        output_mode = "summary"
        needs_personal_join = False
        focus = "all"

        if any(token in msg for token in ("crear ticket", "abrir ticket", "generar ticket")):
            return {
                "intent": "create_ticket",
                "domain": "general",
                "selected_agent": "analista_agent",
                "needs_database": False,
                "output_mode": "summary",
                "needs_personal_join": False,
                "focus": "all",
                "confidence": 0.8,
            }

        if any(
            token in msg
            for token in (
                "crear regla",
                "nueva regla",
                "agregar regla",
                "actualizar regla",
                "modificar regla",
                "ajustar regla",
                "regla de negocio",
                "gobierno de reglas",
            )
        ):
            return {
                "intent": "knowledge_change_request",
                "domain": "general",
                "selected_agent": "analista_agent",
                "needs_database": True,
                "output_mode": "summary",
                "needs_personal_join": False,
                "focus": "all",
                "confidence": 0.8,
            }

        if any(token in msg for token in ("tabla", "lista", "detalle", "mostrar")):
            output_mode = "table" if "tabla" in msg else "list"
        if any(token in msg for token in ("personal", "empleado", "supervisor", "cargo", "area", "carpeta", "nombre", "apellido")):
            needs_personal_join = True
        if any(token in msg for token in ("injustific", "sin justificar")):
            focus = "unjustified"
        if self._contains_missing_personal_focus(message):
            focus = "missing_personal"
            output_mode = "table"

        if self._is_recurrence_request(msg):
            return {
                "intent": "ausentismo_recurrencia",
                "domain": "ausentismo",
                "selected_agent": "ausentismo_agent",
                "needs_database": True,
                "output_mode": "table" if output_mode == "summary" else output_mode,
                "needs_personal_join": True,
                "focus": "unjustified",
                "confidence": 0.85,
            }

        if any(token in msg for token in ("ausent", "asistencia", "injustific", "justific")):
            domain = "ausentismo"
            intent = "ausentismo_query"
            needs_database = True
            if output_mode == "summary" and any(token in msg for token in ("tabla", "lista", "detalle", "mostrar")):
                output_mode = "table"
        elif self._contains_employee_domain(message) or (
            self._is_employee_status_count_request(message)
        ) or self._looks_like_employee_lookup_request(message):
            domain = "empleados"
            intent = "empleados_query"
            needs_database = True
        elif any(token in msg for token in ("transporte", "ruta", "movilidad", "vehicul", "salieron")):
            domain = "general"
            intent = "general_question"
            needs_database = False
        elif any(token in msg for token in ("viatic", "gasto", "reembolso")):
            domain = "viatics"
            intent = "viatics_query"
            needs_database = True
        elif any(token in msg for token in ("nomina", "pago", "descuento", "devengo")):
            domain = "payroll"
            intent = "payroll_query"
            needs_database = True
        elif any(token in msg for token in ("auditor", "traza", "log", "control")):
            domain = "audit"
            intent = "audit_query"
            needs_database = True
        elif any(token in msg for token in ("operacion", "actividad", "ot")):
            domain = "operations"
            intent = "operations_query"
            needs_database = True

        return {
            "intent": intent,
            "domain": domain,
            "selected_agent": self._agent_for_domain(domain),
            "needs_database": needs_database,
            "output_mode": output_mode,
            "needs_personal_join": needs_personal_join,
            "focus": focus,
            "confidence": 0.6,
        }

    def _hard_rule_overrides(self, message: str) -> dict | None:
        msg = self._normalize_text(message)
        if any(
            token in msg
            for token in (
                "crear regla",
                "nueva regla",
                "agregar regla",
                "actualizar regla",
                "modificar regla",
                "ajustar regla",
            )
        ):
            return {
                "intent": "knowledge_change_request",
                "domain": "general",
                "selected_agent": "analista_agent",
                "needs_database": True,
                "output_mode": "summary",
                "needs_personal_join": False,
                "focus": "all",
            }

        if self._is_recurrence_request(msg):
            return {
                "intent": "ausentismo_recurrencia",
                "domain": "ausentismo",
                "selected_agent": "ausentismo_agent",
                "needs_database": True,
                "output_mode": "table",
                "needs_personal_join": True,
                "focus": "unjustified",
            }
        return None

    @staticmethod
    def _agent_for_domain(domain: str | None) -> str:
        mapping = {
            "rrhh": "empleados_agent",
            "empleados": "empleados_agent",
            "attendance": "ausentismo_agent",
            "ausentismo": "ausentismo_agent",
            "transport": "analista_agent",
            "transporte": "analista_agent",
            "operations": "operations_agent",
            "viatics": "viatics_agent",
            "payroll": "payroll_agent",
            "audit": "audit_agent",
            "general": "analista_agent",
        }
        return mapping.get((domain or "").strip().lower(), "analista_agent")

