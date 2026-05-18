"use client";

import type { DashboardSnapshot } from "@/modules/agente-ia/types";

type ToolsPanelProps = {
  snapshot: DashboardSnapshot;
};

const dominiosDisponibles = [
  "inventario_logistica",
  "empleados",
  "ausentismo",
];

const ToolsPanel = ({ snapshot }: ToolsPanelProps) => {
  const toolExecutionItems =
    snapshot.toolsUsed.length > 0
      ? snapshot.toolsUsed
      : [
          {
            key: "tool-idle",
            label: "Sin herramienta visible",
            detail: "La consulta actual no expone una herramienta saneada.",
          },
        ];

  return (
    <div className="space-y-4 text-sm">
      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="text-xs font-semibold tracking-[0.16em] text-gray-500 uppercase dark:text-gray-400">
          Capacidades usadas
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {snapshot.capabilitiesUsed.length > 0 ? (
            snapshot.capabilitiesUsed.map((item) => (
              <span
                key={item.key}
                className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200"
              >
                {item.label}
              </span>
            ))
          ) : (
            <span className="text-gray-500 dark:text-gray-400">
              Aun no se ha seleccionado una capacidad visible.
            </span>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="text-xs font-semibold tracking-[0.16em] text-gray-500 uppercase dark:text-gray-400">
          Dominios disponibles
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {dominiosDisponibles.map((domain) => (
            <span
              key={domain}
              className={`rounded-full border px-3 py-1 text-xs ${
                snapshot.domain === domain
                  ? "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-200"
                  : "border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200"
              }`}
            >
              {domain.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="text-xs font-semibold tracking-[0.16em] text-gray-500 uppercase dark:text-gray-400">
          Estado operativo
        </div>
        <div className="mt-3 space-y-2">
          <div className="rounded-2xl border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-950">
            <div className="font-medium text-gray-900 dark:text-white">
              Ejecucion de herramientas
            </div>
            <div className="mt-2 space-y-2 text-xs text-gray-600 dark:text-gray-300">
              {toolExecutionItems.map((item) => (
                <div key={item.key}>
                  <div>{item.label}</div>
                  {item.detail ? <div className="text-gray-500">{item.detail}</div> : null}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-950">
            <div className="font-medium text-gray-900 dark:text-white">
              Approvals
            </div>
            <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">
              {snapshot.approvals.length > 0
                ? snapshot.approvals.map((item) => item.label).join(", ")
                : "No hay approvals pendientes visibles."}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-950">
            <div className="font-medium text-gray-900 dark:text-white">
              Background runs
            </div>
            <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">
              {snapshot.backgroundRuns.length > 0
                ? snapshot.backgroundRuns.map((item) => item.label).join(", ")
                : "No hay corridas de fondo visibles para esta consulta."}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ToolsPanel;
