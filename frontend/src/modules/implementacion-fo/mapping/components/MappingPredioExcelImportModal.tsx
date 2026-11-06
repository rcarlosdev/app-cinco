"use client";

import React, { useState } from "react";
import { Upload, X, FileSpreadsheet, CheckCircle2, AlertCircle, Download } from "lucide-react";
import { toast } from "sonner";
import { mappingPredioService } from "../services/mappingPredio.service";
import { ImportResult } from "../types";

interface MappingPredioExcelImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportExitoso: () => void;
}

export const MappingPredioExcelImportModal: React.FC<MappingPredioExcelImportModalProps> = ({
  isOpen,
  onClose,
  onImportExitoso,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [resultado, setResultado] = useState<ImportResult | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResultado(null);
    }
  };

  const handleSubir = async () => {
    if (!file) {
      toast.error("Por favor selecciona un archivo CSV (.csv).");
      return;
    }

    if (!file.name.toLowerCase().endsWith(".csv")) {
      toast.error("Solo se permiten archivos en formato CSV (.csv).");
      return;
    }

    setIsUploading(true);
    try {
      const res = await mappingPredioService.importarCsv(file);
      setResultado(res);
      if (res.total_creados > 0) {
        toast.success(`🎉 Se importaron ${res.total_creados} predios exitosamente`);
        onImportExitoso();
      } else {
        toast.warning("No se importó ningún predio. Revisa los datos del archivo CSV.");
      }
    } catch (error: any) {
      const errorMsg =
        error?.response?.data?.error ||
        error?.message ||
        "Error al procesar el archivo CSV.";
      toast.error(errorMsg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDescargarPlantilla = () => {
    // Generar archivo CSV de ejemplo con los 17 campos exactos
    const headers = [
      "NOMBRE CONJUNTO",
      "NOMBRECALL",
      "PLACAUNIDA",
      "NUM_CASAS",
      "APTOS",
      "LOCALES",
      "PISOS",
      "BARRIO",
      "INT",
      "NOMBRECALLANT2",
      "PLACAUNIDAANT2",
      "NOMBRECALLANT3",
      "PLACAUNIDAANT3",
      "DISTRIBUCION",
      "AMP",
      "CORDX",
      "CORDY",
    ];
    const ejemplo = [
      "EDIFICIO NUEVO MILENIUM",
      "CL 21C",
      "40A-15",
      "1",
      "2",
      "1",
      "3",
      "BELEN",
      "6",
      "CRA 22",
      "30-15",
      "",
      "",
      "AP 101-102-103-201-202-203",
      "1",
      "6.308625",
      "-75.54541",
    ];

    const csvContent = "\uFEFF" + headers.join(";") + "\n" + ejemplo.join(";");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "plantilla_mapping_predios.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success("Plantilla CSV descargada");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-800 dark:bg-gray-900">
        {/* Cabecera */}
        <div className="flex items-center justify-between border-b border-gray-100 p-5 dark:border-gray-800">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <FileSpreadsheet className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 dark:text-white">
                Importar predios mediante CSV
              </h3>
              <p className="text-xs text-gray-500">Implementación FO - Mapping</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Contenido */}
        <div className="p-5 space-y-4">
          <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50/70 p-6 text-center dark:border-gray-700 dark:bg-gray-800/40">
            <Upload className="mx-auto h-10 w-10 text-gray-400" />
            <p className="mt-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              {file ? file.name : "Selecciona o arrastra tu archivo CSV"}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Formato soportado: <strong>.csv</strong> (delimitado por comas o punto y coma)
            </p>
            <input
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              id="file-upload"
              className="hidden"
            />
            <label
              htmlFor="file-upload"
              className="mt-4 inline-block cursor-pointer rounded-lg bg-white px-4 py-2 text-xs font-semibold text-gray-800 shadow-xs border border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            >
              {file ? "Cambiar Archivo" : "Examinar Archivo"}
            </label>
          </div>

          <div className="flex items-center justify-between text-xs text-gray-500">
            <button
              type="button"
              onClick={handleDescargarPlantilla}
              className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline dark:text-brand-400"
            >
              <Download className="h-3 w-3" />
              Descargar Plantilla CSV
            </button>
          </div>

          {/* Resultado de la carga */}
          {resultado && (
            <div
              className={`rounded-xl border p-4 text-xs ${
                resultado.total_creados > 0
                  ? "border-green-200 bg-green-50/70 text-green-900 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200"
                  : "border-amber-200 bg-amber-50/70 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
              }`}
            >
              <div className="flex items-center gap-2 font-bold">
                {resultado.total_creados > 0 ? (
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                )}
                <span>Resumen del Procesamiento</span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-800/60">
                  <span className="block font-bold text-sm">{resultado.total_procesados}</span>
                  <span className="text-[10px] text-gray-500">Filas Leídas</span>
                </div>
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-800/60">
                  <span className="block font-bold text-sm text-green-600">
                    {resultado.total_creados}
                  </span>
                  <span className="text-[10px] text-gray-500">Creados</span>
                </div>
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-800/60">
                  <span className="block font-bold text-sm text-red-600">
                    {resultado.total_errores}
                  </span>
                  <span className="text-[10px] text-gray-500">Omitidos/Error</span>
                </div>
              </div>

              {resultado.errores && resultado.errores.length > 0 && (
                <div className="mt-2 max-h-24 overflow-y-auto text-[11px] text-red-700 dark:text-red-300">
                  <p className="font-semibold">Detalle de errores:</p>
                  <ul className="list-disc pl-4">
                    {resultado.errores.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-gray-100 bg-gray-50/50 p-4 dark:border-gray-800 dark:bg-gray-900/50">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-xs font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-white/[0.03] dark:hover:text-white transition-all shadow-xs"
          >
            Cerrar
          </button>
          <button
            type="button"
            disabled={!file || isUploading}
            onClick={handleSubir}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-5 py-2 text-xs font-bold text-white shadow-xs hover:bg-brand-600 active:scale-95 disabled:opacity-50 transition-all"
          >
            {isUploading ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Importar CSV
          </button>
        </div>
      </div>
    </div>
  );
};
