"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, Loader2, X } from "lucide-react";
import type {
  IADevChartPayload,
  IADevChartSeriesMeta,
} from "@/services/ia-dev.service";

type IADevChartPanelProps = {
  chart: IADevChartPayload | null;
  onClose?: () => void;
  embedded?: boolean;
  showDetails?: boolean;
  showHeader?: boolean;
};

type NormalizedChartData = {
  type: "bar" | "line" | "area";
  title: string;
  rows: Array<{ category: string; value: number }>;
};

const normalizeChartType = (type?: string): "bar" | "line" | "area" => {
  const normalized = String(type || "")
    .trim()
    .toLowerCase();
  if (normalized === "line") return "line";
  if (normalized === "area") return "area";
  return "bar";
};

const normalizeNumericString = (value: string): string => {
  let text = value.trim();
  if (!text) return "";
  text = text.replace(/[^\d,.\-]/g, "");
  if (!text || text === "-" || text === "." || text === ",") return "";

  const hasComma = text.includes(",");
  const hasDot = text.includes(".");

  if (hasComma && hasDot) {
    const lastComma = text.lastIndexOf(",");
    const lastDot = text.lastIndexOf(".");
    if (lastComma > lastDot) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else {
      text = text.replace(/,/g, "");
    }
    return text;
  }

  if (hasComma) {
    if (/,\d{1,2}$/.test(text)) {
      return text.replace(",", ".");
    }
    return text.replace(/,/g, "");
  }

  if (hasDot) {
    const dotCount = (text.match(/\./g) || []).length;
    if (dotCount > 1) {
      const lastDot = text.lastIndexOf(".");
      const intPart = text.slice(0, lastDot).replace(/\./g, "");
      const decimalPart = text.slice(lastDot + 1);
      return `${intPart}.${decimalPart}`;
    }
  }

  return text;
};

const asNumberOrNull = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const normalized = normalizeNumericString(value);
    if (!normalized) return null;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const asNumber = (value: unknown): number => {
  return asNumberOrNull(value) ?? 0;
};

const resolveBestYKey = (
  rows: Array<Record<string, unknown>>,
  xKey: string,
  preferredYKey: string,
): string => {
  if (rows.length === 0) return preferredYKey;
  const keys = Array.from(
    new Set(
      rows.flatMap((row) => Object.keys(row)).filter((key) => key !== xKey),
    ),
  );

  const scoreKey = (key: string) => {
    let numericCount = 0;
    let nonZeroCount = 0;
    for (const row of rows) {
      const numeric = asNumberOrNull(row[key]);
      if (numeric == null) continue;
      numericCount += 1;
      if (numeric !== 0) nonZeroCount += 1;
    }
    return { key, numericCount, nonZeroCount };
  };

  const preferredScore = scoreKey(preferredYKey);
  if (preferredScore.numericCount > 0 && preferredScore.nonZeroCount > 0) {
    return preferredYKey;
  }

  const ranked = keys
    .map(scoreKey)
    .sort(
      (a, b) =>
        b.nonZeroCount - a.nonZeroCount || b.numericCount - a.numericCount,
    );

  if (ranked.length === 0) return preferredYKey;
  if (ranked[0].numericCount === 0) return preferredYKey;
  return ranked[0].key;
};

const normalizeRows = (
  chart: IADevChartPayload,
): Array<{ category: string; value: number }> => {
  if (Array.isArray(chart.points) && chart.points.length > 0) {
    return chart.points.map((item) => ({
      category: String(item.x ?? ""),
      value: asNumber(item.y),
    }));
  }

  if (
    Array.isArray(chart.labels) &&
    chart.labels.length > 0 &&
    Array.isArray(chart.series) &&
    chart.series.length > 0 &&
    typeof chart.series[0] === "number"
  ) {
    const values = chart.series as number[];
    return chart.labels.map((label, index) => ({
      category: String(label || ""),
      value: asNumber(values[index]),
    }));
  }

  if (Array.isArray(chart.data) && chart.data.length > 0) {
    const xKey = String(chart.x_key || "categoria");
    const seriesMeta = Array.isArray(chart.series)
      ? (chart.series[0] as IADevChartSeriesMeta)
      : null;
    const preferredYKey =
      String(seriesMeta?.value_key || chart.y_key || "valor").trim() || "valor";
    const yKey = resolveBestYKey(chart.data, xKey, preferredYKey);
    return chart.data.map((item) => ({
      category: String(item?.[xKey] ?? ""),
      value: asNumber(item?.[yKey]),
    }));
  }

  return [];
};

const normalizeChart = (
  chart: IADevChartPayload | null,
): NormalizedChartData | null => {
  if (!chart) return null;
  const rows = normalizeRows(chart).filter((item) => item.category);
  if (rows.length === 0) return null;
  return {
    type: normalizeChartType(chart.type),
    title: String(chart.title || "Visualización de resultados"),
    rows,
  };
};

const IADevChartPanel = ({
  chart,
  onClose,
  embedded = false,
  showDetails = true,
  showHeader = true,
}: IADevChartPanelProps) => {
  const normalized = useMemo(() => normalizeChart(chart), [chart]);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [renderError, setRenderError] = useState("");

  useEffect(() => {
    if (!normalized || !chartRef.current) return;
    let root: any = null;
    let mounted = true;

    const render = async () => {
      try {
        setIsRendering(true);
        setRenderError("");

        const am5 = await import("@amcharts/amcharts5");
        const am5xy = await import("@amcharts/amcharts5/xy");
        const am5themesAnimated =
          await import("@amcharts/amcharts5/themes/Animated");

        if (!mounted || !chartRef.current) return;

        root = am5.Root.new(chartRef.current);
        root.setThemes([am5themesAnimated.default.new(root)]);

        const chartRoot = root.container.children.push(
          am5xy.XYChart.new(root, {
            panX: false,
            panY: false,
            wheelX: "none",
            wheelY: "none",
            layout: root.verticalLayout,
          }),
        );

        const xRenderer = am5xy.AxisRendererX.new(root, {
          minGridDistance: 24,
        });
        xRenderer.labels.template.setAll({
          oversizedBehavior: "truncate",
          maxWidth: 120,
          fill: am5.color(0x94a3b8),
          fontSize: 11,
        });
        xRenderer.grid.template.setAll({ strokeOpacity: 0.08 });

        const xAxis = chartRoot.xAxes.push(
          am5xy.CategoryAxis.new(root, {
            categoryField: "category",
            renderer: xRenderer,
          }),
        );

        const yRenderer = am5xy.AxisRendererY.new(root, {});
        yRenderer.labels.template.setAll({
          fill: am5.color(0x94a3b8),
          fontSize: 11,
        });
        yRenderer.grid.template.setAll({ strokeOpacity: 0.08 });

        const yAxis = chartRoot.yAxes.push(
          am5xy.ValueAxis.new(root, {
            renderer: yRenderer,
            min: 0,
          }),
        );

        let series: any;

        if (normalized.type === "line" || normalized.type === "area") {
          const lineSeries = am5xy.LineSeries.new(root, {
            name: "Total",
            xAxis,
            yAxis,
            valueYField: "value",
            categoryXField: "category",
            stroke: am5.color(0x2563eb),
            fill: am5.color(0x2563eb),
            tooltip: am5.Tooltip.new(root, {
              labelText: "{categoryX}: {valueY}",
            }),
          });
          lineSeries.strokes.template.setAll({ strokeWidth: 2.5 });
          if (normalized.type === "area") {
            lineSeries.fills.template.setAll({
              visible: true,
              fillOpacity: 0.25,
            });
          }
          series = lineSeries;
        } else {
          const columnSeries = am5xy.ColumnSeries.new(root, {
            name: "Total",
            xAxis,
            yAxis,
            valueYField: "value",
            categoryXField: "category",
            fill: am5.color(0x2563eb),
            stroke: am5.color(0x1d4ed8),
            tooltip: am5.Tooltip.new(root, {
              labelText: "{categoryX}: {valueY}",
            }),
          });
          columnSeries.columns.template.setAll({
            cornerRadiusTL: 6,
            cornerRadiusTR: 6,
            strokeOpacity: 0,
            width: am5.percent(70),
          });
          series = columnSeries;
        }

        chartRoot.series.push(series);
        xAxis.data.setAll(normalized.rows);
        series.data.setAll(normalized.rows);
      } catch {
        if (!mounted) return;
        setRenderError("No se pudo renderizar la gráfica en este momento.");
      } finally {
        if (mounted) setIsRendering(false);
      }
    };

    void render();

    return () => {
      mounted = false;
      if (root) {
        root.dispose();
      }
    };
  }, [normalized]);

  if (!chart) return null;

  return (
    <div
      className={`rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900/60 ${
        embedded ? "" : "mx-3 mt-3"
      }`}
    >
      <div
        className={`mb-2 items-start justify-between gap-2 ${
          showHeader ? "flex" : "hidden"
        }`}
      >
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            <BarChart3 size={13} />
            Visualización
          </p>
          <p className="truncate text-sm font-semibold text-gray-800 dark:text-gray-100">
            {normalized?.title || chart.title || "Gráfica de resultados"}
          </p>
        </div>
        {!embedded && (
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-gray-200 text-gray-500 hover:bg-white dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
            title="Cerrar visualización"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {renderError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300">
          {renderError}
        </div>
      ) : (
        <>
          <div className="relative h-56 w-full overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-950">
            {isRendering && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 text-gray-600 dark:bg-gray-950/70 dark:text-gray-300">
                <Loader2 size={16} className="animate-spin" />
              </div>
            )}
            <div ref={chartRef} className="h-full w-full" />
          </div>
          {showDetails && (
            <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
              <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
                amCharts 5
              </span>
              <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
                tipo: {normalized?.type || "bar"}
              </span>
              <span className="rounded-full border border-gray-300 px-2 py-0.5 dark:border-gray-700">
                puntos: {normalized?.rows.length || 0}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default IADevChartPanel;
