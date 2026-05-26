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
    watch,
    formState: { errors },
  } = useForm<ActividadFormData>({
    resolver: zodResolver(ActividadSchema),
    defaultValues,
  });

  const watchOts = watch("ots");
  const watchFechaInicioPadre = watch("fecha_inicio");
  const watchFechaFinPadre = watch("fecha_fin_estimado");

  // Efecto reactivo para el recálculo e integración de fechas entre OTs Hijas y Actividad Padre
  useEffect(() => {
    if (mode === "create") {
      // En modo creación: las fechas del Padre se ingresan manualmente
      // Al ingresar OTs Hijas, si el rango de alguna Hija excede el del Padre, este se extiende reactivamente (reextensión)
      if (watchOts && Array.isArray(watchOts) && watchOts.length > 0) {
        const hijasInicioDates = watchOts
          .map((item) => item?.fecha_inicio)
          .filter((d): d is string => !!d && !isNaN(Date.parse(d)));

        const hijasFinDates = watchOts
          .map((item) => item?.fecha_fin)
          .filter((d): d is string => !!d && !isNaN(Date.parse(d)));

        if (hijasInicioDates.length > 0 && watchFechaInicioPadre) {
          const minHijas = hijasInicioDates.reduce((min, curr) => {
            return new Date(curr) < new Date(min) ? curr : min;
          });
          if (new Date(minHijas) < new Date(watchFechaInicioPadre)) {
            setValue("fecha_inicio", minHijas, { shouldValidate: true });
          }
        }

        if (hijasFinDates.length > 0 && watchFechaFinPadre) {
          const maxHijas = hijasFinDates.reduce((max, curr) => {
            return new Date(curr) > new Date(max) ? curr : max;
          });
          if (new Date(maxHijas) > new Date(watchFechaFinPadre)) {
            setValue("fecha_fin_estimado", maxHijas, { shouldValidate: true });
          }
        }
      }
    } else {
      // En modo edición: las fechas del Padre se autocalculan estrictamente a partir del min/max de sus OTs hijas
      if (watchOts && Array.isArray(watchOts) && watchOts.length > 0) {
        const validInicioDates = watchOts
          .map((item) => item?.fecha_inicio)
          .filter((d): d is string => !!d && !isNaN(Date.parse(d)));

        const validFinDates = watchOts
          .map((item) => item?.fecha_fin)
          .filter((d): d is string => !!d && !isNaN(Date.parse(d)));

        if (validInicioDates.length > 0) {
          const minInicio = validInicioDates.reduce((min, curr) => {
            return new Date(curr) < new Date(min) ? curr : min;
          });
          setValue("fecha_inicio", minInicio, { shouldValidate: true });
        }

        if (validFinDates.length > 0) {
          const maxFin = validFinDates.reduce((max, curr) => {
            return new Date(curr) > new Date(max) ? curr : max;
          });
          setValue("fecha_fin_estimado", maxFin, { shouldValidate: true });
        }
      }
    }
  }, [watchOts, watchFechaInicioPadre, watchFechaFinPadre, setValue, mode]);

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
