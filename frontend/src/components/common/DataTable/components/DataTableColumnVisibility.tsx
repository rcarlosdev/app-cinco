import { Column } from "@tanstack/react-table";
import { useState } from "react";
import Button from "@/components/ui/button/Button";
import Checkbox from "@/components/form/input/Checkbox";
import { Dropdown } from "@/components/ui/dropdown/Dropdown";
import { ChevronDownIcon } from "@/icons";
import { getColumnHeaderLabel } from "../DataTable.utils";

interface DataTableColumnVisibilityProps<TData> {
  columns: Column<TData, unknown>[];
}

/**
 * Componente que permite mostrar/ocultar columnas de la tabla mediante un dropdown.
 * Presenta una lista de checkboxes con las columnas que pueden ocultarse.
 *
 * @template TData - Tipo de datos de la tabla
 */
export function DataTableColumnVisibility<TData>({
  columns,
}: DataTableColumnVisibilityProps<TData>) {
  const [isOpen, setIsOpen] = useState(false);

  // Filtrar solo columnas que pueden ocultarse
  const visibleColumns = columns.filter((column) => column.getCanHide());

  if (visibleColumns.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        className="dropdown-toggle w-full md:w-auto"
        endIcon={<ChevronDownIcon className="h-4 w-4" />}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        Columnas
      </Button>

      <Dropdown
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-64 p-3"
      >
        <div className="space-y-2">
          {visibleColumns.map((column) => {
            const headerLabel = getColumnHeaderLabel(
              column.columnDef.header,
              column.id,
            );

            return (
              <Checkbox
                key={column.id}
                checked={column.getIsVisible()}
                onChange={(checked) => column.toggleVisibility(checked)}
                label={String(headerLabel)}
                id={`column-${column.id}`}
              />
            );
          })}
        </div>
      </Dropdown>
    </div>
  );
}
