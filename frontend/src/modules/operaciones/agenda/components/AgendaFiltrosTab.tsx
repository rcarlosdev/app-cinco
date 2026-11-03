"use client";

import React, { useMemo, useState, useEffect } from "react";
import { Search, Eraser, MapPin, Calendar, Briefcase, Folder } from "lucide-react";
import { FiltrosAgendaState, SedeOption, TecnicoActivoAgenda } from "@/types/agenda.types";
import EmployeeSearchInput from "@/components/form/EmployeeSearchInput";
import { Empleado } from "@/types/empleado";
import { getEmpleadoByCedula, getEmpleadoById } from "@/services/empleado.service";

interface AgendaFiltrosTabProps {
  filtros: FiltrosAgendaState;
  setFiltros: React.Dispatch<React.SetStateAction<FiltrosAgendaState>>;
  tecnicos: TecnicoActivoAgenda[];
  areasDisponibles: string[];
  carpetasDisponibles: string[];
  onBuscar: () => void;
  onLimpiar: () => void;
  isLoading?: boolean;
}

const MESES = [
  { val: "01", label: "Ene" },
  { val: "02", label: "Feb" },
  { val: "03", label: "Mar" },
  { val: "04", label: "Abr" },
  { val: "05", label: "May" },
  { val: "06", label: "Jun" },
  { val: "07", label: "Jul" },
  { val: "08", label: "Ago" },
  { val: "09", label: "Sep" },
  { val: "10", label: "Oct" },
  { val: "11", label: "Nov" },
  { val: "12", label: "Dic" },
];

export const AgendaFiltrosTab: React.FC<AgendaFiltrosTabProps> = ({
  filtros,
  setFiltros,
  tecnicos,
  areasDisponibles,
  carpetasDisponibles,
  onBuscar,
  onLimpiar,
  isLoading = false,
}) => {
  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(null);

  const aniosDisponibles = useMemo(() => {
    const anioActual = new Date().getFullYear();
    return [anioActual - 2, anioActual - 1, anioActual, anioActual + 1];
  }, []);

  // Sincronizar el empleado seleccionado con el filtro de cédula (ej. clics en panel lateral o botón limpiar)
  useEffect(() => {
    if (!filtros.cedula) {
      setSelectedEmployee(null);
      return;
    }
    if (selectedEmployee && String(selectedEmployee.cedula) === String(filtros.cedula) && selectedEmployee.link_foto) {
      return;
    }
    const tec = tecnicos.find((t) => String(t.cedula).trim() === String(filtros.cedula).trim());
    const initialFoto = tec?.link_foto || "";

    if (tec) {
      setSelectedEmployee({
        id: tec.id || tec.empleado_id || 0,
        cedula: tec.cedula,
        nombre: tec.nombre,
        apellido: tec.apellido || "",
        estado: "activo",
        area: tec.area,
        carpeta: tec.carpeta,
        cargo: tec.cargo || "",
        movil: tec.movil || "",
        link_foto: initialFoto,
      } as unknown as Empleado);
    }

    // Consultar ficha completa para cargar la foto oficial
    getEmpleadoByCedula(filtros.cedula)
      .then((emp) => {
        if (emp) setSelectedEmployee(emp);
      })
      .catch(() => {
        if (tec?.id || tec?.empleado_id) {
          const numId = Number(tec.id || tec.empleado_id);
          getEmpleadoById(numId)
            .then((emp) => {
              if (emp) setSelectedEmployee(emp);
            })
            .catch(() => {});
        }
      });
  }, [filtros.cedula, tecnicos]);

  const handleEmployeeFilterChange = (emp: Empleado | null) => {
    setSelectedEmployee(emp);
    setFiltros((prev) => ({
      ...prev,
      cedula: emp?.cedula ? String(emp.cedula) : "",
      area: emp?.area || prev.area,
      carpeta: emp?.carpeta || prev.carpeta,
    }));
  };

  const handleSedeChange = (sede: SedeOption) => {
    setFiltros((prev) => ({ ...prev, sede }));
  };

  const handleMesChange = (mes: string) => {
    setFiltros((prev) => ({ ...prev, mes }));
  };

  const handleAnioChange = (yyyy: string) => {
    setFiltros((prev) => ({ ...prev, yyyy }));
  };

  const resumenFiltros = useMemo(() => {
    const tags: string[] = [];
    if (filtros.sede) tags.push(`Sede: ${filtros.sede.toUpperCase()}`);
    if (filtros.mes && filtros.yyyy) tags.push(`Período: ${filtros.mes}/${filtros.yyyy}`);
    if (filtros.cedula) {
      const tec = tecnicos.find((t) => t.cedula === filtros.cedula);
      tags.push(`Técnico: ${tec ? tec.nombre : filtros.cedula}`);
    }
    if (filtros.actividad) tags.push(`OT: ${filtros.actividad.toUpperCase()}`);
    if (filtros.nombre) tags.push(`Nombre: ${filtros.nombre}`);
    if (filtros.area) tags.push(`Área: ${filtros.area}`);
    if (filtros.carpeta) tags.push(`Carpeta: ${filtros.carpeta}`);
    return tags.length > 0 ? tags.join(" • ") : "Sin filtros aplicados (mostrando todo el mes seleccionado).";
  }, [filtros, tecnicos]);

  return (
    <div className="p-4 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 transition-all">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onBuscar();
        }}
        className="space-y-3"
      >
        {/* Fila 1: Sedes y Meses */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-center">
          {/* Sedes Toggle */}
          <div className="lg:col-span-4 flex items-center space-x-1 bg-gray-100 dark:bg-gray-800/70 p-1 rounded-lg">
            <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 px-2 flex items-center">
              <MapPin className="h-3.5 w-3.5 mr-1" /> Sede:
            </span>
            {(
              [
                { val: "", label: "Todas" },
                { val: "medellin", label: "Medellín" },
                { val: "monteria", label: "Montería" },
                { val: "sincelejo", label: "Sincelejo" },
              ] as const
            ).map((s) => (
              <button
                key={s.val}
                type="button"
                onClick={() => handleSedeChange(s.val)}
                className={`flex-1 py-1 px-2 text-xs font-medium rounded-md transition-colors ${
                  filtros.sede === s.val
                    ? "bg-brand-600 text-white shadow-sm font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Selector de Meses y Año */}
          <div className="lg:col-span-8 flex flex-wrap items-center gap-1.5 justify-end">
            <div className="flex items-center space-x-1 bg-gray-100 dark:bg-gray-800/70 p-1 rounded-lg overflow-x-auto max-w-full">
              <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 px-2 flex items-center">
                <Calendar className="h-3.5 w-3.5 mr-1" /> Mes:
              </span>
              {MESES.map((m) => (
                <button
                  key={m.val}
                  type="button"
                  onClick={() => handleMesChange(m.val)}
                  className={`py-1 px-2.5 text-xs font-medium rounded-md transition-colors ${
                    filtros.mes === m.val
                      ? "bg-brand-600 text-white font-semibold shadow-sm"
                      : "text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {/* Selector de Año */}
            <select
              value={filtros.yyyy}
              onChange={(e) => handleAnioChange(e.target.value)}
              aria-label="Seleccionar año"
              className="py-1.5 px-2.5 text-xs font-semibold bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 focus:ring-1 focus:ring-brand-500"
            >
              {aniosDisponibles.map((y) => (
                <option key={y} value={y.toString()}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Fila 2: Inputs de Búsqueda */}
        <div className="grid grid-cols-2 md:grid-cols-12 gap-2.5 items-start">
          {/* Técnico / Líder Buscador con EmployeeSearchInput */}
          <div className="col-span-2 md:col-span-4">
            <EmployeeSearchInput
              label="Técnico / Líder"
              placeholder="Buscar técnico por nombre, cédula o móvil..."
              value={selectedEmployee}
              onChange={handleEmployeeFilterChange}
            />
          </div>

          {/* OT / Actividad */}
          <div className="col-span-1 md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              <Briefcase className="h-3.5 w-3.5 inline mr-1 text-gray-500" /> OT / Actividad
            </label>
            <input
              type="text"
              placeholder="Ej. OT-10293"
              value={filtros.actividad}
              onChange={(e) => setFiltros((prev) => ({ ...prev, actividad: e.target.value }))}
              className="w-full text-xs py-2 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 uppercase focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Nombre Actividad */}
          <div className="col-span-1 md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Nombre en Agenda
            </label>
            <input
              type="text"
              placeholder="Buscar por nombre..."
              value={filtros.nombre}
              onChange={(e) => setFiltros((prev) => ({ ...prev, nombre: e.target.value }))}
              className="w-full text-xs py-2 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Área */}
          <div className="col-span-1 md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              <Folder className="h-3.5 w-3.5 inline mr-1 text-gray-500" /> Área
            </label>
            <select
              value={filtros.area}
              onChange={(e) => setFiltros((prev) => ({ ...prev, area: e.target.value }))}
              className="w-full text-xs py-2 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Todas las áreas</option>
              {filtros.area && !areasDisponibles.includes(filtros.area) && (
                <option value={filtros.area}>{filtros.area}</option>
              )}
              {areasDisponibles.map((area) => (
                <option key={area} value={area}>
                  {area}
                </option>
              ))}
            </select>
          </div>

          {/* Carpeta */}
          <div className="col-span-1 md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Carpeta
            </label>
            <select
              value={filtros.carpeta}
              onChange={(e) => setFiltros((prev) => ({ ...prev, carpeta: e.target.value }))}
              className="w-full text-xs py-2 px-3 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Todas las carpetas</option>
              {carpetasDisponibles.map((carp) => (
                <option key={carp} value={carp}>
                  {carp}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Fila 3: Resumen y Botones */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pt-1 border-t border-gray-100 dark:border-gray-800">
          <div className="text-[11px] text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 px-2.5 py-1 rounded border border-gray-200/60 dark:border-gray-700/60 flex-1">
            <span className="font-semibold text-gray-700 dark:text-gray-300">Filtro aplicado:</span> {resumenFiltros}
          </div>

          <div className="flex items-center space-x-2 self-end">
            <button
              type="button"
              onClick={onLimpiar}
              disabled={isLoading}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none transition-colors"
            >
              <Eraser className="h-3.5 w-3.5 mr-1 text-gray-400" />
              Limpiar
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex items-center px-4 py-1.5 text-xs font-medium text-white bg-brand-600 rounded-md hover:bg-brand-700 focus:outline-none shadow-sm transition-colors disabled:opacity-50"
            >
              <Search className="h-3.5 w-3.5 mr-1" />
              {isLoading ? "Consultando..." : "Buscar"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
