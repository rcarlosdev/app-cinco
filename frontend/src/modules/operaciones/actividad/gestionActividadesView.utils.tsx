import { ColumnDef } from "@tanstack/react-table";
import { ActividadRecord } from "@/schemas/actividades.schema";
import Badge from "@/components/ui/badge/Badge";
import ModalActividad from "./ModalActividad";
import { toDateOrUndefined } from "./ActividadForm.utils";
import {
  actividadCsvColumns,
  ACTIVIDAD_TABLE_CONFIG,
} from "./actividadTable.utils";
import { exportToCsv } from "@/utils/csv";

const formatDate = (value?: string | null) => {
  if (!value) return "-";

  const date = toDateOrUndefined(value);
  if (!date) return "-";
  if (Number.isNaN(date.getTime())) return "-";

  return date.toLocaleDateString("es-CO");
};

const truncateText = (value?: string, maxLength = 60) => {
  if (!value) return "-";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
};

const formatOts = (ots?: any[]) => {
  if (!ots?.length) return "-";
  return ots
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      return item?.ot || "";
    })
    .filter(Boolean)
    .join(", ");
};

export const getActividadesColumns = (): ColumnDef<ActividadRecord>[] => [
  {
    id: "acciones",
    header: "ACCIONES",
    enableSorting: false,
    enableColumnFilter: false,
    enableHiding: false,
    cell: ({ row }) => {
      const id = row.original.id;

      if (id === undefined) {
        return null;
      }

      const actividad = {
        ...row.original,
        id: id as number,
      };

      return (
        <ModalActividad mode="edit" actividad={actividad} textButton="Editar" />
      );
    },
  },
  {
    id: "ots",
    header: "OTS",
    accessorFn: (row) => formatOts(row.ots),
    cell: ({ getValue }) => {
      const ots = getValue<string>();
      return <span title={ots}>{truncateText(ots, 50)}</span>;
    },
  },
  {
    id: "tipo_trabajo",
    header: "TIPO",
    accessorKey: "detalle.tipo_trabajo",
    cell: ({ row }) => {
      return <span>{row.original.detalle?.tipo_trabajo || "-"}</span>;
    },
  },
  {
    id: "estado",
    header: "ESTADO",
    accessorKey: "estado",
    cell: ({ row }) => {
      const estado = row.original.estado || "Sin estado";
      return (
        <Badge
          size="sm"
          color={
            estado == "completada"
              ? "success"
              : estado == "pendiente"
                ? "warning"
                : "error"
          }
        >
          {estado}
        </Badge>
      );
    },
  },
  {
    id: "responsable",
    header: "RESPONSABLE",
    accessorKey: "responsable_snapshot.nombre",
    cell: ({ row }) => {
      const responsable =
        row.original.responsable_snapshot?.nombre || "Sin responsable";
      return <span>{responsable}</span>;
    },
  },
  {
    id: "area",
    header: "ÁREA",
    accessorKey: "responsable_snapshot.area",
    cell: ({ row }) => {
      return <span>{row.original.responsable_snapshot?.area || "-"}</span>;
    },
  },
  {
    id: "ubicacion",
    header: "UBICACIÓN",
    accessorKey: "ubicacion.direccion",
    cell: ({ row }) => {
      const direccion = row.original.ubicacion?.direccion || "-";
      const nodo = row.original.ubicacion?.nodo;
      return <span>{nodo ? `${direccion} (${nodo})` : direccion}</span>;
    },
  },
  {
    id: "fecha_inicio",
    header: "INICIO",
    accessorKey: "fecha_inicio",
    cell: ({ row }) => {
      return <span>{formatDate(row.original.fecha_inicio)}</span>;
    },
  },
  {
    id: "fecha_fin_estimado",
    header: "FIN EST.",
    accessorKey: "fecha_fin_estimado",
    cell: ({ row }) => {
      return <span>{formatDate(row.original.fecha_fin_estimado)}</span>;
    },
  },
  {
    id: "descripcion",
    header: "DESCRIPCIÓN",
    accessorKey: "detalle.descripcion",
    cell: ({ row }) => {
      const descripcion = row.original.detalle?.descripcion;
      return (
        <span title={descripcion || ""}>{truncateText(descripcion, 70)}</span>
      );
    },
  },
];

export const handleExportToCsvHelper = (visibleRows: ActividadRecord[]) => {
  if (!visibleRows.length) {
    return;
  }

  exportToCsv(visibleRows, {
    fileName: ACTIVIDAD_TABLE_CONFIG.csvFileName,
    columns: actividadCsvColumns,
  });
};

export const GESTION_ACTIVIDADES_CONFIG = {
  breadcrumbTitles: ["Operaciones", "Gestión de Actividades"],
  title: "Modulo de Gestión de Actividades",
  description:
    "Aquí podrás gestionar todas las actividades relacionadas con las operaciones de CINCO SAS.",
  alertDuration: 5000,
  pageSizeOptions: [5, 10, 25, 50, 100],
} as const;
