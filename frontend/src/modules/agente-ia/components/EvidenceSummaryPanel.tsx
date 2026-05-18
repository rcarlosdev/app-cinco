"use client";

type EvidenceSummaryPanelProps = {
  evidence: Record<string, unknown>;
  limitations: string[];
};

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const EvidenceSummaryPanel = ({
  evidence,
  limitations,
}: EvidenceSummaryPanelProps) => {
  const rowcount = Number(evidence.rowcount || 0);
  const extraTableCount = Number(evidence.extra_table_count || 0);
  const responseProfile = String(evidence.response_profile || "").trim();
  const sources = Array.isArray(evidence.sources)
    ? evidence.sources
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];

  return (
    <div className="space-y-3 rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
      <div className="text-sm font-semibold text-gray-950 dark:text-white">
        Evidencia
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl bg-gray-50 p-3 dark:bg-gray-900">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
            Filas
          </div>
          <div className="mt-1 text-lg font-semibold text-gray-950 dark:text-white">
            {rowcount}
          </div>
        </div>
        <div className="rounded-2xl bg-gray-50 p-3 dark:bg-gray-900">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
            Bloques
          </div>
          <div className="mt-1 text-lg font-semibold text-gray-950 dark:text-white">
            {extraTableCount + 1}
          </div>
        </div>
        <div className="rounded-2xl bg-gray-50 p-3 dark:bg-gray-900">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
            Perfil
          </div>
          <div className="mt-1 text-sm font-medium text-gray-950 dark:text-white">
            {responseProfile ? toLabel(responseProfile) : "No informado"}
          </div>
        </div>
      </div>
      {sources.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {sources.map((source) => (
            <span
              key={source}
              className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
            >
              {toLabel(source)}
            </span>
          ))}
        </div>
      ) : null}
      {limitations.length > 0 ? (
        <div className="space-y-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
          <div className="font-semibold">Limitaciones o aclaraciones</div>
          {limitations.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default EvidenceSummaryPanel;
