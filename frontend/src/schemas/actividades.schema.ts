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
  ot: z.string().optional().nullable(),
  ot_items: z
    .array(
      z.object({
        id: z.number().optional(),
        ot: z.string(),
        fecha_inicio: z.string().nullable().optional(),
        fecha_fin: z.string().nullable().optional(),
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
    // descripcion: z.string().min(1, "La descripción es requerida"),
    descripcion: z.string().optional(),
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

  ots: z.preprocess(
    (val) => {
      if (Array.isArray(val)) {
        return val.map((item) => {
          if (typeof item === "string") {
            return { ot: item, fecha_inicio: "", fecha_fin: "" };
          }
          return item;
        });
      }
      return val;
    },
    z
      .array(
        z.object({
          ot: z.string().min(1, "La OT es requerida"),
          fecha_inicio: z
            .string()
            .optional()
            .or(z.literal(""))
            .refine((v) => !v || !isNaN(Date.parse(v)), {
              message: "Fecha de inicio inválida",
            }),
          fecha_fin: z
            .string()
            .optional()
            .or(z.literal(""))
            .refine((v) => !v || !isNaN(Date.parse(v)), {
              message: "Fecha de fin inválida",
            }),
        })
      )
      .min(1, "Debe registrar al menos una OT")
  ),

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

export const ActividadRecordSchema = z.object({
  id: z.number().optional(),
  ot: z.string().optional().nullable(),
  ot_items: z
    .array(
      z.object({
        id: z.number().optional(),
        ot: z.string().optional().default(""),
        fecha_inicio: z.string().nullable().optional(),
        fecha_fin: z.string().nullable().optional(),
        is_active: z.boolean().optional(),
        created_at: z.string().optional(),
        created_by: z.number().nullable().optional(),
        updated_at: z.string().optional(),
        updated_by: z.number().nullable().optional(),
      }),
    )
    .optional(),
  detalle: z.object({
    tipo_trabajo: z.string().optional().default(""),
    descripcion: z.string().optional().default(""),
  }),
  ubicacion: z.object({
    direccion: z.string().optional().default(""),
    coordenada_x: z.string().optional().default(""),
    coordenada_y: z.string().optional().default(""),
    zona: z.string().optional().default(""),
    nodo: z.string().optional().default(""),
  }),
  responsable_snapshot: z
    .object({
      nombre: z.string().optional().default(""),
      area: z.string().optional().default(""),
      carpeta: z.string().optional().default(""),
      cargo: z.string().optional().default(""),
      movil: z.string().optional().default(""),
    })
    .optional(),
  ots: z
    .array(
      z.union([
        z.string(),
        z.object({
          ot: z.string().optional().default(""),
          fecha_inicio: z.string().nullable().optional(),
          fecha_fin: z.string().nullable().optional(),
        }),
      ]),
    )
    .default([]),
  estado: z.string().optional(),
  responsable_id: z.number().optional(),
  fecha_inicio: z.string().optional().nullable(),
  fecha_fin_estimado: z.string().optional().nullable(),
  fecha_fin_real: z.string().optional().nullable(),
});

const toOptionalString = (value: unknown): string | undefined => {
  return typeof value === "string" ? value : undefined;
};

const toNullableString = (value: unknown): string | null | undefined => {
  if (value === null) return null;
  if (typeof value === "string") return value;
  return undefined;
};

const toNumberOrUndefined = (value: unknown): number | undefined => {
  return typeof value === "number" ? value : undefined;
};

const toNullableNumber = (value: unknown): number | null | undefined => {
  if (value === null) return null;
  if (typeof value === "number") return value;
  return undefined;
};

const toBooleanOrUndefined = (value: unknown): boolean | undefined => {
  return typeof value === "boolean" ? value : undefined;
};

export const normalizeActividadFromApi = (value: unknown) => {
  const actividad = (value ?? {}) as Record<string, unknown>;
  const detalle = (actividad.detalle ?? {}) as Record<string, unknown>;
  const ubicacion = (actividad.ubicacion ?? {}) as Record<string, unknown>;
  const responsable =
    actividad.responsable_snapshot &&
    typeof actividad.responsable_snapshot === "object"
      ? (actividad.responsable_snapshot as Record<string, unknown>)
      : undefined;

  const rawOts = Array.isArray(actividad.ots) ? actividad.ots : [];
  const rawOtItems = Array.isArray(actividad.ot_items) ? actividad.ot_items : [];

  return {
    id: toNumberOrUndefined(actividad.id),
    ot: toNullableString(actividad.ot),
    ot_items: rawOtItems.map((item) => {
      const otItem = (item ?? {}) as Record<string, unknown>;

      return {
        id: toNumberOrUndefined(otItem.id),
        ot: toOptionalString(otItem.ot) ?? "",
        fecha_inicio: toNullableString(otItem.fecha_inicio),
        fecha_fin: toNullableString(otItem.fecha_fin),
        is_active: toBooleanOrUndefined(otItem.is_active),
        created_at: toOptionalString(otItem.created_at),
        created_by: toNullableNumber(otItem.created_by),
        updated_at: toOptionalString(otItem.updated_at),
        updated_by: toNullableNumber(otItem.updated_by),
      };
    }),
    detalle: {
      tipo_trabajo: toOptionalString(detalle.tipo_trabajo) ?? "",
      descripcion: toOptionalString(detalle.descripcion) ?? "",
    },
    ubicacion: {
      direccion: toOptionalString(ubicacion.direccion) ?? "",
      coordenada_x: toOptionalString(ubicacion.coordenada_x) ?? "",
      coordenada_y: toOptionalString(ubicacion.coordenada_y) ?? "",
      zona: toOptionalString(ubicacion.zona) ?? "",
      nodo: toOptionalString(ubicacion.nodo) ?? "",
    },
    responsable_snapshot: responsable
      ? {
          nombre: toOptionalString(responsable.nombre) ?? "",
          area: toOptionalString(responsable.area) ?? "",
          carpeta: toOptionalString(responsable.carpeta) ?? "",
          cargo: toOptionalString(responsable.cargo) ?? "",
          movil: toOptionalString(responsable.movil) ?? "",
        }
      : undefined,
    ots: rawOts,
    estado: toOptionalString(actividad.estado),
    responsable_id: toNumberOrUndefined(actividad.responsable_id) ?? 0,
    fecha_inicio: toOptionalString(actividad.fecha_inicio) ?? "",
    fecha_fin_estimado: toOptionalString(actividad.fecha_fin_estimado) ?? "",
    fecha_fin_real: toNullableString(actividad.fecha_fin_real) ?? null,
  };
};

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
export type ActividadRecord = z.infer<typeof ActividadRecordSchema>;
