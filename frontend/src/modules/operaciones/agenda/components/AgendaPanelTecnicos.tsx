"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  UserCheck,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  Layers,
  User,
  Users,
} from "lucide-react";
import { TecnicoActivoAgenda } from "@/types/agenda.types";

interface AgendaPanelTecnicosProps {
  tecnicos: TecnicoActivoAgenda[];
  filtroArea?: string;
  filtroCarpeta?: string;
  cedulaSeleccionada?: string;
  onSeleccionarFiltro: (params: { area?: string; carpeta?: string; cedula?: string }) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

interface CarpetaGroup {
  carpetaNombre: string;
  tecnicos: TecnicoActivoAgenda[];
}

interface AreaGroup {
  areaNombre: string;
  totalTecnicos: number;
  carpetas: CarpetaGroup[];
}

export const AgendaPanelTecnicos: React.FC<AgendaPanelTecnicosProps> = ({
  tecnicos,
  filtroArea = "",
  filtroCarpeta = "",
  cedulaSeleccionada = "",
  onSeleccionarFiltro,
  isCollapsed,
  onToggleCollapse,
}) => {
  const [busqueda, setBusqueda] = useState<string>("");
  const [areasAbiertas, setAreasAbiertas] = useState<Record<string, boolean>>({});
  const [carpetasAbiertas, setCarpetasAbiertas] = useState<Record<string, boolean>>({});

  // Filtrado de técnicos según texto de búsqueda
  const tecnicosFiltrados = useMemo(() => {
    if (!busqueda.trim()) return tecnicos;
    const q = busqueda.toLowerCase().trim();
    return tecnicos.filter(
      (t) =>
        t.nombre.toLowerCase().includes(q) ||
        t.cedula.toLowerCase().includes(q) ||
        t.area?.toLowerCase().includes(q) ||
        t.carpeta?.toLowerCase().includes(q)
    );
  }, [tecnicos, busqueda]);

  // Estructurar árbol jerárquico: Área -> Carpeta -> Técnicos
  const arbolAreas = useMemo(() => {
    const mapaAreas = new Map<string, Map<string, TecnicoActivoAgenda[]>>();

    tecnicosFiltrados.forEach((tec) => {
      const area = (tec.area || "SIN ÁREA").trim().toUpperCase();
      const carpeta = (tec.carpeta || "GENERAL").trim().toUpperCase();

      if (!mapaAreas.has(area)) {
        mapaAreas.set(area, new Map<string, TecnicoActivoAgenda[]>());
      }
      const mapaCarpetas = mapaAreas.get(area)!;

      if (!mapaCarpetas.has(carpeta)) {
        mapaCarpetas.set(carpeta, []);
      }
      mapaCarpetas.get(carpeta)!.push(tec);
    });

    const resultado: AreaGroup[] = [];
    mapaAreas.forEach((mapaCarpetas, areaNombre) => {
      const carpetasArr: CarpetaGroup[] = [];
      let totalEnArea = 0;

      mapaCarpetas.forEach((tecs, carpetaNombre) => {
        totalEnArea += tecs.length;
        carpetasArr.push({
          carpetaNombre,
          tecnicos: tecs.sort((a, b) => (a.nombre || a.cedula).localeCompare(b.nombre || b.cedula)),
        });
      });

      carpetasArr.sort((a, b) => a.carpetaNombre.localeCompare(b.carpetaNombre));

      resultado.push({
        areaNombre,
        totalTecnicos: totalEnArea,
        carpetas: carpetasArr,
      });
    });

    return resultado.sort((a, b) => a.areaNombre.localeCompare(b.areaNombre));
  }, [tecnicosFiltrados]);

  // Configuración de apertura por defecto:
  // - Áreas y Carpetas: Cerradas por defecto (a menos que el usuario esté buscando en el filtro)
  useEffect(() => {
    const areasInit: Record<string, boolean> = {};
    const carpetasInit: Record<string, boolean> = {};
    const hayBusqueda = Boolean(busqueda.trim());

    arbolAreas.forEach((area) => {
      areasInit[area.areaNombre] = hayBusqueda;
      area.carpetas.forEach((carp) => {
        carpetasInit[`${area.areaNombre}__${carp.carpetaNombre}`] = hayBusqueda;
      });
    });

    setAreasAbiertas(areasInit);
    setCarpetasAbiertas(carpetasInit);
  }, [arbolAreas, busqueda]);

  const handleToggleArea = (areaNombre: string) => {
    const isCurrentlyOpen = areasAbiertas[areaNombre] ?? (busqueda.trim().length > 0);
    const nextState = !isCurrentlyOpen;

    setAreasAbiertas((prev) => ({
      ...prev,
      [areaNombre]: nextState,
    }));

    if (nextState) {
      // Al abrir el área, cargar todos los técnicos del área
      onSeleccionarFiltro({ area: areaNombre, carpeta: "", cedula: "" });
    } else {
      // Si se cierra el área activa, volver a todos
      if (filtroArea.toUpperCase() === areaNombre.toUpperCase()) {
        onSeleccionarFiltro({ area: "", carpeta: "", cedula: "" });
      }
    }
  };

  const handleToggleCarpeta = (areaNombre: string, carpetaNombre: string) => {
    const claveCarpeta = `${areaNombre}__${carpetaNombre}`;
    const isCurrentlyOpen = carpetasAbiertas[claveCarpeta] ?? (busqueda.trim().length > 0);
    const nextState = !isCurrentlyOpen;

    setCarpetasAbiertas((prev) => ({
      ...prev,
      [claveCarpeta]: nextState,
    }));

    if (nextState) {
      // Al abrir la carpeta, se cargan TODOS los técnicos de esa carpeta en el cronograma
      onSeleccionarFiltro({ area: areaNombre, carpeta: carpetaNombre, cedula: "" });
    } else {
      // Si se cierra la carpeta activa, volver al nivel del área
      if (
        filtroArea.toUpperCase() === areaNombre.toUpperCase() &&
        filtroCarpeta.toUpperCase() === carpetaNombre.toUpperCase()
      ) {
        onSeleccionarFiltro({ area: areaNombre, carpeta: "", cedula: "" });
      }
    }
  };

  const isTodosActive = !filtroArea && !filtroCarpeta && !cedulaSeleccionada;

  if (isCollapsed) {
    return (
      <div className="w-10 h-full border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 flex flex-col items-center py-4 space-y-4 flex-shrink-0">
        <button
          type="button"
          onClick={onToggleCollapse}
          title="Mostrar panel de técnicos"
          className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <span
          className="text-xs font-semibold text-gray-500 uppercase tracking-widest"
          style={{ writingMode: "vertical-rl", textOrientation: "mixed" }}
        >
          Técnicos ({tecnicos.length})
        </span>
      </div>
    );
  }

  return (
    <div className="w-64 sm:w-68 md:w-76 max-w-[85vw] border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 flex flex-col h-full flex-shrink-0 select-none">
      {/* Encabezado del panel */}
      <div className="p-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between bg-white dark:bg-gray-900">
        <div className="flex items-center space-x-2">
          <UserCheck className="h-4 w-4 text-brand-600 dark:text-brand-400" />
          <h3 className="text-xs font-bold text-gray-800 dark:text-gray-200">
            Técnicos por Área ({tecnicosFiltrados.length})
          </h3>
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          title="Ocultar panel"
          className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 rounded transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* Buscador de técnicos */}
      <div className="p-2 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="relative">
          <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar técnico, área o carpeta..."
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            className="w-full text-xs pl-8 pr-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:ring-1 focus:ring-brand-500"
          />
        </div>
      </div>

      {/* Botón Ver Todos */}
      <div className="p-1.5 border-b border-gray-200/60 dark:border-gray-800/60 bg-gray-50 dark:bg-gray-900">
        <button
          type="button"
          onClick={() => onSeleccionarFiltro({ area: "", carpeta: "", cedula: "" })}
          className={`w-full text-left p-2 rounded-lg text-xs font-semibold transition-colors flex items-center justify-between ${
            isTodosActive
              ? "bg-brand-600 text-white shadow-xs"
              : "text-gray-700 dark:text-gray-300 hover:bg-gray-200/70 dark:hover:bg-gray-800"
          }`}
        >
          <span className="flex items-center space-x-1.5">
            <Users className="h-3.5 w-3.5" />
            <span>Todos los Técnicos</span>
          </span>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full ${
              isTodosActive ? "bg-white/20 text-white" : "bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
            }`}
          >
            {tecnicos.length}
          </span>
        </button>
      </div>

      {/* Árbol Jerárquico: Áreas -> Carpetas -> Técnicos */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
        {arbolAreas.map((area) => {
          const isAreaOpen = areasAbiertas[area.areaNombre] ?? (busqueda.trim().length > 0);
          const isAreaActive =
            filtroArea.toUpperCase() === area.areaNombre.toUpperCase() &&
            !filtroCarpeta &&
            !cedulaSeleccionada;

          return (
            <div
              key={area.areaNombre}
              className={`border rounded-lg overflow-hidden shadow-2xs transition-colors ${
                isAreaActive
                  ? "border-brand-500/80 bg-white dark:bg-gray-900 ring-1 ring-brand-500/30"
                  : "border-gray-200/80 dark:border-gray-800 bg-white dark:bg-gray-900/60"
              }`}
            >
              {/* Nivel 1: Encabezado de Área */}
              <button
                type="button"
                onClick={() => handleToggleArea(area.areaNombre)}
                className={`w-full text-left px-2.5 py-2 flex items-center justify-between transition-colors ${
                  isAreaActive
                    ? "bg-brand-50 dark:bg-brand-950/50 hover:bg-brand-100/60 dark:hover:bg-brand-900/60"
                    : "bg-gray-100/70 dark:bg-gray-800/50 hover:bg-gray-200/60 dark:hover:bg-gray-800"
                }`}
              >
                <div className="flex items-center space-x-2 truncate">
                  {isAreaOpen ? (
                    <ChevronDown className="h-3.5 w-3.5 text-brand-600 dark:text-brand-400 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                  )}
                  <Layers className="h-3.5 w-3.5 text-brand-600 dark:text-brand-400 flex-shrink-0" />
                  <span
                    className={`text-xs font-bold truncate ${
                      isAreaActive ? "text-brand-700 dark:text-brand-300" : "text-gray-800 dark:text-gray-200"
                    }`}
                  >
                    {area.areaNombre}
                  </span>
                </div>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-1 ${
                    isAreaActive
                      ? "bg-brand-600 text-white"
                      : "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                  }`}
                >
                  {area.totalTecnicos}
                </span>
              </button>

              {/* Nivel 2: Carpetas dentro del Área */}
              {isAreaOpen && (
                <div className="p-1 space-y-1 bg-gray-50/40 dark:bg-gray-900/30">
                  {area.carpetas.map((carp) => {
                    const claveCarpeta = `${area.areaNombre}__${carp.carpetaNombre}`;
                    const isCarpetaOpen = carpetasAbiertas[claveCarpeta] ?? (busqueda.trim().length > 0);
                    const isCarpetaActive =
                      filtroArea.toUpperCase() === area.areaNombre.toUpperCase() &&
                      filtroCarpeta.toUpperCase() === carp.carpetaNombre.toUpperCase() &&
                      !cedulaSeleccionada;

                    return (
                      <div
                        key={claveCarpeta}
                        className={`border rounded-md overflow-hidden transition-colors ${
                          isCarpetaActive
                            ? "border-brand-500/70 bg-brand-50/30 dark:bg-brand-950/20 ring-1 ring-brand-500/20"
                            : "border-gray-200/50 dark:border-gray-800/60 bg-white dark:bg-gray-900/80"
                        }`}
                      >
                        {/* Encabezado de Carpeta */}
                        <button
                          type="button"
                          onClick={() => handleToggleCarpeta(area.areaNombre, carp.carpetaNombre)}
                          className={`w-full text-left px-2 py-1.5 flex items-center justify-between transition-colors ${
                            isCarpetaActive
                              ? "bg-brand-100/70 dark:bg-brand-900/50 text-brand-900 dark:text-brand-200 font-semibold"
                              : "hover:bg-gray-100/80 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300"
                          }`}
                        >
                          <div className="flex items-center space-x-1.5 truncate">
                            {isCarpetaOpen ? (
                              <FolderOpen
                                className={`h-3.5 w-3.5 flex-shrink-0 ${
                                  isCarpetaActive ? "text-brand-600 dark:text-brand-400" : "text-amber-500"
                                }`}
                              />
                            ) : (
                              <Folder
                                className={`h-3.5 w-3.5 flex-shrink-0 ${
                                  isCarpetaActive ? "text-brand-600 dark:text-brand-400" : "text-amber-500"
                                }`}
                              />
                            )}
                            <span className="text-[11px] font-semibold truncate">
                              {carp.carpetaNombre}
                            </span>
                          </div>
                          <span
                            className={`text-[9px] font-semibold px-1.5 py-0.2 rounded ${
                              isCarpetaActive
                                ? "bg-brand-600 text-white"
                                : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                            }`}
                          >
                            {carp.tecnicos.length}
                          </span>
                        </button>

                        {/* Nivel 3: Lista de Técnicos en la Carpeta */}
                        {isCarpetaOpen && (
                          <div className="divide-y divide-gray-100 dark:divide-gray-800/60 px-1 pb-1">
                            {carp.tecnicos.map((tec) => {
                              const isSelected = cedulaSeleccionada === tec.cedula;

                              return (
                                <button
                                  key={tec.cedula}
                                  type="button"
                                  onClick={() => {
                                    if (isSelected) {
                                      // Al deseleccionar técnico individual, vuelve a mostrar toda la carpeta
                                      onSeleccionarFiltro({
                                        area: area.areaNombre,
                                        carpeta: carp.carpetaNombre,
                                        cedula: "",
                                      });
                                    } else {
                                      // Cargar solo a este técnico
                                      onSeleccionarFiltro({
                                        area: area.areaNombre,
                                        carpeta: carp.carpetaNombre,
                                        cedula: tec.cedula,
                                      });
                                    }
                                  }}
                                  className={`w-full text-left p-1.5 rounded-md text-xs transition-colors my-0.5 ${
                                    isSelected
                                      ? "bg-brand-600 text-white shadow-xs font-semibold"
                                      : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200"
                                  }`}
                                >
                                  <div className="flex items-center space-x-1.5 truncate">
                                    <User className={`h-3 w-3 flex-shrink-0 ${isSelected ? "text-white" : "text-gray-400"}`} />
                                    <span className="truncate font-medium">
                                      {tec.nombre || `Técnico ${tec.cedula}`}
                                    </span>
                                  </div>
                                  <div
                                    className={`text-[10px] flex items-center justify-between pl-4.5 mt-0.5 ${
                                      isSelected ? "text-brand-100" : "text-gray-400 dark:text-gray-500"
                                    }`}
                                  >
                                    <span>CC: {tec.cedula}</span>
                                    {tec.cargo && <span className="truncate max-w-[80px]">{tec.cargo}</span>}
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {arbolAreas.length === 0 && (
          <div className="p-4 text-center text-xs text-gray-500">
            No se encontraron técnicos para la búsqueda.
          </div>
        )}
      </div>
    </div>
  );
};
