"use client";

import Button from "@/components/ui/button/Button";
import { useActividadFormLogic } from "./ActividadForm.hooks";
import { ActividadFormProps } from "./ActividadForm.types";
import { ActividadFormFields } from "./ActividadFormFields";

const ActividadForm = ({
  defaultValues,
  onSubmit,
  isLoading,
  backendErrors,
  mode = "create",
}: ActividadFormProps) => {
  const {
    control,
    errors,
    handleSubmit,
    selectedEmployee,
    handleEmployeeChange,
  } = useActividadFormLogic({
    defaultValues,
    backendErrors,
    mode,
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
      <ActividadFormFields
        control={control}
        errors={errors}
        mode={mode}
        selectedEmployee={selectedEmployee}
        onEmployeeChange={handleEmployeeChange}
      />

      <div className="mt-6 flex justify-end gap-3">
        <Button type="submit" size="sm" disabled={isLoading}>
          Guardar
        </Button>
      </div>
    </form>
  );
};

export default ActividadForm;

