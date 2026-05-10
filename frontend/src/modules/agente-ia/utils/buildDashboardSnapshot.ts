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

const buildTableTabs = (
  payload: NormalizedAssistantPayload,
): DashboardTableTab[] => {
  const tabs: DashboardTableTab[] = [];

  const pushTab = (label: string, table: NormalizedTable | null) => {
    if (!table || table.rows.length === 0 || table.columns.length === 0) return;
    tabs.push({
      id: `table-${tabs.length}`,
      label,
      table,
    });
  };

  pushTab("Principal", payload.table);

  const extraTables = Array.isArray(payload.extraTables)
    ? payload.extraTables
    : [];

  extraTables.forEach((table, index) => {
    pushTab(`Adicional ${index + 1}`, table);
  });

  return tabs;
};

const buildWidgets = (
  payload: NormalizedAssistantPayload | null,
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

  const tabs = buildTableTabs(payload);
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
  const response = sourceMessage?.response ?? null;
  const isLoading = assistantMessages.some(
    (message) => message.status === "streaming",
  );

  return {
    sourceMessage,
    response,
    payload,
    widgets: buildWidgets(payload),
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
