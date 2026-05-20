"use client";

import { Copy } from "lucide-react";
import DashboardCompositionRenderer from "@/modules/agente-ia/components/DashboardCompositionRenderer";
import DashboardRenderer from "@/modules/agente-ia/components/DashboardRenderer";
import EvidenceSummaryPanel from "@/modules/agente-ia/components/EvidenceSummaryPanel";
import SemanticExplanationPanel from "@/modules/agente-ia/components/SemanticExplanationPanel";
import TaskStatusBadge from "@/modules/agente-ia/components/TaskStatusBadge";
import TaskTimeline from "@/modules/agente-ia/components/TaskTimeline";
import type {
  AgenteIAViewMode,
  DashboardBackgroundJob,
  DashboardSnapshot,
} from "@/modules/agente-ia/types";

type BusinessReportPanelProps = {
  mode?: AgenteIAViewMode;
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

const formatElapsed = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins <= 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
};

const formatCount = (value?: number) =>
  Number.isFinite(value) ? Number(value).toLocaleString("es-CO") : "-";

const buildUserBackgroundHighlights = (backgroundJob: DashboardBackgroundJob) => [
  [
    "Seriales revisados",
    formatCount(backgroundJob.serialsProcessed ?? backgroundJob.rowsProcessed),
  ],
  [
    "Seriales totales",
    formatCount(backgroundJob.serialsUniqueTotal ?? backgroundJob.totalEstimated),
  ],
  ["Encontrados", formatCount(backgroundJob.foundSoFar)],
  ["Pendientes", formatCount(backgroundJob.serialsPending ?? backgroundJob.notFoundSoFar)],
];

const buildRecommendedSteps = (snapshot: DashboardSnapshot) => {
  const steps: string[] = [];

  if (snapshot.clarificationQuestion) {
    steps.push("Responder la aclaracion para completar el analisis.");
  }

  if (snapshot.backgroundJob && snapshot.backgroundJob.status !== "completed") {
    steps.push("Esperar a que finalice el procesamiento para descargar el resultado completo.");
  }

  if (snapshot.widgets.some((widget) => widget.type === "table")) {
    steps.push("Revisar la tabla y exportar el detalle completo si necesitas compartirlo.");
  }

  if (snapshot.limitations.length > 0) {
    steps.push("Considerar las limitaciones antes de tomar una decision definitiva.");
  }

  if (steps.length === 0 && snapshot.summary.trim()) {
    steps.push("Usar este resultado como base para la siguiente consulta o decision.");
  }

  return steps.slice(0, 4);
};

const UserProgressCard = ({
  backgroundJob,
}: {
  backgroundJob: DashboardBackgroundJob;
}) => (
  <section className="rounded-[28px] border border-sky-200 bg-sky-50/85 p-5 shadow-sm dark:border-sky-500/20 dark:bg-sky-500/10">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="text-[11px] font-semibold tracking-[0.18em] text-sky-700 uppercase dark:text-sky-200">
          Progreso
        </div>
        <h3 className="mt-2 text-lg font-semibold text-sky-950 dark:text-sky-50">
          {backgroundJob.resultLabel || "Seguimos procesando tu solicitud"}
        </h3>
        <p className="mt-2 text-sm text-sky-900 dark:text-sky-100">
          {backgroundJob.phaseLabel || toLabel(backgroundJob.phase)}. El avance
          resume el trabajo total por etapas y los contadores muestran seriales
          revisados del archivo.
        </p>
      </div>
      <div className="rounded-3xl bg-white/90 px-4 py-3 text-right shadow-sm dark:bg-sky-950/40">
        <div className="text-[11px] font-semibold tracking-[0.18em] text-sky-700 uppercase dark:text-sky-200">
          Avance
        </div>
        <div className="mt-1 text-2xl font-semibold text-sky-950 dark:text-sky-50">
          {backgroundJob.percentage.toFixed(1)}%
        </div>
      </div>
    </div>

    <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/80 dark:bg-sky-950/40">
      <div
        className="h-full rounded-full bg-sky-500 transition-all"
        style={{ width: `${Math.max(0, Math.min(100, backgroundJob.percentage))}%` }}
      />
    </div>

    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {buildUserBackgroundHighlights(backgroundJob).map(([label, value]) => (
        <article
          key={label}
          className="rounded-3xl bg-white/85 px-4 py-4 shadow-sm dark:bg-sky-950/40"
        >
          <div className="text-[11px] font-semibold tracking-[0.18em] text-sky-700 uppercase dark:text-sky-200">
            {label}
          </div>
          <div className="mt-2 text-xl font-semibold text-sky-950 dark:text-sky-50">
            {value}
          </div>
        </article>
      ))}
    </div>

    <div className="mt-4 grid gap-2 text-xs text-sky-900 sm:grid-cols-2 dark:text-sky-100">
      <div>Archivo: {backgroundJob.attachmentName || "-"}</div>
      <div>Tiempo transcurrido: {formatElapsed(backgroundJob.elapsedSeconds)}</div>
      <div>
        ETA: {backgroundJob.etaSeconds ? formatElapsed(backgroundJob.etaSeconds) : "-"}
      </div>
      <div>
        Lote activo: {backgroundJob.activeChunk ?? backgroundJob.currentChunk ?? 0}
        {backgroundJob.totalChunks > 0 ? ` / ${backgroundJob.totalChunks}` : ""}
      </div>
    </div>
  </section>
);

const DevBackgroundRuntime = ({
  backgroundJob,
}: {
  backgroundJob: DashboardBackgroundJob;
}) => (
  <div className="mt-4 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-semibold">Background Runtime</span>
      <span className="rounded-full bg-white/80 px-2 py-1 text-xs dark:bg-sky-950/40">
        {toLabel(backgroundJob.status)}
      </span>
      {backgroundJob.backgroundRunId ? (
        <span className="rounded-full bg-white/80 px-2 py-1 text-xs dark:bg-sky-950/40">
          Job {backgroundJob.backgroundRunId}
        </span>
      ) : null}
    </div>
    <div className="mt-4">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-medium">
          {backgroundJob.phaseLabel || toLabel(backgroundJob.phase)}
        </span>
        <span>{backgroundJob.percentage.toFixed(1)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/70 dark:bg-sky-950/40">
        <div
          className="h-full rounded-full bg-sky-500 transition-all"
          style={{ width: `${Math.max(0, Math.min(100, backgroundJob.percentage))}%` }}
        />
      </div>
    </div>
    <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      {[
        ["Procesados etapa actual", formatCount(backgroundJob.stageSerialsProcessed)],
        ["Pendientes etapa actual", formatCount(backgroundJob.stageSerialsPending)],
        ["Encontrados globales", formatCount(backgroundJob.foundSoFar)],
        ["Pendientes globales", formatCount(backgroundJob.serialsPending ?? backgroundJob.notFoundSoFar)],
        ["MOVIL", formatCount(backgroundJob.movilSoFar)],
        ["Responsables", formatCount(backgroundJob.enrichedResponsibleSoFar)],
      ].map(([label, value]) => (
        <div
          key={label}
          className="rounded-2xl bg-white/70 px-3 py-3 text-xs dark:bg-sky-950/40"
        >
          <div className="text-[11px] uppercase tracking-[0.14em] text-sky-700/70 dark:text-sky-200/70">
            {label}
          </div>
          <div className="mt-1 text-lg font-semibold text-sky-950 dark:text-sky-50">
            {value}
          </div>
        </div>
      ))}
    </div>
    <div className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
      <div>Archivo: {backgroundJob.attachmentName || "-"}</div>
      <div>Filas archivo: {formatCount(backgroundJob.totalEstimated)}</div>
      <div>Seriales unicos: {formatCount(backgroundJob.serialsUniqueTotal)}</div>
      <div>Tiempo: {formatElapsed(backgroundJob.elapsedSeconds)}</div>
      <div>
        ETA: {backgroundJob.etaSeconds ? formatElapsed(backgroundJob.etaSeconds) : "-"}
      </div>
      <div>
        Chunk activo: {backgroundJob.activeChunk ?? backgroundJob.currentChunk ?? 0}
        {backgroundJob.totalChunks > 0 ? ` / ${backgroundJob.totalChunks}` : ""}
      </div>
      <div>Chunk size: {formatCount(backgroundJob.chunkSize)}</div>
      <div>
        Fallback normalizado:{" "}
        {backgroundJob.normalizedFallbackMode ? toLabel(backgroundJob.normalizedFallbackMode) : "-"}
      </div>
      <div>Base actual: {formatCount(backgroundJob.foundInBaseActual)}</div>
      <div>Asociados actual: {formatCount(backgroundJob.foundInAsociadosActual)}</div>
      <div>Solo historico: {formatCount(backgroundJob.foundInHistorico)}</div>
      <div>
        Etapa actual: {formatCount(backgroundJob.stageSerialsProcessed)} /{" "}
        {formatCount(backgroundJob.stageSerialsTotal)}
      </div>
      <div>Pendientes etapa actual: {formatCount(backgroundJob.stageSerialsPending)}</div>
      <div>Tabla actual: {backgroundJob.tableLabel || "-"}</div>
    </div>
    {backgroundJob.lastChunkMetrics ? (
      <div className="mt-3 rounded-xl bg-white/70 px-3 py-3 text-xs dark:bg-sky-950/40">
        <div className="font-medium">Ultimo chunk</div>
        <div className="mt-2 grid gap-2 sm:grid-cols-4">
          <div>Entrada: {formatCount(Number(backgroundJob.lastChunkMetrics.input_serials || 0))}</div>
          <div>Encontrados: {formatCount(Number(backgroundJob.lastChunkMetrics.found_serials || 0))}</div>
          <div>Queries: {formatCount(Number(backgroundJob.lastChunkMetrics.query_count || 0))}</div>
          <div>SQL ms: {formatCount(Number(backgroundJob.lastChunkMetrics.sql_time_ms || 0))}</div>
        </div>
      </div>
    ) : null}
    {backgroundJob.performanceMetrics ? (
      <div className="mt-3 rounded-xl bg-white/70 px-3 py-3 text-xs dark:bg-sky-950/40">
        <div className="font-medium">Performance runtime</div>
        <div className="mt-2 grid gap-2 sm:grid-cols-4">
          <div>
            Queries totales:{" "}
            {formatCount(Number(backgroundJob.performanceMetrics.query_count_total || 0))}
          </div>
          <div>
            SQL ms totales:{" "}
            {formatCount(Number(backgroundJob.performanceMetrics.sql_time_ms_total || 0))}
          </div>
          <div>
            Filas retornadas:{" "}
            {formatCount(Number(backgroundJob.performanceMetrics.rows_returned_total || 0))}
          </div>
          <div>
            Etapas medidas:{" "}
            {formatCount(
              Array.isArray(backgroundJob.performanceMetrics.stages)
                ? backgroundJob.performanceMetrics.stages.length
                : 0,
            )}
          </div>
        </div>
      </div>
    ) : null}
    {backgroundJob.status !== "completed" ? (
      <div className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-xs dark:bg-sky-950/40">
        {backgroundJob.resultLabel || "Resultado parcial / validacion en proceso"}.
        La etapa actual mide solo la fase en curso; el valor global resume todo el
        descarte acumulado. Este bloque muestra evidencia parcial y no reemplaza el
        informe final. El dashboard consolidado y la descarga completa se publican
        solo cuando el job llegue a completed.
      </div>
    ) : null}
    {backgroundJob.failureReason ? (
      <div className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-200">
        Motivo reportado: {backgroundJob.failureReason}
      </div>
    ) : null}
  </div>
);

const BusinessReportPanel = ({
  mode = "user",
  snapshot,
  onLoadDemo,
  onCopyReport,
}: BusinessReportPanelProps) => {
  const hasDashboardComposition = snapshot.dashboardComposition != null;
  const backgroundJob = snapshot.backgroundJob;
  const isBackgroundInProgress =
    backgroundJob != null && backgroundJob.status !== "completed";
  const shouldHideSemanticExplanation =
    isBackgroundInProgress &&
    snapshot.intent === "inventory_provider_serial_validation";
  const recommendedSteps = buildRecommendedSteps(snapshot);

  if (mode === "dev") {
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
            </div>
          </div>

          {backgroundJob ? <DevBackgroundRuntime backgroundJob={backgroundJob} /> : null}

          {snapshot.clarificationQuestion ? (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
              <div className="font-semibold">Aclaracion requerida</div>
              <div className="mt-1">{snapshot.clarificationQuestion}</div>
            </div>
          ) : null}
        </section>

        {!hasDashboardComposition &&
        snapshot.semanticExplanation &&
        !shouldHideSemanticExplanation ? (
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
            {isBackgroundInProgress ? (
              <div className="rounded-[24px] border border-dashed border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
                La validacion sigue en segundo plano. Este panel mostrara el dashboard
                final y el artifact CSV cuando el job llegue a completed.
              </div>
            ) : hasDashboardComposition && snapshot.dashboardComposition ? (
              <>
                <DashboardCompositionRenderer
                  mode="dev"
                  composition={snapshot.dashboardComposition}
                />
                <details className="rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
                  <summary className="cursor-pointer text-sm font-semibold text-gray-950 dark:text-white">
                    Ver evidencia tecnica avanzada
                  </summary>
                  <div className="mt-4 space-y-5">
                    {snapshot.semanticExplanation ? (
                      <SemanticExplanationPanel explanation={snapshot.semanticExplanation} />
                    ) : null}
                    <EvidenceSummaryPanel
                      evidence={snapshot.evidenceSummary}
                      limitations={snapshot.limitations}
                    />
                  </div>
                </details>
              </>
            ) : (
              <>
                <EvidenceSummaryPanel
                  evidence={snapshot.evidenceSummary}
                  limitations={snapshot.limitations}
                />
                <DashboardRenderer
                  mode="dev"
                  snapshot={snapshot}
                  onLoadDemo={onLoadDemo}
                />
              </>
            )}
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
  }

  return (
    <div className="space-y-5">
      <section className="rounded-[28px] border border-gray-200 bg-white/95 p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950/90">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
              Resumen
            </div>
            <h2 className="text-lg font-semibold text-gray-950 dark:text-white">
              {snapshot.executiveSummary}
            </h2>
            {snapshot.summary && snapshot.summary !== snapshot.executiveSummary ? (
              <p className="max-w-3xl text-sm leading-6 text-gray-600 dark:text-gray-300">
                {snapshot.summary}
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={onCopyReport}
            className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            <Copy size={13} />
            Copiar resumen
          </button>
        </div>
      </section>

      {backgroundJob ? <UserProgressCard backgroundJob={backgroundJob} /> : null}

      {snapshot.clarificationQuestion ? (
        <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-5 shadow-sm dark:border-amber-500/20 dark:bg-amber-500/10">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-amber-700 uppercase dark:text-amber-200">
            Aclaracion necesaria
          </div>
          <p className="mt-2 text-sm text-amber-900 dark:text-amber-100">
            {snapshot.clarificationQuestion}
          </p>
        </section>
      ) : null}

      {snapshot.limitations.length > 0 ? (
        <section className="rounded-[28px] border border-amber-200 bg-white p-5 shadow-sm dark:border-amber-500/20 dark:bg-gray-950">
          <div className="text-[11px] font-semibold tracking-[0.18em] text-amber-700 uppercase dark:text-amber-200">
            Hallazgos a tener en cuenta
          </div>
          <div className="mt-3 space-y-2 text-sm text-gray-700 dark:text-gray-200">
            {snapshot.limitations.map((item) => (
              <div key={item}>{item}</div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rounded-[28px] border border-gray-200 bg-white/95 p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950/90">
        <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
          Resultados
        </div>
        {isBackgroundInProgress ? (
          <div className="rounded-[24px] border border-dashed border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100">
            Cuando termine el procesamiento vas a ver aqui el resultado final, la
            tabla completa y la opcion de exportacion.
          </div>
        ) : hasDashboardComposition && snapshot.dashboardComposition ? (
          <DashboardCompositionRenderer mode="user" composition={snapshot.dashboardComposition} />
        ) : (
          <DashboardRenderer snapshot={snapshot} onLoadDemo={onLoadDemo} mode="user" />
        )}
      </section>

      {snapshot.evidenceSummary && Object.keys(snapshot.evidenceSummary).length > 0 ? (
        <section className="rounded-[28px] border border-gray-200 bg-white/95 p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950/90">
          <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Soporte
          </div>
          <EvidenceSummaryPanel
            evidence={snapshot.evidenceSummary}
            limitations={[]}
          />
        </section>
      ) : null}

      {recommendedSteps.length > 0 ? (
        <section className="rounded-[28px] border border-gray-200 bg-white/95 p-5 shadow-sm dark:border-gray-800 dark:bg-gray-950/90">
          <div className="mb-4 text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            Proximos pasos
          </div>
          <div className="space-y-2 text-sm text-gray-700 dark:text-gray-200">
            {recommendedSteps.map((step) => (
              <div key={step}>{step}</div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
};

export default BusinessReportPanel;
