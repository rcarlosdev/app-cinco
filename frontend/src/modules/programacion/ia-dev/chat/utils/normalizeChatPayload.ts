import type {
  IADevAction,
  IADevChartPayload,
  IADevChatResponse,
} from "@/services/ia-dev.service";
import type {
  NormalizedAssistantPayload,
  NormalizedHighlight,
  NormalizedKPI,
  NormalizedTable,
} from "@/modules/programacion/ia-dev/chat/types";

const asObject = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
};

const asArray = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];

const asString = (value: unknown): string => {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return "";
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toLabel = (value: string) => {
  const raw = value.replace(/[_-]+/g, " ").trim();
  if (!raw) return value;
  return raw
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const isValidChart = (chart: unknown): chart is IADevChartPayload => {
  const candidate = asObject(chart);
  if (!candidate) return false;
  return Boolean(
    candidate.type ||
    (Array.isArray(candidate.data) && candidate.data.length > 0) ||
    (Array.isArray(candidate.points) && candidate.points.length > 0) ||
    (Array.isArray(candidate.labels) && candidate.labels.length > 0),
  );
};

const normalizeChartValue = (value: unknown): unknown => {
  if (Array.isArray(value))
    return value.map((item) => normalizeChartValue(item));
  if (!value || typeof value !== "object") return value;

  const source = value as Record<string, unknown>;
  return Object.keys(source)
    .filter((key) => source[key] !== undefined && key !== "meta")
    .sort()
    .reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = normalizeChartValue(source[key]);
      return acc;
    }, {});
};

const getChartFingerprint = (chart: IADevChartPayload): string => {
  try {
    return JSON.stringify(
      normalizeChartValue({
        type: chart.type,
        x_key: chart.x_key,
        y_key: chart.y_key,
        labels: chart.labels,
        series: chart.series,
        points: chart.points,
        data: chart.data,
      }),
    );
  } catch {
    return String(chart.title || chart.type || Math.random());
  }
};

const dedupeCharts = (
  charts: Array<IADevChartPayload | null | undefined>,
): IADevChartPayload[] => {
  const seen = new Set<string>();
  return charts.filter((chart): chart is IADevChartPayload => {
    if (!chart) return false;
    const fingerprint = getChartFingerprint(chart);
    if (seen.has(fingerprint)) return false;
    seen.add(fingerprint);
    return true;
  });
};

const normalizeKpis = (value: unknown): NormalizedKPI[] => {
  const source = asObject(value);
  if (!source) return [];

  return Object.entries(source)
    .map(([key, rawValue]) => {
      if (
        rawValue == null ||
        (typeof rawValue !== "number" &&
          typeof rawValue !== "string" &&
          typeof rawValue !== "boolean")
      ) {
        return null;
      }
      const numeric = asNumber(rawValue);
      return {
        key,
        label: toLabel(key),
        value: numeric ?? String(rawValue),
        rawValue: numeric ?? String(rawValue),
      } satisfies NormalizedKPI;
    })
    .filter((item): item is NormalizedKPI => item != null);
};

const normalizeInsights = (value: unknown): string[] => {
  return asArray(value)
    .map((item) => asString(item))
    .filter(Boolean);
};

const normalizeLabels = (value: unknown): string[] => {
  return asArray(value)
    .map((item) => asString(item))
    .filter(Boolean);
};

const normalizeSeries = (value: unknown): number[] => {
  return asArray(value)
    .map((item) => asNumber(item))
    .filter((item): item is number => item != null);
};

const normalizeTable = (value: unknown): NormalizedTable | null => {
  const source = asObject(value);
  if (!source) return null;

  const rows = asArray(source.rows).filter(
    (row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === "object",
  );

  if (rows.length === 0) return null;

  const exportRows = asArray(source.export_rows).filter(
    (row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === "object",
  );

  const columns = asArray(source.columns)
    .map((column) => asString(column))
    .filter(Boolean);

  const inferredColumns = columns.length > 0 ? columns : Object.keys(rows[0]);
  const totalRecords =
    asNumber(source.total_records) ?? asNumber(source.rowcount) ?? rows.length;
  const returnedRecords = asNumber(source.returned_records) ?? rows.length;

  return {
    columns: inferredColumns,
    rows,
    exportRows: exportRows.length > 0 ? exportRows : rows,
    rowcount: totalRecords,
    totalRecords,
    returnedRecords,
    exportRecords:
      asNumber(source.export_records) ??
      (exportRows.length > 0 ? exportRows.length : rows.length),
    exportTruncated: Boolean(source.export_truncated),
    exportLimit: asNumber(source.export_limit) ?? 0,
    truncated: Boolean(source.truncated) || totalRecords > returnedRecords,
    limit: asNumber(source.limit) ?? 0,
  };
};

const rebuildChartFromTable = (
  table: NormalizedTable | null,
  title: string,
  meta: Record<string, unknown>,
): IADevChartPayload | null => {
  if (!table || table.rows.length === 0) return null;
  const sample = table.rows[0];
  const keys = Object.keys(sample);
  const categoryKey =
    keys.find((key) => typeof sample[key] === "string") || keys[0];
  const metricKeys = keys.filter(
    (key) => key !== categoryKey && asNumber(sample[key]) != null,
  );
  if (!categoryKey || metricKeys.length === 0) return null;

  return {
    engine: "amcharts5",
    chart_library: "amcharts5",
    type: "bar",
    title,
    x_key: categoryKey,
    series: metricKeys.map((key) => ({ name: toLabel(key), value_key: key })),
    data: table.rows,
    meta,
  };
};

const rebuildChartFromLabelsSeries = (
  labels: string[],
  series: number[],
  title: string,
  meta: Record<string, unknown>,
): IADevChartPayload | null => {
  if (labels.length === 0 || series.length === 0) return null;
  return {
    engine: "amcharts5",
    chart_library: "amcharts5",
    type: "bar",
    title,
    labels,
    series,
    meta,
  };
};

const getChartFromActions = (
  actions: IADevAction[] | undefined,
): IADevChartPayload | null => {
  const renderChartAction = (actions || []).find(
    (action) => action.type === "render_chart",
  );
  if (!renderChartAction) return null;
  return isValidChart(renderChartAction.payload?.chart)
    ? renderChartAction.payload?.chart
    : null;
};

const findDominantHighlight = (
  labels: string[],
  series: number[],
  table: NormalizedTable | null,
): NormalizedHighlight | null => {
  if (table && table.rows.length > 0) {
    const firstRow = table.rows[0];
    const labelKey =
      table.columns.find((column) => typeof firstRow[column] === "string") ||
      table.columns[0];
    const numericKey =
      table.columns.find(
        (column) => asNumber(firstRow[column]) != null && column !== labelKey,
      ) || "";
    if (labelKey && numericKey) {
      const values = table.rows
        .map((row) => asNumber(row[numericKey]))
        .filter((value): value is number => value != null);
      const total = values.reduce((acc, current) => acc + current, 0);
      const topValue = asNumber(firstRow[numericKey]) ?? 0;
      const topLabel = asString(firstRow[labelKey]) || "Categoria principal";
      return {
        label: topLabel,
        value: topValue,
        share:
          total > 0 ? Number(((topValue / total) * 100).toFixed(1)) : undefined,
      };
    }
  }

  if (labels.length > 0 && series.length > 0) {
    const total = series.reduce((acc, current) => acc + current, 0);
    const topValue = Math.max(...series);
    const topIndex = series.findIndex((item) => item === topValue);
    if (topIndex >= 0) {
      return {
        label: labels[topIndex] || "Categoria principal",
        value: topValue,
        share:
          total > 0 ? Number(((topValue / total) * 100).toFixed(1)) : undefined,
      };
    }
  }

  return null;
};

export const normalizeChatPayload = (
  response: Partial<IADevChatResponse> | null | undefined,
): NormalizedAssistantPayload => {
  const fallbackSummary = asString(response?.reply);
  const data = asObject(response?.data) || {};
  const envelope = asObject(response?.response_envelope) || {};
  const runtime = asObject(asObject(response?.data_sources)?.runtime) || {};

  const kpis = normalizeKpis(
    data.kpis ?? (response as Record<string, unknown> | undefined)?.kpis,
  );
  const insights = normalizeInsights(
    data.insights ??
      (response as Record<string, unknown> | undefined)?.insights,
  );
  const labels = normalizeLabels(
    data.labels ?? (response as Record<string, unknown> | undefined)?.labels,
  );
  const series = normalizeSeries(
    data.series ?? (response as Record<string, unknown> | undefined)?.series,
  );
  const table = normalizeTable(
    data.table ?? (response as Record<string, unknown> | undefined)?.table,
  );
  const extraTables = asArray(
    data.extra_tables ??
      (response as Record<string, unknown> | undefined)?.extra_tables,
  )
    .map((item) => normalizeTable(item))
    .filter((item): item is NonNullable<typeof item> => item != null);

  const rawChart = isValidChart(data.chart)
    ? data.chart
    : isValidChart((response as Record<string, unknown> | undefined)?.chart)
      ? ((response as Record<string, unknown>).chart as IADevChartPayload)
      : null;

  const rawCharts = asArray(
    data.charts ?? (response as Record<string, unknown> | undefined)?.charts,
  ).filter(isValidChart);

  const meta: Record<string, unknown> = {
    response_envelope: envelope,
    runtime,
    ...(asObject(data.cause_generation_meta) || {}),
    ...(asObject(data.meta) || {}),
    ...(rawChart?.meta && typeof rawChart.meta === "object"
      ? (rawChart.meta as Record<string, unknown>)
      : {}),
  };

  const summary =
    fallbackSummary ||
    (insights.length > 0
      ? insights[0]
      : "Analisis completado sin resumen textual.");

  const title =
    asString(rawChart?.title) ||
    asString(meta.title) ||
    (summary.length > 0 ? summary.slice(0, 72) : "Analisis de datos");

  const chartFromActions = getChartFromActions(response?.actions);
  const rebuiltChart =
    rebuildChartFromTable(table, title, meta) ||
    rebuildChartFromLabelsSeries(labels, series, title, meta);

  const charts = dedupeCharts([
    rawChart,
    ...rawCharts,
    chartFromActions,
    rebuiltChart,
  ]);
  const chart = charts[0] ?? null;

  const hasStructuredContent = Boolean(
    kpis.length ||
    insights.length ||
    table?.rows.length ||
    extraTables.length ||
    chart ||
    charts.length ||
    (labels.length && series.length),
  );

  const kind: NormalizedAssistantPayload["kind"] =
    summary.toLowerCase().includes("error") || response == null
      ? "error_response"
      : hasStructuredContent
        ? "analytics_response"
        : "text_response";

  return {
    kind,
    summary,
    kpis,
    insights,
    chart,
    charts,
    table,
    extraTables,
    labels,
    series,
    meta,
    hasStructuredContent,
    highlight: findDominantHighlight(labels, series, table),
    route:
      (asObject(envelope.route) || asObject(runtime.route) || {}) as Record<
        string,
        unknown
      >,
    fallbackUsed:
      (asObject(envelope.fallback_used) ||
        asObject(runtime.fallback_used) ||
        {}) as Record<string, unknown>,
    legacyUsed:
      Boolean(envelope.legacy_used) || Boolean(runtime.legacy_used),
    contractPolicyApplied:
      (asObject(envelope.contract_policy_applied) ||
        asObject(runtime.contract_policy_applied) ||
        {}) as Record<string, unknown>,
    needsClarification: Boolean(envelope.needs_clarification),
    blockReason:
      asString(envelope.block_reason) || asString(runtime.block_reason),
    progressSource:
      asString(envelope.progress_source) ||
      asString(runtime.progress_source) ||
      "backend",
  };
};
