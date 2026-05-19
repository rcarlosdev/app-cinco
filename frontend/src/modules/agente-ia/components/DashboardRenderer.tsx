"use client";

import type { ComponentType } from "react";
import {
  AreaChart,
  BarChart3,
  LayoutDashboard,
  Table2,
  WandSparkles,
} from "lucide-react";
import ChartRenderer from "@/modules/agente-ia/components/ChartRenderer";
import DataTable from "@/modules/agente-ia/components/DataTable";
import InsightCards from "@/modules/agente-ia/components/InsightCards";
import KPIGrid from "@/modules/agente-ia/components/KPIGrid";
import type {
  AgenteIAViewMode,
  DashboardSnapshot,
  DashboardWidget,
} from "@/modules/agente-ia/types";

type RendererProps = {
  widget: DashboardWidget;
  mode: AgenteIAViewMode;
};

const KPIWidget = ({ widget }: RendererProps) =>
  widget.type === "kpi" ? <KPIGrid items={widget.data.items} /> : null;

const ChartWidget = ({ widget }: RendererProps) =>
  widget.type === "chart" ? <ChartRenderer charts={widget.data.charts} /> : null;

const TableWidget = ({ widget, mode }: RendererProps) =>
  widget.type === "table" ? <DataTable mode={mode} tabs={widget.data.tabs} /> : null;

const InsightWidget = ({ widget }: RendererProps) =>
  widget.type === "insights" ? <InsightCards items={widget.data.items} /> : null;

const EmptyWidget = () => null;

const widgetRegistry: Record<
  DashboardWidget["type"],
  ComponentType<RendererProps>
> = {
  kpi: KPIWidget,
  chart: ChartWidget,
  table: TableWidget,
  insights: InsightWidget,
  semantic_explanation: EmptyWidget,
};

type DashboardRendererProps = {
  mode?: AgenteIAViewMode;
  snapshot: DashboardSnapshot;
  onLoadDemo: () => void;
};

const DashboardRenderer = ({
  mode = "user",
  snapshot,
  onLoadDemo,
}: DashboardRendererProps) => {
  if (!snapshot.hasStructuredContent) {
    return (
      <div className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-[32px] border border-dashed border-gray-300 bg-white px-6 py-10 text-center dark:border-gray-700 dark:bg-gray-950">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-100 text-gray-700 dark:bg-gray-900 dark:text-gray-200">
          {snapshot.isLoading ? (
            <WandSparkles size={24} />
          ) : (
            <LayoutDashboard size={24} />
          )}
        </div>
        <h3 className="mt-5 text-lg font-semibold text-gray-950 dark:text-white">
          {snapshot.isLoading
            ? "Preparando dashboard"
            : "El dashboard aparecera aqui"}
        </h3>
        <p className="mt-2 max-w-xl text-sm leading-6 text-gray-500 dark:text-gray-400">
          {snapshot.isLoading
            ? "La respuesta esta en curso. Cuando lleguen KPIs, tablas o charts, esta vista los materializara automaticamente."
            : "Conversa a la izquierda y deja que la IA convierta resultados analiticos en tablas, KPIs, graficas e insights sin repetir el texto del chat."}
        </p>
        {!snapshot.isLoading && (
          <button
            type="button"
            onClick={onLoadDemo}
            className="mt-5 inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
          >
            <WandSparkles size={16} />
            Cargar demo analitica
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {snapshot.widgets.map((widget) => {
        const Renderer = widgetRegistry[widget.type];
        const Icon =
          widget.type === "kpi"
            ? LayoutDashboard
            : widget.type === "chart"
              ? AreaChart
              : widget.type === "table"
                ? Table2
                : widget.type === "semantic_explanation"
                  ? WandSparkles
                : BarChart3;

        return (
          <section key={widget.id} className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
              <Icon size={13} />
              {widget.title}
            </div>
            <Renderer widget={widget} mode={mode} />
          </section>
        );
      })}
    </div>
  );
};

export default DashboardRenderer;
