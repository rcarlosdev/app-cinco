"use client";

import { useMemo, useState } from "react";
import { Check, Copy, Wrench } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import type {
  IADevChartPayload,
  IADevChatResponse,
} from "@/services/ia-dev.service";
import KPISection from "@/modules/programacion/ia-dev/chat/components/KPISection";
import InsightList from "@/modules/programacion/ia-dev/chat/components/InsightList";
import SmartChartRenderer from "@/modules/programacion/ia-dev/chat/components/SmartChartRenderer";
import DataTableRenderer from "@/modules/programacion/ia-dev/chat/components/DataTableRenderer";
import ReasoningPanel from "@/modules/programacion/ia-dev/chat/components/ReasoningPanel";
import {
  getSemanticTone,
  toneSoftClass,
} from "@/modules/programacion/ia-dev/chat/utils/semanticTone";

type ResponseRendererProps = {
  message: ChatMessageModel;
  variant?: "full" | "clean";
};

const INTERNAL_TEXT_PATTERN =
  /(sql asistido|solo lectura|ai_dictionary|inferencia semantica|modo sql|restringido|runtime|orchestrator|classifier|compiler|query_sql|join_aware)/i;

const isInternalText = (value: string | undefined | null) =>
  Boolean(value && INTERNAL_TEXT_PATTERN.test(value));

const getRowCount = (payload: NonNullable<ChatMessageModel["normalized"]>) => {
  const rowCountKpi = payload.kpis.find((item) => item.key === "rowcount");
  if (typeof rowCountKpi?.rawValue === "number") return rowCountKpi.rawValue;
  if (payload.table?.rowcount) return payload.table.rowcount;
  return payload.table?.rows.length || null;
};

const cleanSummary = (
  payload: NonNullable<ChatMessageModel["normalized"]>,
  content: string,
) => {
  const candidate = payload.summary || content;
  if (!isInternalText(candidate)) return candidate;

  const rowCount = getRowCount(payload);
  if (rowCount) {
    return `Encontre ${rowCount} registros para tu consulta.`;
  }
  if (payload.insights.some((insight) => !isInternalText(insight))) {
    return "Estos son los resultados principales.";
  }
  return "Consulta completada. Revisa los resultados principales a continuacion.";
};

const cleanChartTitle = (title: unknown) => {
  const value = typeof title === "string" ? title.trim() : "";
  if (!value || isInternalText(value)) return "Resultados principales";
  return value;
};

const cleanChart = (chart: IADevChartPayload): IADevChartPayload => ({
  ...chart,
  title: cleanChartTitle(chart.title),
});

const toCleanPayload = (
  payload: NonNullable<ChatMessageModel["normalized"]>,
  message: ChatMessageModel,
): NonNullable<ChatMessageModel["normalized"]> => {
  const chart = payload.chart ? cleanChart(payload.chart) : null;
  return {
    ...payload,
    summary: cleanSummary(payload, message.content),
    insights: payload.insights.filter((insight) => !isInternalText(insight)),
    chart,
    charts: chart ? [chart] : payload.charts.slice(0, 1).map(cleanChart),
    meta: {},
  };
};

const formatOrchestratorMeta = (message: ChatMessageModel) => {
  const response = message.response as Partial<IADevChatResponse> | undefined;
  if (!response) return [];
  const usedTools =
    response.orchestrator?.used_tools &&
    response.orchestrator.used_tools.length > 0
      ? response.orchestrator.used_tools.join(", ")
      : "sin tools";
  const memoryUsed = response.memory?.used_messages ?? 0;
  const memoryCapacity = response.memory?.capacity_messages ?? 0;
  return [
    {
      label: "Agente",
      value: response.orchestrator?.selected_agent || "analista_agent",
    },
    {
      label: "Dominio",
      value: response.orchestrator?.domain || "general",
    },
    {
      label: "Tools",
      value: usedTools,
    },
    {
      label: "Memoria",
      value: `${memoryUsed}/${memoryCapacity}`,
    },
  ];
};

const ResponseRenderer = ({
  message,
  variant = "full",
}: ResponseRendererProps) => {
  const [copied, setCopied] = useState(false);
  const payload = message.normalized;
  const showRuntimeDetails = variant === "full";
  const renderPayload = useMemo(
    () =>
      payload && variant === "clean"
        ? toCleanPayload(payload, message)
        : payload,
    [message, payload, variant],
  );

  const copyText = useMemo(() => {
    if (renderPayload?.hasStructuredContent) {
      return JSON.stringify(
        {
          summary: renderPayload.summary,
          kpis: renderPayload.kpis,
          insights: renderPayload.insights,
          table: renderPayload.table,
          chart: renderPayload.chart,
        },
        null,
        2,
      );
    }
    return message.content;
  }, [message.content, renderPayload]);

  const metadata = useMemo(() => formatOrchestratorMeta(message), [message]);
  const summaryTone = useMemo(
    () =>
      getSemanticTone({
        value: renderPayload?.summary || message.content,
      }),
    [message.content, renderPayload?.summary],
  );
  const extraCharts = useMemo(
    () => (showRuntimeDetails ? (renderPayload?.charts.slice(1, 3) ?? []) : []),
    [renderPayload?.charts, showRuntimeDetails],
  );

  const copyResponse = async () => {
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1300);
    } catch {
      setCopied(false);
    }
  };

  if (!renderPayload || !renderPayload.hasStructuredContent) {
    return (
      <div className="space-y-4">
        {showRuntimeDetails && (
          <ReasoningPanel
            response={message.response}
            isStreaming={message.status === "streaming"}
          />
        )}
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {showRuntimeDetails && (
        <ReasoningPanel
          response={message.response}
          isStreaming={message.status === "streaming"}
        />
      )}

      <div
        className={`flex items-start justify-between gap-2 rounded-xl border px-3 py-2 ${toneSoftClass[summaryTone]}`}
      >
        <p className="text-sm leading-6 whitespace-pre-wrap">
          {renderPayload.summary || message.content}
        </p>
        <button
          type="button"
          onClick={copyResponse}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition hover:bg-white dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          title="Copiar respuesta"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>

      <KPISection items={renderPayload.kpis} />
      <InsightList insights={renderPayload.insights} />
      <SmartChartRenderer payload={renderPayload} variant={variant} />
      {extraCharts.map((chart, index) => (
        <SmartChartRenderer
          key={`${chart.title || "chart"}-${index}`}
          payload={{
            ...renderPayload,
            chart,
            charts: [chart],
          }}
          variant={variant}
        />
      ))}
      <DataTableRenderer table={renderPayload.table} />

      {showRuntimeDetails && metadata.length > 0 && (
        <section className="space-y-2">
          <p className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            <Wrench size={12} />
            Metadatos de ejecucion
          </p>
          <div className="flex flex-wrap gap-2">
            {metadata.map((item) => (
              <span
                key={item.label}
                className="rounded-full border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
                title={`${item.label}: ${item.value}`}
              >
                <strong>{item.label}:</strong> {item.value}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default ResponseRenderer;
