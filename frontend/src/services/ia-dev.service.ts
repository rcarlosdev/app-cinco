import api from "@/lib/api";

const IA_DEV_CHAT_TIMEOUT_MS = 120000;

export type IADevChatRequest = {
  message: string;
  session_id?: string;
  reset_memory?: boolean;
  attachments?: IADevChatAttachment[];
};

export type IADevChatAttachment = {
  id: string;
  name: string;
  mime_type: string;
  size: number;
  kind: "image" | "document" | string;
  last_modified?: number;
  content_base64: string;
};

export type IADevChartPoint = {
  x: string;
  y: number;
};

export type IADevChartSeriesMeta = {
  name?: string;
  value_key?: string;
};

export type IADevChartPayload = {
  engine?: string;
  chart_library?: string;
  type?: "bar" | "line" | "area" | string;
  title?: string;
  x_key?: string;
  y_key?: string;
  labels?: string[];
  series?: number[] | IADevChartSeriesMeta[];
  points?: IADevChartPoint[];
  data?: Array<Record<string, unknown>>;
  meta?: Record<string, unknown>;
};

export type IADevDashboardEvidence = {
  source_block?: string;
  columns_used?: string[];
  formula?: string;
  row_count_used?: number;
  confidence?: number;
  limitation?: string;
};

export type IADevDashboardCompositionItem = {
  id?: string;
  title?: string;
  text?: string;
  value?: number | string;
  type?: string;
  kind?: string;
  severity?: string;
  priority?: string;
  rows?: Array<Record<string, unknown>>;
  chart?: IADevChartPayload;
  table?: IADevTablePayload;
  evidence?: IADevDashboardEvidence;
};

export type IADevDashboardComposition = {
  executive_summary?: Record<string, unknown>;
  semantic_basis?: Record<string, unknown>;
  primary_kpis?: IADevDashboardCompositionItem[];
  ranked_breakdowns?: IADevDashboardCompositionItem[];
  recommended_charts?: IADevDashboardCompositionItem[];
  priority_tables?: IADevDashboardCompositionItem[];
  business_insights?: IADevDashboardCompositionItem[];
  operational_alerts?: IADevDashboardCompositionItem[];
  evidence_contract?: Record<string, unknown>;
};

export type IADevTablePayload = {
  columns?: string[];
  rows?: Array<Record<string, unknown>>;
  export_rows?: Array<Record<string, unknown>>;
  rowcount?: number;
  total_records?: number;
  returned_records?: number;
  export_records?: number;
  export_truncated?: boolean;
  export_limit?: number;
  truncated?: boolean;
  limit?: number;
  export_artifact?: IADevExportArtifact;
};

export type IADevExportArtifact = {
  available?: boolean;
  format?: string;
  artifact_id?: string;
  filename?: string;
  record_count?: number;
  endpoint_hint?: string;
  expires_in_seconds?: number;
};

export type IADevAction = {
  id: string;
  type: "create_ticket" | "render_chart" | string;
  label: string;
  payload?: Record<string, unknown> & {
    category?: string;
    title?: string;
    description?: string;
    chart?: IADevChartPayload;
    capability_id?: string;
  };
};

export type IADevMemoryCandidate = {
  scope: string;
  candidate_key: string;
  candidate_value?: unknown;
  reason?: string;
  sensitivity?: string;
  decision?: string;
  decision_reason?: string;
  proposal_id?: string | null;
  result_ok?: boolean;
  idempotent?: boolean;
  auto_applied?: boolean;
  error?: string;
};

export type IADevWorkingUpdate = {
  stage: string;
  stage_label?: string;
  status: string;
  summary: string;
  display_text?: string;
  next_step?: string;
  confidence?: number | null;
  at: string;
};

export type IADevReasoningHypothesis = {
  key: string;
  text: string;
  status?: string;
  confidence?: number | null;
  evidence_refs?: string[];
};

export type IADevReasoningDiagnostic = {
  signature: string;
  family?: string;
  severity?: string;
  stage?: string;
  summary: string;
  recommended_action?: string;
  confidence?: number | null;
  domain_code?: string;
  capability_id?: string;
  matched_memory_patterns?: Array<Record<string, unknown>>;
};

export type IADevSemanticTimelineStep = {
  step: string;
  state: "completed" | "current" | "pending" | string;
  detail?: string;
};

export type IADevSemanticExplanation = {
  user_question?: string;
  understood_as?: string;
  domain?: string;
  intent?: string;
  entity?: Record<string, unknown>;
  normalized_filters?: Record<string, unknown>;
  selected_capability?: string;
  selected_tool?: string;
  planner_route_hint?: string;
  validation_status?: Record<string, unknown>;
  evidence_summary?: Record<string, unknown>;
  limitations?: string[];
  clarification_needed?: Record<string, unknown>;
  metadata_used?: Record<string, unknown>;
  fallback_used?: Record<string, unknown>;
  agents_involved?: string[];
  route_participants?: Record<string, unknown>;
  approvals_status?: Record<string, unknown>;
  background_status?: Record<string, unknown>;
  final_state?: Record<string, unknown>;
  timeline?: IADevSemanticTimelineStep[];
};

export type IADevChatResponse = {
  session_id: string;
  reply: string;
  task?: {
    task_id: string;
    current_run: {
      run_id: string;
      status: string;
      domain: string;
      intent: string;
      plan: Record<string, unknown>;
      semantic_explanation?: IADevSemanticExplanation;
      background?: Record<string, unknown>;
      required_tools: string[];
      validation: Record<string, unknown>;
      evidence: Record<string, unknown>;
      final_state: Record<string, unknown>;
      reply: string;
    };
  };
  response_envelope?: {
    mode?: "user" | "debug" | string;
    progress_source?: "backend" | "synthetic" | string;
    route?: Record<string, unknown>;
    fallback_used?: {
      used?: boolean;
      reason?: string;
      flow?: string;
    };
    legacy_used?: boolean;
    contract_policy_applied?: Record<string, unknown>;
    needs_clarification?: boolean;
    block_reason?: string;
  };
  orchestrator: {
    intent?: string;
    domain?: string;
    selected_agent?: string;
    classifier_source?: string;
    needs_database?: boolean;
    output_mode?: string;
    used_tools?: string[];
  };
  data: {
    kpis?: Record<string, number>;
    series?: unknown[];
    labels?: unknown[];
    insights?: string[];
    table?: IADevTablePayload;
    extra_tables?: IADevTablePayload[];
    chart?: IADevChartPayload;
    charts?: IADevChartPayload[];
    meta?: Record<string, unknown>;
    cause_generation_meta?: Record<string, unknown>;
    business_response?: {
      dashboard_composition?: IADevDashboardComposition;
      [key: string]: unknown;
    };
  };
  data_sources?: {
    runtime?: Record<string, unknown>;
    ai_dictionary?: {
      ok: boolean;
      table?: string | null;
      rows?: number;
      error?: string;
      snapshot?: {
        dictionary_table?: string;
        schema?: string;
        counts?: Record<string, number>;
      };
      context?: {
        domain?: {
          id?: number;
          code?: string;
          name?: string;
          description?: string;
          matched?: boolean;
        };
        tables?: Array<Record<string, unknown>>;
        fields?: Array<Record<string, unknown>>;
        rules?: Array<Record<string, unknown>>;
        relations?: Array<Record<string, unknown>>;
        synonyms?: Array<Record<string, unknown>>;
      };
    };
  };
  actions?: IADevAction[];
  memory_candidates?: IADevMemoryCandidate[];
  pending_proposals?: IADevMemoryProposal[];
  working_updates?: IADevWorkingUpdate[];
  reasoning?: {
    enabled: boolean;
    version?: string;
    status?: string;
    working_goal?: string;
    current_next_step?: string;
    hypotheses?: IADevReasoningHypothesis[];
    diagnostics?: IADevReasoningDiagnostic[];
    memory_summary?: Record<string, unknown>;
    duration_ms?: number;
  };
  trace: Array<{
    phase: string;
    status: string;
    at: string;
    detail: unknown;
    active_nodes?: string[];
  }>;
  memory: {
    used_messages: number;
    capacity_messages: number;
    usage_ratio: number;
    trim_events: number;
    saturated: boolean;
    backend?: string;
    redis_enabled?: boolean;
  };
  observability?: {
    enabled: boolean;
    duration_ms: number;
    tool_latencies_ms: Record<string, number>;
    tokens_in: number;
    tokens_out: number;
    estimated_cost_usd: number;
  };
  active_nodes?: string[];
};

export type IADevTaskStatusRequest = {
  run_id?: string;
  background_run_id?: string;
  resume_token?: string;
};

export const sendIADevMessage = async (
  payload: IADevChatRequest,
): Promise<IADevChatResponse> => {
  const response = await api.post<IADevChatResponse>("/ia-dev/chat/", payload, {
    timeout: IA_DEV_CHAT_TIMEOUT_MS,
  });
  return response.data;
};

export const getIADevTaskStatus = async (
  params: IADevTaskStatusRequest,
  options?: { signal?: AbortSignal },
): Promise<IADevChatResponse> => {
  const response = await api.get<IADevChatResponse>("/ia-dev/chat/task-status/", {
    params,
    signal: options?.signal,
    timeout: 60000,
  });
  return response.data;
};

export const downloadIADevProviderSerialArtifact = async (params: {
  artifactId: string;
  backgroundRunId?: string;
}): Promise<Blob> => {
  const response = await api.get(
    "/ia-dev/runtime/artifacts/provider-serial-validation/",
    {
      params: {
        artifact_id: params.artifactId,
        ...(params.backgroundRunId
          ? { background_run_id: params.backgroundRunId }
          : {}),
      },
      responseType: "blob",
    },
  );
  return response.data as Blob;
};

export const resetIADevMemory = async (sessionId: string) => {
  const response = await api.post("/ia-dev/memory/reset/", {
    session_id: sessionId,
  });
  return response.data;
};

export type IADevHealthResponse = {
  status: "ok" | "degraded";
  data_sources: {
    ai_dictionary: {
      ok: boolean;
      table?: string | null;
      rows?: number;
      error?: string;
      snapshot?: {
        dictionary_table?: string;
        schema?: string;
        counts?: Record<string, number>;
      };
    };
  };
};

export const getIADevHealth = async (): Promise<IADevHealthResponse> => {
  const response = await api.get<IADevHealthResponse>("/ia-dev/health/");
  return response.data;
};

export type IADevCreateTicketRequest = {
  session_id?: string;
  category?: string;
  title: string;
  description: string;
};

export type IADevCreateTicketResponse = {
  status: "created";
  ticket: {
    ticket_id: string;
    category: string;
    title: string;
    description: string;
    session_id?: string | null;
    created_at: number;
  };
};

export const createIADevTicket = async (
  payload: IADevCreateTicketRequest,
): Promise<IADevCreateTicketResponse> => {
  const response = await api.post<IADevCreateTicketResponse>(
    "/ia-dev/tickets/",
    payload,
  );
  return response.data;
};

export type IADevKnowledgeProposal = {
  proposal_id: string;
  status: string;
  mode: "ceo" | "auto" | "directo" | string;
  proposal_type: "nueva_regla" | "actualizacion_regla" | string;
  name: string;
  description: string;
  domain_code: string;
  condition_sql: string;
  result_text: string;
  tables_related: string;
  priority: number;
  target_rule_id?: number | null;
  session_id?: string | null;
  requested_by: string;
  similar_rules: Array<Record<string, unknown>>;
  created_at: number;
  updated_at: number;
  persistence?: Record<string, unknown> | null;
  error?: string | null;
};

export type IADevKnowledgeProposalCreateRequest = {
  message?: string;
  session_id?: string;
  requested_by?: string;
  proposal_type?: "nueva_regla" | "actualizacion_regla";
  name?: string;
  description?: string;
  domain_code?: string;
  condition_sql?: string;
  result_text?: string;
  tables_related?: string;
  priority?: number;
  target_rule_id?: number;
};

export type IADevKnowledgeProposalCreateResponse = {
  ok: boolean;
  requires_auth?: boolean;
  applied?: boolean;
  proposal?: IADevKnowledgeProposal;
  apply_result?: Record<string, unknown>;
  error?: string;
};

export type IADevKnowledgeProposalListResponse = {
  status: "ok";
  count: number;
  proposals: IADevKnowledgeProposal[];
};

export type IADevKnowledgeApproveRequest = {
  proposal_id: string;
  auth_key?: string;
  idempotency_key?: string;
};

export type IADevKnowledgeApproveResponse = {
  ok: boolean;
  status?: "accepted";
  async_mode?: string;
  job?: {
    job_id: string;
    job_type: string;
    status: string;
    payload?: Record<string, unknown>;
    result?: Record<string, unknown> | null;
    error?: string | null;
    idempotency_key?: string | null;
    created_at?: number;
    updated_at?: number;
    run_after?: number;
  };
  proposal?: IADevKnowledgeProposal;
  persistence?: Record<string, unknown>;
  error?: string;
  requires_auth?: boolean;
};

export type IADevKnowledgeRejectRequest = {
  proposal_id: string;
  reason?: string;
};

export const createIADevKnowledgeProposal = async (
  payload: IADevKnowledgeProposalCreateRequest,
): Promise<IADevKnowledgeProposalCreateResponse> => {
  const response = await api.post<IADevKnowledgeProposalCreateResponse>(
    "/ia-dev/knowledge/proposals/",
    payload,
  );
  return response.data;
};

export const listIADevKnowledgeProposals = async (params?: {
  status?: string;
  limit?: number;
}): Promise<IADevKnowledgeProposalListResponse> => {
  const response = await api.get<IADevKnowledgeProposalListResponse>(
    "/ia-dev/knowledge/proposals/",
    { params },
  );
  return response.data;
};

export const approveIADevKnowledgeProposal = async (
  payload: IADevKnowledgeApproveRequest,
): Promise<IADevKnowledgeApproveResponse> => {
  const response = await api.post<IADevKnowledgeApproveResponse>(
    "/ia-dev/knowledge/proposals/approve/",
    payload,
  );
  return response.data;
};

export const rejectIADevKnowledgeProposal = async (
  payload: IADevKnowledgeRejectRequest,
): Promise<IADevKnowledgeApproveResponse> => {
  const response = await api.post<IADevKnowledgeApproveResponse>(
    "/ia-dev/knowledge/proposals/reject/",
    payload,
  );
  return response.data;
};

export type IADevAsyncJobStatusResponse = {
  status: "ok";
  job: {
    job_id: string;
    job_type: string;
    status: "pending" | "running" | "done" | "failed" | string;
    payload?: Record<string, unknown>;
    result?: Record<string, unknown> | null;
    error?: string | null;
    idempotency_key?: string | null;
    created_at?: number;
    updated_at?: number;
    run_after?: number;
  };
};

export const getIADevAsyncJobStatus = async (
  jobId: string,
): Promise<IADevAsyncJobStatusResponse> => {
  const response = await api.get<IADevAsyncJobStatusResponse>(
    "/ia-dev/async/jobs/",
    { params: { job_id: jobId } },
  );
  return response.data;
};

export type IADevObservabilitySummaryResponse = {
  status: "ok";
  observability: {
    enabled: boolean;
    window_seconds: number;
    sample_size: number;
    event_types: Record<string, number>;
    totals: {
      events: number;
      tokens_in: number;
      tokens_out: number;
      cost_usd: number;
      latency: {
        count: number;
        avg_ms: number;
        p95_ms: number;
        max_ms: number;
      };
    };
    sources: Record<
      string,
      {
        events: number;
        tokens_in: number;
        tokens_out: number;
        cost_usd: number;
        latency: {
          count: number;
          avg_ms: number;
          p95_ms: number;
          max_ms: number;
        };
      }
    >;
  };
};

export const getIADevObservabilitySummary = async (params?: {
  window_seconds?: number;
  limit?: number;
}): Promise<IADevObservabilitySummaryResponse> => {
  const response = await api.get<IADevObservabilitySummaryResponse>(
    "/ia-dev/observability/summary/",
    { params },
  );
  return response.data;
};

export type IADevAttendancePeriodResolveResponse = {
  status: "ok";
  period_resolution: {
    session_id: string;
    input: {
      message: string;
      explicit_period_detected: boolean;
    };
    resolved_period: {
      label: string;
      source: string;
      start_date: string | null;
      end_date: string | null;
      confidence?: number;
    };
    rules_fallback_period: {
      label: string;
      source: string;
      start_date: string | null;
      end_date: string | null;
    };
    alternative_hint?: string | null;
  };
};

export const resolveIADevAttendancePeriod = async (payload: {
  message: string;
  session_id?: string;
}): Promise<IADevAttendancePeriodResolveResponse> => {
  const response = await api.post<IADevAttendancePeriodResolveResponse>(
    "/ia-dev/attendance/period/resolve/",
    payload,
  );
  return response.data;
};

export type IADevMemoryProposal = {
  proposal_id: string;
  scope: "session" | "user" | "business" | "workflow" | "general" | string;
  status: "pending" | "approved" | "rejected" | "applied" | "failed" | string;
  proposer_user_key: string;
  source_run_id?: string | null;
  candidate_key: string;
  candidate_value?: unknown;
  reason?: string;
  sensitivity?: "low" | "medium" | "high" | string;
  domain_code?: string | null;
  capability_id?: string | null;
  policy_action?: string | null;
  policy_id?: string | null;
  idempotency_key?: string | null;
  error?: string | null;
  version: number;
  created_at: number;
  updated_at: number;
};

export type IADevMemoryProposalCreateRequest = {
  scope?: "session" | "user" | "business" | "workflow" | "general";
  candidate_key: string;
  candidate_value: unknown;
  reason?: string;
  sensitivity?: "low" | "medium" | "high";
  idempotency_key?: string;
  domain_code?: string;
  capability_id?: string;
  direct_write?: boolean;
  source_run_id?: string;
};

export type IADevMemoryProposalCreateResponse = {
  ok: boolean;
  proposal?: IADevMemoryProposal;
  policy?: {
    action: string;
    policy_id: string;
    reason: string;
  };
  auto_applied?: boolean;
  error?: string;
};

export type IADevMemoryProposalListResponse = {
  status: "ok";
  count: number;
  proposals: IADevMemoryProposal[];
};

export const createIADevMemoryProposal = async (
  payload: IADevMemoryProposalCreateRequest,
): Promise<IADevMemoryProposalCreateResponse> => {
  const response = await api.post<IADevMemoryProposalCreateResponse>(
    "/ia-dev/memory/proposals/",
    payload,
  );
  return response.data;
};

export const listIADevMemoryProposals = async (params?: {
  status?: string;
  scope?: string;
  limit?: number;
}): Promise<IADevMemoryProposalListResponse> => {
  const response = await api.get<IADevMemoryProposalListResponse>(
    "/ia-dev/memory/proposals/",
    { params },
  );
  return response.data;
};

export const approveIADevMemoryProposal = async (payload: {
  proposal_id: string;
  comment?: string;
}): Promise<{
  ok: boolean;
  proposal?: IADevMemoryProposal;
  error?: string;
}> => {
  const response = await api.post("/ia-dev/memory/proposals/approve/", payload);
  return response.data;
};

export const rejectIADevMemoryProposal = async (payload: {
  proposal_id: string;
  comment?: string;
}): Promise<{
  ok: boolean;
  proposal?: IADevMemoryProposal;
  error?: string;
}> => {
  const response = await api.post("/ia-dev/memory/proposals/reject/", payload);
  return response.data;
};

export type IADevUserMemoryItem = {
  id: number;
  user_key: string;
  memory_key: string;
  memory_value: unknown;
  sensitivity: "low" | "medium" | "high" | string;
  source: string;
  confidence: number;
  expires_at?: number | null;
  created_at: number;
  updated_at: number;
};

export const listIADevUserMemory = async (params?: {
  limit?: number;
  user_key?: string;
}): Promise<{ status: "ok"; count: number; memory: IADevUserMemoryItem[] }> => {
  const response = await api.get("/ia-dev/memory/user/", { params });
  return response.data;
};

export const setIADevUserMemory = async (payload: {
  memory_key: string;
  memory_value: unknown;
  sensitivity?: "low" | "medium" | "high";
}): Promise<{ ok: boolean; memory?: IADevUserMemoryItem; error?: string }> => {
  const response = await api.post("/ia-dev/memory/user/", payload);
  return response.data;
};

export type IADevMemoryAuditEvent = {
  id: number;
  event_type: string;
  memory_scope: string;
  entity_key: string;
  action: string;
  actor_type: string;
  actor_key: string;
  run_id?: string | null;
  trace_id?: string | null;
  before?: unknown;
  after?: unknown;
  meta?: Record<string, unknown>;
  created_at: number;
};

export const listIADevMemoryAudit = async (params?: {
  scope?: string;
  entity_key?: string;
  limit?: number;
}): Promise<{
  status: "ok";
  count: number;
  events: IADevMemoryAuditEvent[];
}> => {
  const response = await api.get("/ia-dev/memory/audit/", { params });
  return response.data;
};
