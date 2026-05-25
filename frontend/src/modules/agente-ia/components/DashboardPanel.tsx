"use client";

import { Bot, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import BusinessReportPanel from "@/modules/agente-ia/components/BusinessReportPanel";
import TaskStatusBadge from "@/modules/agente-ia/components/TaskStatusBadge";
import type { AgenteIAViewMode, DashboardSnapshot } from "@/modules/agente-ia/types";

type DashboardHistoryEntry = {
  messageId: string;
  label: string;
  shortLabel: string;
};

type DashboardPanelProps = {
  mode?: AgenteIAViewMode;
  snapshot: DashboardSnapshot;
  liveSnapshot: DashboardSnapshot | null;
  historyEntries: DashboardHistoryEntry[];
  selectedMessageId: string | null;
  selectedMessageLabel: string;
  canSelectPrevious: boolean;
  canSelectNext: boolean;
  onSelectPrevious: () => void;
  onSelectNext: () => void;
  onSelectMessage: (messageId: string) => void;
  onLoadDemo: () => void;
  onCopyReport: () => void;
};

const DashboardPanel = ({
  mode = "dev",
  snapshot,
  liveSnapshot,
  historyEntries,
  selectedMessageId,
  selectedMessageLabel,
  canSelectPrevious,
  canSelectNext,
  onSelectPrevious,
  onSelectNext,
  onSelectMessage,
  onLoadDemo,
  onCopyReport,
}: DashboardPanelProps) => {
  const hasLatestRuntimeNotice =
    liveSnapshot != null &&
    liveSnapshot.messageId != null &&
    liveSnapshot.lifecycleStage !== "completed";
  const isViewingHistoricalSnapshot =
    Boolean(selectedMessageId) &&
    selectedMessageId !== liveSnapshot?.messageId;

  return (
    <section className="flex h-full min-h-0 flex-col bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.08),transparent_42%),linear-gradient(180deg,rgba(248,250,252,0.98),rgba(255,255,255,1))] dark:bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.12),transparent_35%),linear-gradient(180deg,#020617_0%,#0f172a_100%)]">
      <header className="border-b border-gray-200 px-5 py-4 dark:border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-950 dark:text-white">
              <Bot size={16} />
              {mode === "user" ? "Resultados" : "Panel de analisis"}
            </div>
            <p className="mt-1 max-w-2xl text-sm text-gray-500 dark:text-gray-400">
              {mode === "user"
                ? "Resumen, hallazgos y detalle util relacionado con la respuesta actual."
                : "Evidencia, metricas y contexto operativo de cada respuesta."}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {mode === "dev" ? (
              <TaskStatusBadge
                label={snapshot.taskStatusLabel}
                tone={snapshot.taskStatusTone}
              />
            ) : null}
            {snapshot.isLoading ? (
              <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
                <Loader2 size={12} className="animate-spin" />
                {mode === "user" ? "Actualizando resultados" : "Actualizando dashboard"}
              </span>
            ) : null}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onSelectPrevious}
            disabled={!canSelectPrevious}
            className="inline-flex items-center gap-1 rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
          >
            <ChevronLeft size={14} />
            Anterior
          </button>
          <button
            type="button"
            onClick={onSelectNext}
            disabled={!canSelectNext}
            className="inline-flex items-center gap-1 rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
          >
            Siguiente
            <ChevronRight size={14} />
          </button>
          <div className="flex min-w-0 flex-1 gap-2 overflow-auto pb-1">
            {historyEntries.map((entry) => {
              const isActive = entry.messageId === selectedMessageId;

              return (
                <button
                  key={entry.messageId}
                  type="button"
                  onClick={() => onSelectMessage(entry.messageId)}
                  className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    isActive
                      ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-200"
                      : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                  }`}
                  title={entry.label}
                >
                  {mode === "user" ? entry.label : entry.shortLabel}
                </button>
              );
            })}
          </div>
        </div>

        {mode === "user" ? (
          <div className="mt-3 rounded-2xl border border-gray-200 bg-white/85 px-3 py-2 text-sm text-gray-600 dark:border-gray-800 dark:bg-gray-900/70 dark:text-gray-300">
            <span className="font-medium text-gray-900 dark:text-white">
              Vista actual:
            </span>{" "}
            {selectedMessageLabel}
          </div>
        ) : null}

        {mode === "dev" && hasLatestRuntimeNotice && isViewingHistoricalSnapshot ? (
          <div className="mt-3 rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
            <span className="font-semibold">Estado mas reciente:</span>{" "}
            se mantiene visible {selectedMessageLabel} mientras el runtime va en{" "}
            {liveSnapshot.lifecycleLabel.toLowerCase()}.
          </div>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-5">
        <BusinessReportPanel
          mode={mode}
          snapshot={snapshot}
          onLoadDemo={onLoadDemo}
          onCopyReport={onCopyReport}
        />
      </div>
    </section>
  );
};

export default DashboardPanel;
