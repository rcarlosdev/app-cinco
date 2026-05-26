import Button from "@/components/ui/button/Button";
import { DownloadIcon } from "@/icons";
import { ActividadFormData } from "@/schemas/actividades.schema";
import { handleExportToCsvHelper } from "../gestionActividadesView.utils";

interface GestionActividadesToolbarProps {
  visibleRows: ActividadFormData[];
}

export const GestionActividadesToolbar = ({
  visibleRows,
}: GestionActividadesToolbarProps) => {
  return (
    <Button
      variant="outline"
      size="sm"
      className="w-full sm:w-auto"
      onClick={() => handleExportToCsvHelper(visibleRows)}
      startIcon={<DownloadIcon className="h-4 w-4" />}
      disabled={!visibleRows.length}
    >
      Exportar CSV
    </Button>
  );
};
