"use client";

import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import ComponentCard from "@/components/common/ComponentCard";
import { EmployeeSearchInput } from "@/components/form/EmployeeSearchInput";
import Alert from "@/components/ui/alert/Alert";
import Button from "@/components/ui/button/Button";
import { getErrorMessage, classifyError } from "@/lib/errorHandler";
import { downloadCertificadoLaboral } from "@/services/empleado.service";
import { Empleado } from "@/types/empleado";
import { Download, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/auth.store";
import { useRouter } from "next/navigation";

type DocumentType = "CC" | "PT" | "TI" | "CE";

const documentTypeOptions: { value: DocumentType; label: string }[] = [
  { value: "CC", label: "CC" },
  { value: "PT", label: "PT" },
  { value: "TI", label: "TI" },
  { value: "CE", label: "CE" },
];

const selectClasses =
  "h-11 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800";

const CertificadosLaboralesModule = () => {
  const user = useAuthStore((state) => state.user);
  const isSuperuser = Boolean(user?.is_superuser);
  const router = useRouter();

  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("CC");
  const [isDownloading, setIsDownloading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    if (!isSuperuser) {
      router.replace("/");
    }
  }, [isSuperuser, router]);

  if (!isSuperuser) {
    return null;
  }

  const handleDownload = async () => {
    if (!selectedEmployee || isDownloading) return;

    setIsDownloading(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const { blob, filename } = await downloadCertificadoLaboral(
        selectedEmployee.id,
        documentType,
      );
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      setSuccessMessage(
        `Se generó el certificado de ${selectedEmployee.nombre} ${selectedEmployee.apellido}.`,
      );
    } catch (error) {
      const classified = classifyError(error);
      setErrorMessage(getErrorMessage(classified));
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageBreadcrumb pageTitle={["RRHH", "Certificados Laborales"]} />

      <ComponentCard
        title="Prueba de generación de certificado"
        desc="Selecciona un empleado y descarga el PDF generado por el backend para validar contenido, diseño y respuesta del endpoint."
      >
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_320px]">
          <div className="space-y-6">
            <EmployeeSearchInput
              label="Empleado"
              value={selectedEmployee}
              onChange={(employee) => {
                setSelectedEmployee(employee);
                setErrorMessage("");
                setSuccessMessage("");
              }}
              placeholder="Busca por nombre, apellido o cédula"
              hint="El selector consume el endpoint de empleados del backend."
            />

            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Tipo de documento
              </label>
              <select
                value={documentType}
                onChange={(event) =>
                  setDocumentType(event.target.value as DocumentType)
                }
                className={selectClasses}
              >
                {documentTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={() => void handleDownload()}
                disabled={!selectedEmployee || isDownloading}
                startIcon={<Download size={16} />}
              >
                {isDownloading ? "Generando certificado..." : "Descargar certificado"}
              </Button>

              {selectedEmployee && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Endpoint objetivo:{" "}
                  <span className="font-medium text-gray-700 dark:text-white/80">
                    /empleados/empleados/{selectedEmployee.id}/certificado-laboral/
                  </span>
                </p>
              )}
            </div>

            {errorMessage ? (
              <Alert
                variant="error"
                title="No fue posible generar el certificado"
                message={errorMessage}
              />
            ) : null}

            {successMessage ? (
              <Alert
                variant="success"
                title="Certificado generado"
                message={successMessage}
              />
            ) : null}
          </div>

          <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50/70 p-5 dark:border-gray-700 dark:bg-gray-900/40">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-brand-50 p-3 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                <FileText size={20} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-800 dark:text-white/90">
                  Resumen de validación
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Útil para verificar rápido la integración.
                </p>
              </div>
            </div>

            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Empleado</dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {selectedEmployee
                    ? `${selectedEmployee.nombre} ${selectedEmployee.apellido}`
                    : "Sin seleccionar"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Cédula</dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {selectedEmployee?.cedula || "Sin seleccionar"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Cargo</dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {selectedEmployee?.cargo || "No disponible"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400">
                  Tipo de documento
                </dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {documentType}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400">
                  Estado de prueba
                </dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {isDownloading
                    ? "Generando PDF..."
                    : successMessage
                      ? "Descarga ejecutada"
                      : "Pendiente"}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </ComponentCard>
    </div>
  );
};

export default CertificadosLaboralesModule;
