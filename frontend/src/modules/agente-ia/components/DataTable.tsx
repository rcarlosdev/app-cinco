"use client";

import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { DashboardTableTab } from "@/modules/agente-ia/types";

type DataTableProps = {
  tabs: DashboardTableTab[];
};

const formatValue = (value: unknown) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("es-CO", {
      maximumFractionDigits: 2,
    }).format(value);
  }

  if (value == null || value === "") return "-";
  return String(value);
};

const DataTable = ({ tabs }: DataTableProps) => {
  const [activeTabId, setActiveTabId] = useState(tabs[0]?.id ?? "");
  const activeTab = useMemo(
    () => tabs.find((tab) => tab.id === activeTabId) ?? tabs[0] ?? null,
    [activeTabId, tabs],
  );

  const columns = useMemo(() => {
    if (!activeTab) return [];
    const helper = createColumnHelper<Record<string, unknown>>();
    return activeTab.table.columns.map((column) =>
      helper.accessor((row) => row[column], {
        id: column,
        header: column,
        cell: (info) => formatValue(info.getValue()),
      }),
    );
  }, [activeTab]);

  // TanStack Table is intentionally used here for client-side pagination.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: activeTab?.table.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize: 8,
      },
    },
  });

  if (!activeTab) return null;

  return (
    <div className="space-y-4">
      {tabs.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTabId(tab.id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                tab.id === activeTab.id
                  ? "border-[#111827] bg-[#111827] text-white"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      <div className="overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="border-b border-gray-200 px-4 py-3 font-semibold text-gray-700 dark:border-gray-800 dark:text-gray-200"
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-gray-100 last:border-b-0 dark:border-gray-900"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-4 py-3 text-gray-700 dark:text-gray-200"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          <span>
            {activeTab.table.rowcount} filas reportadas
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="rounded-full border border-gray-300 px-3 py-1 disabled:opacity-40 dark:border-gray-700"
            >
              Anterior
            </button>
            <span>
              Pagina {table.getState().pagination.pageIndex + 1} de{" "}
              {table.getPageCount() || 1}
            </span>
            <button
              type="button"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="rounded-full border border-gray-300 px-3 py-1 disabled:opacity-40 dark:border-gray-700"
            >
              Siguiente
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataTable;
