"use client";

import { useMemo, useState } from "react";
import { Check, Copy, Wrench } from "lucide-react";
import type { ChatMessageModel } from "@/modules/programacion/ia-dev/chat/types";
import KPISection from "@/modules/programacion/ia-dev/chat/components/KPISection";
import InsightList from "@/modules/programacion/ia-dev/chat/components/InsightList";
import SmartChartRenderer from "@/modules/programacion/ia-dev/chat/components/SmartChartRenderer";
import DataTableRenderer from "@/modules/programacion/ia-dev/chat/components/DataTableRenderer";
import ReasoningPanel from "@/modules/programacion/ia-dev/chat/components/ReasoningPanel";

type ResponseRendererProps = {
  message: ChatMessageModel;
};

const formatOrchestratorMeta = (message: ChatMessageModel) => {
  const response = message.response;
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

const ResponseRenderer = ({ message }: ResponseRendererProps) => {
  const [copied, setCopied] = useState(false);
  const payload = message.normalized;

  const copyText = useMemo(() => {
    if (payload?.hasStructuredContent) {
      return JSON.stringify(
        {
          summary: payload.summary,
          kpis: payload.kpis,
          insights: payload.insights,
          table: payload.table,
          chart: payload.chart,
        },
        null,
        2,
      );
    }
    return message.content;
  }, [message.content, payload]);

  const metadata = useMemo(() => formatOrchestratorMeta(message), [message]);
  const extraCharts = useMemo(
    () => payload?.charts.slice(1, 3) ?? [],
    [payload?.charts],
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

  if (!payload || !payload.hasStructuredContent) {
    return (
      <div className="space-y-4">
        <ReasoningPanel
          response={message.response}
          isStreaming={message.status === "streaming"}
        />
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ReasoningPanel
        response={message.response}
        isStreaming={message.status === "streaming"}
      />

      <div className="flex items-start justify-between gap-2">
        <p className="text-sm leading-6 whitespace-pre-wrap text-gray-800 dark:text-gray-200">
          {payload.summary || message.content}
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

      <KPISection items={payload.kpis} />
      <InsightList insights={payload.insights} />
      <SmartChartRenderer payload={payload} />
      {extraCharts.map((chart, index) => (
        <SmartChartRenderer
          key={`${chart.title || "chart"}-${index}`}
          payload={{
            ...payload,
            chart,
            charts: [chart],
          }}
        />
      ))}
      <DataTableRenderer table={payload.table} />

      {metadata.length > 0 && (
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
