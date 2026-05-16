"use client";

import EvidenceSummaryPanel from "@/modules/agente-ia/components/EvidenceSummaryPanel";
import TaskTimeline from "@/modules/agente-ia/components/TaskTimeline";
import ValidationStatusPanel from "@/modules/agente-ia/components/ValidationStatusPanel";
import type { IADevSemanticExplanation } from "@/services/ia-dev.service";

type SemanticExplanationPanelProps = {
  explanation: IADevSemanticExplanation;
};

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const toEntries = (value: Record<string, unknown>) =>
  Object.entries(value)
    .map(([key, rawValue]) => {
      if (rawValue == null) return null;
      if (Array.isArray(rawValue)) {
        const normalized = rawValue
          .map((item) => String(item || "").trim())
          .filter(Boolean)
          .join(", ");
        return normalized ? [key, normalized] : null;
      }
      if (typeof rawValue === "object") return null;
      const normalized = String(rawValue).trim();
      return normalized ? [key, normalized] : null;
    })
    .filter((item): item is [string, string] => item != null);

const SemanticExplanationPanel = ({
  explanation,
}: SemanticExplanationPanelProps) => {
  const entity = explanation.entity || {};
  const filters = explanation.normalized_filters || {};
  const evidence = explanation.evidence_summary || {};
  const validation = explanation.validation_status || {};
  const metadataUsed = explanation.metadata_used || {};
  const fallbackUsed = explanation.fallback_used || {};
  const approvalsStatus = explanation.approvals_status || {};
  const backgroundStatus = explanation.background_status || {};
  const limitations = Array.isArray(explanation.limitations)
    ? explanation.limitations
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const agents = Array.isArray(explanation.agents_involved)
    ? explanation.agents_involved
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const timeline = Array.isArray(explanation.timeline) ? explanation.timeline : [];
  const clarification = (explanation.clarification_needed || {}) as Record<
    string,
    unknown
  >;

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="space-y-3 rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <div className="text-sm font-semibold text-gray-950 dark:text-white">
            Que entendi
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-gray-50 p-3 dark:bg-gray-900">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                Dominio
              </div>
              <div className="mt-1 text-sm font-medium text-gray-950 dark:text-white">
                {explanation.domain ? toLabel(explanation.domain) : "No identificado"}
              </div>
            </div>
            <div className="rounded-2xl bg-gray-50 p-3 dark:bg-gray-900">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                Intencion
              </div>
              <div className="mt-1 text-sm font-medium text-gray-950 dark:text-white">
                {explanation.intent ? toLabel(explanation.intent) : "No identificada"}
              </div>
            </div>
          </div>
          {explanation.understood_as ? (
            <div className="rounded-2xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
              {explanation.understood_as}
            </div>
          ) : null}
          {toEntries(entity).length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                Entidad y alcance
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {toEntries(entity).map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-2xl border border-gray-200 px-3 py-2 text-sm text-gray-700 dark:border-gray-700 dark:text-gray-300"
                  >
                    <span className="font-medium text-gray-950 dark:text-white">
                      {toLabel(key)}:
                    </span>{" "}
                    {value}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {toEntries(filters).length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                Filtros aplicados
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {toEntries(filters).map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-2xl border border-gray-200 px-3 py-2 text-sm text-gray-700 dark:border-gray-700 dark:text-gray-300"
                  >
                    <span className="font-medium text-gray-950 dark:text-white">
                      {toLabel(key)}:
                    </span>{" "}
                    {value}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        <section className="space-y-3 rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <div className="text-sm font-semibold text-gray-950 dark:text-white">
            Ruta usada
          </div>
          <div className="space-y-3 text-sm">
            <div>
              <span className="font-medium text-gray-950 dark:text-white">
                Capability:
              </span>{" "}
              <span className="text-gray-700 dark:text-gray-300">
                {explanation.selected_capability
                  ? toLabel(explanation.selected_capability)
                  : "No informada"}
              </span>
            </div>
            <div>
              <span className="font-medium text-gray-950 dark:text-white">
                Herramienta:
              </span>{" "}
              <span className="text-gray-700 dark:text-gray-300">
                {explanation.selected_tool
                  ? toLabel(explanation.selected_tool)
                  : "No informada"}
              </span>
            </div>
            <div>
              <span className="font-medium text-gray-950 dark:text-white">
                Ruta:
              </span>{" "}
              <span className="text-gray-700 dark:text-gray-300">
                {explanation.planner_route_hint
                  ? toLabel(explanation.planner_route_hint)
                  : "No informada"}
              </span>
            </div>
            {agents.length > 0 ? (
              <div>
                <span className="font-medium text-gray-950 dark:text-white">
                  Agentes:
                </span>{" "}
                <span className="text-gray-700 dark:text-gray-300">
                  {agents.map((agent) => toLabel(agent)).join(", ")}
                </span>
              </div>
            ) : null}
          </div>
          {Boolean(clarification.required) ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
              <div className="font-semibold">Falta aclaracion</div>
              <div className="mt-1">
                {String(clarification.question || "Hace falta una precision para continuar.")}
              </div>
            </div>
          ) : null}
        </section>
      </div>

      <ValidationStatusPanel
        validation={validation}
        metadataUsed={metadataUsed}
        fallbackUsed={fallbackUsed}
        approvalsStatus={approvalsStatus}
        backgroundStatus={backgroundStatus}
      />

      <EvidenceSummaryPanel evidence={evidence} limitations={limitations} />

      <TaskTimeline steps={timeline} />
    </div>
  );
};

export default SemanticExplanationPanel;
