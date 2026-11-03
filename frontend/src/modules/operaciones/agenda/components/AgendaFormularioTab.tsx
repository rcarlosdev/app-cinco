"use client";

import React, { useState, useMemo } from "react";
import {
  Calendar,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  User,
  MapPin,
  Palette,
  Loader2,
  Info,
} from "lucide-react";
import { ActividadOtConsulta, TecnicoActivoAgenda } from "@/types/agenda.types";
import { agendaService } from "@/services/agenda.service";
import { toast } from "sonner";
import EmployeeSearchInput from "@/components/form/EmployeeSearchInput";
import { Empleado } from "@/types/empleado";
import { getEmpleadoById } from "@/services/empleado.service";
import DatePicker from "@/components/form/date-picker";

const toDateOrUndefined = (value?: string | null): Date | undefined => {
  if (!value) return undefined;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return undefined;
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day), 12);
};

interface AgendaFormularioTabProps {
  tecnicos: TecnicoActivoAgenda[];
  onAgendaGuardada: () => void;
  sedeDefault?: string;
}

const PALETA_COLORES_DEFAULT = [
  { param: "1", color: "#66bb6a", label: "Verde" },
  { param: "2", color: "#42a5f5", label: "Azul" },
  { param: "3", color: "#E67E22", label: "Naranja" },
  { param: "4", color: "#5c6bc0", label: "Índigo" },
  { param: "5", color: "#f44336", label: "Rojo" },
  { param: "6", color: "#90a4ae", label: "Gris" },
  { param: "7", color: "#000000", label: "Negro" },
];

export const AgendaFormularioTab: React.FC<AgendaFormularioTabProps> = ({
  tecnicos,
  onAgendaGuardada,
  sedeDefault = "medellin",
}) => {
  const hoyStr = new Date().toISOString().split("T")[0];

  const [sede, setSede] = useState<string>(sedeDefault);
  const [area, setArea] = useState<string>("");
  const [carpeta, setCarpeta] = useState<string>("");
  const [cedulaTecnico, setCedulaTecnico] = useState<string>("");
  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(null);
  const [ot, setOt] = useState<string>("");
  const [nombreActividad, setNombreActividad] = useState<string>("");
  const [fechaInicio, setFechaInicio] = useState<string>(hoyStr);
  const [fechaFin, setFechaFin] = useState<string>(hoyStr);
  const [latitud, setLatitud] = useState<string>("");
  const [longitud, setLongitud] = useState<string>("");
  const [colorSeleccionado, setColorSeleccionado] = useState<string>("#66bb6a");

  // Estados de Validación de OT
  const [otStatus, setOtStatus] = useState<"idle" | "loading" | "valid" | "invalid">("idle");
  const [otErrorMsg, setOtErrorMsg] = useState<string>("");
  const [otData, setOtData] = useState<ActividadOtConsulta | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Calcular contador de días
  const cantidadDias = useMemo(() => {
    if (!fechaInicio || !fechaFin) return 1;
    const ini = new Date(fechaInicio);
    const fin = new Date(fechaFin);
    const diff = Math.ceil((fin.getTime() - ini.getTime()) / (1000 * 3600 * 24)) + 1;
    return diff > 0 ? diff : 1;
  }, [fechaInicio, fechaFin]);

  // Manejo de cambio en el input de OT (resetea validación si se edita)
  const handleOtChange = (valor: string) => {
    setOt(valor);
    if (otStatus !== "idle") {
      setOtStatus("idle");
      setOtErrorMsg("");
      setOtData(null);
      setNombreActividad("");
      setLatitud("");
      setLongitud("");
      setFechaInicio(hoyStr);
      setFechaFin(hoyStr);
    }
  };

  // Validación y Búsqueda de la OT
  const handleBuscarOt = async () => {
    const otTrim = ot.trim();
    if (!otTrim) {
      setOtStatus("invalid");
      setOtErrorMsg("Debe ingresar una OT/Actividad.");
      return;
    }

    setOtStatus("loading");
    setOtErrorMsg("");

    try {
      const res = await agendaService.buscarActividadPorOt(otTrim);
      if (res.success && res.data) {
        setOtData(res.data);
        setOtStatus("valid");
        setNombreActividad(res.data.tipo_trabajo || res.data.descripcion || res.data.ot);
        setLatitud(res.data.latitud || "");
        setLongitud(res.data.longitud || "");
        if (res.data.responsable_area) setArea(res.data.responsable_area);
        if (res.data.responsable_carpeta) setCarpeta(res.data.responsable_carpeta);
        // Asignar fechas de la actividad
        if (res.data.fecha_inicio) {
          setFechaInicio(res.data.fecha_inicio);
          setFechaFin(res.data.fecha_fin_estimado || res.data.fecha_inicio);
        } else if (res.data.fecha_fin_estimado) {
          setFechaInicio(res.data.fecha_fin_estimado);
          setFechaFin(res.data.fecha_fin_estimado);
        }

        // Preseleccionar técnico si coincide con la lista disponible o buscarlo por ID
        if (res.data.responsable_id) {
          const tecCoincidente = tecnicos.find(
            (t) => t.id === res.data.responsable_id || t.empleado_id === res.data.responsable_id
          );
          if (tecCoincidente) {
            setCedulaTecnico(tecCoincidente.cedula);
            if (tecCoincidente.sede) setSede(tecCoincidente.sede.toLowerCase());
            setSelectedEmployee({
              id: tecCoincidente.id || tecCoincidente.empleado_id || 0,
              cedula: tecCoincidente.cedula,
              nombre: tecCoincidente.nombre,
              apellido: tecCoincidente.apellido || "",
              estado: "activo",
              area: tecCoincidente.area,
              carpeta: tecCoincidente.carpeta,
              cargo: tecCoincidente.cargo || "",
              movil: tecCoincidente.movil || "",
              link_foto: tecCoincidente.link_foto || "",
            } as unknown as Empleado);
          } else {
            getEmpleadoById(res.data.responsable_id)
              .then((emp) => {
                if (emp) {
                  setSelectedEmployee(emp);
                  setCedulaTecnico(String(emp.cedula));
                  const empSede = (emp as any).sede;
                  if (empSede) setSede(String(empSede).toLowerCase());
                  if (emp.area && !res.data.responsable_area) setArea(emp.area);
                  if (emp.carpeta && !res.data.responsable_carpeta) setCarpeta(emp.carpeta);
                }
              })
              .catch(() => {});
          }
        }

        toast.success(`OT ${res.data.ot} verificada correctamente.`);
      } else {
        setOtStatus("invalid");
        setOtData(null);
        setOtErrorMsg(`La OT "${otTrim}" no existe en el módulo de actividades.`);
      }
    } catch (error: any) {
      setOtStatus("invalid");
      setOtData(null);
      setOtErrorMsg(`La OT "${otTrim}" no existe en el sistema de actividades.`);
      toast.error(`La OT "${otTrim}" no fue encontrada.`);
    }
  };

  // Cuando se selecciona un técnico mediante EmployeeSearchInput
  const handleEmployeeChange = (emp: Empleado | null) => {
    setSelectedEmployee(emp);
    if (emp) {
      setCedulaTecnico(String(emp.cedula));
      const empSede = (emp as any).sede;
      if (empSede) setSede(String(empSede).toLowerCase());
      if (emp.area) setArea(emp.area);
      if (emp.carpeta) setCarpeta(emp.carpeta);
    } else {
      setCedulaTecnico("");
    }
  };

  const handleLimpiarForm = () => {
    setOt("");
    setNombreActividad("");
    setSelectedEmployee(null);
    setCedulaTecnico("");
    setArea("");
    setCarpeta("");
    setFechaInicio(hoyStr);
    setFechaFin(hoyStr);
    setLatitud("");
    setLongitud("");
    setOtData(null);
    setOtStatus("idle");
    setOtErrorMsg("");
    setColorSeleccionado("#66bb6a");
  };

  const handleGuardar = async (e: React.FormEvent) => {
    e.preventDefault();

    if (otStatus !== "valid" || !otData) {
      toast.error("Debes validar que la OT exista en el sistema antes de agendar.");
      return;
    }

    if (!selectedEmployee && !cedulaTecnico) {
      toast.warning("Debes seleccionar un técnico.");
      return;
    }
    if (!fechaInicio || !fechaFin) {
      toast.warning("Verifica las fechas de inicio y fin.");
      return;
    }

    // Resolver el responsable_id (ID de auth_user) del técnico seleccionado
    const tecObj = tecnicos.find((t) => t.cedula === (selectedEmployee?.cedula ? String(selectedEmployee.cedula) : cedulaTecnico));
    const responsableIdFinal = selectedEmployee?.id || tecObj?.id || tecObj?.empleado_id || otData.responsable_id;
    const cedulaFinal = selectedEmployee?.cedula ? String(selectedEmployee.cedula) : cedulaTecnico;

    setIsSaving(true);
    try {
      const res = await agendaService.guardarAgenda({
        actividad_id: otData.id,
        responsable_id: responsableIdFinal,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        sede,
        color_hex: colorSeleccionado,
        observacion: otData.descripcion || nombreActividad,
        // Compatibilidad con data_form
        data_form: {
          actividad_id: otData.id,
          responsable_id: responsableIdFinal,
          rad_sede_agen: sede,
          area_agen: area,
          carp_agen: carpeta,
          cc_agen_tecnico_search: cedulaFinal,
          actividad_param: ot.trim().toUpperCase(),
          nombre_param: nombreActividad.trim().toUpperCase(),
          fec_agen_ini: fechaInicio,
          fec_agen_fin: fechaFin,
          color_hex: colorSeleccionado,
        },
      });

      if (res.success) {
        toast.success(res.msg || "La actividad se ha guardado en la agenda del técnico.");
        handleLimpiarForm();
        onAgendaGuardada();
      } else {
        toast.error(res.msg || "Ocurrió un error inesperado al guardar.");
      }
    } catch (error: any) {
      const mensaje = error?.response?.data?.msg || error?.message || "Error al conectar con el servidor.";
      toast.error(mensaje);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="p-4 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <form onSubmit={handleGuardar} className="space-y-4">
        {/* Sede y Dependencias */}
        <div className="grid grid-cols-2 md:grid-cols-12 gap-3 items-center">
          <div className="col-span-2 md:col-span-4 flex items-center space-x-1 bg-gray-100 dark:bg-gray-800/70 p-1 rounded-lg">
            <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 px-2 flex items-center">
              <MapPin className="h-3.5 w-3.5 mr-1" /> Sede:
            </span>
            {(
              [
                { val: "medellin", label: "Medellín" },
                { val: "monteria", label: "Montería" },
                { val: "sincelejo", label: "Sincelejo" },
              ] as const
            ).map((s) => (
              <button
                key={s.val}
                type="button"
                onClick={() => setSede(s.val)}
                className={`flex-1 py-1 px-2 text-xs font-medium rounded-md transition-colors ${
                  sede === s.val
                    ? "bg-brand-600 text-white shadow-xs font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          <div className="col-span-1 md:col-span-4">
            <input
              type="text"
              placeholder="Área de asignación"
              value={area}
              onChange={(e) => setArea(e.target.value)}
              className="w-full text-xs py-1.5 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200"
            />
          </div>

          <div className="col-span-1 md:col-span-4">
            <input
              type="text"
              placeholder="Carpeta de asignación"
              value={carpeta}
              onChange={(e) => setCarpeta(e.target.value)}
              className="w-full text-xs py-1.5 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200"
            />
          </div>
        </div>

        {/* Datos de OT con Validación y Autocompletado */}
        <div className="grid grid-cols-2 md:grid-cols-12 gap-3">
          {/* OT / Actividad con Buscador y Estado */}
          <div className="col-span-2 md:col-span-4">
            <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              OT / Actividad *
            </label>
            <div className="relative flex">
              <input
                type="text"
                placeholder="Ingresa código de OT..."
                value={ot}
                onChange={(e) => handleOtChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleBuscarOt();
                  }
                }}
                onBlur={() => {
                  if (ot.trim() && otStatus === "idle") {
                    handleBuscarOt();
                  }
                }}
                required
                className={`w-full text-xs py-1.5 pl-3 pr-8 rounded-l-md border uppercase transition-colors ${
                  otStatus === "valid"
                    ? "border-emerald-500 bg-emerald-50/20 text-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-emerald-500"
                    : otStatus === "invalid"
                    ? "border-red-500 bg-red-50/20 text-red-900 dark:text-red-200 focus:ring-1 focus:ring-red-500"
                    : "border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-brand-500"
                }`}
              />
              <div className="absolute right-12 top-2 pointer-events-none">
                {otStatus === "valid" && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                {otStatus === "invalid" && <AlertCircle className="h-4 w-4 text-red-600" />}
              </div>
              <button
                type="button"
                onClick={handleBuscarOt}
                disabled={otStatus === "loading" || !ot.trim()}
                title="Validar y consultar OT"
                className="px-3 bg-brand-600 hover:bg-brand-700 text-white rounded-r-md flex items-center justify-center transition-colors disabled:opacity-50"
              >
                {otStatus === "loading" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Search className="h-3.5 w-3.5" />
                )}
              </button>
            </div>

            {/* Mensajes de Validación */}
            {otStatus === "invalid" && (
              <p className="text-[10px] text-red-600 dark:text-red-400 mt-1 font-medium flex items-center">
                <AlertCircle className="h-3 w-3 mr-1 flex-shrink-0" />
                {otErrorMsg || "Debe ingresar una OT/Actividad válida."}
              </p>
            )}
            {otStatus === "valid" && otData && (
              <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 font-medium flex items-center">
                <CheckCircle2 className="h-3 w-3 mr-1 flex-shrink-0" />
                OT verificada
              </p>
            )}
          </div>

          {/* Nombre en Agenda (Autocompletado / Readonly) */}
          <div className="col-span-2 md:col-span-4">
            <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              Nombre / Tipo de Trabajo
            </label>
            <input
              type="text"
              placeholder="Nombre del trabajo / actividad"
              value={nombreActividad}
              readOnly={Boolean(otData)}
              onChange={(e) => setNombreActividad(e.target.value)}
              required
              className={`w-full text-xs py-1.5 px-3 rounded-md border border-gray-300 dark:border-gray-700 ${
                otData
                  ? "bg-gray-100 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300 cursor-default font-medium"
                  : "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-brand-500 uppercase"
              }`}
            />
          </div>

          {/* Coordenadas Longitud y Latitud (Readonly) */}
          <div className="col-span-1 md:col-span-2">
            <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              Coordenada X (Longitud)
            </label>
            <input
              type="text"
              placeholder="-75.567"
              value={longitud}
              readOnly={Boolean(otData && longitud)}
              onChange={(e) => setLongitud(e.target.value)}
              className="w-full text-xs py-1.5 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200"
            />
          </div>

          <div className="col-span-1 md:col-span-2">
            <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              Coordenada Y (Latitud)
            </label>
            <input
              type="text"
              placeholder="6.244"
              value={latitud}
              readOnly={Boolean(otData && latitud)}
              onChange={(e) => setLatitud(e.target.value)}
              className="w-full text-xs py-1.5 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200"
            />
          </div>
        </div>

        {/* Resumen Detallado de la OT Verificada */}
        {otData && (
          <div className="p-3 bg-brand-50 dark:bg-brand-950/40 border border-brand-200 dark:border-brand-800/60 rounded-xl space-y-1.5 text-xs text-brand-900 dark:text-brand-200">
            <div className="flex items-center justify-between border-b border-brand-200/60 dark:border-brand-800/40 pb-1.5">
              <div className="flex items-center space-x-1.5 font-bold">
                <span>OT: {otData.ot}</span>
                <span className="text-gray-400 font-normal">|</span>
                <span className="font-semibold text-brand-700 dark:text-brand-300">
                  {otData.tipo_trabajo || "Sin tipología"}
                </span>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
                {otData.estado}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] pt-0.5">
              <div>
                <span className="font-semibold text-gray-600 dark:text-gray-400 block">Ubicación / Dirección:</span>
                <span className="truncate block font-medium">
                  {otData.direccion ? `📍 ${otData.direccion}` : "Sin dirección registrada"}
                </span>
              </div>
              <div>
                <span className="font-semibold text-gray-600 dark:text-gray-400 block">Zona / Nodo:</span>
                <span className="font-medium">{otData.zona || otData.nodo ? `${otData.zona || ""} ${otData.nodo ? `(Nodo: ${otData.nodo})` : ""}` : "No especificado"}</span>
              </div>
              <div>
                <span className="font-semibold text-gray-600 dark:text-gray-400 block">Responsable Asignado:</span>
                <span className="font-medium">{otData.responsable_nombre || "Sin responsable"}</span>
              </div>
            </div>
          </div>
        )}

        {/* Técnico Asignado y Fechas */}
        <div className="grid grid-cols-2 md:grid-cols-12 gap-3 items-start">
          {/* Técnico Asignado */}
          <div className="col-span-2 md:col-span-4">
            <EmployeeSearchInput
              label="Técnico para Agendar"
              placeholder="Buscar técnico por nombre, cédula o móvil..."
              value={selectedEmployee}
              onChange={handleEmployeeChange}
              required
            />
          </div>

          {/* Fecha Inicio */}
          <div className="col-span-1 md:col-span-3">
            <label htmlFor="agendar_fecha_inicio" className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              <Calendar className="h-3 w-3 inline mr-1" /> Fecha Inicio *
            </label>
            <DatePicker
              id="agendar_fecha_inicio"
              placeholder="Inicio de agenda"
              defaultDate={fechaInicio ? toDateOrUndefined(fechaInicio) : undefined}
              onChange={(dates: Date[] | Date) => {
                const selected = Array.isArray(dates) ? dates[0] : dates;
                if (selected instanceof Date && !isNaN(selected.getTime())) {
                  const y = selected.getFullYear();
                  const m = String(selected.getMonth() + 1).padStart(2, "0");
                  const d = String(selected.getDate()).padStart(2, "0");
                  setFechaInicio(`${y}-${m}-${d}`);
                }
              }}
            />
          </div>

          {/* Fecha Fin */}
          <div className="col-span-1 md:col-span-3">
            <label htmlFor="agendar_fecha_fin" className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1">
              <Calendar className="h-3 w-3 inline mr-1" /> Fecha Fin *
            </label>
            <DatePicker
              id="agendar_fecha_fin"
              placeholder="Fin de agenda"
              defaultDate={fechaFin ? toDateOrUndefined(fechaFin) : undefined}
              onChange={(dates: Date[] | Date) => {
                const selected = Array.isArray(dates) ? dates[0] : dates;
                if (selected instanceof Date && !isNaN(selected.getTime())) {
                  const y = selected.getFullYear();
                  const m = String(selected.getMonth() + 1).padStart(2, "0");
                  const d = String(selected.getDate()).padStart(2, "0");
                  setFechaFin(`${y}-${m}-${d}`);
                }
              }}
            />
          </div>

          {/* Contador de Días */}
          <div className="col-span-2 md:col-span-2">
            <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1 text-center">
              <Clock className="h-3 w-3 inline mr-1" /> Días
            </label>
            <div className="py-1.5 px-3 rounded-md bg-brand-50 dark:bg-brand-950/50 border border-brand-300 dark:border-brand-800 text-brand-700 dark:text-brand-300 font-bold text-center text-xs">
              {cantidadDias} {cantidadDias === 1 ? "día" : "días"}
            </div>
          </div>
        </div>

        {/* Selector de Color de la Actividad */}
        <div>
          <label className="block text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
            <Palette className="h-3.5 w-3.5 inline mr-1 text-gray-500" /> Color de Identificación en Calendario:
          </label>
          <div className="flex flex-wrap items-center gap-2">
            {PALETA_COLORES_DEFAULT.map((item) => (
              <button
                key={item.param}
                type="button"
                onClick={() => setColorSeleccionado(item.color)}
                title={item.label}
                className={`w-7 h-7 rounded-full flex items-center justify-center transition-transform ${
                  colorSeleccionado === item.color
                    ? "ring-2 ring-offset-2 ring-brand-500 scale-110 shadow-md"
                    : "hover:scale-105 opacity-85 hover:opacity-100"
                }`}
                style={{ backgroundColor: item.color }}
              >
                {colorSeleccionado === item.color && <CheckCircle2 className="h-4 w-4 text-white drop-shadow" />}
              </button>
            ))}
          </div>
        </div>

        {/* Acciones */}
        <div className="flex items-center justify-end space-x-3 pt-2 border-t border-gray-100 dark:border-gray-800">
          <button
            type="button"
            onClick={handleLimpiarForm}
            disabled={isSaving}
            className="px-4 py-2 text-xs font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none transition-colors"
          >
            Limpiar Formulario
          </button>
          <button
            type="submit"
            disabled={isSaving || otStatus !== "valid" || !otData}
            title={
              otStatus !== "valid"
                ? "Debes validar una OT existente para poder agendar"
                : "Guardar agendamiento"
            }
            className="inline-flex items-center px-5 py-2 text-xs font-semibold text-white bg-brand-600 rounded-md hover:bg-brand-700 focus:outline-none shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> Guardando...
              </>
            ) : (
              <>
                <Calendar className="h-3.5 w-3.5 mr-2" /> Agendar Actividad
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
