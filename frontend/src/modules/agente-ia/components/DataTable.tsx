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
import type { AgenteIAViewMode } from "@/modules/agente-ia/types";
import { downloadIADevProviderSerialArtifact } from "@/services/ia-dev.service";
import { exportToCsv } from "@/utils/csv";

type DataTableProps = {
  mode?: AgenteIAViewMode;
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

const DataTable = ({ mode = "user", tabs }: DataTableProps) => {
  const [activeTabId, setActiveTabId] = useState(tabs[0]?.id ?? "");
  const [globalFilter, setGlobalFilter] = useState("");
  const [isDownloadingArtifact, setIsDownloadingArtifact] = useState(false);
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
  const tableRows = activeTab?.table.rows ?? [];
  const exportRowsSource =
    activeTab?.table.exportRows && activeTab.table.exportRows.length > 0
      ? activeTab.table.exportRows
      : tableRows;

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

  const filteredRows = table.getFilteredRowModel().rows.map((row) => row.original);
  const hasFilteredRows = filteredRows.length > 0;
  const totalRows = activeTab.table.totalRecords ?? activeTab.table.rowcount;
  const returnedRows =
    activeTab.table.returnedRecords ?? activeTab.table.rows.length;
  const exportRows = activeTab.table.exportRecords ?? exportRowsSource.length;
  const isTruncated = Boolean(activeTab.table.truncated);
  const isExportTruncated = Boolean(activeTab.table.exportTruncated);
  const exportArtifact = activeTab.table.exportArtifact;
  const hasFullArtifact =
    Boolean(exportArtifact?.available) && Boolean(exportArtifact?.artifactId);
  const currentPage = table.getState().pagination.pageIndex + 1;
  const pageCount = table.getPageCount() || 1;

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

    const rowsToExport =
      deferredGlobalFilter.trim().length > 0 ? filteredRows : exportRowsSource;

    exportToCsv(rowsToExport, {
      fileName: buildExportFileName(activeTab.label, "csv"),
      columns: activeTab.table.columns.map((column) => ({
        header: column,
        accessor: (row) => row[column],
      })),
    });
  };

  const handleExportXlsx = async () => {
    if (!hasFilteredRows) return;

    const rowsToExport =
      deferredGlobalFilter.trim().length > 0 ? filteredRows : exportRowsSource;
    const XLSX = await import("xlsx");
    const worksheet = XLSX.utils.json_to_sheet(rowsToExport, {
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

  const handleDownloadArtifact = async () => {
    if (!exportArtifact?.artifactId || isDownloadingArtifact) return;
    setIsDownloadingArtifact(true);
    try {
      const blob = await downloadIADevProviderSerialArtifact({
        artifactId: exportArtifact.artifactId,
      });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        exportArtifact.filename || buildExportFileName(activeTab.label, "csv");
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setIsDownloadingArtifact(false);
    }
  };

  return (
    <div className="space-y-4">
      {tabs.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabChange(tab.id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                tab.id === activeTab.id
                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              }`}
            >
              <span className="flex items-center gap-2">
                <span>{tab.label}</span>
                {mode === "dev" && tab.badges.length > 0 ? (
                  <span className="flex flex-wrap gap-1">
                    {tab.badges.map((badge) => (
                      <span
                        key={`${tab.id}-${badge}`}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-[0.08em] uppercase ${
                          tab.id === activeTab.id
                            ? "bg-white/15 text-white dark:bg-slate-700 dark:text-white"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300"
                        }`}
                      >
                        {badge}
                      </span>
                    ))}
                  </span>
                ) : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}

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
              className="h-10 w-full rounded-full border border-gray-300 bg-white pr-3 pl-9 text-sm text-gray-800 transition outline-none placeholder:text-gray-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/10 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-sky-300"
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={!hasFilteredRows}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-gray-300 bg-white px-3 text-xs font-semibold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              title="Exportar filas disponibles a CSV"
            >
              <Download size={15} />
              Exportar CSV
            </button>
            <button
              type="button"
              onClick={handleExportXlsx}
              disabled={!hasFilteredRows}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-gray-300 bg-white px-3 text-xs font-semibold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
              title="Exportar filas disponibles a XLSX"
            >
              <FileSpreadsheet size={15} />
              Exportar XLSX
            </button>
            {hasFullArtifact ? (
              <button
                type="button"
                onClick={() => void handleDownloadArtifact()}
                disabled={isDownloadingArtifact}
                className="inline-flex h-10 items-center gap-2 rounded-full border border-emerald-300 bg-emerald-50 px-3 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200 dark:hover:bg-emerald-500/20"
                title="Descargar dataset completo"
              >
                <Download size={15} />
                {isDownloadingArtifact ? "Descargando..." : "Exportar completo"}
              </button>
            ) : null}
          </div>
        </div>

        <div className="border-b border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          {mode === "user" ? (
            <span>
              {filteredRows.length} filas disponibles en esta vista.
              {returnedRows < exportRows
                ? ` Mostrando una muestra de ${returnedRows}; la exportacion incluye ${exportRows}.`
                : ` La exportacion incluye ${exportRows}.`}
              {hasFullArtifact && exportArtifact?.recordCount
                ? ` Tambien puedes descargar el dataset completo con ${exportArtifact.recordCount} filas.`
                : ""}
            </span>
          ) : (
            <span>
              {filteredRows.length} de {exportRows} filas disponibles
              {totalRows > exportRows ? ` (${totalRows} total reportadas)` : ""}
              {returnedRows < exportRows
                ? `, ${returnedRows} usadas para visualizacion inicial`
                : ""}
              {hasFullArtifact && exportArtifact?.recordCount
                ? `, artifact completo ${exportArtifact.recordCount} filas`
                : ""}
              {isTruncated && activeTab.table.limit
                ? `, limite ${activeTab.table.limit}`
                : ""}
              {isExportTruncated && activeTab.table.exportLimit && !hasFullArtifact
                ? `, exportacion limitada a ${activeTab.table.exportLimit}`
                : ""}
            </span>
          )}
        </div>

        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="sticky top-0 bg-gray-50 dark:bg-gray-900">
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
                      className="px-4 py-3 align-top text-gray-700 dark:text-gray-200"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {!hasFilteredRows ? (
                <tr>
                  <td
                    colSpan={activeTab.table.columns.length}
                    className="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400"
                  >
                    No se encontraron resultados para la busqueda.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          <span>
            {mode === "user"
              ? `Pagina ${currentPage} de ${pageCount}.`
              : `Pagina ${currentPage} de ${pageCount}. Navegacion local sobre la vista cargada.`}
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
