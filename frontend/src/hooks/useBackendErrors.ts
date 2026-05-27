// src/hooks/useBackendErrors.ts
import { useEffect } from "react";
import { UseFormSetError, FieldValues, Path } from "react-hook-form";

/**
 * Hook reutilizable para aplicar errores del backend a formularios de React Hook Form
 * 
 * Maneja múltiples formatos de error que pueden venir del backend:
 * - Arrays de strings: `{"field": ["Error message"]}`
 * - Strings directos: `{"field": "Error message"}`
 * - Objetos anidados: `{"nested": {"field": ["Error"]}}`
 * 
 * @param backendErrors - Objeto con errores del backend (generalmente del formato Django REST)
 * @param setError - Función setError de React Hook Form
 * 
 * @example
 * ```tsx
 * const { control, formState: { errors }, setError } = useForm();
 * 
 * useBackendErrors(backendErrors, setError);
 * ```
 */
export function useBackendErrors<TFieldValues extends FieldValues>(
  backendErrors: Record<string, any> | null | undefined,
  setError: UseFormSetError<TFieldValues>,
) {
  useEffect(() => {
    if (!backendErrors) return;

    /**
     * Función recursiva para aplicar errores de forma plana o anidada
     * @param errors - Objeto con errores a procesar
     * @param prefix - Prefijo para construir rutas anidadas (ej: "detalle.tipo_trabajo")
     */
    const applyErrors = (errors: Record<string, any>, prefix = "") => {
      Object.keys(errors).forEach((field) => {
        const fullPath = prefix ? `${prefix}.${field}` : field;
        const value = errors[field];

        if (Array.isArray(value)) {
          const stringMessages = value.filter(
            (item): item is string => typeof item === "string",
          );

          if (stringMessages.length > 0) {
            setError(fullPath as Path<TFieldValues>, {
              type: "server",
              message: stringMessages[0],
            });
            return;
          }

          value.forEach((item, index) => {
            if (item && typeof item === "object") {
              applyErrors(item, `${fullPath}.${index}`);
            }
          });
        } else if (typeof value === "string") {
          setError(fullPath as Path<TFieldValues>, {
            type: "server",
            message: value,
          });
        } else if (
          typeof value === "object" &&
          value !== null &&
          typeof value.message === "string"
        ) {
          setError(fullPath as Path<TFieldValues>, {
            type: "server",
            message: value.message,
          });
        } else if (typeof value === "object" && value !== null) {
          applyErrors(value, fullPath);
        }
      });
    };

    applyErrors(backendErrors);
  }, [backendErrors, setError]);
}
