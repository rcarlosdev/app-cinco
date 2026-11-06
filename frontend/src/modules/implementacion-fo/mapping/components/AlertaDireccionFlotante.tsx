"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { DireccionCheckResult } from "../types";

interface AlertaDireccionFlotanteProps {
  checkResult: DireccionCheckResult | null;
  onConfirmarNuevaUnidad?: () => void;
}

export const AlertaDireccionFlotante: React.FC<AlertaDireccionFlotanteProps> = ({
  checkResult,
  onConfirmarNuevaUnidad,
}) => {
  if (!checkResult || !checkResult.existe_exacta) {
    return null;
  }

  const primeraCoincidencia = checkResult.coincidencias?.[0];

  return (
    <div className="rounded-lg border border-red-300 bg-red-50/90 p-3 text-xs text-red-900 shadow-xs dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
      <div className="flex items-start gap-2.5">
        <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold text-red-950 dark:text-red-100">
            Dirección duplicada
          </p>
          {primeraCoincidencia && (
            <p className="mt-0.5 text-red-800 dark:text-red-300">
              Registrado como: <strong>{primeraCoincidencia.nombre_conjunto || primeraCoincidencia.direccion_completa}</strong> ({primeraCoincidencia.barrio} - Plancha {primeraCoincidencia.lote_amp}).
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
