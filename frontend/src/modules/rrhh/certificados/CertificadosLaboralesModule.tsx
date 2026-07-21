"use client";

import PageBreadcrumb from "@/components/common/PageBreadCrumb";
import ComponentCard from "@/components/common/ComponentCard";
import { EmployeeSearchInput } from "@/components/form/EmployeeSearchInput";
import Alert from "@/components/ui/alert/Alert";
import Button from "@/components/ui/button/Button";
import { getErrorMessage, classifyError } from "@/lib/errorHandler";
import { downloadCertificadoLaboral, CertificadoLaboralManualData } from "@/services/empleado.service";
import { Empleado } from "@/types/empleado";
import { Download, FileText, Edit, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/auth.store";
import { hasCertificadosPermission } from "@/utils/permission";
import { useRouter } from "next/navigation";

type DocumentType = "CC" | "PT" | "TI" | "CE";

const documentTypeOptions: { value: DocumentType; label: string }[] = [
  { value: "CC", label: "CC" },
  { value: "PT", label: "PT" },
  { value: "TI", label: "TI" },
  { value: "CE", label: "CE" },
];

const contratoOptions = [
  { value: "OBRA Y LABOR", label: "Obra y labor" },
  { value: "Término indefinido", label: "Término indefinido" },
  { value: "Término fijo", label: "Término fijo" },
];

const selectClasses =
  "h-11 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800";

const inputClasses =
  "h-11 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800";

const CertificadosLaboralesModule = () => {
  const user = useAuthStore((state) => state.user);
  const hasPermission = hasCertificadosPermission(user);
  const router = useRouter();

  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("CC");
  const [isDownloading, setIsDownloading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  // Manual form state
  const [showManualForm, setShowManualForm] = useState(false);
  const [salario, setSalario] = useState("");
  const [tipoContrato, setTipoContrato] = useState("OBRA Y LABOR");
  const [cargo, setCargo] = useState("");
  const [fechaIngreso, setFechaIngreso] = useState("");
  const [fechaEgreso, setFechaEgreso] = useState("");
  const [estado, setEstado] = useState("ACTIVO");
  const [genero, setGenero] = useState("M");

  useEffect(() => {
    if (user && !hasPermission) {
      router.replace("/");
    }
  }, [user, hasPermission, router]);

  useEffect(() => {
    if (selectedEmployee) {
      setCargo(selectedEmployee.cargo || "");
      setFechaIngreso(selectedEmployee.fecha_ingreso || "");
      setFechaEgreso(selectedEmployee.fecha_egreso || "");
      setEstado(selectedEmployee.estado || "ACTIVO");
      const empGenero = selectedEmployee?.genero;
      setGenero(typeof empGenero === "string" && empGenero.toUpperCase().startsWith("F") ? "F" : "M");
      setSalario("");
      setShowManualForm(false);
      setErrorMessage("");
      setSuccessMessage("");
    }
  }, [selectedEmployee]);

  if (!hasPermission) {
    return null;
  }

  const triggerDownload = async (manualData?: CertificadoLaboralManualData) => {
    if (!selectedEmployee || isDownloading) return;

    setIsDownloading(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const { blob, filename } = await downloadCertificadoLaboral(
        selectedEmployee.id,
        documentType,
        manualData,
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
    } catch (error: any) {
      const classified = classifyError(error);
      const msg = getErrorMessage(classified);
      setErrorMessage(msg);
      // Auto-display manual form if SIIGO or contract/salary data is missing
      setShowManualForm(true);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDownloadAuto = () => {
    void triggerDownload();
  };

  const handleDownloadManual = () => {
    if (!salario || Number(salario) <= 0) {
      setErrorMessage("Por favor ingrese un salario básico válido mayor a cero.");
      return;
    }
    const manualData: CertificadoLaboralManualData = {
      salario,
      tipo_contrato: tipoContrato,
      cargo,
      fecha_ingreso: fechaIngreso,
      fecha_egreso: fechaEgreso,
      estado,
      genero,
    };
    void triggerDownload(manualData);
  };

  return (
    <div className="space-y-6">
      <PageBreadcrumb pageTitle={["RRHH", "Certificados Laborales"]} />

      <ComponentCard
        title="Generación de certificado laboral"
        desc="Selecciona un empleado para descargar su certificado laboral en PDF. Si el empleado no existe en SIIGO, puedes ingresar los datos manualmente."
      >
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_320px]">
          <div className="space-y-6">
            <EmployeeSearchInput
              label="Empleado"
              value={selectedEmployee}
              onChange={(employee) => {
                setSelectedEmployee(employee);
              }}
              placeholder="Busca por nombre, apellido o cédula"
              hint="El selector consume el endpoint de empleados del backend."
              includeInactive={true}
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
                onClick={handleDownloadAuto}
                disabled={!selectedEmployee || isDownloading}
                startIcon={<Download size={16} />}
              >
                {isDownloading ? "Generando certificado..." : "Descargar certificado"}
              </Button>

              {selectedEmployee && !showManualForm && (
                <Button
                  variant="outline"
                  onClick={() => setShowManualForm(true)}
                  startIcon={<Edit size={16} />}
                >
                  Ingresar datos manualmente
                </Button>
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

            {/* Formulario para ingreso manual si no hay SIIGO o se elige ingresar manualmente */}
            {selectedEmployee && showManualForm && (
              <div className="rounded-2xl border border-brand-200 bg-brand-50/40 p-5 dark:border-brand-900/50 dark:bg-brand-950/20 space-y-4">
                <div className="flex items-center gap-2 text-brand-700 dark:text-brand-300">
                  <UserX size={18} />
                  <h4 className="text-sm font-semibold">
                    Ingreso manual de datos del certificado
                  </h4>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  Completa o modifica la información del contrato y salario para generar el PDF.
                </p>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Salario básico ($) *
                    </label>
                    <input
                      type="number"
                      value={salario}
                      onChange={(e) => setSalario(e.target.value)}
                      placeholder="Ej: 1423500"
                      className={inputClasses}
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Tipo de Contrato *
                    </label>
                    <select
                      value={tipoContrato}
                      onChange={(e) => setTipoContrato(e.target.value)}
                      className={selectClasses}
                    >
                      {contratoOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Cargo
                    </label>
                    <input
                      type="text"
                      value={cargo}
                      onChange={(e) => setCargo(e.target.value)}
                      placeholder="Ej: TECNICO INSTALACIONES"
                      className={inputClasses}
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Estado
                    </label>
                    <select
                      value={estado}
                      onChange={(e) => setEstado(e.target.value)}
                      className={selectClasses}
                    >
                      <option value="ACTIVO">Activo</option>
                      <option value="INACTIVO">Inactivo / Retirado</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Fecha de Ingreso
                    </label>
                    <input
                      type="date"
                      value={fechaIngreso}
                      onChange={(e) => setFechaIngreso(e.target.value)}
                      className={inputClasses}
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Fecha de egreso (si aplica)
                    </label>
                    <input
                      type="date"
                      value={fechaEgreso}
                      onChange={(e) => setFechaEgreso(e.target.value)}
                      className={inputClasses}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                      Género gramatical
                    </label>
                    <select
                      value={genero}
                      onChange={(e) => setGenero(e.target.value)}
                      className={selectClasses}
                    >
                      <option value="M">Masculino (el señor / identificado)</option>
                      <option value="F">Femenino (la señora / identificada)</option>
                    </select>
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-between gap-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowManualForm(false)}
                  >
                    Ocultar formulario
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleDownloadManual}
                    disabled={isDownloading}
                    startIcon={<Download size={15} />}
                  >
                    {isDownloading ? "Generando..." : "Generar con datos manuales"}
                  </Button>
                </div>
              </div>
            )}
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
                  Información para verificar la generación.
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
                  {cargo || selectedEmployee?.cargo || "No disponible"}
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
                  Modo de generación
                </dt>
                <dd className="font-medium text-gray-800 dark:text-white/90">
                  {showManualForm ? "Ingreso manual de datos" : "Automático (SIIGO)"}
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
