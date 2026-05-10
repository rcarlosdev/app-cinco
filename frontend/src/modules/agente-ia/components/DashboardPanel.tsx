"use client";

import { Bot, Loader2 } from "lucide-react";
import DashboardRenderer from "@/modules/agente-ia/components/DashboardRenderer";
import type { DashboardSnapshot } from "@/modules/agente-ia/types";

type DashboardPanelProps = {
  snapshot: DashboardSnapshot;
  onLoadDemo: () => void;
};

const formatBadge = (value: string) =>
  value.replace(/[_-]+/g, " ").trim() || "general";

const DashboardPanel = ({
  snapshot,
  onLoadDemo,
}: DashboardPanelProps) => {
  return (
    <section className="flex h-full min-h-0 flex-col bg-[radial-gradient(circle_at_top,_rgba(15,23,42,0.045),_transparent_45%),linear-gradient(180deg,_rgba(248,250,252,0.96),_rgba(255,255,255,1))] dark:bg-gray-950">
      <header className="border-b border-gray-200 px-5 py-4 dark:border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-950 dark:text-white">
              <Bot size={16} />
              Vista estructurada
            </div>
            <p className="mt-1 max-w-2xl text-sm text-gray-500 dark:text-gray-400">
              KPIs, tablas y visualizaciones persistentes para respuestas analiticas.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
              intent: {formatBadge(snapshot.intent)}
            </span>
            <span className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
              domain: {formatBadge(snapshot.domain)}
            </span>
            <span className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
              agent: {formatBadge(snapshot.selectedAgent)}
            </span>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
          <span className="rounded-full bg-gray-100 px-3 py-1 dark:bg-gray-900">
            {snapshot.summary}
          </span>
          {snapshot.isLoading && (
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
              <Loader2 size={12} className="animate-spin" />
              Actualizando dashboard
            </span>
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-5">
        <DashboardRenderer snapshot={snapshot} onLoadDemo={onLoadDemo} />
      </div>
    </section>
  );
};

export default DashboardPanel;
