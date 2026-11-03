"use client";

import React, { useState, useMemo } from "react";
import { AgendaItem, TecnicoActivoAgenda } from "@/types/agenda.types";
import { Empleado } from "@/types/empleado";
import {
  Calendar,
  User,
  Briefcase,
  MapPin,
  Clock,
  X,
  Edit3,
  Trash2,
  CalendarX,
  Save,
  AlertTriangle,
  Loader2,
  Palette,
  Check,
  Hourglass,
  Info,
  Tag,
} from "lucide-react";
import { toast } from "sonner";
import { agendaService } from "@/services/agenda.service";
import { Modal } from "@/components/ui/modal";
import Label from "@/components/form/Label";
import Input from "@/components/form/input/InputField";
import Select from "@/components/form/Select";
import TextArea from "@/components/form/input/TextArea";
import Button from "@/components/ui/button/Button";
import EmployeeSearchInput from "@/components/form/EmployeeSearchInput";
import DatePicker from "@/components/form/date-picker";
import { getEmpleadoByCedula, getEmpleadoById } from "@/services/empleado.service";
import { getFestivoColombia } from "@/utils/festivos";

interface AgendaCalendarioGridProps {
  mes: string;
  yyyy: string;
  agendamientos: AgendaItem[];
  tecnicos: TecnicoActivoAgenda[];
  isLoading: boolean;
  onAgendaActualizada?: () => void;
}

const DIAS_SEMANA = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];

const PALETA_COLORES = [
  { param: "1", color: "#66bb6a", label: "Verde" },
  { param: "2", color: "#42a5f5", label: "Azul" },
  { param: "3", color: "#E67E22", label: "Naranja" },
  { param: "4", color: "#5c6bc0", label: "Índigo" },
  { param: "5", color: "#f44336", label: "Rojo" },
  { param: "6", color: "#90a4ae", label: "Gris" },
  { param: "7", color: "#000000", label: "Negro" },
];

const ESTADOS_ACTIVIDAD = [
  { value: "pendiente", label: "Pendiente" },
  { value: "en_progreso", label: "En Progreso" },
  { value: "completada", label: "Completada" },
  { value: "cancelada", label: "Cancelada" },
  { value: "pausada", label: "Pausada" },
  { value: "agendado", label: "Agendado" },
];

export const AgendaCalendarioGrid: React.FC<AgendaCalendarioGridProps> = ({
  mes,
  yyyy,
  agendamientos,
  tecnicos,
  isLoading,
  onAgendaActualizada,
}) => {
  const [actividadDetalle, setActividadDetalle] = useState<AgendaItem | null>(null);

  // Estados para el modo de edición
  const [modoEdicion, setModoEdicion] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [confirmarEliminar, setConfirmarEliminar] = useState<boolean>(false);

  // Campos del formulario de edición reciclados
  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(null);
  const [editFechaInicio, setEditFechaInicio] = useState<string>("");
  const [editFechaFin, setEditFechaFin] = useState<string>("");
  const [editColor, setEditColor] = useState<string>("#66bb6a");
  const [editEstado, setEditEstado] = useState<string>("pendiente");
  const [editTipoTrabajo, setEditTipoTrabajo] = useState<string>("");
  const [editDescripcion, setEditDescripcion] = useState<string>("");
  const [editDireccion, setEditDireccion] = useState<string>("");
  const [editZona, setEditZona] = useState<string>("");
  const [editNodo, setEditNodo] = useState<string>("");
  const [editLongitud, setEditLongitud] = useState<string>("");
  const [editLatitud, setEditLatitud] = useState<string>("");
  const [hoveredActKey, setHoveredActKey] = useState<string | null>(null);

  // Estado para el tooltip flotante estilizado
  const [tooltipState, setTooltipState] = useState<{
    act: AgendaItem;
    tec: TecnicoActivoAgenda;
    dia: {
      numero: number;
      diaSemana: string;
      esFinDeSemana: boolean;
      esFestivo: boolean;
      nombreFestivo: string | null;
      esNoHabil: boolean;
      esHoy: boolean;
      fechaYmd: string;
    };
    x: number;
    y: number;
  } | null>(null);

  const MESES_ABR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

  const calcularDiasDuracion = (fIniStr?: string | null, fFinStr?: string | null): number => {
    if (!fIniStr || !fFinStr) return 1;
    const s1 = String(fIniStr).split("T")[0].split(" ")[0];
    const s2 = String(fFinStr).split("T")[0].split(" ")[0];
    const d1 = new Date(s1);
    const d2 = new Date(s2);
    if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 1;
    const diffTime = Math.abs(d2.getTime() - d1.getTime());
    const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24)) + 1;
    return isNaN(diffDays) ? 1 : diffDays;
  };

  const formatFechaBonita = (dateStr?: string | null): string => {
    if (!dateStr) return "";
    const clean = String(dateStr).split("T")[0].split(" ")[0];
    const parts = clean.split("-");
    if (parts.length === 3) {
      const dia = parseInt(parts[2], 10);
      const mesIdx = parseInt(parts[1], 10) - 1;
      if (mesIdx >= 0 && mesIdx < 12) {
        return `${dia} ${MESES_ABR[mesIdx]}`;
      }
    }
    return clean;
  };

  const formatPeriodoYDuracion = (fIniStr?: string | null, fFinStr?: string | null): string => {
    const fIni = formatFechaBonita(fIniStr);
    const fFin = formatFechaBonita(fFinStr);
    const dias = calcularDiasDuracion(fIniStr, fFinStr);
    const diasStr = dias > 1 ? ` (${dias} días)` : ` (1 día)`;

    if (!fIni && !fFin) return "No registrado";
    if (!fFin || fIni === fFin) return `${fIni || fFin}${diasStr}`;
    return `${fIni} - ${fFin}${diasStr}`;
  };

  const getEstadoTextColor = (estado?: string | null): string => {
    const est = (estado || "PENDIENTE").trim().toUpperCase();
    if (est.includes("COMPLET") || est.includes("FINALIZ") || est.includes("REALIZ")) {
      return "text-emerald-600 dark:text-emerald-400";
    }
    if (est.includes("CANCEL") || est.includes("ANULAD")) {
      return "text-red-600 dark:text-red-400";
    }
    if (est.includes("PROGRES") || est.includes("PROCESO") || est.includes("INICIAD") || est.includes("EJECUC")) {
      return "text-blue-600 dark:text-blue-400";
    }
    if (est.includes("PAUS") || est.includes("SUSPEND")) {
      return "text-orange-600 dark:text-orange-400";
    }
    // PENDIENTE, AGENDADO, PROGRAMADO en amarillo / ámbar
    return "text-amber-500 dark:text-amber-400";
  };

  const getEstadoBadgeClasses = (estado?: string | null): string => {
    const est = (estado || "PENDIENTE").trim().toUpperCase();
    if (est.includes("COMPLET") || est.includes("FINALIZ") || est.includes("REALIZ")) {
      return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-800/60";
    }
    if (est.includes("CANCEL") || est.includes("ANULAD")) {
      return "bg-red-50 text-red-700 dark:bg-red-950/70 dark:text-red-300 border border-red-200/60 dark:border-red-800/60";
    }
    if (est.includes("PROGRES") || est.includes("PROCESO") || est.includes("INICIAD") || est.includes("EJECUC")) {
      return "bg-blue-50 text-blue-700 dark:bg-blue-950/70 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60";
    }
    if (est.includes("PAUS") || est.includes("SUSPEND")) {
      return "bg-orange-50 text-orange-700 dark:bg-orange-950/70 dark:text-orange-300 border border-orange-200/60 dark:border-orange-800/60";
    }
    // PENDIENTE, AGENDADO, PROGRAMADO
    return "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300 border border-amber-200/60 dark:border-amber-800/60";
  };

  const handleMouseMoveBar = (
    e: React.MouseEvent,
    act: AgendaItem,
    tec: TecnicoActivoAgenda,
    dia: {
      numero: number;
      diaSemana: string;
      esFinDeSemana: boolean;
      esFestivo: boolean;
      nombreFestivo: string | null;
      esNoHabil: boolean;
      esHoy: boolean;
      fechaYmd: string;
    }
  ) => {
    const mouseX = e.clientX;
    const mouseY = e.clientY;
    const tooltipWidth = 350;
    const tooltipHeight = 280;

    let posX = mouseX + 14;
    let posY = mouseY + 14;

    if (typeof window !== "undefined") {
      if (posX + tooltipWidth > window.innerWidth - 12) {
        posX = Math.max(12, mouseX - tooltipWidth - 14);
      }
      if (posY + tooltipHeight > window.innerHeight - 12) {
        posY = Math.max(12, mouseY - tooltipHeight - 14);
      }
    }

    setTooltipState({
      act,
      tec,
      dia,
      x: posX,
      y: posY,
    });
  };

  // Calcular días del mes seleccionado
  const diasMes = useMemo(() => {
    const m = parseInt(mes, 10);
    const y = parseInt(yyyy, 10);
    if (isNaN(m) || isNaN(y)) return [];

    const totalDias = new Date(y, m, 0).getDate();
    const lista = [];
    const hoy = new Date();
    const hoyYmd = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;

    for (let d = 1; d <= totalDias; d++) {
      const fechaObj = new Date(y, m - 1, d);
      const diaSemanaNum = fechaObj.getDay();
      const fechaYmd = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const festivoInfo = getFestivoColombia(fechaYmd);
      const esFestivoDia = festivoInfo !== null;
      const esNoHabil = diaSemanaNum === 0 || esFestivoDia;

      lista.push({
        numero: d,
        diaSemana: DIAS_SEMANA[diaSemanaNum],
        esFinDeSemana: diaSemanaNum === 0, // Solo el domingo es fin de semana no hábil (sábados habilitados)
        esFestivo: esFestivoDia,
        nombreFestivo: festivoInfo?.nombre || null,
        esNoHabil,
        fechaYmd,
        esHoy: fechaYmd === hoyYmd,
      });
    }
    return lista;
  }, [mes, yyyy]);

  // Agrupar agendamientos por técnico
  const agendaPorTecnico = useMemo(() => {
    const mapa = new Map<string, AgendaItem[]>();

    agendamientos.forEach((item) => {
      const ced = String(item.cedula || "").trim();
      const empId = item.empleado_id ? String(item.empleado_id).trim() : "";

      if (ced) {
        if (!mapa.has(ced)) mapa.set(ced, []);
        mapa.get(ced)!.push(item);
      }
      if (empId && empId !== ced) {
        if (!mapa.has(empId)) mapa.set(empId, []);
        mapa.get(empId)!.push(item);
      }
    });

    return mapa;
  }, [agendamientos]);

  // Lista de técnicos que se mostrarán en la tabla
  const tecnicosAMostrar = useMemo<TecnicoActivoAgenda[]>(() => {
    if (tecnicos.length > 0) return tecnicos;
    const cedulasUnicas = Array.from(new Set(agendamientos.map((a) => String(a.cedula || a.empleado_id || ""))));
    return cedulasUnicas.filter(Boolean).map((ced) => {
      const item = agendamientos.find((a) => String(a.cedula) === ced || String(a.empleado_id) === ced);
      const numId = typeof item?.id === "number" ? item.id : Number(item?.id) || null;
      const numEmpId = typeof item?.empleado_id === "number" ? item.empleado_id : Number(item?.empleado_id) || null;
      return {
        id: numId,
        empleado_id: numEmpId,
        cedula: ced,
        nombre: item?.nombre || item?.datos?.legacy_responsable_nombre || `Técnico ${ced}`,
        sede: item?.sede || "",
        area: item?.area || "",
        carpeta: item?.carpeta || "",
      };
    });
  }, [tecnicos, agendamientos]);

  // Manejador para abrir el modal en modo lectura
  const handleAbrirDetalle = async (item: AgendaItem) => {
    setActividadDetalle(item);
    setModoEdicion(false);
    setConfirmarEliminar(false);

    // Enriquecer datos de la actividad si faltan detalles como zona, coordenadas o dirección
    const otBusqueda = item.ot || item.actividad;
    if (otBusqueda && (!item.ubicacion_zona || !item.latitud || !item.longitud || !item.ubicacion_direccion)) {
      try {
        const resOt = await agendaService.buscarActividadPorOt(otBusqueda);
        if (resOt.success && resOt.data) {
          const d = resOt.data;
          setActividadDetalle((prev) => {
            if (!prev || (prev.ot !== otBusqueda && prev.actividad !== otBusqueda)) return prev;
            return {
              ...prev,
              tipo_trabajo: prev.tipo_trabajo || d.tipo_trabajo,
              detalle_descripcion: prev.detalle_descripcion || d.descripcion,
              ubicacion_direccion: prev.ubicacion_direccion || d.direccion,
              ubicacion_zona: prev.ubicacion_zona || d.zona,
              ubicacion_nodo: prev.ubicacion_nodo || d.nodo,
              longitud: prev.longitud || d.longitud,
              latitud: prev.latitud || d.latitud,
            };
          });
        }
      } catch (e) {
        console.warn("No se pudieron cargar datos adicionales de la OT:", e);
      }
    }
  };

  const handleCerrarModal = () => {
    setActividadDetalle(null);
    setModoEdicion(false);
    setConfirmarEliminar(false);
  };

  const formatYmd = (dateStr?: string | null): string => {
    if (!dateStr) return "";
    const clean = String(dateStr).trim().split("T")[0].split(" ")[0];
    if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) return clean;
    const d = new Date(dateStr);
    if (!isNaN(d.getTime())) {
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    }
    return clean;
  };

  const toDateOrUndefined = (value?: string | null): Date | undefined => {
    if (!value) return undefined;
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (!match) return undefined;
    const [, year, month, day] = match;
    return new Date(Number(year), Number(month) - 1, Number(day), 12);
  };

  // Manejador para activar modo edición
  const handleIniciarEdicion = async () => {
    if (!actividadDetalle) return;

    // Buscar técnico correspondiente
    const cedBuscada = String(actividadDetalle.cedula || actividadDetalle.empleado_id || "");
    const tecMatch = tecnicos.find(
      (t) => String(t.cedula) === cedBuscada || String(t.id) === cedBuscada || String(t.empleado_id) === cedBuscada
    );

    const initialFoto = actividadDetalle.responsable_link_foto || actividadDetalle.link_foto || tecMatch?.link_foto || "";

    if (tecMatch) {
      setSelectedEmployee({
        id: tecMatch.id || tecMatch.empleado_id || 0,
        cedula: tecMatch.cedula,
        nombre: tecMatch.nombre,
        apellido: tecMatch.apellido || "",
        estado: "activo",
        area: tecMatch.area,
        carpeta: tecMatch.carpeta,
        cargo: tecMatch.cargo || "",
        movil: tecMatch.movil || "",
        link_foto: initialFoto,
      } as unknown as Empleado);
    } else {
      setSelectedEmployee({
        id: typeof actividadDetalle.empleado_id === "number" ? actividadDetalle.empleado_id : 0,
        cedula: cedBuscada,
        nombre: actividadDetalle.nombre || `Técnico ${cedBuscada}`,
        apellido: "",
        estado: "activo",
        area: actividadDetalle.area || "",
        carpeta: actividadDetalle.carpeta || "",
        link_foto: initialFoto,
      } as unknown as Empleado);
    }

    // Consultar ficha completa del empleado para cargar foto y datos oficiales
    if (cedBuscada) {
      getEmpleadoByCedula(cedBuscada)
        .then((emp) => {
          if (emp) {
            setSelectedEmployee(emp);
          }
        })
        .catch(() => {
          const numId = Number(actividadDetalle.empleado_id);
          if (numId) {
            getEmpleadoById(numId)
              .then((emp) => {
                if (emp) setSelectedEmployee(emp);
              })
              .catch(() => {});
          }
        });
    }

    const iniFormateada = formatYmd(actividadDetalle.fecha_inicio || actividadDetalle.fecha);
    const finFormateada = formatYmd(actividadDetalle.fecha_fin || actividadDetalle.fecha_inicio || actividadDetalle.fecha);

    setEditFechaInicio(iniFormateada);
    setEditFechaFin(finFormateada);
    setEditColor(actividadDetalle.observaciones_dia?.color || actividadDetalle.color || actividadDetalle.datos?.color || "#66bb6a");
    setEditEstado((actividadDetalle.estado || "pendiente").toLowerCase());
    setEditTipoTrabajo(actividadDetalle.nombre_act || actividadDetalle.tipo_trabajo || actividadDetalle.ot || actividadDetalle.actividad || "");
    setEditDescripcion(actividadDetalle.detalle_descripcion || actividadDetalle.observacion || "");
    setEditDireccion(actividadDetalle.ubicacion_direccion || actividadDetalle.direccion || "");
    setEditZona(actividadDetalle.ubicacion_zona || actividadDetalle.zona || "");
    setEditNodo(actividadDetalle.ubicacion_nodo || actividadDetalle.nodo || "");
    setEditLongitud(actividadDetalle.longitud || actividadDetalle.datos?.longitud || "");
    setEditLatitud(actividadDetalle.latitud || actividadDetalle.datos?.latitud || "");
    setModoEdicion(true);
    setConfirmarEliminar(false);

    // Si faltan datos en la actividad y tiene OT, buscar en backend para prellenar
    const otBusqueda = actividadDetalle.ot || actividadDetalle.actividad;
    if (otBusqueda && (!actividadDetalle.ubicacion_zona || !actividadDetalle.latitud || !actividadDetalle.longitud)) {
      try {
        const resOt = await agendaService.buscarActividadPorOt(otBusqueda);
        if (resOt.success && resOt.data) {
          const d = resOt.data;
          if (d.tipo_trabajo) setEditTipoTrabajo((prev) => prev || d.tipo_trabajo);
          if (d.descripcion) setEditDescripcion((prev) => prev || d.descripcion);
          if (d.direccion) setEditDireccion((prev) => prev || d.direccion);
          if (d.zona) setEditZona((prev) => prev || d.zona);
          if (d.nodo) setEditNodo((prev) => prev || d.nodo);
          if (d.longitud) setEditLongitud((prev) => prev || d.longitud);
          if (d.latitud) setEditLatitud((prev) => prev || d.latitud);
        }
      } catch (e) {
        console.warn("No se pudieron cargar datos adicionales de la OT:", e);
      }
    }
  };

  const handleCancelarEdicion = () => {
    setModoEdicion(false);
    setConfirmarEliminar(false);
  };

  // Guardar cambios editados
  const handleGuardarCambios = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actividadDetalle) return;

    if (!editFechaInicio || !editFechaFin) {
      toast.warning("Las fechas de inicio y fin son obligatorias.");
      return;
    }
    if (editFechaFin < editFechaInicio) {
      toast.warning("La fecha fin no puede ser anterior a la fecha de inicio.");
      return;
    }

    const respIdFinal = selectedEmployee?.id || actividadDetalle.empleado_id;
    const cedulaFinal = selectedEmployee?.cedula ? String(selectedEmployee.cedula) : String(actividadDetalle.cedula);

    setIsSaving(true);
    try {
      const res = await agendaService.guardarAgenda({
        id: actividadDetalle.id,
        actividad_id: actividadDetalle.actividad_id,
        responsable_id: typeof respIdFinal === "number" && respIdFinal > 0 ? respIdFinal : undefined,
        fecha_inicio: editFechaInicio,
        fecha_fin: editFechaFin,
        sede: actividadDetalle.sede || "medellin",
        color_hex: editColor,
        observacion: editDescripcion,
        estado: editEstado.toUpperCase(),
        tipo_trabajo: editTipoTrabajo,
        descripcion: editDescripcion,
        direccion: editDireccion,
        zona: editZona,
        nodo: editNodo,
        longitud: editLongitud,
        latitud: editLatitud,
        data_form: {
          id: actividadDetalle.id,
          actividad_id: actividadDetalle.actividad_id,
          cc_agen_tecnico_search: cedulaFinal,
          actividad_param: actividadDetalle.ot || actividadDetalle.actividad,
          nombre_param: editTipoTrabajo,
          fec_agen_ini: editFechaInicio,
          fec_agen_fin: editFechaFin,
          color_hex: editColor,
          estado: editEstado.toUpperCase(),
          descripcion_actividad_param: editDescripcion,
          direccion_actividad_param: editDireccion,
          zona_actividad_param: editZona,
          nodo_actividad_param: editNodo,
          longitud_param: editLongitud,
          latitud_param: editLatitud,
        },
      });

      if (res.success) {
        toast.success(res.msg || "Agendamiento y actividad actualizados correctamente.");
        handleCerrarModal();
        if (onAgendaActualizada) {
          onAgendaActualizada();
        }
      } else {
        toast.error(res.msg || "Error al actualizar el agendamiento.");
      }
    } catch (error: any) {
      const msg = error?.response?.data?.msg || error?.message || "Error al conectar con el servidor.";
      toast.error(msg);
    } finally {
      setIsSaving(false);
    }
  };

  // Cancelar agendamiento (eliminar de la agenda)
  const handleEliminarAgenda = async () => {
    if (!actividadDetalle || !actividadDetalle.id) {
      toast.error("No se puede cancelar: ID de agenda no válido.");
      return;
    }

    setIsDeleting(true);
    try {
      const res = await agendaService.eliminarAgenda(actividadDetalle.id);
      if (res.success) {
        toast.success(res.msg || "Agendamiento cancelado correctamente.");
        handleCerrarModal();
        if (onAgendaActualizada) {
          onAgendaActualizada();
        }
      } else {
        toast.error(res.msg || "Error al cancelar el agendamiento.");
      }
    } catch (error: any) {
      const msg = error?.response?.data?.msg || error?.message || "Error al cancelar el agendamiento.";
      toast.error(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  // Calcular cantidad de días en modo edición
  const diasCalculadosEdicion = useMemo(() => {
    if (!editFechaInicio || !editFechaFin) return 1;
    const ini = new Date(editFechaInicio);
    const fin = new Date(editFechaFin);
    const diff = Math.ceil((fin.getTime() - ini.getTime()) / (1000 * 3600 * 24)) + 1;
    return diff > 0 ? diff : 1;
  }, [editFechaInicio, editFechaFin]);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 bg-white dark:bg-gray-900">
        <div className="text-center space-y-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600 mx-auto"></div>
          <p className="text-xs text-gray-500 font-medium">Cargando cronograma de agendas...</p>
        </div>
      </div>
    );
  }

  if (tecnicosAMostrar.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 bg-white dark:bg-gray-900">
        <div className="text-center max-w-sm space-y-2">
          <Calendar className="h-10 w-10 text-gray-300 dark:text-gray-600 mx-auto" />
          <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300">Sin agendamientos</h4>
          <p className="text-xs text-gray-500">
            No se encontraron actividades agendadas con los filtros seleccionados para este mes.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-[72vh] md:h-full overflow-auto bg-white dark:bg-gray-900 relative min-w-0">
      <table className="w-full border-collapse text-xs select-none table-fixed">
        {/* Encabezado del calendario con días */}
        <thead className="sticky top-0 z-20 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-xs">
          <tr>
            <th className="p-1.5 md:p-2.5 text-left font-bold text-gray-700 dark:text-gray-300 w-28 min-w-[110px] max-w-[110px] md:w-64 md:min-w-[240px] md:max-w-[260px] border-r border-gray-200 dark:border-gray-700 sticky top-0 left-0 bg-gray-100 dark:bg-gray-800 z-30">
              <span className="hidden md:inline">Técnico / Responsable</span>
              <span className="inline md:hidden text-[11px]">Técnico</span>
            </th>
            {diasMes.map((dia) => (
              <th
                key={dia.numero}
                title={dia.esFestivo ? `Festivo: ${dia.nombreFestivo}` : dia.esFinDeSemana ? "Domingo (No hábil)" : undefined}
                className={`sticky top-0 z-20 p-1 text-center font-semibold w-12 min-w-[48px] max-w-[48px] border-r border-gray-200/70 dark:border-gray-700/70 transition-colors ${
                  dia.esHoy
                    ? "bg-brand-100 text-brand-900 dark:bg-brand-950 dark:text-brand-200 font-bold"
                    : dia.esNoHabil
                    ? "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500"
                    : "bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                }`}
              >
                <div className="text-[10px] leading-tight opacity-75">{dia.diaSemana}</div>
                <div className="text-xs leading-tight">{dia.numero}</div>
              </th>
            ))}
          </tr>
        </thead>

        {/* Filas por técnico */}
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800 font-medium">
          {tecnicosAMostrar.map((tec) => {
            const itemsTec = Array.from(
              new Set([
                ...(agendaPorTecnico.get(String(tec.cedula || "").trim()) || []),
                ...(tec.empleado_id ? agendaPorTecnico.get(String(tec.empleado_id).trim()) || [] : []),
                ...(tec.id ? agendaPorTecnico.get(String(tec.id).trim()) || [] : []),
              ])
            ).sort((a, b) => {
              const fIniA = formatYmd(a.fecha_inicio || a.fecha);
              const fIniB = formatYmd(b.fecha_inicio || b.fecha);
              if (fIniA !== fIniB) return fIniA.localeCompare(fIniB);

              const fFinA = formatYmd(a.fecha_fin || a.fecha_inicio || a.fecha);
              const fFinB = formatYmd(b.fecha_fin || b.fecha_inicio || b.fecha);
              if (fFinA !== fFinB) return fFinB.localeCompare(fFinA); // Mayor duración arriba

              return String(a.id || a.actividad_id || a.ot || "").localeCompare(
                String(b.id || b.actividad_id || b.ot || "")
              );
            });

            // Asignador de carriles fijos (Gantt Track Allocator) para línea horizontal recta continua
            const trackEnds: string[] = [];
            const itemTrackMap = new Map<string, number>();

            itemsTec.forEach((act, actIdx) => {
              const actKey = String(act.id || act.actividad_id || `${act.ot}-${act.fecha_inicio || act.fecha}-${actIdx}`);
              const fIni = formatYmd(act.fecha_inicio || act.fecha);
              const fFin = formatYmd(act.fecha_fin || act.fecha_inicio || act.fecha);

              let assignedTrack = -1;
              for (let t = 0; t < trackEnds.length; t++) {
                if (trackEnds[t] < fIni) {
                  assignedTrack = t;
                  trackEnds[t] = fFin;
                  break;
                }
              }

              if (assignedTrack === -1) {
                assignedTrack = trackEnds.length;
                trackEnds.push(fFin);
              }

              itemTrackMap.set(actKey, assignedTrack);
            });

            const totalTracks = Math.max(1, trackEnds.length);
            const trackIndexes = Array.from({ length: totalTracks }, (_, i) => i);

            return (
              <tr key={tec.cedula || tec.id} className="hover:bg-gray-50/70 dark:hover:bg-gray-800/40 transition-colors">
                {/* Columna fija: Nombre del técnico */}
                <td className="p-1.5 md:p-2.5 border-r border-gray-200 dark:border-gray-800 sticky left-0 bg-white dark:bg-gray-900 z-10 w-28 min-w-[110px] max-w-[110px] md:w-64 md:min-w-[240px] md:max-w-[260px] align-middle">
                  <div className="font-bold text-gray-900 dark:text-gray-100 truncate text-[11px] md:text-xs max-w-[95px] md:max-w-[200px]" title={tec.nombre}>
                    {tec.nombre || `Técnico ${tec.cedula}`}
                  </div>
                  <div className="text-[10px] md:text-[11px] text-gray-500 flex flex-col md:flex-row md:items-center md:justify-between mt-0.5">
                    <span className="truncate">CC: {tec.cedula}</span>
                    <span className="hidden md:inline truncate max-w-[90px]">{tec.area || tec.sede}</span>
                  </div>
                </td>

                {/* Celdas de días del mes con carriles fijos continuos */}
                {diasMes.map((dia) => {
                  return (
                    <td
                      key={dia.numero}
                      className={`p-0 text-center relative border-r border-gray-100 dark:border-gray-800/70 w-12 min-w-[48px] max-w-[48px] overflow-hidden align-top ${
                        dia.esHoy
                          ? "bg-brand-50/40 dark:bg-brand-950/20"
                          : dia.esNoHabil
                          ? "bg-gray-50/60 dark:bg-gray-800/30"
                          : ""
                      }`}
                    >
                      {trackIndexes.map((trackIdx) => {
                        const act = itemsTec.find((item, itemIdx) => {
                          const actKey = String(item.id || item.actividad_id || `${item.ot}-${item.fecha_inicio || item.fecha}-${itemIdx}`);
                          if (itemTrackMap.get(actKey) !== trackIdx) return false;
                          const fIni = formatYmd(item.fecha_inicio || item.fecha);
                          const fFin = formatYmd(item.fecha_fin || item.fecha_inicio || item.fecha);
                          return dia.fechaYmd >= fIni && dia.fechaYmd <= fFin;
                        });

                        if (!act) {
                          return (
                            <div
                              key={`empty-${trackIdx}`}
                              className="h-6 my-0.5 w-full opacity-0 pointer-events-none select-none"
                              aria-hidden="true"
                            />
                          );
                        }

                        const bgCol =
                          act.observaciones_dia?.color ||
                          act.color ||
                          act.datos?.color ||
                          "#66bb6a";

                        const tituloVisual =
                          act.nombre_act ||
                          act.tipo_trabajo ||
                          act.datos?.nombre_act ||
                          act.ot ||
                          act.actividad ||
                          "Actividad";

                        const fIni = formatYmd(act.fecha_inicio || act.fecha);
                        const fFin = formatYmd(act.fecha_fin || act.fecha_inicio || act.fecha);

                        const esMismoDia = !fFin || fIni === fFin || (dia.fechaYmd === fIni && dia.fechaYmd === fFin);
                        const esInicio = dia.fechaYmd === fIni;
                        const esFin = dia.fechaYmd === fFin;

                        const actIdKey = String(act.id || act.actividad_id || `${act.ot}-${fIni}`);
                        const isHovered = hoveredActKey === actIdKey;

                        const roundedClass = esMismoDia || (esInicio && esFin)
                          ? "rounded-md mx-0.5"
                          : esInicio
                          ? "rounded-l-md ml-0.5 mr-0"
                          : esFin
                          ? "rounded-r-md ml-0 mr-0.5"
                          : "rounded-none mx-0";

                        return (
                          <div
                            key={`act-${trackIdx}-${actIdKey}`}
                            onClick={() => handleAbrirDetalle(act)}
                            onMouseEnter={(e) => {
                              setHoveredActKey(actIdKey);
                              handleMouseMoveBar(e, act, tec, dia);
                            }}
                            onMouseMove={(e) => handleMouseMoveBar(e, act, tec, dia)}
                            onMouseLeave={() => {
                              setHoveredActKey(null);
                              setTooltipState(null);
                            }}
                            className={`h-6 my-0.5 w-auto overflow-hidden flex items-center justify-start text-[10px] font-bold text-white cursor-pointer select-none transition-all ${roundedClass} ${
                              isHovered
                                ? "brightness-110 shadow-sm ring-1 ring-white/60 scale-y-105 z-10"
                                : "hover:brightness-105 shadow-2xs"
                            }`}
                            style={{ backgroundColor: bgCol }}
                          >
                            {esInicio || esMismoDia ? (
                              <span className="block w-full max-w-full truncate px-1 whitespace-nowrap text-left font-semibold tracking-tight overflow-hidden text-ellipsis">
                                {tituloVisual}
                              </span>
                            ) : (
                              <span className="w-full h-full block opacity-0 pointer-events-none">&nbsp;</span>
                            )}
                          </div>
                        );
                      })}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Tooltip Flotante Minimalista con Jerarquía Optimizada Label vs. Valor */}
      {tooltipState && (
        <div
          className="fixed z-50 pointer-events-none transition-all duration-75 ease-out shadow-xl shadow-gray-300/40 dark:shadow-2xl dark:shadow-black/70 rounded-xl border border-gray-200/90 dark:border-gray-800 bg-white/95 dark:bg-gray-900/95 p-3.5 text-xs backdrop-blur-md min-w-[280px] max-w-[360px] select-none space-y-2.5"
          style={{
            left: `${tooltipState.x}px`,
            top: `${tooltipState.y}px`,
          }}
        >
          {/* Header: Día y OT Badge */}
          <div className="flex items-center justify-between gap-2 border-b border-gray-100 dark:border-gray-800 pb-2">
            <span className="font-bold text-gray-900 dark:text-white text-xs tracking-tight">
              Día {tooltipState.dia.numero} ({tooltipState.dia.diaSemana})
            </span>
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-bold text-white shadow-xs shrink-0"
              style={{
                backgroundColor:
                  tooltipState.act.observaciones_dia?.color ||
                  tooltipState.act.color ||
                  tooltipState.act.datos?.color ||
                  "#66bb6a",
              }}
            >
              {tooltipState.act.ot || tooltipState.act.actividad || "OT"}
            </span>
          </div>

          {/* Nombre / Tipo de Actividad (Completo sin cortes) */}
          <div>
            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 block uppercase tracking-wider mb-0.5">
              Actividad
            </span>
            <span className="font-bold text-gray-900 dark:text-white text-xs block break-words whitespace-normal leading-snug">
              {tooltipState.act.nombre_act ||
                tooltipState.act.tipo_trabajo ||
                tooltipState.act.datos?.nombre_act ||
                tooltipState.act.ot ||
                "Sin Tipo"}
            </span>
          </div>

          {/* Lista compacta Label y Valor alineados a la izquierda */}
          <div className="space-y-1.5 text-[11px] text-left">
            {/* Período y Duración Unificados */}
            <div className="flex items-start gap-1.5 text-left">
              <span className="text-slate-500 dark:text-slate-400 shrink-0">Período:</span>
              <span className="font-medium text-gray-900 dark:text-white break-words">
                {formatPeriodoYDuracion(
                  tooltipState.act.fecha_inicio || tooltipState.act.fecha,
                  tooltipState.act.fecha_fin || tooltipState.act.fecha_inicio || tooltipState.act.fecha
                )}
              </span>
            </div>

            {/* Técnico */}
            <div className="flex items-start gap-1.5 text-left">
              <span className="text-slate-500 dark:text-slate-400 shrink-0">Técnico:</span>
              <span className="font-medium text-gray-900 dark:text-white break-words whitespace-normal leading-tight">
                {tooltipState.act.nombre ||
                  tooltipState.act.responsable_nombre ||
                  tooltipState.tec.nombre ||
                  `CC ${tooltipState.act.cedula}`}
              </span>
            </div>

            {/* Ubicación si existe */}
            {(tooltipState.act.ubicacion_direccion ||
              tooltipState.act.direccion ||
              tooltipState.act.ubicacion_zona ||
              tooltipState.act.zona) && (
              <div className="flex items-start gap-1.5 text-left">
                <span className="text-slate-500 dark:text-slate-400 shrink-0">Ubicación:</span>
                <span className="font-medium text-gray-900 dark:text-white break-words whitespace-normal leading-tight">
                  {tooltipState.act.ubicacion_direccion || tooltipState.act.direccion || ""}
                  {tooltipState.act.ubicacion_zona || tooltipState.act.zona
                    ? ` • ${tooltipState.act.ubicacion_zona || tooltipState.act.zona}`
                    : ""}
                </span>
              </div>
            )}

            {/* Estado */}
            <div className="flex items-center gap-1.5 text-left">
              <span className="text-slate-500 dark:text-slate-400 shrink-0">Estado:</span>
              <span className={`font-semibold uppercase ${getEstadoTextColor(tooltipState.act.estado)}`}>
                {tooltipState.act.estado || "PENDIENTE"}
              </span>
            </div>
          </div>

          {/* Observación / Detalle Completo si existe */}
          {(tooltipState.act.detalle_descripcion || tooltipState.act.observacion) && (
            <div className="border-t border-gray-100 dark:border-gray-800 pt-1.5 text-gray-600 dark:text-gray-300 text-[10.5px] italic break-words whitespace-normal leading-snug">
              {tooltipState.act.detalle_descripcion || tooltipState.act.observacion}
            </div>
          )}
        </div>
      )}

      {/* Modal Reutilizable con el Sistema de Diseño Oficial de Actividades */}
      {actividadDetalle && (
        <Modal
          isOpen={Boolean(actividadDetalle)}
          onClose={handleCerrarModal}
          className="max-w-xl p-5"
        >
          {/* Header del Modal */}
          <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-3 mb-4">
            <div className="flex items-center space-x-2.5">
              <div
                className="w-4 h-4 rounded-full shrink-0 shadow-xs"
                style={{
                  backgroundColor: modoEdicion
                    ? editColor
                    : actividadDetalle.observaciones_dia?.color ||
                      actividadDetalle.color ||
                      "#66bb6a",
                }}
              />
              <div>
                <h3 className="text-base font-semibold text-gray-800 dark:text-white/90">
                  {modoEdicion
                    ? "Editar Agendamiento / Actividad"
                    : actividadDetalle.nombre_act ||
                      actividadDetalle.tipo_trabajo ||
                      actividadDetalle.ot ||
                      actividadDetalle.actividad}
                </h3>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  OT: {actividadDetalle.ot || actividadDetalle.actividad}
                </p>
              </div>
            </div>
          </div>

          {/* Confirmación de Cancelación de Agenda */}
          {confirmarEliminar ? (
            <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-xl p-4 space-y-3 mb-2">
              <div className="flex items-start space-x-3">
                <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
                <div>
                  <h5 className="text-sm font-semibold text-red-900 dark:text-red-200">
                    ¿Confirmas cancelar este agendamiento?
                  </h5>
                  <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                    Esta acción retirará la programación del técnico en el calendario. La actividad y su OT no serán borradas.
                  </p>
                </div>
              </div>
              <div className="flex justify-end space-x-2 pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setConfirmarEliminar(false)}
                  disabled={isDeleting}
                >
                  Volver
                </Button>
                <button
                  type="button"
                  onClick={handleEliminarAgenda}
                  disabled={isDeleting}
                  className="px-3 py-1.5 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center space-x-1.5 transition-colors shadow-theme-xs disabled:opacity-50"
                >
                  {isDeleting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                      Cancelando...
                    </>
                  ) : (
                    <>
                      <CalendarX className="h-4 w-4 mr-1" />
                      Sí, cancelar agenda
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : modoEdicion ? (
            /* --- FORMULARIO DE EDICIÓN CON COMPONENTES OFICIALES --- */
            <form onSubmit={handleGuardarCambios} className="space-y-4">
              {/* Técnico Responsable (EmployeeSearchInput oficial) */}
              <div>
                <EmployeeSearchInput
                  label="Técnico Responsable *"
                  placeholder="Buscar técnico por nombre, cédula o móvil..."
                  value={selectedEmployee}
                  onChange={(emp) => setSelectedEmployee(emp)}
                  required
                />
              </div>

              {/* Fila 1: Nombre y Descripción */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="edit_tipo_trabajo">
                    Nombre <strong className="text-red-400">*</strong>
                  </Label>
                  <Input
                    id="edit_tipo_trabajo"
                    value={editTipoTrabajo}
                    onChange={(e) => setEditTipoTrabajo(e.target.value)}
                    placeholder="Ej. ACOMETIDA"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="edit_descripcion">Descripción</Label>
                  <Input
                    id="edit_descripcion"
                    value={editDescripcion}
                    onChange={(e) => setEditDescripcion(e.target.value)}
                    placeholder="Ej. NATURA REAL TORRE"
                  />
                </div>
              </div>

              {/* Fila 2: Dirección */}
              <div>
                <Label htmlFor="edit_direccion">
                  <MapPin className="h-3.5 w-3.5 inline mr-1 text-gray-500" /> Dirección
                </Label>
                <Input
                  id="edit_direccion"
                  value={editDireccion}
                  onChange={(e) => setEditDireccion(e.target.value)}
                  placeholder="Ej. CL 10B 6-39 LA CEJA"
                />
              </div>

              {/* Fila 3: Zona y Nodo */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="edit_zona">Zona</Label>
                  <Input
                    id="edit_zona"
                    value={editZona}
                    onChange={(e) => setEditZona(e.target.value)}
                    placeholder="Ej. LA CEJA"
                  />
                </div>
                <div>
                  <Label htmlFor="edit_nodo">Nodo</Label>
                  <Input
                    id="edit_nodo"
                    value={editNodo}
                    onChange={(e) => setEditNodo(e.target.value)}
                    placeholder="Ej. LJAF1E"
                  />
                </div>
              </div>

              {/* Fila 4: Longitud y Latitud (Coordenadas) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="edit_longitud">Longitud (Coordenada X)</Label>
                  <Input
                    id="edit_longitud"
                    value={editLongitud}
                    onChange={(e) => setEditLongitud(e.target.value)}
                    placeholder="Ej. 6.0301959"
                  />
                </div>
                <div>
                  <Label htmlFor="edit_latitud">Latitud (Coordenada Y)</Label>
                  <Input
                    id="edit_latitud"
                    value={editLatitud}
                    onChange={(e) => setEditLatitud(e.target.value)}
                    placeholder="Ej. -75.4331435"
                  />
                </div>
              </div>

              {/* Fila 5: Fechas de Inicio y Fin con DatePicker Oficial */}
              <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
                <div className="sm:col-span-5">
                  <Label htmlFor="edit_fecha_inicio">
                    Fecha Inicio <strong className="text-red-400">*</strong>
                  </Label>
                  <DatePicker
                    id="edit_fecha_inicio"
                    placeholder="Inicio de agenda"
                    defaultDate={editFechaInicio ? toDateOrUndefined(editFechaInicio) : undefined}
                    onChange={(dates: Date[] | Date) => {
                      const selected = Array.isArray(dates) ? dates[0] : dates;
                      if (selected instanceof Date && !isNaN(selected.getTime())) {
                        const y = selected.getFullYear();
                        const m = String(selected.getMonth() + 1).padStart(2, "0");
                        const d = String(selected.getDate()).padStart(2, "0");
                        setEditFechaInicio(`${y}-${m}-${d}`);
                      }
                    }}
                  />
                </div>

                <div className="sm:col-span-5">
                  <Label htmlFor="edit_fecha_fin">
                    Fecha Fin Estimada <strong className="text-red-400">*</strong>
                  </Label>
                  <DatePicker
                    id="edit_fecha_fin"
                    placeholder="Fin estimado de agenda"
                    defaultDate={editFechaFin ? toDateOrUndefined(editFechaFin) : undefined}
                    onChange={(dates: Date[] | Date) => {
                      const selected = Array.isArray(dates) ? dates[0] : dates;
                      if (selected instanceof Date && !isNaN(selected.getTime())) {
                        const y = selected.getFullYear();
                        const m = String(selected.getMonth() + 1).padStart(2, "0");
                        const d = String(selected.getDate()).padStart(2, "0");
                        setEditFechaFin(`${y}-${m}-${d}`);
                      }
                    }}
                  />
                </div>

                <div className="sm:col-span-2">
                  <div className="h-8 flex items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-950/50 border border-brand-300 dark:border-brand-800 text-brand-700 dark:text-brand-300 font-bold text-center text-xs">
                    {diasCalculadosEdicion} {diasCalculadosEdicion === 1 ? "día" : "días"}
                  </div>
                </div>
              </div>

              {/* Fila 6: Estado y Color */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-start">
                <div>
                  <Label htmlFor="edit_estado">Estado de la Actividad</Label>
                  <Select
                    options={ESTADOS_ACTIVIDAD}
                    value={editEstado}
                    onChange={(val) => setEditEstado(val)}
                  />
                </div>

                <div>
                  <Label>
                    <Palette className="h-3.5 w-3.5 inline mr-1 text-gray-500" /> Color en Calendario
                  </Label>
                  <div className="flex items-center space-x-2 h-8">
                    {PALETA_COLORES.map((pal) => (
                      <button
                        key={pal.param}
                        type="button"
                        onClick={() => setEditColor(pal.color)}
                        title={pal.label}
                        className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                          editColor.toLowerCase() === pal.color.toLowerCase()
                            ? "ring-2 ring-offset-2 ring-brand-500 scale-110 shadow-xs"
                            : "hover:scale-105 opacity-80 hover:opacity-100"
                        }`}
                        style={{ backgroundColor: pal.color }}
                      >
                        {editColor.toLowerCase() === pal.color.toLowerCase() && (
                          <Check className="h-3.5 w-3.5 text-white" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Botones de Acción */}
              <div className="pt-3 border-t border-gray-100 dark:border-gray-800 flex justify-end space-x-2">
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  onClick={handleCancelarEdicion}
                  disabled={isSaving}
                >
                  Cancelar
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  disabled={isSaving}
                  startIcon={isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                >
                  {isSaving ? "Guardando..." : "Guardar Cambios"}
                </Button>
              </div>
            </form>
          ) : (
            /* --- MODO CONSULTA / DETALLE CON INFORMACIÓN COMPLETA --- */
            <div className="space-y-3.5 text-sm text-gray-700 dark:text-gray-300">
              {/* Encabezado: Nombre y Descripción */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-gray-50 dark:bg-gray-800/60 p-3 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block mb-0.5">
                    Nombre / Tipo de Actividad
                  </span>
                  <p className="font-bold text-gray-900 dark:text-white text-sm">
                    {actividadDetalle.nombre_act || actividadDetalle.tipo_trabajo || actividadDetalle.ot || "Sin nombre"}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800/60 p-3 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block mb-0.5">
                    Descripción
                  </span>
                  <p className="font-medium text-gray-800 dark:text-gray-200 text-sm">
                    {actividadDetalle.detalle_descripcion || actividadDetalle.observacion || "Sin descripción"}
                  </p>
                </div>
              </div>

              {/* Dirección */}
              <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                  <MapPin className="h-3.5 w-3.5 inline mr-1 text-gray-400 shrink-0" /> Dirección
                </span>
                <p className="text-gray-800 dark:text-gray-200 mt-0.5 font-medium">
                  {actividadDetalle.ubicacion_direccion || actividadDetalle.direccion || "Sin dirección registrada"}
                </p>
              </div>

              {/* Zona y Nodo */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    Zona
                  </span>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 mt-0.5">
                    {actividadDetalle.ubicacion_zona || actividadDetalle.zona || "N/A"}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    Nodo
                  </span>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 mt-0.5">
                    {actividadDetalle.ubicacion_nodo || actividadDetalle.nodo || "N/A"}
                  </p>
                </div>
              </div>

              {/* Coordenadas (Longitud y Latitud) */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    Longitud (Coordenada X)
                  </span>
                  <p className="font-mono text-xs font-medium text-gray-800 dark:text-gray-200 mt-0.5">
                    {actividadDetalle.longitud || "No registrada"}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    Latitud (Coordenada Y)
                  </span>
                  <p className="font-mono text-xs font-medium text-gray-800 dark:text-gray-200 mt-0.5">
                    {actividadDetalle.latitud || "No registrada"}
                  </p>
                </div>
              </div>

              {/* Fechas de Inicio y Fin */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    <Calendar className="h-3.5 w-3.5 inline mr-1 text-gray-400" /> Fecha Inicio
                  </span>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 mt-0.5">
                    {actividadDetalle.fecha_inicio || actividadDetalle.fecha}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    <Calendar className="h-3.5 w-3.5 inline mr-1 text-gray-400" /> Fecha Fin Estimada
                  </span>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 mt-0.5">
                    {actividadDetalle.fecha_fin || actividadDetalle.fecha_inicio}
                  </p>
                </div>
              </div>

              {/* Técnico Asignado y Estado */}
              <div className="grid grid-cols-2 gap-3 items-center">
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block">
                    <User className="h-3.5 w-3.5 inline mr-1 text-gray-400" /> Técnico Asignado
                  </span>
                  <p className="font-semibold text-gray-900 dark:text-gray-100 mt-0.5">
                    {actividadDetalle.nombre || `CC ${actividadDetalle.cedula}`}
                  </p>
                  <span className="text-[11px] text-gray-500">Cédula: {actividadDetalle.cedula}</span>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800/40 p-2.5 rounded-lg border border-gray-100 dark:border-gray-800 flex flex-col justify-center">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 block mb-1">
                    Estado de la Actividad
                  </span>
                  <span
                    className={`inline-block px-2.5 py-1 rounded-md font-bold uppercase text-xs w-fit ${getEstadoBadgeClasses(
                      actividadDetalle.estado
                    )}`}
                  >
                    {actividadDetalle.estado || "PENDIENTE"}
                  </span>
                </div>
              </div>

              {/* Footer del Modal con Botones del Sistema */}
              <div className="pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setConfirmarEliminar(true)}
                  className="px-3 py-1.5 text-xs font-semibold text-red-600 hover:text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 rounded-lg flex items-center transition-colors"
                >
                  <CalendarX className="h-4 w-4 mr-1.5" />
                  Cancelar Agenda
                </button>

                <div className="flex items-center space-x-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCerrarModal}
                  >
                    Cerrar
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={handleIniciarEdicion}
                    startIcon={<Edit3 className="h-4 w-4" />}
                  >
                    Editar
                  </Button>
                </div>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
};
