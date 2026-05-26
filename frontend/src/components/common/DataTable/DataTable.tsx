"use client";

import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  VisibilityState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTableProps } from "@/types/table";
import { getNextState } from "./DataTable.utils";
import {
  useControlledTableState,
  useVisibleDataChange,
} from "./DataTable.hooks";
import { DataTableToolbar } from "./components/DataTableToolbar";
import { DataTableDesktop } from "./components/DataTableDesktop";
import { DataTableMobile } from "./components/DataTableMobile";
import { DataTablePagination } from "./components/DataTablePagination";

/**
 * Componente DataTable reutilizable y profesional.
 *
 * Características:
 * - Filtrado global y por columnas
 * - Ordenamiento multi-columna
 * - Visibilidad de columnas personalizable
 * - Paginación con tamaños configurables
 * - Vista responsive para móviles
 * - Estado controlado mediante props
 * - Callbacks para sincronización externa
 *
 * Arquitectura:
 * - Componente principal actúa como orquestador
 * - Lógica separada en hooks personalizados
 * - Rendering delegado a sub-componentes especializados
 * - Utilidades aisladas en módulo separado
 *
 * @template TData - Tipo de datos de las filas
 *
 * @example
 * ```tsx
 * <DataTable
 *   data={users}
 *   columns={userColumns}
 *   enablePagination
 *   enableGlobalFilter
 *   enableSorting
 *   enableColumnVisibility
 *   onPageChange={(page) => setPage(page)}
 *   toolbarActions={<Button>Export</Button>}
 * />
 * ```
 */
export function DataTable<TData>({
  data,
  columns,
  isLoading = false,
  emptyMessage = "No data available",
  enablePagination = true,
  pageSize = 10,
  enableGlobalFilter = false,
  enableColumnFilters = false,
  enableSorting = false,
  enableColumnVisibility = true,
  globalFilterPlaceholder = "Buscar...",
  enablePageSizeSelector = true,
  pageSizeOptions = [10, 20, 50],
  initialGlobalFilter = "",
  initialColumnFilters = [],
  initialSorting = [],
  initialColumnVisibility = {},
  globalFilterValue,
  columnFiltersValue,
  sortingValue,
  columnVisibilityValue,
  pageIndexValue,
  pageSizeValue,
  onGlobalFilterChange,
  onColumnFiltersChange,
  onSortingChange,
  onColumnVisibilityChange,
  onPageChange,
  onPageSizeChange,
  onVisibleDataChange,
  onRowClick,
  renderRowActions,
  toolbarActions,
}: DataTableProps<TData>) {
  // Estado local de la tabla
  const [globalFilter, setGlobalFilter] = useState(initialGlobalFilter);
  const [columnFilters, setColumnFilters] =
    useState<ColumnFiltersState>(initialColumnFilters);
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    initialColumnVisibility,
  );

  // Estado de paginación inicial
  const initialPageSize = pageSizeValue ?? pageSize;
  const initialPageIndex = pageIndexValue ?? 0;

  // Agregar columna de acciones si se proporciona renderRowActions
  const columnsWithActions = useMemo<ColumnDef<TData>[]>(() => {
    if (!renderRowActions) {
      return columns;
    }

    return [
      ...columns,
      {
        id: "__actions",
        header: "Acciones",
        enableSorting: false,
        enableColumnFilter: false,
        enableHiding: false,
        cell: ({ row }) => renderRowActions(row.original),
      },
    ];
  }, [columns, renderRowActions]);

  // Configuración de la tabla con React Table
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns: columnsWithActions,
    state: {
      globalFilter,
      columnFilters,
      sorting,
      columnVisibility,
    },
    onGlobalFilterChange: (updater) => {
      const nextValue = getNextState(updater, globalFilter);
      setGlobalFilter(nextValue);
      onGlobalFilterChange?.(nextValue);
    },
    onColumnFiltersChange: (updater) => {
      const nextFilters = getNextState(updater, columnFilters);
      setColumnFilters(nextFilters);
      onColumnFiltersChange?.(nextFilters);
    },
    onSortingChange: (updater) => {
      const nextSorting = getNextState(updater, sorting);
      setSorting(nextSorting);
      onSortingChange?.(nextSorting);
    },
    onColumnVisibilityChange: (updater) => {
      const nextVisibility = getNextState(updater, columnVisibility);
      setColumnVisibility(nextVisibility);
      onColumnVisibilityChange?.(nextVisibility);
    },
    enableSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: enableSorting ? getSortedRowModel() : undefined,
    ...(enablePagination && { getPaginationRowModel: getPaginationRowModel() }),
    initialState: {
      pagination: {
        pageSize: initialPageSize,
        pageIndex: initialPageIndex,
      },
    },
    autoResetPageIndex: false,
  });

  // Hook para sincronizar estado controlado
  useControlledTableState(table, {
    globalFilterValue,
    columnFiltersValue,
    sortingValue,
    columnVisibilityValue,
    pageIndexValue,
    pageSizeValue,
    globalFilter,
    columnFilters,
    sorting,
    columnVisibility,
    setGlobalFilter,
    setColumnFilters,
    setSorting,
    setColumnVisibility,
  });

  // Hook para notificar cambios en datos visibles
  useVisibleDataChange(
    table,
    data,
    globalFilter,
    columnFilters,
    sorting,
    onVisibleDataChange,
  );

  return (
    <div className="flex w-full min-w-0 flex-col rounded-xl border border-gray-200 bg-white dark:border-white/5 dark:bg-white/3 md:h-full">
      {/* Toolbar con búsqueda, columnas y acciones */}
      <DataTableToolbar
        table={table}
        enableGlobalFilter={enableGlobalFilter}
        enableColumnVisibility={enableColumnVisibility}
        globalFilterPlaceholder={globalFilterPlaceholder}
        toolbarActions={toolbarActions}
      />

      {/* Contenedor scrolleable de la tabla */}
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden w-full">
        {/* Vista desktop de la tabla */}
        <DataTableDesktop
          table={table}
          isLoading={isLoading}
          emptyMessage={emptyMessage}
          enableSorting={enableSorting}
          enableColumnFilters={enableColumnFilters}
          onRowClick={onRowClick}
        />

        {/* Vista móvil (tarjetas) */}
        <DataTableMobile
          table={table}
          isLoading={isLoading}
          emptyMessage={emptyMessage}
          onRowClick={onRowClick}
        />
      </div>

      {/* Controles de paginación */}
      {enablePagination && (
        <DataTablePagination
          table={table}
          enablePageSizeSelector={enablePageSizeSelector}
          pageSizeOptions={pageSizeOptions}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      )}
    </div>
  );
}
