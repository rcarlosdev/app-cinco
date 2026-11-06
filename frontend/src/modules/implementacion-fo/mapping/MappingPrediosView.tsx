"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  MapPin,
  Plus,
  ListFilter,
  FileSpreadsheet,
  Building,
  Home,
  Store,
  Layers,
  Sparkles,
  RefreshCw,
  Cloud,
  UploadCloud,
} from "lucide-react";
import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import { MappingPredio, MappingPredioFiltros } from "./types";
import { mappingPredioService } from "./services/mappingPredio.service";
import { MappingPredioForm } from "./components/MappingPredioForm";
import { MappingPrediosTable } from "./components/MappingPrediosTable";
import { MappingPredioExcelImportModal } from "./components/MappingPredioExcelImportModal";

type ActiveTab = "formulario" | "listado";

export const MappingPrediosView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>("formulario");
  const [predios, setPredios] = useState<MappingPredio[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filtros, setFiltros] = useState<MappingPredioFiltros>({});
  const [predioEditando, setPredioEditando] = useState<MappingPredio | null>(null);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);

  const cargarPredios = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await mappingPredioService.listar(filtros);
      setPredios(data);
    } catch {
      // Silencioso o notificado en servicio
    } finally {
      setIsLoading(false);
    }
  }, [filtros]);

  useEffect(() => {
    cargarPredios();
  }, [cargarPredios]);

  const handleEditarPredio = (predio: MappingPredio) => {
    setPredioEditando(predio);
    setActiveTab("formulario");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleGuardadoExitoso = (predio: MappingPredio) => {
    cargarPredios();
    if (predioEditando) {
      setPredioEditando(null);
    }
  };

  // Cálculos de métricas rápidas
  const totalCasas = predios.reduce((acc, p) => acc + (p.num_casas || 0), 0);
  const totalAptos = predios.reduce((acc, p) => acc + (p.num_apartamentos || 0), 0);
  const totalLocales = predios.reduce((acc, p) => acc + (p.num_locales || 0), 0);
  const totalUnidades = totalCasas + totalAptos + totalLocales;
  const barriosUnicos = new Set(predios.map((p) => p.barrio).filter(Boolean)).size;
  const planchasUnicas = new Set(predios.map((p) => p.lote_amp).filter(Boolean)).size;
  const totalSincronizados = predios.filter((p) => p.sp_synced).length;

  return (
    <div className="space-y-6">
      <PageBreadcrumb pageTitle={["Implementación FO", "Mapping de Predios"]} />

      {/* Pestañas de Navegación estilo Agenda */}
      <div className="flex border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 rounded-xl px-4 pt-2 shadow-xs">
        <nav className="-mb-px flex space-x-2" aria-label="Tabs">
          <button
            type="button"
            onClick={() => setActiveTab("formulario")}
            className={`group inline-flex items-center px-4 py-2.5 font-medium text-xs md:text-sm rounded-t-lg border-b-2 transition-all duration-150 ${
              activeTab === "formulario"
                ? "bg-brand-50 text-brand-700 border-brand-600 dark:bg-brand-950/50 dark:text-brand-300 dark:border-brand-400 font-semibold shadow-xs"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            <Plus
              className={`-ml-0.5 mr-2 h-4 w-4 ${
                activeTab === "formulario"
                  ? "text-brand-600 dark:text-brand-400"
                  : "text-gray-400 group-hover:text-gray-500 dark:text-gray-500"
              }`}
            />
            {predioEditando ? "Editando Predio" : "Registrar Predio"}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("listado")}
            className={`group inline-flex items-center px-4 py-2.5 font-medium text-xs md:text-sm rounded-t-lg border-b-2 transition-all duration-150 ${
              activeTab === "listado"
                ? "bg-brand-50 text-brand-700 border-brand-600 dark:bg-brand-950/50 dark:text-brand-300 dark:border-brand-400 font-semibold shadow-xs"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            <ListFilter
              className={`-ml-0.5 mr-2 h-4 w-4 ${
                activeTab === "listado"
                  ? "text-brand-600 dark:text-brand-400"
                  : "text-gray-400 group-hover:text-gray-500 dark:text-gray-500"
              }`}
            />
            Predios Levantados
            <span
              className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                activeTab === "listado"
                  ? "bg-brand-200/80 text-brand-800 dark:bg-brand-900/60 dark:text-brand-200"
                  : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
              }`}
            >
              {predios.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setIsImportModalOpen(true)}
            className="group inline-flex items-center px-4 py-2.5 font-medium text-xs md:text-sm rounded-t-lg border-b-2 border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 transition-all duration-150"
          >
            <UploadCloud className="-ml-0.5 mr-2 h-4 w-4 text-gray-400 group-hover:text-gray-500 dark:text-gray-500" />
            Importar CSV
          </button>
        </nav>
      </div>

      {/* Renderizado condicional según la pestaña activa */}
      {activeTab === "formulario" ? (
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xs dark:border-gray-800 dark:bg-gray-900">
          <div className="mb-5 flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
            <h2 className="text-base font-bold text-gray-900 dark:text-white">
              {predioEditando ? "Modificar Datos del Predio" : "Formulario de Mapping"}
            </h2>
            {predioEditando && (
              <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-bold text-brand-700 dark:bg-brand-950 dark:text-brand-300">
                Editando ID #{predioEditando.id}
              </span>
            )}
          </div>

          <MappingPredioForm
            predioEditando={predioEditando}
            onGuardadoExitoso={handleGuardadoExitoso}
            onCancelarEdicion={() => {
              setPredioEditando(null);
            }}
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Tarjetas de Resumen en Vivo (KPIs visibles solo en Predios Levantados) */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-xs dark:border-gray-800 dark:bg-gray-900">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Predios Levantados</span>
                <Building className="h-4 w-4 text-brand-600 dark:text-brand-400" />
              </div>
              <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{predios.length}</p>
              <span className="text-[11px] text-gray-400">{barriosUnicos} barrios cubiertos</span>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-xs dark:border-gray-800 dark:bg-gray-900">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Total Unidades</span>
                <Sparkles className="h-4 w-4 text-green-600 dark:text-green-400" />
              </div>
              <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{totalUnidades}</p>
              <span className="text-[11px] text-gray-400">
                {totalAptos} aptos • {totalCasas} casas • {totalLocales} loc.
              </span>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-xs dark:border-gray-800 dark:bg-gray-900">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Planchas / AMPs</span>
                <Layers className="h-4 w-4 text-brand-700 dark:text-brand-300" />
              </div>
              <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{planchasUnicas}</p>
              <span className="text-[11px] text-gray-400">Lotes de cartografía</span>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-xs dark:border-gray-800 dark:bg-gray-900">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">SharePoint (Listas)</span>
                <Cloud className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
                {totalSincronizados}
                <span className="text-xs font-normal text-gray-400"> / {predios.length}</span>
              </p>
              <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                {predios.length > 0 && totalSincronizados === predios.length
                  ? "100% Sincronizado"
                  : `${predios.length - totalSincronizados} pendientes`}
              </span>
            </div>
          </div>

          <MappingPrediosTable
            predios={predios}
            isLoading={isLoading}
            filtros={filtros}
            onFiltrosChange={setFiltros}
            onRefrescar={cargarPredios}
            onEditarPredio={handleEditarPredio}
            onAbrirImportModal={() => setIsImportModalOpen(true)}
          />
        </div>
      )}

      {/* Modal de Carga Masiva de Excel */}
      <MappingPredioExcelImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImportExitoso={() => {
          cargarPredios();
        }}
      />
    </div>
  );
};

export default MappingPrediosView;
