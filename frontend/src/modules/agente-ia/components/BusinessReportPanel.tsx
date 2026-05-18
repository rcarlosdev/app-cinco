"use client";

import { Copy, Download } from "lucide-react";
import DashboardRenderer from "@/modules/agente-ia/components/DashboardRenderer";
import EvidenceSummaryPanel from "@/modules/agente-ia/components/EvidenceSummaryPanel";
import SemanticExplanationPanel from "@/modules/agente-ia/components/SemanticExplanationPanel";
import TaskStatusBadge from "@/modules/agente-ia/components/TaskStatusBadge";
import TaskTimeline from "@/modules/agente-ia/components/TaskTimeline";
import type { DashboardSnapshot } from "@/modules/agente-ia/types";

type BusinessReportPanelProps = {
  snapshot: DashboardSnapshot;
  onLoadDemo: () => void;
  onCopyReport: () => void;
};

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const BusinessReportPanel = ({
  snapshot,
  onLoadDemo,
  onCopyReport,
}: BusinessReportPanelProps) => {
  return (
    <div className="space-y-5">
      <section className="rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
              Resumen ejecutivo
            </div>
            <h2 className="text-lg font-semibold text-gray-950 dark:text-white">
              {snapshot.executiveSummary}
            </h2>
            <div className="flex flex-wrap gap-2">
              <TaskStatusBadge
                label={snapshot.taskStatusLabel}
                tone={snapshot.taskStatusTone}
              />
              <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
                Dominio: {toLabel(snapshot.domain)}
              </span>
              <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
                Intencion: {toLabel(snapshot.intent)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onCopyReport}
              className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              <Copy size={13} />
              Copiar informe
            </button>
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-500"
            >
              <Download size={13} />
              Exportar pronto
            </button>
          </div>
        </div>

        {snapshot.clarificationQuestion ? (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
            <div className="font-semibold">Aclaracion requerida</div>
            <div className="mt-1">{snapshot.clarificationQuestion}</div>
          </div>
        ) : null}
      </section>

      {snapshot.semanticExplanation ? (
        <section className="rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950">
          <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Que entendio el sistema
          </div>
          <SemanticExplanationPanel explanation={snapshot.semanticExplanation} />
        </section>
      ) : null}

      <section className="rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950">
        <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
          Evidencia y dashboard
        </div>
        <div className="space-y-5">
          <EvidenceSummaryPanel
            evidence={snapshot.evidenceSummary}
            limitations={snapshot.limitations}
          />
          <DashboardRenderer snapshot={snapshot} onLoadDemo={onLoadDemo} />
        </div>
      </section>

      <section className="rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950">
        <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
          Timeline de tarea
        </div>
        <TaskTimeline steps={snapshot.taskTimeline} />
      </section>
    </div>
  );
};

export default BusinessReportPanel;
