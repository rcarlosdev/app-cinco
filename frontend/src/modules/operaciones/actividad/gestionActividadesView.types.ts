import { SortingState, ColumnDef } from "@tanstack/react-table";
import { ActividadRecord } from "@/schemas/actividades.schema";

export interface GestionActividadesTableState {
  globalFilter: string;
  sorting: SortingState;
  pageIndex: number;
  pageSize: number;
  visibleRows: ActividadRecord[];
  columns: ColumnDef<ActividadRecord>[];
  loadWarning?: string | null;
}

export interface GestionActividadesTableActions {
  setGlobalFilter: (value: string) => void;
  setSorting: (sorting: SortingState) => void;
  setPageIndex: (index: number) => void;
  setPageSize: (size: number) => void;
  setVisibleRows: (rows: ActividadRecord[]) => void;
}

export interface GestionActividadesTableProps
  extends GestionActividadesTableState, GestionActividadesTableActions {
  actividades: ActividadRecord[];
}
