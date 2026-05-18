"use client";

type ValidationStatusPanelProps = {
  validation: Record<string, unknown>;
  metadataUsed: Record<string, unknown>;
  fallbackUsed: Record<string, unknown>;
  approvalsStatus: Record<string, unknown>;
  backgroundStatus: Record<string, unknown>;
};

const toLabel = (value: string) =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const humanizeValidationReason = (
  validation: Record<string, unknown>,
  validationReason: string,
) => {
  const normalized = validationReason.trim().toLowerCase();
  if (!normalized) return "";
  if (normalized === "ok") {
    return "La consulta pasó las validaciones principales.";
  }
  if (Boolean(validation.needs_clarification)) {
    return "Hace falta una precisión para completar la consulta con seguridad.";
  }
  return "La consulta no pudo completarse por una validación interna.";
};

const pillClass = (active: boolean, tone: "emerald" | "amber" | "gray") => {
  if (!active) {
    return "border-gray-200 bg-gray-50 text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400";
  }

  if (tone === "emerald") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200";
  }

  if (tone === "amber") {
    return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200";
  }

  return "border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200";
};

const ValidationStatusPanel = ({
  validation,
  metadataUsed,
  fallbackUsed,
  approvalsStatus,
  backgroundStatus,
}: ValidationStatusPanelProps) => {
  const approvalState = String(approvalsStatus.status || "").trim();
  const backgroundState = String(backgroundStatus.status || "").trim();
  const validationReason = String(validation.reason || "").trim();
  const validationDetail = humanizeValidationReason(validation, validationReason);

  return (
    <div className="space-y-3 rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
      <div className="text-sm font-semibold text-gray-950 dark:text-white">
        Como lo resolvi
      </div>
      <div className="flex flex-wrap gap-2">
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(Boolean(metadataUsed.governed_used), "emerald")}`}
        >
          {Boolean(metadataUsed.governed_used)
            ? "Gobierno semántico validado"
            : "Gobierno semántico en revisión"}
        </span>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(Boolean(fallbackUsed.shadow_fallback_used), "amber")}`}
        >
          {Boolean(fallbackUsed.shadow_fallback_used)
            ? "Compatibilidad semántica temporal"
            : "Ruta validada"}
        </span>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(approvalState === "awaiting_approval", "amber")}`}
        >
          Approval {approvalState ? toLabel(approvalState) : "No aplica"}
        </span>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(Boolean(backgroundState), "gray")}`}
        >
          Background {backgroundState ? toLabel(backgroundState) : "Sync"}
        </span>
      </div>
      <div className="rounded-2xl bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-900 dark:text-gray-300">
        <div className="font-medium text-gray-950 dark:text-white">
          Validacion: {toLabel(String(validation.status || "pending"))}
        </div>
        {validationDetail ? <div className="mt-1">{validationDetail}</div> : null}
      </div>
    </div>
  );
};

export default ValidationStatusPanel;
