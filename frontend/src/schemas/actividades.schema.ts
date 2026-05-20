import { z } from "zod";

type ZodSchema = z.ZodTypeAny;

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

export const ActividadSchema = z.object({
  id: z.number().optional(),
  ot_items: z
    .array(
      z.object({
        id: z.number().optional(),
        ot: z.string(),
        is_active: z.boolean().optional(),
        created_at: z.string().optional(),
        created_by: z.number().nullable().optional(),
        updated_at: z.string().optional(),
        updated_by: z.number().nullable().optional(),
      }),
    )
    .optional(),

  detalle: z.object({
    tipo_trabajo: z.string().min(1, "El tipo de trabajo es requerido"),
    descripcion: z.string().min(1, "La descripción es requerida"),
    // extra: z.string().optional(),
  }),

  ubicacion: z.object({
    direccion: z.string().min(1, "La dirección es requerida"),
    // coordenada_x: z.string().min(1, "La coordenada X es requerida"),
    coordenada_x: z.string().optional(),
    // coordenada_y: z.string().min(1, "La coordenada Y es requerida"),
    coordenada_y: z.string().optional(),
    // zona: z.string().min(1, "La zona es requerida"),
    zona: z.string().optional(),
    // nodo: z.string().min(1, "El nodo es requerido"),
    nodo: z.string().optional(),
  }),

  responsable_snapshot: z
    .object({
      nombre: z.string().min(1, "El nombre del responsable es requerido"),
      area: z.string().min(1, "El área del responsable es requerida"),
      carpeta: z.string().min(1, "La carpeta del responsable es requerida"),
      cargo: z.string().min(1, "El cargo del responsable es requerido"),
      movil: z.string().min(1, "El móvil del responsable es requerido"),
    })
    .optional(),

  ots: z
    .array(z.string().min(1, "La OT no puede estar vacía"))
    .min(1, "Debe registrar al menos una OT"),

  estado: z.string().optional(), // opcional, se asignará automáticamente al crear la actividad

  responsable_id: z
    .number({
      message: "Debe seleccionar un responsable válido",
    })
    .min(1, "Debe seleccionar un responsable"),

  fecha_inicio: z
    .string()
    .min(1, "La fecha de inicio es requerida")
    .refine((v) => !isNaN(Date.parse(v)), {
      message: "Fecha de inicio inválida",
    }),

  fecha_fin_estimado: z
    .string()
    .min(1, "La fecha de fin estimada es requerida")
    .refine((v) => !isNaN(Date.parse(v)), {
      message: "Fecha de fin estimada inválida",
    }),

  // no obligatoria, puede ser vacía o una fecha válida, permitir null
  fecha_fin_real: z
    .string()
    .optional()
    .nullable()
    .refine((v) => !v || !isNaN(Date.parse(v)), {
      message: "Fecha de fin real inválida",
    }),
});

const unwrapSchema = (schema: ZodSchema): ZodSchema => {
  let current = schema;

  while (
    typeof (current as ZodSchema & { unwrap?: () => ZodSchema }).unwrap ===
      "function" &&
    (current.type === "optional" ||
      current.type === "nullable" ||
      current.type === "default")
  ) {
    current = (current as ZodSchema & { unwrap: () => ZodSchema }).unwrap();
  }

  return current;
};

export const isActividadFieldRequired = (fieldPath: string): boolean => {
  const segments = fieldPath.split(".").filter(Boolean);
  let current: ZodSchema = ActividadSchema;

  for (const segment of segments) {
    const schema = unwrapSchema(current);

    if (schema.type !== "object") {
      return false;
    }

    const shape = (schema.def as unknown as { shape: Record<string, ZodSchema> })
      .shape;
    const fieldSchema = shape[segment];

    if (!fieldSchema || fieldSchema.isOptional()) {
      return false;
    }

    current = fieldSchema;
  }

  return !current.isOptional();
};

export type ActividadFormData = z.infer<typeof ActividadSchema>;
