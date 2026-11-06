"use client";

import React, { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, X } from "lucide-react";
import { CuadraCheckResult } from "../types";

interface AlertaCuadraBannerProps {
  checkResult: CuadraCheckResult | null;
  isLoading: boolean;
  onIgnorar?: () => void;
}

export const AlertaCuadraBanner: React.FC<AlertaCuadraBannerProps> = ({
  checkResult,
  isLoading,
  onIgnorar,
}) => {
  const [expandido, setExpandido] = useState(false);

  // Silencioso mientras carga para evitar que el formulario salte al escribir
  if (isLoading || !checkResult || !checkResult.tiene_registros) {
    return null;
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/90 px-3.5 py-2.5 text-xs text-amber-900 shadow-xs dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-200">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p className="truncate">
            <span className="font-semibold">Sector con registros previos:</span>{" "}
            Ya tiene{" "}
            <span className="font-bold">
              {checkResult.total_predios} mapping(s)
            </span>
            .
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {checkResult.predios_recientes?.length > 0 && (
            <button
              type="button"
              onClick={() => setExpandido(!expandido)}
              className="inline-flex items-center gap-1 font-medium text-amber-800 hover:text-amber-950 dark:text-amber-300 dark:hover:text-amber-100"
            >
              <span>{expandido ? "Ocultar" : "Ver"}</span>
              {expandido ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          )}

          {onIgnorar && (
            <button
              type="button"
              onClick={onIgnorar}
              title="Cerrar aviso"
              className="rounded p-1 text-amber-600 hover:bg-amber-200/60 hover:text-amber-950 transition-colors dark:text-amber-400 dark:hover:bg-amber-900/50"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Lista colapsable solo si el usuario decide hacer clic en 'Ver' */}
      {expandido && checkResult.predios_recientes?.length > 0 && (
        <div className="mt-2 pt-2 border-t border-amber-200/70 dark:border-amber-800/60">
          <ul className="divide-y divide-amber-100 dark:divide-amber-900/40 max-h-36 overflow-y-auto">
            {checkResult.predios_recientes.map((p) => (
              <li
                key={p.id}
                className="py-1.5 flex items-center justify-between text-[11px]"
              >
                <span className="font-medium text-amber-950 dark:text-amber-100">
                  {p.nombre_calle} #{p.placa_unidad}
                  {p.interior ? ` Int. ${p.interior}` : ""}
                  {p.nombre_conjunto ? ` (${p.nombre_conjunto})` : ""}
                </span>
                <span className="text-amber-700 dark:text-amber-400">
                  {p.total_unidades} un. · AMP: {p.lote_amp}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
