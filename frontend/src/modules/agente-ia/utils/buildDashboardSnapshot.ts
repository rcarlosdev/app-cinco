import type {
  ChatMessageModel,
  NormalizedAssistantPayload,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";
import { normalizeChatPayload } from "@/modules/programacion/ia-dev/chat/utils/normalizeChatPayload";
import type {
  DashboardSnapshot,
  DashboardTableTab,
  DashboardWidget,
} from "@/modules/agente-ia/types";

const asString = (value: unknown) =>
  typeof value === "string" ? value.trim() : "";

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

const normalizeColumnKey = (value: string) =>
  value.trim().toLowerCase().replace(/\s+/g, "_");

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
  if (hasRequiredColumns(table, MATERIALS_COLUMNS)) {
    return inferInventoryTypePresentation(table);
  }

  if (hasRequiredColumns(table, SERIALIZED_COLUMNS)) {
    return {
      label: "Serializados / Equipos",
      badges: ["Serializados", "Equipos"],
    };
  }

  return null;
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

const getNormalizedPayload = (
  message: ChatMessageModel,
): NormalizedAssistantPayload | null => {
  if (message.normalized) return message.normalized;
  if (!message.response) return null;
  return normalizeChatPayload(message.response);
};

export const buildDashboardSnapshot = (
  messages: ChatMessageModel[],
): DashboardSnapshot => {
  const assistantMessages = messages.filter((message) => message.role === "assistant");
  const lastAssistant = assistantMessages[assistantMessages.length - 1] ?? null;
  const latestStructuredMessage =
    [...assistantMessages].reverse().find((message) => {
      const payload = getNormalizedPayload(message);
      return Boolean(payload?.hasStructuredContent);
    }) ?? null;

  const sourceMessage = latestStructuredMessage ?? lastAssistant;
  const payload = sourceMessage ? getNormalizedPayload(sourceMessage) : null;
  const response = sourceMessage?.response;
  const isLoading = assistantMessages.some(
    (message) => message.status === "streaming",
  );

  return {
    sourceMessage,
    response: response ?? null,
    payload,
    widgets: buildWidgets(payload, response),
    summary:
      payload?.summary ||
      asString(sourceMessage?.content) ||
      "Esperando resultados analiticos.",
    intent: asString(response?.orchestrator?.intent) || "conversational_query",
    domain: asString(response?.orchestrator?.domain) || "general",
    selectedAgent:
      asString(response?.orchestrator?.selected_agent) || "assistant",
    isLoading,
    hasStructuredContent: Boolean(payload?.hasStructuredContent),
  };
};
