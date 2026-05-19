import type {
  ChatMessageModel,
  NormalizedAssistantPayload,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";
import { normalizeChatPayload } from "@/modules/programacion/ia-dev/chat/utils/normalizeChatPayload";
import type {
  DashboardBackgroundJob,
  DashboardLifecycleStage,
  DashboardSnapshot,
  DashboardSupportItem,
  DashboardTaskStatusTone,
  DashboardTimelineStep,
  DashboardTableTab,
  DashboardWidget,
} from "@/modules/agente-ia/types";

const asString = (value: unknown) =>
  typeof value === "string" ? value.trim() : "";

const asObject = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
};

const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

const readStringMeta = (
  payload: NormalizedAssistantPayload | null,
  key: string,
) => asString(payload?.meta?.[key]);

const MATERIALS_COLUMNS = [
  "codigo",
  "descripcion",
  "tipo",
  "entregas",
  "devoluciones",
  "consumos",
  "cobros",
  "saldo",
] as const;

const SERIALIZED_COLUMNS = [
  "serial",
  "codigo",
  "descripcion",
  "familia",
  "estado",
  "en_movil",
  "en_base",
  "cobros",
  "saldo",
] as const;

const SERIALIZED_SUMMARY_COLUMNS = [
  "codigo",
  "descripcion",
  "familia",
  "seriales_total",
  "en_movil",
  "en_base",
  "cobros",
  "saldo",
] as const;

const normalizeColumnKey = (value: string) =>
  value.trim().toLowerCase().replace(/\s+/g, "_");

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const normalizeStatus = (value: unknown) =>
  asString(value).toLowerCase().replace(/\s+/g, "_");

const includesToken = (value: string, token: string) =>
  value.toLocaleLowerCase("es-CO").includes(token.toLocaleLowerCase("es-CO"));

const formatPlannerSummary = (
  payload: NormalizedAssistantPayload | null,
  fallbackSummary: string,
) => {
  const composition = payload?.dashboardComposition;
  if (!composition) return fallbackSummary || "Sin resumen ejecutivo disponible.";

  const semanticBasis = asObject(composition.semantic_basis) || {};
  const filters = asObject(semanticBasis.filters) || {};
  const executiveSummary = asObject(composition.executive_summary) || {};
  const evidenceContract = asObject(composition.evidence_contract) || {};

  const familyFilter = asString(filters.material_family);
  const familyMatchMode = asString(filters.material_family_match_mode);
  const groupingDimension = toLabel(
    asString(semanticBasis.grouping_dimension) || "dimension",
  ).toLocaleLowerCase("es-CO");
  const supportedPattern = asString(
    evidenceContract.semantic_pattern || evidenceContract.supported_pattern,
  );
  const responseProfile = asString(
    asObject(executiveSummary.resolved_route)?.response_profile,
  );
  const fallbackSource = [
    fallbackSummary,
    payload?.summary || "",
    ...(payload?.insights || []),
  ]
    .join(" ")
    .trim();

  const sentences: string[] = [];

  if (familyFilter) {
    sentences.push(
      familyMatchMode === "contains"
        ? `Se analizaron familias del catalogo que contienen ${familyFilter}.`
        : `Se analizo la familia ${familyFilter}.`,
    );
  }

  if (includesToken(fallbackSource, "estado movil")) {
    sentences.push("El saldo corresponde a seriales en estado MOVIL.");
  } else {
    const saldoDefinition = asString(executiveSummary.saldo_definition);
    if (saldoDefinition) {
      sentences.push(saldoDefinition);
    }
  }

  if (
    supportedPattern === "inventory.serial.stock.dimension" ||
    responseProfile.startsWith("inventory.serial.stock.dimension")
  ) {
    sentences.push(
      `La ruta usada fue inventario serializado agrupado por ${groupingDimension}.`,
    );
  }

  return sentences.join(" ").trim() || fallbackSummary || "Sin resumen ejecutivo disponible.";
};

const taskStatusLabels: Record<string, string> = {
  awaiting_approval: "Esperando aprobacion",
  blocked: "Bloqueado",
  cancelled: "Cancelado",
  completed: "Completado",
  executing: "En ejecucion",
  expired: "Expirado",
  failed: "Fallido",
  partial: "Parcial",
  paused: "Pausado",
  queued: "En cola",
  requires_clarification: "Requiere aclaracion",
  resumed: "Reanudado",
  running: "En ejecucion",
};

const taskStatusTones: Record<string, DashboardTaskStatusTone> = {
  awaiting_approval: "warning",
  blocked: "warning",
  cancelled: "neutral",
  completed: "success",
  executing: "info",
  expired: "danger",
  failed: "danger",
  partial: "warning",
  paused: "neutral",
  queued: "neutral",
  requires_clarification: "warning",
  resumed: "info",
  running: "info",
};

const taskPreparationLabels: Record<string, string> = {
  awaiting_approval: "Esperando aprobacion",
  blocked: "Bloqueado por validacion o alcance",
  cancelled: "Cancelado",
  completed: "Completado",
  executing: "Ejecutando",
  expired: "Expirado",
  failed: "Se produjo un fallo",
  partial: "Resultado parcial disponible",
  paused: "Pausado",
  queued: "Entendiendo consulta",
  resumed: "Reanudando tarea",
  requires_clarification: "Falta una aclaracion",
  running: "Preparando informe",
};

const stageLabels: Record<string, string> = {
  capability_selected: "Buscando capacidad",
  completed: "Completado",
  executing: "Ejecutando",
  evidence_ready: "Preparando informe",
  planned: "Validando",
  queued: "Entendiendo consulta",
  received: "Entendiendo consulta",
  requires_clarification: "Falta una aclaracion",
  semantic_plan_created: "Buscando capacidad",
  tool_selected: "Validando",
  validation_passed: "Validando",
};

const lifecycleLabels: Record<DashboardLifecycleStage, string> = {
  idle: "Sin corrida activa",
  preparing: "Preparando tarea",
  routing: "Resolviendo ruta",
  planning: "Planeando ejecucion",
  executing_tools: "Ejecutando herramientas",
  waiting_approval: "Esperando aprobacion",
  streaming_evidence: "Transmitiendo evidencia",
  completed: "Completado",
  failed: "Fallido",
  partial: "Resultado parcial",
};

const hasRequiredColumns = (
  table: NormalizedTable,
  requiredColumns: readonly string[],
) => {
  const availableColumns = new Set(table.columns.map(normalizeColumnKey));
  return requiredColumns.every((column) => availableColumns.has(column));
};

const inferInventoryTypePresentation = (table: NormalizedTable) => {
  const normalizedTipoKey = table.columns.find(
    (column) => normalizeColumnKey(column) === "tipo",
  );
  if (!normalizedTipoKey) {
    return {
      label: "Material Claro / Ferretero",
      badges: ["Material Claro", "Ferretero"],
    };
  }

  const tipos = new Set(
    table.rows
      .map((row) => asString(row[normalizedTipoKey]).toLowerCase())
      .filter(Boolean),
  );

  if (tipos.size === 1 && tipos.has("material")) {
    return {
      label: "Material Claro",
      badges: ["Material Claro"],
    };
  }

  if (tipos.size === 1 && tipos.has("ferretero")) {
    return {
      label: "Ferretero",
      badges: ["Ferretero"],
    };
  }

  return {
    label: "Material Claro / Ferretero",
    badges: ["Material Claro", "Ferretero"],
  };
};

const inferTablePresentation = (table: NormalizedTable) => {
  if (
    hasRequiredColumns(table, [
      "fecha",
      "tipo_movimiento",
      "codigo",
      "cedula",
      "cantidad",
      "efecto",
      "saldo_movimiento",
    ])
  ) {
    return {
      label: "Kardex Operativo",
      badges: ["Kardex", "Empleado", "Codigo"],
    };
  }

  if (hasRequiredColumns(table, MATERIALS_COLUMNS)) {
    return inferInventoryTypePresentation(table);
  }

  if (hasRequiredColumns(table, SERIALIZED_COLUMNS)) {
    return {
      label: "Serializados / Equipos",
      badges: ["Serializados", "Equipos"],
    };
  }

  if (hasRequiredColumns(table, SERIALIZED_SUMMARY_COLUMNS)) {
    return {
      label: "Serializados / Equipos",
      badges: ["Serializados", "Equipos"],
    };
  }

  return null;
};

const buildSupportItems = (items: unknown[]): DashboardSupportItem[] =>
  items
    .map((item, index) => {
      if (typeof item === "string") {
        const normalized = item.trim();
        if (!normalized) return null;
        return {
          key: `${normalized}-${index}`,
          label: toLabel(normalized),
        } satisfies DashboardSupportItem;
      }

      const candidate = asObject(item);
      if (!candidate) return null;

      const key =
        asString(candidate.id) ||
        asString(candidate.key) ||
        asString(candidate.tool_name) ||
        asString(candidate.capability) ||
        `${index}`;
      const label =
        asString(candidate.label) ||
        asString(candidate.name) ||
        asString(candidate.tool_name) ||
        asString(candidate.capability) ||
        asString(candidate.status);
      const detail =
        asString(candidate.detail) ||
        asString(candidate.reason) ||
        asString(candidate.summary) ||
        asString(candidate.execution_status);

      if (!label) return null;

      return {
        key,
        label: toLabel(label),
        detail: detail || undefined,
      } satisfies DashboardSupportItem;
    })
    .filter((item): item is DashboardSupportItem => item != null);

const buildTaskTimeline = (
  response: ChatMessageModel["response"],
): DashboardTimelineStep[] => {
  const semanticTimeline = Array.isArray(
    response?.task?.current_run?.semantic_explanation?.timeline,
  )
    ? response?.task?.current_run?.semantic_explanation?.timeline
    : [];

  if (semanticTimeline.length > 0) {
    return semanticTimeline.map((step) => ({
      step: step.step,
      state: step.state,
      detail: step.detail,
    }));
  }

  const trace = Array.isArray(response?.trace) ? response.trace : [];
  if (trace.length > 0) {
    return trace.slice(-6).map((item) => ({
      step: item.phase || "processing",
      state: item.status || "pending",
      detail: asString(item.detail),
    }));
  }

  const currentStatus = normalizeStatus(response?.task?.current_run?.status);
  if (!currentStatus) return [];

  return [
    {
      step: currentStatus,
      state:
        currentStatus === "completed"
          ? "completed"
          : currentStatus === "failed"
            ? "failed"
            : currentStatus === "awaiting_approval"
              ? "current"
              : "current",
    },
  ];
};

const getTaskStatus = (response: ChatMessageModel["response"], isLoading: boolean) => {
  const status = normalizeStatus(response?.task?.current_run?.status);
  if (status) return status;
  if (Boolean(response?.response_envelope?.needs_clarification)) {
    return "requires_clarification";
  }
  if (isLoading) return "running";
  return "completed";
};

const getTaskPreparationLabel = (
  response: ChatMessageModel["response"],
  taskStatus: string,
  isLoading: boolean,
) => {
  if (isLoading) {
    const workingUpdates = Array.isArray(response?.working_updates)
      ? response.working_updates
      : [];
    const lastUpdate = workingUpdates[workingUpdates.length - 1];
    const stage = normalizeStatus(lastUpdate?.stage || lastUpdate?.stage_label);
    if (stage && stageLabels[stage]) {
      return stageLabels[stage];
    }
    return "Preparando informe";
  }

  return taskPreparationLabels[taskStatus] || "Listo";
};

const getLatestWorkingUpdate = (
  response: ChatMessageModel["response"],
) => {
  const workingUpdates = Array.isArray(response?.working_updates)
    ? response.working_updates
    : [];
  return workingUpdates[workingUpdates.length - 1] ?? null;
};

const toOptionalNumber = (value: unknown) => {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
};

const buildBackgroundJob = (
  response: ChatMessageModel["response"],
): DashboardBackgroundJob | null => {
  const background = asObject(response?.task?.current_run?.background);
  if (!background) return null;
  const progress =
    asObject(asObject(response?.task?.current_run?.evidence)?.background_progress) ||
    asObject(asObject(response?.task?.current_run?.semantic_explanation)?.background_status) ||
    (asObject(asObject(response?.data)?.meta)?.background_job as Record<string, unknown> | null) ||
    null;
  const status = asString(background.run_status || progress?.status).toLowerCase();
  if (!status) return null;
  return {
    status,
    backgroundRunId:
      asString(progress?.background_run_id) || asString(background.background_run_id),
    jobId: asString(progress?.job_id) || asString(background.job_id),
    rowsProcessed: Number(progress?.rows_processed || 0),
    totalEstimated: Number(progress?.total_estimated || 0),
    percentage: Number(progress?.percentage || 0),
    phase: asString(progress?.phase) || status,
    phaseLabel: asString(progress?.phase_label) || undefined,
    elapsedSeconds: Number(progress?.elapsed_seconds || 0),
    etaSeconds: Number(progress?.eta_seconds || 0) || undefined,
    currentChunk: Number(progress?.current_chunk || 0),
    totalChunks: Number(progress?.total_chunks || 0),
    activeChunk: toOptionalNumber(progress?.active_chunk),
    serialsUniqueTotal: toOptionalNumber(progress?.serials_unique_total),
    serialsProcessed: toOptionalNumber(progress?.serials_processed),
    serialsPending: toOptionalNumber(progress?.serials_pending),
    stageSerialsTotal: toOptionalNumber(progress?.stage_serials_total),
    stageSerialsProcessed: toOptionalNumber(progress?.stage_serials_processed),
    stageSerialsPending: toOptionalNumber(progress?.stage_serials_pending),
    tableLabel: asString(progress?.table_label) || undefined,
    tableSerialsTotal: toOptionalNumber(progress?.table_serials_total),
    tableSerialsPending: toOptionalNumber(progress?.table_serials_pending),
    tableChunkTotal: toOptionalNumber(progress?.table_chunk_total),
    foundSoFar: Number(progress?.found_so_far || 0),
    notFoundSoFar: Number(progress?.not_found_so_far || 0),
    movilSoFar: Number(progress?.movil_so_far || 0),
    enrichedResponsibleSoFar: Number(progress?.enriched_responsible_so_far || 0),
    foundInBaseActual: toOptionalNumber(progress?.found_in_base_actual),
    foundInAsociadosActual: toOptionalNumber(progress?.found_in_asociados_actual),
    foundInHistorico: toOptionalNumber(progress?.found_in_historico),
    attachmentName: asString(progress?.attachment_name) || undefined,
    artifactId: asString(progress?.artifact_id) || undefined,
    resultKind: asString(progress?.result_kind) || undefined,
    resultLabel: asString(progress?.result_label) || undefined,
    failureReason:
      asString(background.failure_reason) || asString(progress?.failure_reason) || undefined,
    updatedAt: Number(progress?.updated_at || 0) || undefined,
  };
};

const getLifecycleStage = (
  sourceMessage: ChatMessageModel | null,
  response: ChatMessageModel["response"],
  payload: NormalizedAssistantPayload | null,
  taskStatus: string,
): DashboardLifecycleStage => {
  if (!sourceMessage || sourceMessage.id === "assistant-initial") {
    return "idle";
  }

  if (sourceMessage.status === "error" || taskStatus === "failed") {
    return "failed";
  }

  if (taskStatus === "awaiting_approval") {
    return "waiting_approval";
  }

  if (
    taskStatus === "requires_clarification" ||
    taskStatus === "blocked" ||
    taskStatus === "partial" ||
    Boolean(response?.response_envelope?.needs_clarification)
  ) {
    return "partial";
  }

  if (sourceMessage.status === "streaming") {
    if (payload?.hasStructuredContent) {
      return "streaming_evidence";
    }

    const lastUpdate = getLatestWorkingUpdate(response);
    const currentStage = normalizeStatus(lastUpdate?.stage || lastUpdate?.stage_label);

    if (
      currentStage === "received" ||
      currentStage === "queued" ||
      currentStage === "intake" ||
      currentStage === "bootstrap" ||
      currentStage === "progress"
    ) {
      return "preparing";
    }

    if (
      currentStage === "semantic_plan_created" ||
      currentStage === "capability_selected"
    ) {
      return "routing";
    }

    if (
      currentStage === "planning" ||
      currentStage === "tool_selected" ||
      currentStage === "validation_passed"
    ) {
      return "planning";
    }

    if (
      currentStage === "executing" ||
      currentStage === "running" ||
      currentStage === "tool_execution"
    ) {
      return "executing_tools";
    }

    return "streaming_evidence";
  }

  return "completed";
};

const getLifecycleDetail = (
  sourceMessage: ChatMessageModel | null,
  response: ChatMessageModel["response"],
  taskStatus: string,
  lifecycleStage: DashboardLifecycleStage,
  hasStructuredContent: boolean,
) => {
  if (!sourceMessage || sourceMessage.id === "assistant-initial") {
    return "Todavia no hay evidencia operativa para inspeccionar.";
  }

  if (lifecycleStage === "failed") {
    return (
      sourceMessage.error ||
      asString(response?.task?.current_run?.final_state?.failure_reason) ||
      "La corrida no pudo completarse."
    );
  }

  if (lifecycleStage === "waiting_approval") {
    return "La tarea necesita aprobacion antes de continuar.";
  }

  if (lifecycleStage === "partial") {
    return (
      asString(
        response?.task?.current_run?.semantic_explanation?.clarification_needed?.question,
      ) ||
      asString(response?.response_envelope?.block_reason) ||
      "La corrida quedo en un estado parcial o requiere precision."
    );
  }

  if (sourceMessage.status === "streaming") {
    const lastUpdate = getLatestWorkingUpdate(response);
    return (
      asString(lastUpdate?.display_text) ||
      asString(lastUpdate?.summary) ||
      taskPreparationLabels[taskStatus] ||
      "La corrida esta generando evidencia."
    );
  }

  if (hasStructuredContent) {
    return "La evidencia operativa esta lista para inspeccion.";
  }

  return "La respuesta no genero dashboard estructurado para esta corrida.";
};

const humanizeExplicitTableLabel = (value: string) => {
  const normalizedValue = normalizeColumnKey(value);

  if (
    normalizedValue.includes("materiales") &&
    normalizedValue.includes("ferretero")
  ) {
    return "Material Claro / Ferretero";
  }

  if (
    normalizedValue.includes("serializados") &&
    normalizedValue.includes("equipos")
  ) {
    return "Serializados / Equipos";
  }

  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const getExtraTablePreferredName = (
  response: ChatMessageModel["response"],
  index: number,
) => {
  const extraTables = Array.isArray(response?.data?.extra_tables)
    ? response.data.extra_tables
    : [];
  const rawTable = extraTables[index];
  if (!rawTable || typeof rawTable !== "object") return "";

  const candidate = rawTable as Record<string, unknown>;
  return (
    asString(candidate.name) || asString(candidate.title) || asString(candidate.key)
  );
};

const buildTableTabs = (
  payload: NormalizedAssistantPayload,
  response: ChatMessageModel["response"],
): DashboardTableTab[] => {
  const tabs: DashboardTableTab[] = [];

  const pushTab = (
    fallbackLabel: string,
    table: NormalizedTable | null,
    preferredLabel?: string,
  ) => {
    if (!table || table.rows.length === 0 || table.columns.length === 0) return;
    const inferredPresentation = inferTablePresentation(table);
    const explicitLabel = preferredLabel
      ? humanizeExplicitTableLabel(preferredLabel)
      : "";
    tabs.push({
      id: `table-${tabs.length}`,
      label: explicitLabel || inferredPresentation?.label || fallbackLabel,
      badges: inferredPresentation?.badges ?? [],
      table,
    });
  };

  pushTab("Tabla principal", payload.table);

  const extraTables = Array.isArray(payload.extraTables)
    ? payload.extraTables
    : [];

  extraTables.forEach((table, index) => {
    pushTab(
      `Tabla adicional ${index + 1}`,
      table,
      getExtraTablePreferredName(response, index),
    );
  });

  return tabs;
};

const buildWidgets = (
  payload: NormalizedAssistantPayload | null,
  response: ChatMessageModel["response"],
): DashboardWidget[] => {
  if (!payload) return [];

  const widgets: DashboardWidget[] = [];

  if ((payload.kpis ?? []).length > 0) {
    widgets.push({
      id: "kpi-grid",
      type: "kpi",
      title: "Indicadores clave",
      data: {
        items: payload.kpis ?? [],
      },
    });
  }

  if ((payload.charts ?? []).length > 0) {
    widgets.push({
      id: "charts",
      type: "chart",
      title: "Visualizaciones",
      data: {
        charts: payload.charts ?? [],
      },
    });
  }

  if ((payload.insights ?? []).length > 0) {
    widgets.push({
      id: "insights",
      type: "insights",
      title: "Insights de negocio",
      data: {
        items: payload.insights ?? [],
      },
    });
  }

  const tabs = buildTableTabs(payload, response);
  if (tabs.length > 0) {
    widgets.push({
      id: "tables",
      type: "table",
      title: "Tablas operativas",
      data: {
        tabs,
      },
    });
  }

  return widgets;
};

export const getNormalizedPayload = (
  message: ChatMessageModel,
): NormalizedAssistantPayload | null => {
  if (message.normalized) return message.normalized;
  if (!message.response) return null;
  return normalizeChatPayload(message.response);
};

export const buildDashboardSnapshotFromMessage = (
  sourceMessage: ChatMessageModel | null,
): DashboardSnapshot => {
  const payload = sourceMessage ? getNormalizedPayload(sourceMessage) : null;
  const response = sourceMessage?.response;
  const isLoading = sourceMessage?.status === "streaming";
  const semanticExplanation = payload?.semanticExplanation ?? null;
  const dashboardComposition = payload?.dashboardComposition ?? null;
  const taskStatus = getTaskStatus(response, isLoading);
  const backgroundJob = buildBackgroundJob(response);
  const isProviderSerialBackgroundActive =
    backgroundJob != null &&
    ["queued", "running", "resumed"].includes(backgroundJob.status) &&
    (
      asString(response?.task?.current_run?.semantic_explanation?.selected_capability) ||
      asString(response?.task?.current_run?.intent) ||
      asString(response?.orchestrator?.intent)
    ) === "inventory_provider_serial_validation";
  const taskTimeline = buildTaskTimeline(response);
  const evidenceSummary = asObject(semanticExplanation?.evidence_summary)
    || asObject(response?.task?.current_run?.evidence)
    || {};
  const validationSummary = asObject(semanticExplanation?.validation_status)
    || asObject(response?.task?.current_run?.validation)
    || {};
  const limitationList = Array.isArray(semanticExplanation?.limitations)
    ? semanticExplanation.limitations
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const clarificationQuestion = isProviderSerialBackgroundActive
    ? ""
    : asString(semanticExplanation?.clarification_needed?.question);
  const toolsUsed = buildSupportItems([
    ...(semanticExplanation?.selected_tool ? [semanticExplanation.selected_tool] : []),
    ...(Array.isArray(response?.orchestrator?.used_tools)
      ? response.orchestrator.used_tools
      : []),
    ...(Array.isArray(response?.task?.current_run?.required_tools)
      ? response.task.current_run.required_tools
      : []),
  ]);
  const capabilitiesUsed = buildSupportItems([
    ...(semanticExplanation?.selected_capability
      ? [semanticExplanation.selected_capability]
      : []),
  ]);
  const approvals = buildSupportItems([
    semanticExplanation?.approvals_status,
    asObject(response?.task?.current_run?.final_state)?.approvals,
  ]);
  const backgroundRuns = buildSupportItems([
    semanticExplanation?.background_status,
    asObject(response?.task?.current_run?.final_state)?.background,
  ]);
  const fallbackExecutiveSummary =
    asString(response?.reply) ||
    asString(response?.task?.current_run?.reply) ||
    payload?.summary ||
    "Sin resumen ejecutivo disponible.";
  const executiveSummary = formatPlannerSummary(
    payload,
    fallbackExecutiveSummary,
  );
  const hasStructuredContent = Boolean(payload?.hasStructuredContent);
  const lifecycleStage = getLifecycleStage(
    sourceMessage,
    response,
    payload,
    taskStatus,
  );
  const terminalStatuses = new Set([
    "blocked",
    "cancelled",
    "completed",
    "expired",
    "failed",
    "partial",
    "requires_clarification",
  ]);

  return {
    sourceMessage,
    response: response ?? null,
    payload,
    widgets: buildWidgets(payload, response),
    messageId: sourceMessage?.id ?? null,
    messageCreatedAt: sourceMessage?.createdAt ?? null,
    summary: payload?.summary || executiveSummary || "Esperando resultados analiticos.",
    executiveSummary,
    intent:
      asString(response?.orchestrator?.intent) ||
      readStringMeta(payload, "intent") ||
      "conversational_query",
    domain:
      asString(response?.orchestrator?.domain) ||
      readStringMeta(payload, "domain") ||
      "general",
    selectedAgent:
      asString(response?.orchestrator?.selected_agent) ||
      readStringMeta(payload, "selected_agent") ||
      "assistant",
    taskStatus,
    taskStatusLabel: taskStatusLabels[taskStatus] || toLabel(taskStatus || "idle"),
    taskStatusTone: taskStatusTones[taskStatus] || "neutral",
    taskPreparationLabel: getTaskPreparationLabel(response, taskStatus, isLoading),
    taskTimeline,
    backgroundJob,
    toolsUsed,
    capabilitiesUsed,
    approvals,
    backgroundRuns,
    clarificationQuestion,
    limitations: isProviderSerialBackgroundActive ? [] : limitationList,
    evidenceSummary,
    validationSummary,
    isLoading,
    isTerminal: !isLoading && terminalStatuses.has(taskStatus),
    hasStructuredContent,
    semanticExplanation,
    dashboardComposition,
    lifecycleStage,
    lifecycleLabel: lifecycleLabels[lifecycleStage],
    stageDetail: getLifecycleDetail(
      sourceMessage,
      response,
      taskStatus,
      lifecycleStage,
      hasStructuredContent,
    ),
  };
};

export const buildDashboardSnapshot = (
  messages: ChatMessageModel[],
  preferredMessageId?: string | null,
): DashboardSnapshot => {
  const assistantMessages = messages.filter((message) => message.role === "assistant");
  const explicitMessage =
    preferredMessageId
      ? assistantMessages.find((message) => message.id === preferredMessageId) ?? null
      : null;

  if (explicitMessage) {
    return buildDashboardSnapshotFromMessage(explicitMessage);
  }

  const lastAssistant = assistantMessages[assistantMessages.length - 1] ?? null;
  const latestActiveBackgroundMessage =
    [...assistantMessages].reverse().find((message) => {
      const response = message.response;
      const semantic = asObject(response?.task?.current_run?.semantic_explanation);
      const capability = asString(
        semantic?.selected_capability ||
          response?.task?.current_run?.intent ||
          response?.orchestrator?.intent,
      );
      const routeHint = asString(semantic?.planner_route_hint);
      const status = asString(
        response?.task?.current_run?.background?.run_status ||
          response?.task?.current_run?.status,
      ).toLowerCase();
      return (
        capability === "inventory_provider_serial_validation" &&
        routeHint === "inventory.serial.validation.provider_file" &&
        ["queued", "running", "resumed"].includes(status)
      );
    }) ?? null;

  if (latestActiveBackgroundMessage) {
    return buildDashboardSnapshotFromMessage(latestActiveBackgroundMessage);
  }

  const latestStructuredMessage =
    [...assistantMessages].reverse().find((message) => {
      const payload = getNormalizedPayload(message);
      return Boolean(payload?.hasStructuredContent);
    }) ?? null;

  return buildDashboardSnapshotFromMessage(latestStructuredMessage ?? lastAssistant);
};
