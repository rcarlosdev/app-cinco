import { ActividadRecord } from "@/schemas/actividades.schema";
import { CsvColumn } from "@/utils/csv";

export const actividadCsvColumns: CsvColumn<ActividadRecord>[] = [
  {
    header: "ID",
    accessor: (row) => row.id,
  },
  {
    header: "OTs",
    accessor: (row) =>
      row.ots
        ?.map((item) => (typeof item === "string" ? item : item.ot))
        .filter(Boolean)
        .join(", "),
  },
  {
    header: "Estado",
    accessor: (row) => row.estado,
  },
  {
    header: "Responsable",
    accessor: (row) => row.responsable_snapshot?.nombre,
  },
  {
    header: "Tipo Trabajo",
    accessor: (row) => row.detalle?.tipo_trabajo,
  },
  {
    header: "Descripcion",
    accessor: (row) => row.detalle?.descripcion,
  },
  {
    header: "Fecha Inicio",
    accessor: (row) => row.fecha_inicio,
  },
  {
    header: "Fecha Fin Estimado",
    accessor: (row) => row.fecha_fin_estimado,
  },
  {
    header: "Fecha Fin Real",
    accessor: (row) => row.fecha_fin_real,
  },
  {
    header: "Direccion",
    accessor: (row) => row.ubicacion?.direccion,
  },
  {
    header: "Zona",
    accessor: (row) => row.ubicacion?.zona,
  },
  {
    header: "Nodo",
    accessor: (row) => row.ubicacion?.nodo,
  },
];

export const ACTIVIDAD_TABLE_CONFIG = {
  defaultPageSize: 5,
  defaultPageIndex: 0,
  csvFileName: "actividades_export.csv",
};
