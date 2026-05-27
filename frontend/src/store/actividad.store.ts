// src/store/menu.store.ts
import { create } from "zustand";
import { getActividades } from "@/services/actividades.service";
import {
  ActividadRecordSchema,
  normalizeActividadFromApi,
} from "@/schemas/actividades.schema";
import {
  ApiErrorDetail,
  classifyError,
  createApiError,
} from "@/lib/errorHandler";
import { logDevelopmentWarning } from "@/lib/environment";

export const useActividadStore = create<any>((set) => ({
  actividades: ActividadRecordSchema.array().parse([]),
  loadError: null as ApiErrorDetail | null,
  loadWarning: null as string | null,

  loadActividades: async () => {
    try {
      const response = await getActividades();
      const normalized = Array.isArray(response)
        ? response.map(normalizeActividadFromApi)
        : [];

      const parsedRows = normalized.map((item, index) => ({
        index,
        result: ActividadRecordSchema.safeParse(item),
      }));

      const actividades = parsedRows
        .filter((row) => row.result.success)
        .map((row) => row.result.data);

      const invalidRows = parsedRows.filter(
        (
          row,
        ): row is {
          index: number;
          result: Extract<
            (typeof parsedRows)[number]["result"],
            { success: false }
          >;
        } => !row.result.success,
      );
      const loadWarning =
        invalidRows.length > 0
          ? `Se omitieron ${invalidRows.length} actividad(es) con datos incompletos o inválidos.`
          : null;

      if (invalidRows.length > 0) {
        logDevelopmentWarning(
          "Actividades omitidas por formato inesperado:",
          invalidRows.map((row) => ({
            index: row.index,
            issues: row.result.error.issues,
            row: normalized[row.index],
          })),
        );
      }

      set({ actividades, loadError: null, loadWarning });
      return actividades;
    } catch (error) {
      const loadError = classifyError(error);
      set({ loadError, loadWarning: null });
      throw createApiError(error);
    }
  },

  upsertActividad: (actividad: any) => {
    set((state: any) => ({
      actividades: state.actividades.some((item: any) => item.id === actividad.id)
        ? state.actividades.map((item: any) =>
            item.id === actividad.id ? actividad : item,
          )
        : [actividad, ...state.actividades],
    }));
  },
}));
