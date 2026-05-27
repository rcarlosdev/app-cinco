// /components/actividad/useActividadSubmit.ts

import { ActividadFormData } from "@/schemas/actividades.schema";
import { useFormSubmit } from "@/hooks/useFormSubmit";
import { useActividadStore } from "@/store/actividad.store";
import { toast } from "sonner";

const toNullableDate = (value?: string | null) => {
  if (!value || !value.trim()) {
    return null;
  }

  return value;
};

const buildActividadPayload = (data: ActividadFormData): ActividadFormData => ({
  ...data,
  fecha_fin_real: toNullableDate(data.fecha_fin_real),
  ots: data.ots.map((item) => ({
    ...item,
    fecha_inicio: toNullableDate(item.fecha_inicio) ?? undefined,
    fecha_fin: toNullableDate(item.fecha_fin) ?? undefined,
  })),
});

export const useActividadSubmit = () => {
  const { submit, isLoading, error } = useFormSubmit<ActividadFormData>();
  const { upsertActividad } = useActividadStore();

  const handleSubmit = async (
    data: ActividadFormData,
    mode: "create" | "edit",
    id?: number,
    onSuccessCallback?: () => void,
  ) => {
    const endpoint =
      mode === "create"
        ? "/operaciones/actividades/"
        : `/operaciones/actividades/${id}/`;

    const method = mode === "create" ? "POST" : "PATCH";
    const payload = buildActividadPayload(data);

    await submit(payload, {
      endpoint,
      method,
      onSuccess: (response) => {
        toast.success(
          mode === "create"
            ? "Actividad creada exitosamente"
            : "Actividad actualizada exitosamente",
        );

        upsertActividad(response);

        if (onSuccessCallback) {
          onSuccessCallback();
        }
      },
      onError: (err) => {
        toast.error(
          err.message ||
            "No se pudo realizar la operación. Por favor, intenta nuevamente.",
        );
      },
    });
  };

  return {
    handleSubmit,
    isLoading,
    error,
  };
};
