from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ia_dev.application.contracts.chat_contracts import ensure_chat_response_contract
from apps.ia_dev.application.orchestration.chat_application_service import ChatApplicationService
from apps.ia_dev.services.attendance_period_resolver_service import AttendancePeriodResolverService
from apps.ia_dev.services.async_job_service import AsyncJobService
from apps.ia_dev.services.dictionary_tool_service import DictionaryToolService
from apps.ia_dev.services.knowledge_governance_service import KnowledgeGovernanceService
from apps.ia_dev.services.observability_service import ObservabilityService
from apps.ia_dev.services.runtime_fallback_service import RuntimeFallbackService
from apps.ia_dev.services.session_memory_runtime_service import SessionMemoryRuntimeService
from apps.ia_dev.services.ticket_service import TicketService
from apps.security.permissions.api_permissions import IsAuthenticatedUser


chat_application_service = None
runtime_fallback_service = None
session_memory_runtime_service = SessionMemoryRuntimeService()
attendance_period_resolver_service = AttendancePeriodResolverService()
dictionary_tool_service = DictionaryToolService()
knowledge_governance_service = KnowledgeGovernanceService()
async_job_service = AsyncJobService()
observability_service = ObservabilityService()


def _get_chat_application_service() -> ChatApplicationService:
    global chat_application_service
    if chat_application_service is None:
        chat_application_service = ChatApplicationService()
    return chat_application_service


def _get_runtime_fallback_service() -> RuntimeFallbackService:
    global runtime_fallback_service
    if runtime_fallback_service is None:
        runtime_fallback_service = RuntimeFallbackService()
    return runtime_fallback_service


def _resolve_user_key(request) -> str | None:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    user_id = getattr(user, "id", None)
    username = getattr(user, "username", None)
    if user_id is not None:
        return f"user:{user_id}"
    if username:
        return f"user:{username}"
    return None


def _attach_http_runtime_metadata(
    *,
    response: dict,
    legacy_runtime_fallback_used: bool,
    legacy_runtime_fallback_reason: str | None = None,
) -> dict:
    payload = ensure_chat_response_contract(response)
    data_sources = dict(payload.get("data_sources") or {})
    runtime = dict(data_sources.get("runtime") or {})
    runtime["entrypoint"] = "chat_view_direct"
    runtime["runtime_owner"] = "ChatApplicationService"
    runtime["legacy_adapter_removed"] = True
    runtime["legacy_runtime_fallback_used"] = bool(legacy_runtime_fallback_used)
    if legacy_runtime_fallback_reason:
        runtime["legacy_runtime_fallback_reason"] = str(legacy_runtime_fallback_reason)
    else:
        runtime.pop("legacy_runtime_fallback_reason", None)
    data_sources["runtime"] = runtime
    payload["data_sources"] = data_sources
    return payload


def _record_chat_entrypoint_observability(
    *,
    session_id: str | None,
    response: dict,
    legacy_runtime_fallback_used: bool,
    legacy_runtime_fallback_reason: str | None = None,
) -> None:
    runtime = dict(((response.get("data_sources") or {}).get("runtime") or {}))
    observability_service.record_event(
        event_type="runtime_http_entrypoint_resolved",
        source="IADevChatView",
        meta={
            "entrypoint": "chat_view_direct",
            "runtime_owner": "ChatApplicationService",
            "legacy_adapter_removed": True,
            "legacy_runtime_fallback_used": bool(legacy_runtime_fallback_used),
            "legacy_runtime_fallback_reason": str(legacy_runtime_fallback_reason or ""),
            "session_id": str(response.get("session_id") or session_id or ""),
            "response_flow": str(
                runtime.get("flow")
                or ((response.get("orchestrator") or {}).get("runtime_flow") or "")
            ),
            "final_intent": str(
                runtime.get("final_intent")
                or ((response.get("orchestrator") or {}).get("final_intent") or "")
            ),
            "final_domain": str(
                runtime.get("final_domain")
                or ((response.get("orchestrator") or {}).get("final_domain") or "")
            ),
        },
    )


class IADevChatView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        message = str(request.data.get("message", "")).strip()
        session_id = request.data.get("session_id")
        reset_memory = bool(request.data.get("reset_memory", False))

        if not message:
            return Response(
                {"detail": "message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_user_key = _resolve_user_key(request)
        legacy_runtime_fallback_used = False
        legacy_runtime_fallback_reason = None
        try:
            result = _get_chat_application_service().run(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                legacy_runner=lambda **kwargs: _get_runtime_fallback_service().run(**kwargs),
                observability=observability_service,
                actor_user_key=actor_user_key,
            )
            runtime_meta = dict(((result.get("data_sources") or {}).get("runtime") or {}))
            legacy_runtime_fallback_used = bool(
                runtime_meta.get("legacy_runtime_fallback_used")
            )
            if legacy_runtime_fallback_used:
                legacy_runtime_fallback_reason = str(
                    runtime_meta.get("legacy_runtime_fallback_reason") or ""
                ) or None
        except Exception as exc:
            legacy_runtime_fallback_used = True
            legacy_runtime_fallback_reason = (
                f"chat_application_service_exception:{exc.__class__.__name__}"
            )
            result = _get_runtime_fallback_service().run(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                actor_user_key=actor_user_key,
                fallback_reason=legacy_runtime_fallback_reason,
            )

        result = _attach_http_runtime_metadata(
            response=result,
            legacy_runtime_fallback_used=legacy_runtime_fallback_used,
            legacy_runtime_fallback_reason=legacy_runtime_fallback_reason,
        )
        _record_chat_entrypoint_observability(
            session_id=session_id,
            response=result,
            legacy_runtime_fallback_used=legacy_runtime_fallback_used,
            legacy_runtime_fallback_reason=legacy_runtime_fallback_reason,
        )
        return Response(result, status=status.HTTP_200_OK)


class IADevMemoryResetView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        session_id = str(request.data.get("session_id", "")).strip()
        if not session_id:
            return Response(
                {"detail": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = session_memory_runtime_service.reset_memory(session_id)
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class IADevAttendancePeriodResolveView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        return self._resolve(
            message=str(request.query_params.get("message", "")).strip(),
            session_id=str(request.query_params.get("session_id", "")).strip() or None,
        )

    def post(self, request):
        return self._resolve(
            message=str(request.data.get("message", "")).strip(),
            session_id=str(request.data.get("session_id", "")).strip() or None,
        )

    @staticmethod
    def _resolve(*, message: str, session_id: str | None):
        if not message:
            return Response(
                {"detail": "message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = attendance_period_resolver_service.resolve_attendance_period(
            message=message,
            session_id=session_id,
        )
        if payload.get("error"):
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "ok", "period_resolution": payload}, status=status.HTTP_200_OK)


class IADevHealthView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        try:
            dictionary_status = dictionary_tool_service.check_connection()
            try:
                dictionary_status["snapshot"] = dictionary_tool_service.get_dictionary_snapshot()
            except Exception:
                pass
            payload = {
                "status": "ok",
                "data_sources": {
                    "ai_dictionary": dictionary_status,
                },
            }
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as exc:
            payload = {
                "status": "degraded",
                "data_sources": {
                    "ai_dictionary": {
                        "ok": False,
                        "error": str(exc),
                    }
                },
            }
            return Response(payload, status=status.HTTP_200_OK)


class IADevTicketView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        title = str(request.data.get("title", "")).strip()
        description = str(request.data.get("description", "")).strip()
        category = str(request.data.get("category", "general")).strip().lower()
        session_id = str(request.data.get("session_id", "")).strip() or None

        if not title:
            return Response(
                {"detail": "title is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not description:
            return Response(
                {"detail": "description is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket = TicketService.create_ticket(
            title=title,
            description=description,
            category=category,
            session_id=session_id,
        )
        return Response(
            {
                "status": "created",
                "ticket": ticket,
            },
            status=status.HTTP_201_CREATED,
        )


class IADevKnowledgeProposalView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        status_filter = str(request.query_params.get("status", "")).strip() or None
        limit = int(request.query_params.get("limit", 30))
        proposals = knowledge_governance_service.list_proposals(
            status=status_filter,
            limit=limit,
        )
        return Response(
            {
                "status": "ok",
                "count": len(proposals),
                "proposals": proposals,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        message = str(request.data.get("message", "")).strip()
        session_id = str(request.data.get("session_id", "")).strip() or None
        requested_by = str(request.data.get("requested_by", "analista_agent")).strip()
        raw_target_rule_id = request.data.get("target_rule_id")
        target_rule_id = None
        if raw_target_rule_id not in (None, "", "null"):
            try:
                target_rule_id = int(raw_target_rule_id)
            except (TypeError, ValueError):
                return Response(
                    {"ok": False, "error": "target_rule_id debe ser numérico"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            priority = int(request.data.get("priority", 50))
        except (TypeError, ValueError):
            return Response(
                {"ok": False, "error": "priority debe ser numérico"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if message:
            result = knowledge_governance_service.create_proposal_from_message(
                message=message,
                session_id=session_id,
                requested_by=requested_by,
            )
        else:
            result = knowledge_governance_service.create_proposal(
                proposal_type=str(request.data.get("proposal_type", "nueva_regla")).strip(),
                name=str(request.data.get("name", "")).strip(),
                description=str(request.data.get("description", "")).strip(),
                domain_code=str(request.data.get("domain_code", "GENERAL")).strip(),
                condition_sql=str(request.data.get("condition_sql", "")).strip(),
                result_text=str(request.data.get("result_text", "")).strip(),
                tables_related=str(request.data.get("tables_related", "")).strip(),
                priority=priority,
                target_rule_id=target_rule_id,
                session_id=session_id,
                requested_by=requested_by,
            )

        if not result.get("ok"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class IADevKnowledgeApproveView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        proposal_id = str(request.data.get("proposal_id", "")).strip()
        auth_key = str(request.data.get("auth_key", "")).strip() or None
        idempotency_key = (
            str(request.data.get("idempotency_key", "")).strip()
            or str(request.headers.get("X-Idempotency-Key", "")).strip()
            or None
        )
        async_mode = async_job_service.mode
        if not proposal_id:
            return Response(
                {"ok": False, "error": "proposal_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if async_mode != "sync":
            if knowledge_governance_service.mode == "ceo":
                if not knowledge_governance_service.validate_auth_key(auth_key):
                    return Response(
                        {
                            "ok": False,
                            "error": "Clave de autorizacion invalida",
                            "requires_auth": True,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
                payload = {
                    "proposal_id": proposal_id,
                    "bypass_auth": True,
                    "idempotency_key": idempotency_key,
                }
            else:
                payload = {
                    "proposal_id": proposal_id,
                    "auth_key": auth_key,
                    "idempotency_key": idempotency_key,
                }

            job = async_job_service.enqueue(
                job_type="knowledge_approve",
                payload=payload,
                idempotency_key=idempotency_key,
            )
            return Response(
                {
                    "ok": True,
                    "status": "accepted",
                    "async_mode": async_mode,
                    "job": job,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        result = knowledge_governance_service.apply_proposal(
            proposal_id=proposal_id,
            auth_key=auth_key,
            idempotency_key=idempotency_key,
        )
        if result.get("ok"):
            return Response(result, status=status.HTTP_200_OK)

        if result.get("requires_auth"):
            return Response(result, status=status.HTTP_403_FORBIDDEN)

        return Response(result, status=status.HTTP_400_BAD_REQUEST)


class IADevKnowledgeRejectView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        proposal_id = str(request.data.get("proposal_id", "")).strip()
        reason = str(request.data.get("reason", "")).strip()
        result = knowledge_governance_service.reject_proposal(
            proposal_id=proposal_id,
            reason=reason,
        )
        if not result.get("ok"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class IADevAsyncJobView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        job_id = str(request.query_params.get("job_id", "")).strip()
        if not job_id:
            return Response({"detail": "job_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        job = async_job_service.store.get_async_job(job_id)
        if not job:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"status": "ok", "job": job}, status=status.HTTP_200_OK)


class IADevObservabilitySummaryView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        try:
            window_seconds = int(request.query_params.get("window_seconds", 3600))
        except (TypeError, ValueError):
            return Response(
                {"detail": "window_seconds debe ser numerico"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            limit = int(request.query_params.get("limit", 2000))
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit debe ser numerico"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        domain_code = str(request.query_params.get("domain_code", "")).strip() or None
        generator = str(request.query_params.get("generator", "")).strip().lower() or None
        fallback_reason = str(request.query_params.get("fallback_reason", "")).strip().lower() or None
        if generator and generator not in {"openai", "heuristic"}:
            return Response(
                {"detail": "generator debe ser openai o heuristic"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = observability_service.summary_filtered(
            window_seconds=window_seconds,
            limit=limit,
            domain_code=domain_code,
            generator=generator,
            fallback_reason=fallback_reason,
        )
        return Response({"status": "ok", "observability": payload}, status=status.HTTP_200_OK)
