"use client";

import { useMemo } from "react";
import { BarChart3 } from "lucide-react";
import type { IADevChartPayload } from "@/services/ia-dev.service";
import type { NormalizedAssistantPayload } from "@/modules/programacion/ia-dev/chat/types";
import {
  selectBestChartConfig,
  type SmartChartConfig,
} from "@/modules/programacion/ia-dev/chat/utils/selectBestChartConfig";
import IADevChartPanel from "@/modules/programacion/ia-dev/components/IADevChartPanel";

type SmartChartRendererProps = {
  payload: NormalizedAssistantPayload;
  variant?: "full" | "clean";
};

const asNumber = (value: unknown): number => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const withSort = (
  rows: Array<Record<string, unknown>>,
  config: SmartChartConfig,
): Array<Record<string, unknown>> => {
  if (config.sort === "none") return rows;
  const valueKey = config.valueKeys[0];
  return [...rows].sort((left, right) => {
    const delta = asNumber(left[valueKey]) - asNumber(right[valueKey]);
    return config.sort === "asc" ? delta : -delta;
  });
};

const formatValue = (value: unknown): string => {
  if (typeof value !== "number") return String(value ?? "-");
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(
    value,
  );
};

const toEmbeddedChartPayload = (
  config: SmartChartConfig,
  data: Array<Record<string, unknown>>,
): IADevChartPayload => {
  const primaryValueKey = config.valueKeys[0];
  const normalizedType =
    config.type === "line" || config.type === "area" ? config.type : "bar";

  return {
    engine: "amcharts5",
    chart_library: "amcharts5",
    type: normalizedType,
    title: config.title,
    x_key: config.labelKey,
    y_key: primaryValueKey,
    series: [
      {
        name: primaryValueKey,
        value_key: primaryValueKey,
      },
    ],
    data,
  };
};

const SmartChartRenderer = ({
  payload,
  variant = "full",
}: SmartChartRendererProps) => {
  const showDetails = variant === "full";
  const config = useMemo(
    () =>
      selectBestChartConfig({
        labels: payload.labels,
        series: payload.series,
        table: payload.table,
        chart: payload.chart,
        charts: payload.charts,
        meta: payload.meta,
      }),
    [
      payload.chart,
      payload.charts,
      payload.labels,
      payload.meta,
      payload.series,
      payload.table,
    ],
  );

  const chartData = useMemo(() => {
    if (!config) return [];
    return withSort(config.data, config);
  }, [config]);

  const chartPayload = useMemo(() => {
    if (!config || chartData.length === 0) return null;
    return toEmbeddedChartPayload(config, chartData);
  }, [chartData, config]);

  if (!config || !chartPayload) return null;

  const valueKey = config.valueKeys[0];
  const showChartHeader = variant === "full";

  return (
    <section className="space-y-2">
      <div>
        <p className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
          <BarChart3 size={12} />
          Grafica principal
        </p>
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {config.title}
        </p>
        {config.subtitle && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {config.subtitle}
          </p>
        )}
      </div>

      <IADevChartPanel
        chart={chartPayload}
        embedded
        showDetails={showDetails}
        showHeader={showChartHeader}
      />

      {payload.highlight && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-400/25 dark:bg-emerald-400/8 dark:text-emerald-200">
          Lider actual: <strong>{payload.highlight.label}</strong> con{" "}
          <strong>{formatValue(payload.highlight.value)}</strong>
          {typeof payload.highlight.share === "number" ? (
            <span> ({payload.highlight.share}%)</span>
          ) : null}
          .
        </div>
      )}

      {showDetails && (
        <div className="flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
          <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
            tipo: {config.type}
          </span>
          <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
            metrica principal: {valueKey}
          </span>
          <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
            puntos: {chartData.length}
          </span>
        </div>
      )}
    </section>
  );
};

export default SmartChartRenderer;
