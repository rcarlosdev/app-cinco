"use client";

import { useDeferredValue, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Download, FileSpreadsheet, Search } from "lucide-react";
import type { DashboardTableTab } from "@/modules/agente-ia/types";
import { exportToCsv } from "@/utils/csv";

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

const normalizeSearchValue = (value: unknown) =>
  formatValue(value).toLocaleLowerCase("es-CO");

const buildExportFileName = (label: string, extension: "csv" | "xlsx") => {
  const normalizedLabel = label
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();

  const suffix = normalizedLabel || "tabla";
  return `agente-ia-${suffix}.${extension}`;
};

const DataTable = ({ tabs }: DataTableProps) => {
  const [activeTabId, setActiveTabId] = useState(tabs[0]?.id ?? "");
  const [globalFilter, setGlobalFilter] = useState("");
  const deferredGlobalFilter = useDeferredValue(globalFilter);

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
  const tableRows = activeTab?.table.exportRows ?? activeTab?.table.rows ?? [];

  const table = useReactTable({
    data: tableRows,
    columns,
    state: {
      globalFilter: deferredGlobalFilter,
    },
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    globalFilterFn: (row, _columnId, filterValue) => {
      const normalizedFilter = String(filterValue)
        .trim()
        .toLocaleLowerCase("es-CO");

      if (!normalizedFilter) return true;

      return activeTab.table.columns.some((column) =>
        normalizeSearchValue(row.original[column]).includes(normalizedFilter),
      );
    },
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize: 8,
      },
    },
  });

  if (!activeTab) return null;

  const filteredRows = table
    .getFilteredRowModel()
    .rows.map((row) => row.original);
  const hasFilteredRows = filteredRows.length > 0;
  const totalRows = activeTab.table.totalRecords ?? activeTab.table.rowcount;
  const returnedRows =
    activeTab.table.returnedRecords ?? activeTab.table.rows.length;
  const exportRows = activeTab.table.exportRecords ?? tableRows.length;
  const isTruncated = Boolean(activeTab.table.truncated);
  const isExportTruncated = Boolean(activeTab.table.exportTruncated);

  const handleSearchChange = (value: string) => {
    setGlobalFilter(value);
    table.setPageIndex(0);
  };

  const handleTabChange = (tabId: string) => {
    setActiveTabId(tabId);
    setGlobalFilter("");
    table.setPageIndex(0);
  };

  const handleExportCsv = () => {
    if (!hasFilteredRows) return;

    exportToCsv(filteredRows, {
      fileName: buildExportFileName(activeTab.label, "csv"),
      columns: activeTab.table.columns.map((column) => ({
        header: column,
        accessor: (row) => row[column],
      })),
    });
  };

  const handleExportXlsx = async () => {
    if (!hasFilteredRows) return;

    const XLSX = await import("xlsx");
    const worksheet = XLSX.utils.json_to_sheet(filteredRows, {
      header: activeTab.table.columns,
    });
    const workbook = XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
      workbook,
      worksheet,
      activeTab.label.slice(0, 31),
    );
    XLSX.writeFile(workbook, buildExportFileName(activeTab.label, "xlsx"));
  };

  return (
    <div className="space-y-4">
      {tabs.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabChange(tab.id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                tab.id === activeTab.id
                  ? "border-[#111827] bg-[#111827] text-white"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              }`}
            >
              <span className="flex items-center gap-2">
                <span>{tab.label}</span>
                {tab.badges.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {tab.badges.map((badge) => (
                      <span
                        key={`${tab.id}-${badge}`}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-[0.08em] uppercase ${
                          tab.id === activeTab.id
                            ? "bg-white/15 text-white"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
                        }`}
                      >
                        {badge}
                      </span>
                    ))}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
          <label className="relative min-w-[220px] flex-1 sm:max-w-sm">
            <Search
              size={16}
              className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-gray-400"
            />
            <input
              type="search"
              value={globalFilter}
              onChange={(event) => handleSearchChange(event.target.value)}
              placeholder="Buscar en la tabla"
              className="h-10 w-full rounded-full border border-gray-300 bg-white pr-3 pl-9 text-sm text-gray-800 transition outline-none placeholder:text-gray-400 focus:border-[#111827] focus:ring-2 focus:ring-[#111827]/10 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-white"
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={!hasFilteredRows}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-gray-300 bg-white px-3 text-xs font-semibold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              title="Exportar tabla filtrada a CSV"
            >
              <Download size={15} />
              CSV
            </button>
            <button
              type="button"
              onClick={handleExportXlsx}
              disabled={!hasFilteredRows}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-gray-300 bg-white px-3 text-xs font-semibold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              title="Exportar tabla filtrada a XLSX"
            >
              <FileSpreadsheet size={15} />
              XLSX
            </button>
          </div>
        </div>

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
              {!hasFilteredRows && (
                <tr>
                  <td
                    colSpan={activeTab.table.columns.length}
                    className="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400"
                  >
                    No se encontraron resultados para la busqueda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          <span>
            {filteredRows.length} de {exportRows} filas disponibles
            {totalRows > exportRows ? ` (${totalRows} total reportadas)` : ""}
            {returnedRows < exportRows
              ? `, ${returnedRows} usadas para visualizacion inicial`
              : ""}
            {isTruncated && activeTab.table.limit
              ? `, limite ${activeTab.table.limit}`
              : ""}
            {isExportTruncated && activeTab.table.exportLimit
              ? `, exportacion limitada a ${activeTab.table.exportLimit}`
              : ""}
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
