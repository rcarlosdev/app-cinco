// /components/actividad/useActividadSubmit.ts

import { ActividadFormData } from "@/schemas/actividades.schema";
import { useFormSubmit } from "@/hooks/useFormSubmit";
import { useActividadStore } from "@/store/actividad.store";
import { toast } from "sonner";

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

    await submit(data, {
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
