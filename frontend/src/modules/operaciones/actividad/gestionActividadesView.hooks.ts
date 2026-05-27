import { useEffect, useMemo, useState } from "react";
import { useActividadStore } from "@/store/actividad.store";
import { useTableUrlState } from "@/hooks/useTableUrlState";
import { ColumnDef } from "@tanstack/react-table";
import { ActividadRecord } from "@/schemas/actividades.schema";
import { ACTIVIDAD_TABLE_CONFIG } from "./actividadTable.utils";
import { getActividadesColumns } from "./gestionActividadesView.utils";
import { logDevelopmentError } from "@/lib/environment";
import { ApiError } from "@/lib/errorHandler";

const formatLoadErrorForLog = (error: unknown) => {
  if (error instanceof Error) {
    const apiError = error as ApiError;

    return {
      name: error.name,
      message: error.message,
      stack: error.stack,
      type: apiError.type,
      status: apiError.status,
      errors: apiError.errors,
      originalError: apiError.originalError,
    };
  }

  return error;
};

export const useGestionActividadesData = () => {
  const { loadActividades, actividades, loadError, loadWarning } =
    useActividadStore();
  const [showAlert, setShowAlert] = useState(false);
  const [visibleRows, setVisibleRows] = useState<ActividadRecord[]>([]);

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
        logDevelopmentError(
          "Error cargando actividades:",
          formatLoadErrorForLog(error),
        );
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

  const columns: ColumnDef<ActividadRecord>[] = useMemo(
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
    loadWarning,
  };
};
