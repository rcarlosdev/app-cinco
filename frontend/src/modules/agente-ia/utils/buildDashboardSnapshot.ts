import type {
  ChatMessageModel,
  NormalizedAssistantPayload,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";
import { normalizeChatPayload } from "@/modules/programacion/ia-dev/chat/utils/normalizeChatPayload";
import type {
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
  const taskStatus = getTaskStatus(response, isLoading);
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
  const clarificationQuestion = asString(
    semanticExplanation?.clarification_needed?.question,
  );
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
  const executiveSummary =
    asString(response?.reply) ||
    asString(response?.task?.current_run?.reply) ||
    payload?.summary ||
    "Sin resumen ejecutivo disponible.";
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
    toolsUsed,
    capabilitiesUsed,
    approvals,
    backgroundRuns,
    clarificationQuestion,
    limitations: limitationList,
    evidenceSummary,
    validationSummary,
    isLoading,
    isTerminal: !isLoading && terminalStatuses.has(taskStatus),
    hasStructuredContent,
    semanticExplanation,
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
  const latestStructuredMessage =
    [...assistantMessages].reverse().find((message) => {
      const payload = getNormalizedPayload(message);
      return Boolean(payload?.hasStructuredContent);
    }) ?? null;

  return buildDashboardSnapshotFromMessage(latestStructuredMessage ?? lastAssistant);
};
