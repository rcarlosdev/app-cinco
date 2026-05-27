import { Controller, FieldPath, useFieldArray } from "react-hook-form";
import Label from "@/components/form/Label";
import Input from "@/components/form/input/InputField";
import DatePicker from "@/components/form/date-picker";
import TextArea from "@/components/form/input/TextArea";
import Select from "@/components/form/Select";
import EmployeeSearchInput from "@/components/form/EmployeeSearchInput";
import {
  ActividadFormData,
  isActividadFieldRequired,
} from "@/schemas/actividades.schema";
import { ActividadFormFieldsProps } from "./ActividadForm.types";
import {
  getDateFromPicker,
  toDateOrUndefined,
  toIsoDate,
} from "./ActividadForm.utils";

const ESTADO_OPTIONS = [
  { value: "pendiente", label: "Pendiente" },
  { value: "en_progreso", label: "En Progreso" },
  { value: "completada", label: "Completada" },
  { value: "cancelada", label: "Cancelada" },
  { value: "pausada", label: "Pausada" },
  { value: "reprogramada", label: "Reprogramada" },
];

const RequiredMark = () => <strong className="text-red-400">*</strong>;

interface FieldLabelProps {
  htmlFor: string;
  field: FieldPath<ActividadFormData>;
  children: React.ReactNode;
}

const FieldLabel = ({ htmlFor, field, children }: FieldLabelProps) => (
  <Label htmlFor={htmlFor}>
    {children}
    {isActividadFieldRequired(field) && (
      <>
        {" "}
        <RequiredMark />
      </>
    )}
  </Label>
);

const getArrayFieldErrorMessage = (value: unknown): string | undefined => {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  const maybeError = value as {
    message?: unknown;
    root?: { message?: unknown };
  };

  if (typeof maybeError.message === "string") {
    return maybeError.message;
  }

  if (typeof maybeError.root?.message === "string") {
    return maybeError.root.message;
  }

  return undefined;
};

export const ActividadFormFields = ({
  control,
  errors,
  mode,
  selectedEmployee,
  onEmployeeChange,
}: ActividadFormFieldsProps) => {
  const { fields, append, remove } = useFieldArray({
    control,
    name: "ots",
  });

  const isEditMode = mode === "edit";
  const otsErrorMessage = getArrayFieldErrorMessage(errors.ots);

  return (
    <div className="grid max-h-96 grid-cols-1 gap-5 overflow-auto pr-2 sm:grid-cols-2">
      {/* 1. OT / Actividad Padre y Responsable */}
      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="ot_padre" field="ots">
          OT / Actividad Padre {!isEditMode && <RequiredMark />}
        </FieldLabel>
        <Controller
          name="ots.0.ot"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="ot_padre"
              placeholder="Ingresa la OT Padre"
              disabled={isEditMode}
              readOnly={isEditMode}
              error={!!errors.ots?.[0]?.ot}
              hint={errors.ots?.[0]?.ot?.message}
            />
          )}
        />
      </div>

      <div className="col-span-2">
        <Controller
          name="responsable_id"
          control={control}
          render={({ field }) => (
            <EmployeeSearchInput
              label="JEFE, LIDER, COORDINADOR"
              placeholder="Buscar responsable..."
              value={selectedEmployee}
              onChange={(empleado) => {
                onEmployeeChange(empleado);
                field.onChange(empleado?.id ?? 0);
              }}
              required={isActividadFieldRequired("responsable_id")}
              error={!!errors.responsable_id}
              hint={
                errors.responsable_id
                  ? String(errors.responsable_id.message)
                  : "Busca por nombre, cédula, cargo o móvil"
              }
              name="responsable_id"
            />
          )}
        />
      </div>

      {/* 2. Área y Carpeta del Responsable */}
      <div className="col-span-2 md:col-span-1">
        <Label htmlFor="area_responsable">Área del Responsable</Label>
        <Input
          type="text"
          id="area_responsable"
          placeholder="Área del responsable"
          value={selectedEmployee?.area || ""}
          disabled
          readOnly
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <Label htmlFor="carpeta_responsable">Carpeta del Responsable</Label>
        <Input
          type="text"
          id="carpeta_responsable"
          placeholder="Carpeta del responsable"
          value={selectedEmployee?.carpeta || ""}
          disabled
          readOnly
        />
      </div>

      {/* 3. Sección OTs Hijas (Subformulario dinámico premium) */}
      <div className="col-span-2 border-b border-gray-200 dark:border-gray-700 pb-2 mt-2">
        <h3 className="text-base font-semibold text-gray-800 dark:text-white flex items-center gap-2">
          <span>OTs Hijas (Órdenes de Trabajo Relacionadas)</span>
          <span className="text-xs font-normal text-gray-500 dark:text-gray-400">
            Cada OT hija debe tener su propio rango de tiempo
          </span>
        </h3>
      </div>

      <div className="col-span-2 space-y-4">
        {fields.map((fieldItem, index) => {
          // Omitimos el primero (índice 0) porque se renderiza arriba como la OT Padre
          if (index === 0) return null;

          return (
            <div
              key={fieldItem.id}
              className="relative p-5 pr-12 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/40 hover:shadow-md transition-all duration-300 grid grid-cols-1 sm:grid-cols-3 gap-4 items-start"
            >
              {/* Botón de eliminar flotante absoluto en la esquina superior derecha */}
              <div className="absolute top-3 right-3">
                <button
                  type="button"
                  onClick={() => remove(index)}
                  className="p-1.5 rounded-lg border flex items-center justify-center transition-all duration-200 border-red-200 text-red-500 hover:bg-red-50 hover:text-red-600 dark:border-red-900/30 dark:text-red-400 dark:hover:bg-red-950/20 active:scale-95"
                  title="Eliminar OT Hija"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>

              {/* Código OT */}
              <div className="col-span-1">
                <FieldLabel
                  htmlFor={`ots.${index}.ot`}
                  field={`ots.${index}.ot`}
                >
                  OT Hija #{index}
                </FieldLabel>
                <Controller
                  name={`ots.${index}.ot`}
                  control={control}
                  render={({ field: inputField }) => (
                    <Input
                      {...inputField}
                      id={`ots.${index}.ot`}
                      placeholder="Ej. OT-2026-001"
                      error={!!errors.ots?.[index]?.ot}
                      hint={errors.ots?.[index]?.ot?.message}
                    />
                  )}
                />
              </div>

              {/* Fecha Inicio */}
              <div className="col-span-1">
                <FieldLabel
                  htmlFor={`ots.${index}.fecha_inicio`}
                  field={`ots.${index}.fecha_inicio`}
                >
                  Fecha Inicio
                </FieldLabel>
                <Controller
                  name={`ots.${index}.fecha_inicio`}
                  control={control}
                  render={({ field: inputField }) => (
                    <DatePicker
                      id={`ots.${index}.fecha_inicio`}
                      placeholder="Inicio de OT"
                      defaultDate={inputField.value ? toDateOrUndefined(inputField.value) : undefined}
                      onChange={(dates: Date[] | Date) => {
                        const value = getDateFromPicker(dates);
                        inputField.onChange(toIsoDate(value));
                      }}
                      error={!!errors.ots?.[index]?.fecha_inicio}
                      hint={errors.ots?.[index]?.fecha_inicio?.message}
                    />
                  )}
                />
              </div>

              {/* Fecha Fin */}
              <div className="col-span-1">
                <FieldLabel
                  htmlFor={`ots.${index}.fecha_fin`}
                  field={`ots.${index}.fecha_fin`}
                >
                  Fecha Fin
                </FieldLabel>
                <Controller
                  name={`ots.${index}.fecha_fin`}
                  control={control}
                  render={({ field: inputField }) => (
                    <DatePicker
                      id={`ots.${index}.fecha_fin`}
                      placeholder="Fin de OT"
                      defaultDate={inputField.value ? toDateOrUndefined(inputField.value) : undefined}
                      onChange={(dates: Date[] | Date) => {
                        const value = getDateFromPicker(dates);
                        inputField.onChange(toIsoDate(value));
                      }}
                      error={!!errors.ots?.[index]?.fecha_fin}
                      hint={errors.ots?.[index]?.fecha_fin?.message}
                    />
                  )}
                />
              </div>
            </div>
          );
        })}

        <div className="flex justify-start">
          <button
            type="button"
            onClick={() => append({ ot: "", fecha_inicio: "", fecha_fin: "" })}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900/50 hover:border-indigo-300 active:scale-95 transition-all duration-200"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.5"
                d="M12 4v16m8-8H4"
              />
            </svg>
            Agregar OT Hija
          </button>
        </div>

        {otsErrorMessage && (
          <p className="text-xs text-red-500 font-medium mt-1">
            {otsErrorMessage}
          </p>
        )}
      </div>

      {/* 4. Fechas del Padre y Estado */}
      <div className="col-span-2 border-t border-gray-200 dark:border-gray-700 mt-2 pt-4">
        <h4 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {isEditMode ? "Detalles de la Actividad Padre (Autocalculados)" : "Tiempos de la Actividad Padre"}
        </h4>
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="fecha_inicio_actividad" field="fecha_inicio">
          Fecha de Inicio (Padre)
        </FieldLabel>
        <Controller
          name="fecha_inicio"
          control={control}
          render={({ field }) => (
            <DatePicker
              id="fecha_actividad"
              placeholder={isEditMode ? "Autocalculado a partir de OTs" : "Selecciona fecha de inicio"}
              defaultDate={field.value}
              disabled={isEditMode}
              onChange={(dates: Date[] | Date) => {
                const value = getDateFromPicker(dates);
                field.onChange(toIsoDate(value));
              }}
              error={!!errors.fecha_inicio}
              hint={
                errors.fecha_inicio ? errors.fecha_inicio.message : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel
          htmlFor="fecha_fin_estimado"
          field="fecha_fin_estimado"
        >
          Fecha de Fin Estimada (Padre)
        </FieldLabel>
        <Controller
          name="fecha_fin_estimado"
          control={control}
          render={({ field }) => (
            <DatePicker
              id="fecha_fin_estimado"
              placeholder={isEditMode ? "Autocalculado a partir de OTs" : "Selecciona fecha de fin"}
              defaultDate={toDateOrUndefined(field.value)}
              disabled={isEditMode}
              onChange={(dates: Date[] | Date) => {
                const value = getDateFromPicker(dates);
                field.onChange(toIsoDate(value));
              }}
              error={!!errors.fecha_fin_estimado}
              hint={
                errors.fecha_fin_estimado
                  ? errors.fecha_fin_estimado.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="fecha_fin_real" field="fecha_fin_real">
          Fecha de Fin Real
        </FieldLabel>
        <Controller
          name="fecha_fin_real"
          control={control}
          render={({ field }) => (
            <DatePicker
              id="fecha_fin_real"
              placeholder="Selecciona una fecha"
              defaultDate={toDateOrUndefined(field.value)}
              onChange={(dates: Date[] | Date) => {
                const value = getDateFromPicker(dates);
                field.onChange(toIsoDate(value));
              }}
              error={!!errors.fecha_fin_real}
              hint={
                errors.fecha_fin_real
                  ? errors.fecha_fin_real.message
                  : undefined
              }
            />
          )}
        />
      </div>

      {isEditMode && (
        <div className="col-span-2 md:col-span-1">
          <FieldLabel htmlFor="estado_actividad" field="estado">
            Estado
          </FieldLabel>
          <Controller
            name="estado"
            control={control}
            render={({ field }) => (
              <Select
                options={ESTADO_OPTIONS}
                placeholder="Selecciona un estado"
                value={field.value || ""}
                onChange={field.onChange}
                error={!!errors.estado}
                hint={errors.estado ? String(errors.estado.message) : undefined}
              />
            )}
          />
        </div>
      )}

      {/* 5. Tipo de Actividad, Descripción y Ubicación */}
      <div className="col-span-2 border-t border-gray-200 dark:border-gray-700 mt-2 pt-4">
        <h4 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Información Adicional y Ubicación
        </h4>
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="tipo_actividad" field="detalle.tipo_trabajo">
          Tipo de Actividad
        </FieldLabel>
        <Controller
          name="detalle.tipo_trabajo"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="tipo_actividad"
              name="detalle.tipo_trabajo"
              placeholder="Tipo de actividad"
              error={!!errors.detalle?.tipo_trabajo}
              hint={
                errors.detalle?.tipo_trabajo
                  ? errors.detalle.tipo_trabajo.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2">
        <FieldLabel htmlFor="descripcion" field="detalle.descripcion">
          Descripción
        </FieldLabel>
        <Controller
          name="detalle.descripcion"
          control={control}
          render={({ field }) => (
            <TextArea
              {...field}
              id="descripcion"
              name="detalle.descripcion"
              placeholder="Descripción de la actividad"
              error={!!errors.detalle?.descripcion}
              hint={
                errors.detalle?.descripcion
                  ? errors.detalle.descripcion.message
                  : undefined
              }
              rows={2}
            />
          )}
        />
      </div>

      <div className="col-span-2">
        <FieldLabel htmlFor="ubicacion" field="ubicacion.direccion">
          Dirección
        </FieldLabel>
        <Controller
          name="ubicacion.direccion"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="ubicacion"
              name="ubicacion.direccion"
              placeholder="Dirección de la actividad"
              error={!!errors.ubicacion?.direccion}
              hint={
                errors.ubicacion?.direccion
                  ? errors.ubicacion.direccion.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="coordenada_x" field="ubicacion.coordenada_x">
          Latitud / Coordenada X
        </FieldLabel>
        <Controller
          name="ubicacion.coordenada_x"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="coordenada_x"
              name="ubicacion.coordenada_x"
              placeholder="Ej: 6.212698"
              error={!!errors.ubicacion?.coordenada_x}
              hint={
                errors.ubicacion?.coordenada_x
                  ? errors.ubicacion.coordenada_x.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="coordenada_y" field="ubicacion.coordenada_y">
          Longitud / Coordenada Y
        </FieldLabel>
        <Controller
          name="ubicacion.coordenada_y"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="coordenada_y"
              name="ubicacion.coordenada_y"
              placeholder="Ej: -75.593246"
              error={!!errors.ubicacion?.coordenada_y}
              hint={
                errors.ubicacion?.coordenada_y
                  ? errors.ubicacion.coordenada_y.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="zona" field="ubicacion.zona">
          Zona
        </FieldLabel>
        <Controller
          name="ubicacion.zona"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="zona"
              name="ubicacion.zona"
              placeholder="Zona de la actividad"
              error={!!errors.ubicacion?.zona}
              hint={
                errors.ubicacion?.zona
                  ? errors.ubicacion.zona.message
                  : undefined
              }
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="nodo" field="ubicacion.nodo">
          Nodo
        </FieldLabel>
        <Controller
          name="ubicacion.nodo"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              type="text"
              id="nodo"
              name="ubicacion.nodo"
              placeholder="Nodo de la actividad"
              error={!!errors.ubicacion?.nodo}
              hint={
                errors.ubicacion?.nodo
                  ? errors.ubicacion.nodo.message
                  : undefined
              }
            />
          )}
        />
      </div>
    </div>
  );
};
