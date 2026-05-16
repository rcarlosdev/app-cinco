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

  return (
    <div className="space-y-3 rounded-[24px] border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
      <div className="text-sm font-semibold text-gray-950 dark:text-white">
        Como lo resolvi
      </div>
      <div className="flex flex-wrap gap-2">
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(Boolean(metadataUsed.governed_used), "emerald")}`}
        >
          Metadata gobernada {Boolean(metadataUsed.governed_used) ? "usada" : "no usada"}
        </span>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${pillClass(Boolean(fallbackUsed.shadow_fallback_used), "amber")}`}
        >
          Fallback sombreado {Boolean(fallbackUsed.shadow_fallback_used) ? "detectado" : "no"}
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
        {validationReason ? <div className="mt-1">{validationReason}</div> : null}
      </div>
    </div>
  );
};

export default ValidationStatusPanel;
