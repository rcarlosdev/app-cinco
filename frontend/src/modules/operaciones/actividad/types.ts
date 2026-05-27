// /modules/operaciones/actividad/types.ts

import { ActividadRecord } from "@/schemas/actividades.schema";

export interface Actividad extends ActividadRecord {
  id: number;
}
