// /modules/operaciones/actividad/actividad.defaults.ts

import { ActividadFormData } from "@/schemas/actividades.schema";

export const actividadCreateDefaultValues: ActividadFormData = {
  ots: [{ ot: "", fecha_inicio: new Date().toISOString().split("T")[0], fecha_fin: "" }], // El primer elemento (ots.0) representa a la OT Padre en creación
  responsable_id: 0,
  fecha_inicio: new Date().toISOString().split("T")[0],
  fecha_fin_estimado: "",
  fecha_fin_real: null,
  detalle: {
    tipo_trabajo: "",
    descripcion: "",
  },
  ubicacion: {
    direccion: "",
    coordenada_x: "",
    coordenada_y: "",
    zona: "",
    nodo: "",
  },
};

export const actividadEditDefaultValues = (
  actividad: any,
): ActividadFormData => {
  const otPrincipal = actividad.ot || "";
  const otItems = actividad.ot_items || [];

  // Buscamos el elemento de la OT principal dentro de la lista detallada
  const itemPrincipal = otItems.find((item: any) => item.ot === otPrincipal);
  const otrosItems = otItems.filter((item: any) => item.ot !== otPrincipal);

  const otsMapped = [];

  // Anteponemos la OT principal en el índice 0 para representar a la OT Padre
  if (itemPrincipal) {
    otsMapped.push({
      ot: itemPrincipal.ot,
      fecha_inicio: itemPrincipal.fecha_inicio || actividad.fecha_inicio || "",
      fecha_fin: itemPrincipal.fecha_fin || actividad.fecha_fin_estimado || "",
    });
  } else {
    otsMapped.push({
      ot: otPrincipal,
      fecha_inicio: actividad.fecha_inicio || "",
      fecha_fin: actividad.fecha_fin_estimado || "",
    });
  }

  // Agregamos el resto de las OTs Hijas reales a partir del índice 1
  // Si no tienen fecha de inicio o fin asignadas (registros históricos), adoptan por defecto las fechas del Padre
  otrosItems.forEach((item: any) => {
    otsMapped.push({
      ot: item.ot,
      fecha_inicio: item.fecha_inicio || actividad.fecha_inicio || "",
      fecha_fin: item.fecha_fin || actividad.fecha_fin_estimado || "",
    });
  });

  return {
    id: actividad.id,
    ots: otsMapped,
    estado: actividad.estado,
    responsable_id: actividad.responsable_id,
    responsable_snapshot: actividad.responsable_snapshot,
    fecha_inicio: actividad.fecha_inicio,
    fecha_fin_estimado: actividad.fecha_fin_estimado,
    fecha_fin_real: actividad.fecha_fin_real,
    detalle: {
      tipo_trabajo: actividad.detalle?.tipo_trabajo || "",
      descripcion: actividad.detalle?.descripcion || "",
    },
    ubicacion: {
      direccion: actividad.ubicacion?.direccion || "",
      coordenada_x: actividad.ubicacion?.coordenada_x || "",
      coordenada_y: actividad.ubicacion?.coordenada_y || "",
      zona: actividad.ubicacion?.zona || "",
      nodo: actividad.ubicacion?.nodo || "",
    },
  };
};
