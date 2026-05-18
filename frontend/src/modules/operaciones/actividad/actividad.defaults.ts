// /modules/operaciones/actividad/actividad.defaults.ts

import { ActividadFormData } from "@/schemas/actividades.schema";

export const actividadCreateDefaultValues: ActividadFormData = {
  ots: [""],
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

// {
//     "id": 3,
//     "detalle": {
//         "id": 3,
//         "tipo_trabajo": "PRUEBA",
//         "descripcion": "Esta es una actividad de prueba",
//         "extra": null
//     },
//     "ubicacion": {
//         "id": 3,
//         "direccion": "Medellin",
//         "coordenada_x": "000000000",
//         "coordenada_y": "000000000",
//         "zona": "SUR",
//         "nodo": "N600"
//     },
//     "responsable_snapshot": {
//         "nombre": "CARLOS ALBERTO",
//         "area": "DEPARTAMENTO TI",
//         "carpeta": "PROGRAMACION",
//         "cargo": "LIDER DESARROLLADOR",
//         "movil": "PROGRAM01"
//     },
//     "ot": "00003",
//     "ots": ["00003", "00004"],
//     "estado": "pendiente",
//     "responsable_id": 2761,
//     "fecha_inicio": "2026-02-17",
//     "fecha_fin_estimado": "2026-02-19",
//     "fecha_fin_real": "1900-01-01",
//     "created_at": "2026-02-12T16:01:35.352362-05:00",
//     "created_by": null,
//     "updated_at": "2026-02-12T16:01:35.352362-05:00",
//     "updated_by": null,
//     "is_deleted": false,
//     "deleted_at": null,
//     "deleted_by": null
// },

export const actividadEditDefaultValues = (
  actividad: ActividadFormData,
): ActividadFormData => ({
  id: actividad.id,
  ots: actividad.ots,
  estado: actividad.estado,
  responsable_id: actividad.responsable_id,
  responsable_snapshot: actividad.responsable_snapshot,
  fecha_inicio: actividad.fecha_inicio,
  fecha_fin_estimado: actividad.fecha_fin_estimado,
  fecha_fin_real: actividad.fecha_fin_real,
  detalle: {
    tipo_trabajo: actividad.detalle.tipo_trabajo,
    descripcion: actividad.detalle.descripcion,
  },
  ubicacion: {
    direccion: actividad.ubicacion.direccion,
    coordenada_x: actividad.ubicacion.coordenada_x,
    coordenada_y: actividad.ubicacion.coordenada_y,
    zona: actividad.ubicacion.zona,
    nodo: actividad.ubicacion.nodo,
  },
});
