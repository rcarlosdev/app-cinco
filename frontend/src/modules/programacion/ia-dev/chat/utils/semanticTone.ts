export type SemanticTone = "danger" | "warning" | "success" | "neutral";

type ToneInput = {
  label?: unknown;
  value?: unknown;
  row?: Record<string, unknown>;
};

const DAY_MS = 24 * 60 * 60 * 1000;
const UPCOMING_DAYS = 30;

const normalizeText = (value: unknown): string =>
  String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

const parseDate = (value: unknown): Date | null => {
  if (value instanceof Date && Number.isFinite(value.getTime())) return value;
  if (typeof value !== "string") return null;

  const text = value.trim();
  if (!text) return null;

  const isoMatch = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  const localMatch = text.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})/);
  const parts = isoMatch
    ? [Number(isoMatch[1]), Number(isoMatch[2]), Number(isoMatch[3])]
    : localMatch
      ? [Number(localMatch[3]), Number(localMatch[2]), Number(localMatch[1])]
      : null;

  if (!parts) return null;
  const [year, month, day] = parts;
  const date = new Date(year, month - 1, day);
  return Number.isFinite(date.getTime()) ? date : null;
};

const isDateContext = (label: string): boolean =>
  /(fecha|vencimiento|vigencia|vence|certificado|caducidad|expira)/.test(label);

const dateTone = (value: unknown): SemanticTone | null => {
  const date = parseDate(value);
  if (!date) return null;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  const diffDays = Math.ceil((date.getTime() - today.getTime()) / DAY_MS);
  if (diffDays < 0) return "danger";
  if (diffDays <= UPCOMING_DAYS) return "warning";
  return "success";
};

const numericValue = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const parsed = Number(value.replace(/[^\d,.\-]/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
};

export const getSemanticTone = ({
  label,
  value,
  row,
}: ToneInput): SemanticTone => {
  const labelText = normalizeText(label);
  const valueText = normalizeText(value);
  const combined = `${labelText} ${valueText}`;
  const numeric = numericValue(value);

  if (isDateContext(labelText)) {
    const tone = dateTone(value);
    if (tone) return tone;
  }

  if (
    /(proxim|por vencer|vence pronto|pendiente|advertencia|warning)/.test(
      combined,
    )
  ) {
    if (numeric === 0) return "success";
    return "warning";
  }

  if (
    /(vencid|expirad|caducad|inactivo|negativ|fallid|error|incumpl|critico|riesgo|bloquead)/.test(
      combined,
    )
  ) {
    if (numeric === 0) return "success";
    return "danger";
  }

  if (
    /(vigente|activo|positiv|aprobado|cumplid|correcto|ok|success|exitos)/.test(
      combined,
    )
  ) {
    return "success";
  }

  if (numeric != null && numeric < 0) return "danger";

  if (row) {
    const rowText = normalizeText(Object.values(row).join(" "));
    if (/(vencid|expirad|caducad|negativ|fallid|error|incumpl)/.test(rowText)) {
      return "danger";
    }
    if (/(proxim|por vencer|pendiente|advertencia|warning)/.test(rowText)) {
      return "warning";
    }
    if (
      /(vigente|activo|positiv|aprobado|cumplid|correcto|ok|success)/.test(
        rowText,
      )
    ) {
      return "success";
    }
  }

  return "neutral";
};

export const toneCardClass: Record<SemanticTone, string> = {
  danger:
    "border-red-200 bg-red-50 text-red-900 dark:border-red-500/30 dark:bg-red-500/8 dark:text-red-200",
  warning:
    "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/8 dark:text-amber-200",
  success:
    "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-400/30 dark:bg-emerald-400/8 dark:text-emerald-200",
  neutral:
    "border-gray-200 bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-900/80 dark:text-white",
};

export const toneSoftClass: Record<SemanticTone, string> = {
  danger:
    "border-red-200 bg-red-50/80 text-red-800 dark:border-red-500/30 dark:bg-red-500/8 dark:text-red-200",
  warning:
    "border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-400/30 dark:bg-amber-400/8 dark:text-amber-200",
  success:
    "border-emerald-200 bg-emerald-50/80 text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-400/8 dark:text-emerald-200",
  neutral:
    "border-blue-light-200 bg-blue-light-50/70 text-blue-light-900 dark:border-blue-light-500/25 dark:bg-blue-light-500/8 dark:text-blue-light-200",
};

export const toneCellClass: Record<SemanticTone, string> = {
  danger: "bg-red-50 text-red-800 dark:bg-red-500/8 dark:text-red-200",
  warning: "bg-amber-50 text-amber-800 dark:bg-amber-400/8 dark:text-amber-200",
  success:
    "bg-emerald-50 text-emerald-800 dark:bg-emerald-400/8 dark:text-emerald-200",
  neutral: "text-gray-700 dark:text-gray-300",
};
