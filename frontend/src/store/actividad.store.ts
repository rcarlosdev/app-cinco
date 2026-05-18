// src/store/menu.store.ts
import { create } from "zustand";
import { getActividades } from "@/services/actividades.service";
import { ActividadSchema } from "@/schemas/actividades.schema";
import { ApiErrorDetail, classifyError } from "@/lib/errorHandler";

export const useActividadStore = create<any>((set) => ({
  actividades: ActividadSchema.array().parse([]),
  loadError: null as ApiErrorDetail | null,

  loadActividades: async () => {
    try {
      const actividades = ActividadSchema.array().parse(await getActividades());
      set({ actividades, loadError: null });
      return actividades;
    } catch (error) {
      const loadError = classifyError(error);
      set({ loadError });
      throw loadError;
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
