"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Table } from "lucide-react";
import type { NormalizedTable } from "@/modules/programacion/ia-dev/chat/types";
import {
  getSemanticTone,
  toneCellClass,
} from "@/modules/programacion/ia-dev/chat/utils/semanticTone";

type DataTableRendererProps = {
  table: NormalizedTable | null;
};

const DEFAULT_VISIBLE_ROWS = 8;

const formatCell = (value: unknown): string => {
  if (value == null) return "-";
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(
      value,
    );
  }
  return String(value);
};

const DataTableRenderer = ({ table }: DataTableRendererProps) => {
  const [expanded, setExpanded] = useState(false);

  const visibleRows = useMemo(() => {
    if (!table) return [];
    if (expanded) return table.rows;
    return table.rows.slice(0, DEFAULT_VISIBLE_ROWS);
  }, [expanded, table]);

  if (!table || table.columns.length === 0 || table.rows.length === 0)
    return null;

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
          <Table size={12} />
          Tabla de detalle
        </p>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {table.rowcount} filas
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900/80">
        <div className="max-h-[360px] overflow-auto">
          <table className="w-full min-w-[460px] border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
              <tr>
                {table.columns.map((column) => (
                  <th
                    key={column}
                    className="border-b border-gray-200 px-3 py-2 font-semibold text-gray-700 dark:border-gray-700 dark:text-gray-200"
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => (
                <tr
                  key={`table-row-${index}`}
                  className="odd:bg-white even:bg-gray-50/40 dark:odd:bg-gray-900/80 dark:even:bg-gray-800/45"
                >
                  {table.columns.map((column) => {
                    const tone = getSemanticTone({
                      label: column,
                      value: row[column],
                      row,
                    });

                    return (
                      <td
                        key={`${column}-${index}`}
                        className={`border-b border-gray-100 px-3 py-2 dark:border-gray-800 ${toneCellClass[tone]}`}
                      >
                        {formatCell(row[column])}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {table.rows.length > DEFAULT_VISIBLE_ROWS && (
        <button
          type="button"
          className="text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200 inline-flex items-center gap-1 text-xs font-semibold"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? (
            <>
              <ChevronUp size={12} />
              Mostrar menos filas
            </>
          ) : (
            <>
              <ChevronDown size={12} />
              Ver tabla completa ({table.rows.length})
            </>
          )}
        </button>
      )}
    </section>
  );
};

export default DataTableRenderer;
