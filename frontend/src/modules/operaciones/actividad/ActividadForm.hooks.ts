import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import {
  ActividadSchema,
  ActividadFormData,
} from "@/schemas/actividades.schema";
import { Empleado } from "@/types/empleado";
import { getEmpleadoById, getEmpleadoByCedula } from "@/services/empleado.service";
import { preloadAvatar } from "@/utils/avatar";
import {
  buildResponsableSnapshot,
  getSnapshotEmpleado,
} from "./ActividadForm.utils";
import { getUser } from "@/utils/storage";
import { useBackendErrors } from "@/hooks/useBackendErrors";
import {
  logDevelopmentError,
  logDevelopmentWarning,
} from "@/lib/environment";

interface UseActividadFormLogicParams {
  defaultValues: ActividadFormData;
  backendErrors?: Record<string, any> | null;
  mode?: "create" | "edit";
}

export const useActividadFormLogic = ({
  defaultValues,
  backendErrors,
  mode = "create",
}: UseActividadFormLogicParams) => {
  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(
    null,
  );

  const {
    control,
    handleSubmit,
    reset,
    setError,
    setValue,
    formState: { errors },
  } = useForm<ActividadFormData>({
    resolver: zodResolver(ActividadSchema),
    defaultValues,
  });

  useEffect(() => {
    let isActive = true;

    reset(defaultValues);

    const loadEmployee = async () => {
      // Si estamos en modo creación y no hay empleado seleccionado, cargar el usuario de sesión
      if (mode === "create" && (!defaultValues.responsable_id || defaultValues.responsable_id === 0)) {
        try {
          const user = getUser();
          
          if (!user) {
            logDevelopmentWarning("No user found in session");
            return;
          }
          
          if (!user.username) {
            logDevelopmentWarning("User has no username/cedula:", user);
            return;
          }

          if (!isActive) return;

          // Buscar empleado por cédula (username)
          const empleado = await getEmpleadoByCedula(user.username);
          
          if (!isActive) return;

          if (empleado) {
            setSelectedEmployee(empleado);
            setValue("responsable_id", empleado.id);
            setValue("responsable_snapshot", buildResponsableSnapshot(empleado));
            
            if (empleado.link_foto) {
              preloadAvatar(empleado.link_foto);
            }
          }
        } catch (error) {
          // No es un error crítico, simplemente no se pudo cargar el empleado del usuario
          logDevelopmentWarning(
            "Could not load employee for current user:",
            error instanceof Error ? error.message : String(error),
          );
        }
        return;
      }

      // Modo edición o ya hay un responsable
      if (defaultValues.responsable_id && defaultValues.responsable_id > 0) {
        try {
          const empleadoBase = getSnapshotEmpleado(defaultValues);

          if (empleadoBase && isActive) {
            setSelectedEmployee(empleadoBase);
          }

          const empleadoFull = await getEmpleadoById(
            defaultValues.responsable_id,
          );
          if (!isActive) return;

          setSelectedEmployee({
            ...empleadoBase,
            ...empleadoFull,
          });

          preloadAvatar(empleadoFull.link_foto);
        } catch (error) {
          logDevelopmentError("Error preloading employee:", error);
        }
      } else if (isActive) {
        setSelectedEmployee(null);
      }
    };

    loadEmployee();

    return () => {
      isActive = false;
    };
  }, [defaultValues, reset, mode, setValue]);

  // Aplicar errores del backend al formulario
  useBackendErrors(backendErrors, setError);

  const handleEmployeeChange = (empleado: Empleado | null) => {
    setSelectedEmployee(empleado);
    setValue("responsable_id", empleado?.id ?? 0);

    if (empleado) {
      setValue("responsable_snapshot", buildResponsableSnapshot(empleado));
    }
  };

  return {
    control,
    errors,
    handleSubmit,
    selectedEmployee,
    handleEmployeeChange,
  };
};
