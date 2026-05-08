"use client";

import { BarChart2 } from "lucide-react";
import type { NormalizedKPI } from "@/modules/programacion/ia-dev/chat/types";
import {
  getSemanticTone,
  toneCardClass,
} from "@/modules/programacion/ia-dev/chat/utils/semanticTone";

type KPISectionProps = {
  items: NormalizedKPI[];
};

const formatValue = (value: number | string) => {
  if (typeof value !== "number" || !Number.isFinite(value))
    return String(value);
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(
    value,
  );
};

const KPISection = ({ items }: KPISectionProps) => {
  if (items.length === 0) return null;

  return (
    <section className="space-y-2">
      <p className="text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
        KPIs
      </p>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((kpi) => (
          <article
            key={kpi.key}
            className={`shadow-theme-xs rounded-xl border px-3 py-2 ${toneCardClass[getSemanticTone({ label: `${kpi.key} ${kpi.label}`, value: kpi.rawValue })]}`}
          >
            <div className="mb-1 flex items-center gap-2 text-[11px] opacity-75">
              <BarChart2 size={12} />
              <span className="truncate">{kpi.label}</span>
            </div>
            <p className="truncate text-lg font-semibold">
              {formatValue(kpi.value)}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
};

export default KPISection;
