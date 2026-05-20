import { Controller, FieldPath } from "react-hook-form";
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

export const ActividadFormFields = ({
  control,
  errors,
  mode,
  selectedEmployee,
  onEmployeeChange,
}: ActividadFormFieldsProps) => {
  return (
    <div className="grid max-h-96 grid-cols-1 gap-5 overflow-auto pr-2 sm:grid-cols-2">
      <div className="col-span-2">
        <FieldLabel htmlFor="ots" field="ots">
          OTs Relacionadas
        </FieldLabel>
        <Controller
          name="ots"
          control={control}
          render={({ field }) => (
            <TextArea
              id="ots"
              name="ots"
              placeholder={"Ingresa una OT por línea\nOT-2026-001\nOT-2026-002"}
              value={Array.isArray(field.value) ? field.value.join("\n") : ""}
              onChange={(event) => {
                const values = event.target.value
                  .split(/\r?\n|,/)
                  .map((value) => value.trim());
                field.onChange(values);
              }}
              error={!!errors.ots}
              hint={
                errors.ots
                  ? String(errors.ots.message)
                  : "Puedes separar varias OTs por línea o por coma"
              }
              rows={3}
            />
          )}
        />
      </div>

      <div className="col-span-2 md:col-span-1">
        <Controller
          name="responsable_id"
          control={control}
          render={({ field }) => (
            <EmployeeSearchInput
              label="Responsable"
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
      
      <div className="col-span-2 md:col-span-1">
        <FieldLabel htmlFor="fecha_inicio_actividad" field="fecha_inicio">
          Fecha de Inicio
        </FieldLabel>
        <Controller
          name="fecha_inicio"
          control={control}
          render={({ field }) => (
            <DatePicker
              id="fecha_actividad"
              placeholder="Selecciona una fecha"
              defaultDate={field.value}
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

      {mode === "edit" && (
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

      <div className="col-span-2 md:col-span-1">
        <FieldLabel
          htmlFor="fecha_fin_estimado"
          field="fecha_fin_estimado"
        >
          Fecha de Fin Estimada
        </FieldLabel>
        <Controller
          name="fecha_fin_estimado"
          control={control}
          render={({ field }) => (
            <DatePicker
              id="fecha_fin_estimado"
              placeholder="Selecciona una fecha"
              defaultDate={toDateOrUndefined(field.value)}
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
