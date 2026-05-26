"use client";

import { PlusIcon } from "@/icons";
import ModalActividad from "./ModalActividad";
import Alert from "@/components/ui/alert/Alert";
import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import { useGestionActividadesData } from "./gestionActividadesView.hooks";
import { GESTION_ACTIVIDADES_CONFIG } from "./gestionActividadesView.utils";
import { GestionActividadesTable } from "./components/GestionActividadesTable";
import { GestionActividadesToolbar } from "./components/GestionActividadesToolbar";

const GestionActividadesView = () => {
  const {
    actividades,
    columns,
    globalFilter,
    setGlobalFilter,
    sorting,
    setSorting,
    pageIndex,
    setPageIndex,
    pageSize,
    setPageSize,
    visibleRows,
    setVisibleRows,
    showAlert,
    loadError,
  } = useGestionActividadesData();

  // {
  //     "id": 3,
  //     "detalle": {
  //         "id": 3,
  //         "tipo_trabajo": "PRUEBA",
  //         "descripcion": "Esta es una actividad de prueba",
  //         "extra": null
  //     },
  //     "ubicacion": {
  //         "id": 3,
  //         "direccion": "Medellin",
  //         "coordenada_x": "000000000",
  //         "coordenada_y": "000000000",
  //         "zona": "SUR",
  //         "nodo": "N600"
  //     },
  //     "responsable_snapshot": {
  //         "nombre": "CARLOS ALBERTO",
  //         "area": "DEPARTAMENTO TI",
  //         "carpeta": "PROGRAMACION",
  //         "cargo": "LIDER DESARROLLADOR",
  //         "movil": "PROGRAM01"
  //     },
  //     "ot": "00003",
  //     "estado": "pendiente",
  //     "responsable_id": 2761,
  //     "fecha_inicio": "2026-02-17",
  //     "fecha_fin_estimado": "2026-02-19",
  //     "fecha_fin_real": "1900-01-01",
  //     "created_at": "2026-02-12T16:01:35.352362-05:00",
  //     "created_by": null,
  //     "updated_at": "2026-02-12T16:01:35.352362-05:00",
  //     "updated_by": null,
  //     "is_deleted": false,
  //     "deleted_at": null,
  //     "deleted_by": null
  // },

  const toolbarActions = (
    <GestionActividadesToolbar visibleRows={visibleRows} />
  );

  return (
    <div className="w-full min-w-0 overflow-x-hidden">
      <PageBreadcrumb
        pageTitle={[...GESTION_ACTIVIDADES_CONFIG.breadcrumbTitles]}
      />
      <div className="w-full min-w-0 overflow-x-hidden rounded-2xl border border-gray-200 bg-white px-5 py-7 xl:px-10 xl:py-12 dark:border-gray-800 dark:bg-white/3">
        <div className="mx-auto w-full max-w-157.5 text-center">
          <h3 className="text-theme-xl mb-4 font-semibold text-gray-800 sm:text-2xl dark:text-white/90">
            {GESTION_ACTIVIDADES_CONFIG.title}
          </h3>

          <p className="text-gray-600 dark:text-white/70">
            {GESTION_ACTIVIDADES_CONFIG.description}
          </p>
        </div>

        <ModalActividad
          mode="create"
          iconButton={<PlusIcon />}
          textButton="Actividad"
        />

        {showAlert && (
          <Alert
            variant="success"
            title="Actividad Creada"
            message="La actividad ha sido creada exitosamente."
          />
        )}

        {loadError && (
          <div className="mt-4">
            <Alert
              variant="error"
              title="No fue posible cargar las actividades"
              message={loadError.message}
            />
          </div>
        )}

        <div className="mt-8 min-h-0 min-w-0 overflow-x-hidden md:h-112">
          <GestionActividadesTable
            actividades={actividades}
            columns={columns}
            globalFilter={globalFilter}
            setGlobalFilter={setGlobalFilter}
            sorting={sorting}
            setSorting={setSorting}
            pageIndex={pageIndex}
            setPageIndex={setPageIndex}
            pageSize={pageSize}
            setPageSize={setPageSize}
            visibleRows={visibleRows}
            setVisibleRows={setVisibleRows}
            toolbarActions={toolbarActions}
          />
        </div>
      </div>
    </div>
  );
};

export default GestionActividadesView;
