from datetime import datetime, timezone
from time import perf_counter

from django.http import FileResponse
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
from apps.ia_dev.services.runtime_artifact_service import RuntimeArtifactService
from apps.ia_dev.services.runtime_fallback_service import RuntimeFallbackService
from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService
from apps.ia_dev.services.session_memory_runtime_service import SessionMemoryRuntimeService
from apps.ia_dev.services.ticket_service import TicketService
from apps.ia_dev.application.runtime.semantic_gap_review_service import SemanticGapReviewService
from apps.security.permissions.api_permissions import IsAuthenticatedUser


chat_application_service = None
runtime_fallback_service = None
session_memory_runtime_service = SessionMemoryRuntimeService()
attendance_period_resolver_service = AttendancePeriodResolverService()
dictionary_tool_service = DictionaryToolService()
knowledge_governance_service = KnowledgeGovernanceService()
async_job_service = AsyncJobService()
observability_service = ObservabilityService()
runtime_governance_service = RuntimeGovernanceService()
semantic_gap_review_service = SemanticGapReviewService()
runtime_artifact_service = RuntimeArtifactService()


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


def _request_debug_mode(request) -> bool:
    header = str(request.headers.get("X-IA-Dev-Debug", "") or "").strip().lower()
    query = str(request.query_params.get("debug", "") or "").strip().lower()
    body = str(request.data.get("debug", "") or "").strip().lower() if hasattr(request, "data") else ""
    return header in {"1", "true", "yes", "on"} or query in {"1", "true", "yes", "on"} or body in {
        "1",
        "true",
        "yes",
        "on",
    }


def _legacy_is_blocked_for_message(*, message: str) -> tuple[bool, dict]:
    service = _get_chat_application_service()
    classification = service._bootstrap_classification(message=message, session_context={})
    contract_payload = service._resolve_agent_contract(
        agent_id=str(classification.get("selected_agent") or "") or None,
        domain_code=str(classification.get("domain") or "") or None,
    )
    blocked = bool(contract_payload) and not service._legacy_allowed_for_contract(
        contract_payload=contract_payload
    )
    return blocked, classification


def _attach_http_runtime_metadata(
    *,
    response: dict,
    legacy_runtime_fallback_used: bool,
    legacy_runtime_fallback_reason: str | None = None,
) -> dict:
    payload = ensure_chat_response_contract(response)
    task = dict(payload.get("task") or {})
    current_run = dict(task.get("current_run") or {})
    current_run["reply"] = str(payload.get("reply") or "")
    task["current_run"] = current_run
    payload["task"] = task
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
    envelope = dict(payload.get("response_envelope") or {})
    envelope["progress_source"] = str(envelope.get("progress_source") or "backend")
    envelope["legacy_used"] = bool(runtime.get("legacy_used") or legacy_runtime_fallback_used)
    payload["response_envelope"] = envelope
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
        attachments = request.data.get("attachments")
        normalized_attachments = [
            dict(item)
            for item in list(attachments or [])
            if isinstance(item, dict)
        ]

        if not message:
            return Response(
                {"detail": "message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_user_key = _resolve_user_key(request)
        response_debug_mode = _request_debug_mode(request)
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
                response_debug_mode=response_debug_mode,
                attachments=normalized_attachments,
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
            legacy_runtime_fallback_reason = f"chat_application_service_exception:{exc.__class__.__name__}"
            blocked, classification = _legacy_is_blocked_for_message(message=message)
            if blocked:
                result = _get_chat_application_service().build_controlled_runtime_limitation_response(
                    message=message,
                    session_id=session_id,
                    classification=classification,
                    block_reason=legacy_runtime_fallback_reason,
                    response_debug_mode=response_debug_mode,
                )
                legacy_runtime_fallback_used = False
            else:
                legacy_runtime_fallback_used = True
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


class IADevRuntimeOperationsSummaryView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 100))
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit debe ser numerico"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        status_filter = str(request.query_params.get("status", "")).strip().lower() or None
        payload = runtime_governance_service.build_runtime_operations_summary(
            limit=limit,
            status=status_filter,
        )
        return Response({"status": "ok", "operations": payload}, status=status.HTTP_200_OK)


class IADevRuntimeTaskExplorerView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        run_id = str(request.query_params.get("run_id", "")).strip() or None
        resume_token = str(request.query_params.get("resume_token", "")).strip() or None
        background_run_id = str(request.query_params.get("background_run_id", "")).strip() or None
        if not any((run_id, resume_token, background_run_id)):
            return Response(
                {"detail": "run_id, resume_token o background_run_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = runtime_governance_service.build_task_trace_explorer(
            run_id=run_id,
            resume_token=resume_token,
            background_run_id=background_run_id,
        )
        if not payload:
            return Response(
                {"detail": "task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "ok", "task_explorer": payload}, status=status.HTTP_200_OK)


class IADevChatTaskStatusView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        started_at = perf_counter()
        run_id = str(request.query_params.get("run_id", "")).strip() or None
        resume_token = str(request.query_params.get("resume_token", "")).strip() or None
        background_run_id = str(request.query_params.get("background_run_id", "")).strip() or None
        if not any((run_id, resume_token, background_run_id)):
            return Response(
                {"detail": "run_id, resume_token o background_run_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = _get_chat_application_service().build_task_status_response(
                run_id=run_id,
                resume_token=resume_token,
                background_run_id=background_run_id,
            )
        except ValueError as exc:
            if str(exc) == "background_workflow_not_found":
                return Response({"detail": "task not found"}, status=status.HTTP_404_NOT_FOUND)
            raise
        if not payload:
            return Response({"detail": "task not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = ensure_chat_response_contract(payload)
        response_time_ms = round((perf_counter() - started_at) * 1000.0, 2)
        current_run = dict(((payload.get("task") or {}).get("current_run") or {}))
        evidence = dict(current_run.get("evidence") or {})
        progress = dict(evidence.get("background_progress") or {})
        last_progress_update_at = str(progress.get("last_progress_update_at") or "").strip()
        snapshot_age_ms = 0
        if last_progress_update_at:
            try:
                last_update_dt = datetime.fromisoformat(last_progress_update_at.replace("Z", "+00:00"))
                if last_update_dt.tzinfo is None:
                    last_update_dt = last_update_dt.replace(tzinfo=timezone.utc)
                snapshot_age_ms = max(
                    0,
                    int((datetime.now(timezone.utc) - last_update_dt.astimezone(timezone.utc)).total_seconds() * 1000),
                )
            except ValueError:
                snapshot_age_ms = 0
        progress["response_time_ms"] = response_time_ms
        progress["snapshot_age_ms"] = snapshot_age_ms
        evidence["background_progress"] = progress
        current_run["evidence"] = evidence
        payload.setdefault("task", {})["current_run"] = current_run
        data = dict(payload.get("data") or {})
        meta = dict(data.get("meta") or {})
        background_job = dict(meta.get("background_job") or {})
        if background_job:
            background_job["response_time_ms"] = response_time_ms
            background_job["snapshot_age_ms"] = snapshot_age_ms
            meta["background_job"] = background_job
        data["meta"] = meta
        payload["data"] = data
        return Response(payload, status=status.HTTP_200_OK)


class IADevProviderSerialArtifactDownloadView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        artifact_id = str(request.query_params.get("artifact_id", "")).strip()
        background_run_id = str(request.query_params.get("background_run_id", "")).strip()
        if not artifact_id:
            return Response({"detail": "artifact_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)
        if background_run_id:
            explorer = runtime_governance_service.build_task_trace_explorer(
                background_run_id=background_run_id,
                run_id=None,
                resume_token=None,
            )
            if not explorer:
                return Response({"detail": "task not found"}, status=status.HTTP_404_NOT_FOUND)
            response_snapshot = dict(
                ((runtime_governance_service._find_task_workflow(
                    run_id=None,
                    resume_token=None,
                    background_run_id=background_run_id,
                ) or {}).get("state") or {}).get("response_snapshot")
                or {}
            )
            workflow_state = dict(
                ((runtime_governance_service._find_task_workflow(
                    run_id=None,
                    resume_token=None,
                    background_run_id=background_run_id,
                ) or {}).get("state") or {})
            )
            table = dict((dict(response_snapshot.get("data") or {}).get("table") or {}))
            export_artifact = dict(table.get("export_artifact") or {})
            background = dict(workflow_state.get("background") or {})
            partial_evidence = dict(background.get("partial_evidence") or {})
            final_evidence = dict(background.get("final_evidence") or {})
            allowed_artifact_ids = {
                str(export_artifact.get("artifact_id") or "").strip(),
                str(partial_evidence.get("artifact_id") or "").strip(),
                str(final_evidence.get("artifact_id") or "").strip(),
            }
            allowed_artifact_ids.discard("")
            if artifact_id not in allowed_artifact_ids:
                return Response({"detail": "artifact not allowed for task"}, status=status.HTTP_403_FORBIDDEN)
        try:
            artifact_path = runtime_artifact_service.resolve_artifact_path(artifact_id=artifact_id)
        except ValueError as exc:
            detail = str(exc)
            if detail == "artifact_not_found":
                return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)
            if detail in {"artifact_invalid", "artifact_expired"}:
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
            raise
        return FileResponse(
            artifact_path.open("rb"),
            as_attachment=True,
            filename=artifact_path.name,
            content_type="text/csv",
        )


class IADevRuntimeGovernanceHealthView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        domain = str(request.query_params.get("domain", "ausentismo")).strip() or "ausentismo"
        try:
            days = int(request.query_params.get("days", 1))
        except (TypeError, ValueError):
            return Response(
                {"detail": "days debe ser numerico"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        since_fix = str(request.query_params.get("since_fix", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        created_after = str(request.query_params.get("created_after", "")).strip() or None
        payload = {
            "monitor_summary": runtime_governance_service.build_monitor_summary(
                domain=domain,
                days=days,
            ),
            "pilot_health": runtime_governance_service.build_pilot_health(
                domain=domain,
                days=days,
                since_fix=since_fix,
                created_after=created_after,
            ),
        }
        return Response({"status": "ok", "governance": payload}, status=status.HTTP_200_OK)


class IADevSemanticGapOperationsView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 100))
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit debe ser numerico"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        include_summary = str(request.query_params.get("summary", "")).strip().lower() in {"1", "true", "yes", "on"}
        payload = {
            "brechas_pendientes": semantic_gap_review_service.listar_brechas_pendientes(limit=limit),
            "brechas_por_categoria": semantic_gap_review_service.agrupar_por_categoria(limit=limit),
            "brechas_frecuentes": semantic_gap_review_service.ver_brechas_frecuentes(limit=limit),
        }
        if include_summary:
            payload["resumen"] = semantic_gap_review_service.build_operations_snapshot(limit=limit)
        return Response({"status": "ok", "gestion_brechas_semanticas": payload}, status=status.HTTP_200_OK)

    def post(self, request):
        action = str(request.data.get("action", "")).strip().lower()
        try:
            brecha_id = int(request.data.get("brecha_id", 0))
        except (TypeError, ValueError):
            return Response({"detail": "brecha_id debe ser numerico"}, status=status.HTTP_400_BAD_REQUEST)
        actor = _resolve_user_key(request) or str(request.data.get("actor", "")).strip() or "user:unknown"

        try:
            if action == "marcar_en_revision":
                payload = semantic_gap_review_service.marcar_en_revision(
                    brecha_id=brecha_id,
                    revisado_por=actor,
                    asignado_a=str(request.data.get("asignado_a", "")).strip(),
                    comentario=str(request.data.get("comentario", "")).strip(),
                )
            elif action == "marcar_descartada":
                payload = semantic_gap_review_service.marcar_descartada(
                    brecha_id=brecha_id,
                    revisado_por=actor,
                    decision=str(request.data.get("decision", "")).strip() or "descartar_brecha",
                    comentario=str(request.data.get("comentario", "")).strip(),
                )
            elif action == "marcar_resuelta":
                payload = semantic_gap_review_service.marcar_resuelta(
                    brecha_id=brecha_id,
                    revisado_por=actor,
                    decision=str(request.data.get("decision", "")).strip() or "resolver_brecha",
                    comentario=str(request.data.get("comentario", "")).strip(),
                    prueba_validacion=str(request.data.get("prueba_validacion", "")).strip(),
                )
            elif action == "crear_propuesta":
                payload = semantic_gap_review_service.crear_propuesta(
                    brecha_id=brecha_id,
                    revisado_por=actor,
                    tipo_propuesta=str(request.data.get("tipo_propuesta", "")).strip(),
                    descripcion=str(request.data.get("descripcion", "")).strip(),
                    destino_sugerido=str(request.data.get("destino_sugerido", "")).strip(),
                    valor_sugerido=request.data.get("valor_sugerido"),
                    evidencia=dict(request.data.get("evidencia") or {}),
                    riesgo=str(request.data.get("riesgo", "medio")).strip(),
                )
            elif action == "aprobar_propuesta":
                payload = semantic_gap_review_service.aprobar_propuesta(
                    brecha_id=brecha_id,
                    aprobado_por=actor,
                    rol_aprobador=str(request.data.get("rol_aprobador", "governance")).strip(),
                    evidencia_post_aprobacion=dict(request.data.get("evidencia_post_aprobacion") or {}),
                )
            elif action == "aplicar_propuesta":
                payload = semantic_gap_review_service.aplicar_propuesta_gobernada(
                    brecha_id=brecha_id,
                    aplicado_por=actor,
                    aplicado_en=str(request.data.get("aplicado_en", "")).strip(),
                    referencia_metadata_creada=str(request.data.get("referencia_metadata_creada", "")).strip(),
                    referencia_capacidad_creada=str(request.data.get("referencia_capacidad_creada", "")).strip(),
                    referencia_agente_creado=str(request.data.get("referencia_agente_creado", "")).strip(),
                    prueba_validacion=str(request.data.get("prueba_validacion", "")).strip(),
                    validado_por_eval=bool(request.data.get("validado_por_eval", False)),
                )
            elif action == "vincular_eval":
                payload = semantic_gap_review_service.vincular_eval(
                    brecha_id=brecha_id,
                    eval_id=str(request.data.get("eval_id", "")).strip(),
                    vinculado_por=actor,
                    caso_real_reproducible=str(request.data.get("caso_real_reproducible", "")).strip(),
                    eval_actualizado=bool(request.data.get("eval_actualizado", False)),
                )
            else:
                return Response({"detail": "action no soportada"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": "ok", "gestion_brechas_semanticas": payload}, status=status.HTTP_200_OK)
