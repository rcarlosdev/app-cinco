import { Table as ReactTable } from "@tanstack/react-table";
import {
  getColumnHeaderLabel,
  renderMobileCellValue,
} from "../DataTable.utils";

interface DataTableMobileProps<TData> {
  table: ReactTable<TData>;
  isLoading: boolean;
  emptyMessage: string;
  onRowClick?: (row: TData) => void;
}

/**
 * Componente que renderiza la vista móvil de la tabla.
 * Convierte las filas en tarjetas verticales con todos los datos visibles.
 *
 * @template TData - Tipo de datos de la tabla
 */
export function DataTableMobile<TData>({
  table,
  isLoading,
  emptyMessage,
  onRowClick,
}: DataTableMobileProps<TData>) {
  const rows = table.getRowModel().rows;
  const visibleColumns = table.getVisibleLeafColumns();

  return (
    <div className="min-w-0 space-y-3 overflow-y-auto p-4 md:hidden">
      {isLoading ? (
        <div className="rounded-xl border border-gray-200 p-4 text-center text-sm text-gray-500 dark:border-white/5 dark:text-gray-400">
          Loading...
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-gray-200 p-4 text-center text-sm text-gray-500 dark:border-white/5 dark:text-gray-400">
          {emptyMessage}
        </div>
      ) : (
        rows.map((row) => (
          <div
            key={row.id}
            className="min-w-0 overflow-hidden rounded-xl border border-gray-200 p-4 shadow-theme-xs dark:border-white/5"
            onClick={onRowClick ? () => onRowClick(row.original) : undefined}
          >
            <div className="space-y-2">
              {visibleColumns.map((column) => {
                const headerLabel = getColumnHeaderLabel(
                  column.columnDef.header,
                  column.id,
                );
                const value = renderMobileCellValue(row, column.id);

                return (
                  <div
                    key={`${row.id}-${column.id}`}
                    className="min-w-0 flex flex-col gap-1 text-sm sm:flex-row sm:gap-2"
                  >
                    <span className="min-w-0 font-medium text-gray-700 dark:text-white/90">
                      {String(headerLabel)}:
                    </span>
                    <span className="min-w-0 overflow-hidden break-words text-gray-600 dark:text-gray-300">
                      {value}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
