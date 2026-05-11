"use client";

import type { NormalizedKPI } from "@/modules/programacion/ia-dev/chat/types";

type KPIGridProps = {
  items: NormalizedKPI[];
};

const formatValue = (value: number | string) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("es-CO", {
      maximumFractionDigits: 2,
    }).format(value);
  }

  return String(value);
};

const KPIGrid = ({ items }: KPIGridProps) => {
  if (items.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <article
          key={item.key}
          className="rounded-3xl border border-gray-200 bg-white px-4 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-950"
        >
          <p className="text-[11px] font-semibold tracking-[0.18em] text-gray-500 uppercase dark:text-gray-400">
            {item.label}
          </p>
          <p className="mt-3 text-2xl font-semibold text-gray-950 dark:text-white">
            {formatValue(item.value)}
          </p>
        </article>
      ))}
    </div>
  );
};

export default KPIGrid;
