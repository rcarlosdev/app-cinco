import { useState } from "react";
import Button from "@/components/ui/button/Button";
import { DownloadIcon } from "@/icons";
import { ActividadRecord } from "@/schemas/actividades.schema";
import { handleExportToCsvHelper } from "../gestionActividadesView.utils";
import ModalImportarCsv from "./ModalImportarCsv";

interface GestionActividadesToolbarProps {
  visibleRows: ActividadRecord[];
}

export const GestionActividadesToolbar = ({
  visibleRows,
}: GestionActividadesToolbarProps) => {
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);

  return (
    <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
      <Button
        variant="outline"
        size="sm"
        className="w-full sm:w-auto flex items-center justify-center gap-2"
        onClick={() => setIsImportModalOpen(true)}
        startIcon={
          <svg
            className="h-4 w-4 text-gray-500 dark:text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
            />
          </svg>
        }
      >
        Importar CSV
      </Button>

      <Button
        variant="outline"
        size="sm"
        className="w-full sm:w-auto flex items-center justify-center gap-2"
        onClick={() => handleExportToCsvHelper(visibleRows)}
        startIcon={<DownloadIcon className="h-4 w-4" />}
        disabled={!visibleRows.length}
      >
        Exportar CSV
      </Button>

      <ModalImportarCsv
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
      />
    </div>
  );
};
