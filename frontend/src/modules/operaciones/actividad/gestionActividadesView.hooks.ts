import { useEffect, useMemo, useState } from "react";
import { useActividadStore } from "@/store/actividad.store";
import { useTableUrlState } from "@/hooks/useTableUrlState";
import { ColumnDef } from "@tanstack/react-table";
import { ActividadFormData } from "@/schemas/actividades.schema";
import { ACTIVIDAD_TABLE_CONFIG } from "./actividadTable.utils";
import { getActividadesColumns } from "./gestionActividadesView.utils";

export const useGestionActividadesData = () => {
  const { loadActividades, actividades, loadError } = useActividadStore();
  const [showAlert, setShowAlert] = useState(false);
  const [visibleRows, setVisibleRows] = useState<ActividadFormData[]>([]);

  const {
    globalFilter,
    setGlobalFilter,
    sorting,
    setSorting,
    pageIndex,
    setPageIndex,
    pageSize,
    setPageSize,
  } = useTableUrlState({
    defaultPageSize: ACTIVIDAD_TABLE_CONFIG.defaultPageSize,
    defaultPageIndex: ACTIVIDAD_TABLE_CONFIG.defaultPageIndex,
  });

  useEffect(() => {
    const loadData = async () => {
      try {
        await loadActividades();
      } catch (error) {
        console.error("Error cargando actividades:", error);
      }
    };

    void loadData();
  }, [loadActividades]);

  useEffect(() => {
    if (!showAlert) return;

    const timer = setTimeout(() => {
      setShowAlert(false);
    }, 5000);

    return () => clearTimeout(timer);
  }, [showAlert]);

  const columns: ColumnDef<ActividadFormData>[] = useMemo(
    () => getActividadesColumns(),
    [],
  );

  return {
    actividades,
    columns,
    globalFilter,
    setGlobalFilter,
    sorting,
    setSorting,
    pageIndex,
    setPageIndex,
    pageSize,
    setPageSize,
    visibleRows,
    setVisibleRows,
    showAlert,
    setShowAlert,
    loadError,
  };
};
