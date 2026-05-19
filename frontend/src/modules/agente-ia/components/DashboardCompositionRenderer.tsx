"use client";

import ChartRenderer from "@/modules/agente-ia/components/ChartRenderer";
import DataTable from "@/modules/agente-ia/components/DataTable";
import KPIGrid from "@/modules/agente-ia/components/KPIGrid";
import type { AgenteIAViewMode, DashboardTableTab } from "@/modules/agente-ia/types";
import type { NormalizedKPI, NormalizedTable } from "@/modules/programacion/ia-dev/chat/types";
import type {
  IADevDashboardComposition,
  IADevDashboardCompositionItem,
  IADevDashboardEvidence,
} from "@/services/ia-dev.service";

type DashboardCompositionRendererProps = {
  mode?: AgenteIAViewMode;
  composition: IADevDashboardComposition;
};

const asString = (value: unknown) =>
  typeof value === "string"
    ? value.trim()
    : typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : "";

const asNumber = (value: unknown) => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const asObject = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
};

const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const buildKpis = (items: IADevDashboardCompositionItem[] | undefined): NormalizedKPI[] =>
  (items || [])
    .map((item) => {
      const id = asString(item.id);
      const title = asString(item.title);
      const rawValue = item.value;
      if (!id || rawValue == null) return null;
      const numeric = asNumber(rawValue);
      return {
        key: id,
        label: title || toLabel(id),
        value: numeric ?? asString(rawValue),
        rawValue: numeric ?? asString(rawValue),
      } satisfies NormalizedKPI;
    })
    .filter((item): item is NormalizedKPI => item != null);

const buildTable = (tableValue: unknown): NormalizedTable | null => {
  const table = asObject(tableValue);
  if (!table) return null;
  const rows = asArray(table.rows).filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item),
  );
  if (rows.length === 0) return null;
  const exportRows = asArray(table.export_rows).filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item),
  );
  const columns = asArray(table.columns)
    .map((item) => asString(item))
    .filter(Boolean);
  return {
    columns: columns.length > 0 ? columns : Object.keys(rows[0] || {}),
    rows,
    exportRows: exportRows.length > 0 ? exportRows : rows,
    rowcount: asNumber(table.rowcount) ?? rows.length,
    totalRecords: asNumber(table.total_records) ?? asNumber(table.rowcount) ?? rows.length,
    returnedRecords: asNumber(table.returned_records) ?? rows.length,
    exportRecords:
      asNumber(table.export_records) ??
      (exportRows.length > 0 ? exportRows.length : rows.length),
    exportTruncated: Boolean(table.export_truncated),
    exportLimit: asNumber(table.export_limit) ?? 0,
    truncated:
      Boolean(table.truncated) ||
      (asNumber(table.total_records) ?? rows.length) >
        (asNumber(table.returned_records) ?? rows.length),
    limit: asNumber(table.limit) ?? 0,
    exportArtifact: null,
  };
};

const EvidenceBadge = ({ evidence }: { evidence?: IADevDashboardEvidence }) => {
  const source = asString(evidence?.source_block);
  const formula = asString(evidence?.formula);
  const rowCount = asNumber(evidence?.row_count_used);
  const confidence = asNumber(evidence?.confidence);
  const limitation = asString(evidence?.limitation);

  if (!source && !formula && rowCount == null && confidence == null && !limitation) {
    return null;
  }

  return (
    <div className="mt-3 rounded-2xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
      <span className="font-semibold text-gray-800 dark:text-gray-100">Evidencia:</span>{" "}
      {source ? `fuente ${source}` : "fuente no informada"}
      {formula ? `, formula ${formula}` : ""}
      {rowCount != null ? `, filas ${rowCount}` : ""}
      {confidence != null ? `, confianza ${confidence}` : ""}
      {limitation ? `. Limitacion: ${limitation}` : ""}
    </div>
  );
};

const SummaryCard = ({
  title,
  value,
}: {
  title: string;
  value: string;
}) => {
  if (!value) return null;
  return (
    <article className="rounded-3xl border border-gray-200 bg-white px-4 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-950">
      <p className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
        {title}
      </p>
      <p className="mt-2 text-sm leading-6 text-gray-700 dark:text-gray-200">
        {value}
      </p>
    </article>
  );
};

const findPrimaryValue = (row: Record<string, unknown>) => {
  for (const key of [
    "codigo",
    "movil",
    "familia",
    "dimension",
    "cedula",
    "bodega",
    "descripcion",
  ]) {
    const value = asString(row[key]);
    if (value) return value;
  }
  return "Sin dato";
};

const findSecondaryValue = (row: Record<string, unknown>, primaryValue: string) => {
  const candidates = [
    [asString(row.descripcion), "Descripcion"],
    [asString(row.nombre) || asString(row.empleado), "Persona"],
    [asString(row.familia), "Familia"],
    [asString(row.cedula), "Cedula"],
  ] as const;

  const match = candidates.find(([value]) => value && value !== primaryValue);
  return match ? { label: match[1], value: match[0] } : null;
};

const findValueMetric = (row: Record<string, unknown>) => {
  for (const [key, label] of [
    ["saldo_total", "Saldo"],
    ["saldo", "Saldo"],
    ["seriales_total", "Seriales"],
    ["registros", "Registros"],
  ] as const) {
    const value = asNumber(row[key]);
    if (value != null) {
      return { label, value };
    }
  }
  return null;
};

const buildRankingMeta = (row: Record<string, unknown>) =>
  Object.entries(row)
    .filter(([key, value]) => {
      if (value == null || asString(value) === "") return false;
      return ![
        "codigo",
        "movil",
        "familia",
        "dimension",
        "cedula",
        "bodega",
        "descripcion",
        "nombre",
        "empleado",
        "saldo_total",
        "saldo",
      ].includes(key);
    })
    .slice(0, 3);

const RankingCards = ({
  items,
}: {
  items: IADevDashboardCompositionItem[];
}) => {
  if (items.length === 0) return null;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {items.map((item) => {
        const rows = asArray(item.rows).filter(
          (candidate): candidate is Record<string, unknown> =>
            Boolean(candidate) &&
            typeof candidate === "object" &&
            !Array.isArray(candidate),
        );
        return (
          <article
            key={asString(item.id) || asString(item.title)}
            className="rounded-[28px] border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950"
          >
            <div className="text-sm font-semibold text-gray-950 dark:text-white">
              {asString(item.title)}
            </div>
            <div className="mt-3 space-y-2">
              {rows.slice(0, 5).map((row, index) => (
                <div
                  key={`${asString(item.id)}-${index}`}
                  className="rounded-3xl border border-gray-200 px-4 py-3 text-sm dark:border-gray-700"
                >
                  {(() => {
                    const primaryValue = findPrimaryValue(row);
                    const secondaryValue = findSecondaryValue(row, primaryValue);
                    const metric = findValueMetric(row);
                    const meta = buildRankingMeta(row);

                    return (
                      <div className="space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
                              Puesto {index + 1}
                            </div>
                            <div className="truncate text-base font-semibold text-gray-950 dark:text-white">
                              {primaryValue}
                            </div>
                            {secondaryValue ? (
                              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                                <span className="font-medium">
                                  {secondaryValue.label}:
                                </span>{" "}
                                {secondaryValue.value}
                              </div>
                            ) : null}
                          </div>
                          {metric ? (
                            <div className="rounded-2xl bg-sky-50 px-3 py-2 text-right dark:bg-sky-500/10">
                              <div className="text-[11px] font-semibold tracking-[0.14em] text-sky-700 uppercase dark:text-sky-200">
                                {metric.label}
                              </div>
                              <div className="text-lg font-semibold text-sky-900 dark:text-sky-100">
                                {metric.value.toLocaleString("es-CO")}
                              </div>
                            </div>
                          ) : null}
                        </div>

                        {meta.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {meta.map(([key, value]) => (
                              <span
                                key={key}
                                className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                              >
                                <span className="font-medium">{toLabel(key)}:</span>{" "}
                                {asString(value)}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  })()}
                </div>
              ))}
            </div>
            <EvidenceBadge evidence={item.evidence} />
          </article>
        );
      })}
    </div>
  );
};

const InsightList = ({
  title,
  items,
}: {
  title: string;
  items: IADevDashboardCompositionItem[];
}) => {
  if (items.length === 0) return null;
  return (
    <section className="space-y-3">
      <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
        {title}
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {items.map((item) => (
          <article
            key={asString(item.id) || asString(item.text)}
            className="rounded-3xl border border-gray-200 bg-white px-4 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-950"
          >
            {item.severity ? (
              <div className="text-[11px] font-semibold tracking-[0.18em] text-amber-700 uppercase dark:text-amber-200">
                {toLabel(asString(item.severity))}
              </div>
            ) : null}
            <p className="mt-2 text-sm leading-6 text-gray-700 dark:text-gray-200">
              {asString(item.text)}
            </p>
            <EvidenceBadge evidence={item.evidence} />
          </article>
        ))}
      </div>
    </section>
  );
};

const DashboardCompositionRenderer = ({
  mode = "user",
  composition,
}: DashboardCompositionRendererProps) => {
  const executiveSummary = asObject(composition.executive_summary) || {};
  const semanticBasis = asObject(composition.semantic_basis) || {};
  const primaryKpis = buildKpis(composition.primary_kpis);
  const rankings = (composition.ranked_breakdowns || []).filter(Boolean);
  const charts = (composition.recommended_charts || [])
    .map((item) => item.chart)
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
  const priorityTables = (composition.priority_tables || [])
    .map((item, index) => {
      const table = buildTable(item.table);
      if (!table) return null;
      return {
        id: asString(item.id) || `composition-table-${index}`,
        label: asString(item.title) || `Tabla ${index + 1}`,
        badges: [toLabel(asString(item.priority) || "prioridad")],
        table,
      } satisfies DashboardTableTab;
    })
    .filter((item): item is DashboardTableTab => item != null);
  const evidenceContract = asObject(composition.evidence_contract) || {};
  const businessInsights = (composition.business_insights || []).filter(Boolean);
  const operationalAlerts = (composition.operational_alerts || []).filter(Boolean);

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
          Consulta resuelta
        </div>
        <div className="grid gap-3 xl:grid-cols-2">
          <SummaryCard
            title="Solicitud"
            value={asString(executiveSummary.requested_question)}
          />
          <SummaryCard
            title="Filtro de familia"
            value={asString(executiveSummary.applied_family_filter) || "No informado"}
          />
          <SummaryCard
            title="Ruta resuelta"
            value={[
              asString(asObject(executiveSummary.resolved_route)?.capability),
              asString(asObject(executiveSummary.resolved_route)?.planner_route_hint),
              asString(asObject(executiveSummary.resolved_route)?.response_profile),
            ]
              .filter(Boolean)
              .join(" | ")}
          />
          <SummaryCard
            title="Detalle operativo"
            value="El drill-down operativo queda mas abajo con busqueda y exportacion CSV/XLSX."
          />
        </div>
      </section>

      {primaryKpis.length > 0 ? (
        <section className="space-y-3">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Kpis principales
          </div>
          <KPIGrid items={primaryKpis} />
        </section>
      ) : null}

      {rankings.length > 0 ? (
        <section className="space-y-3">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Rankings priorizados
          </div>
          <RankingCards items={rankings} />
        </section>
      ) : null}

      {charts.length > 0 ? (
        <section className="space-y-3">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Graficos recomendados
          </div>
          <ChartRenderer charts={charts} />
        </section>
      ) : null}

      {priorityTables.length > 0 ? (
        <section className="space-y-3">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Drill-down operativo
          </div>
          <DataTable mode={mode} tabs={priorityTables} />
        </section>
      ) : null}

      <InsightList title="Insights de negocio" items={businessInsights} />
      <InsightList title="Alertas operativas" items={operationalAlerts} />

      {mode === "dev" ? (
        <>
          <details className="rounded-[28px] border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950">
            <summary className="cursor-pointer text-sm font-semibold text-gray-950 dark:text-white">
              Ver contexto semantico
            </summary>
            <div className="mt-4 grid gap-3 xl:grid-cols-4">
              <SummaryCard title="Dominio" value={toLabel(asString(semanticBasis.domain) || "general")} />
              <SummaryCard title="Intencion" value={toLabel(asString(semanticBasis.intent) || "no informada")} />
              <SummaryCard title="Dimension" value={toLabel(asString(semanticBasis.grouping_dimension) || "no informada")} />
              <SummaryCard
                title="Filtros"
                value={Object.entries(asObject(semanticBasis.filters) || {})
                  .map(([key, value]) => `${toLabel(key)}: ${asString(value)}`)
                  .join(" | ")}
              />
              <SummaryCard
                title="Significado de saldo"
                value={asString(executiveSummary.saldo_definition)}
              />
            </div>
          </details>

          <details className="rounded-[28px] border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950">
            <summary className="cursor-pointer text-sm font-semibold text-gray-950 dark:text-white">
              Ver detalles tecnicos de evidencia
            </summary>
            <div className="mt-4 grid gap-3 xl:grid-cols-2">
              {Object.entries(evidenceContract).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-2xl border border-gray-200 px-3 py-2 text-sm text-gray-700 dark:border-gray-700 dark:text-gray-300"
                >
                  <span className="font-medium text-gray-950 dark:text-white">
                    {toLabel(key)}:
                  </span>{" "}
                  {Array.isArray(value)
                    ? value.map((item) => asString(item)).filter(Boolean).join(", ")
                    : typeof value === "object" && value != null
                      ? JSON.stringify(value)
                      : asString(value)}
                </div>
              ))}
            </div>
          </details>
        </>
      ) : null}
    </div>
  );
};

export default DashboardCompositionRenderer;
