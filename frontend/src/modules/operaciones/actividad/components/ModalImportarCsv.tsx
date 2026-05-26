import { useState, useRef } from "react";
import api from "@/lib/api";
import { getEmpleadoByCedula } from "@/services/empleado.service";
import { useActividadStore } from "@/store/actividad.store";
import { toast } from "sonner";

interface ModalImportarCsvProps {
  isOpen: boolean;
  onClose: () => void;
}

interface CsvRowData {
  index: number;
  ot: string;
  fecha_inicio: string;
  fecha_fin_estimado: string;
  responsable_cedula: string;
  responsable_id?: number;
  responsable_nombre?: string;
  tipo_trabajo: string;
  descripcion: string;
  direccion: string;
  nodo: string;
  ots_hijas: string[];
  status: "pending" | "validating" | "valid" | "error" | "uploading" | "success";
  errorMessage?: string;
}

const splitCsvLine = (text: string, delimiter: string): string[] => {
  const entries: string[] = [];
  let insideQuote = false;
  let current = "";

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (insideQuote && text[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        insideQuote = !insideQuote;
      }
      continue;
    }

    if (char === delimiter && !insideQuote) {
      entries.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  entries.push(current.trim());
  return entries.map((value) => value.trim());
};

const parseCsvLine = (text: string, delimiter: string): string[] =>
  splitCsvLine(text, delimiter).map((value) => {
    let cleaned = value;
    if (cleaned.startsWith('"') && cleaned.endsWith('"')) {
      cleaned = cleaned.slice(1, -1);
    }
    return cleaned.trim();
  });

const hasMeaningfulCsvValue = (columns: string[]): boolean =>
  columns.some((value) => value.trim().length > 0);

const detectCsvDelimiter = (headerLine: string): string => {
  const commaColumns = splitCsvLine(headerLine, ",").length;
  const semicolonColumns = splitCsvLine(headerLine, ";").length;
  return semicolonColumns > commaColumns ? ";" : ",";
};

const formatApiError = (error: any): string => {
  const data = error?.response?.data;
  if (!data) {
    return error?.message || "Error al subir la actividad.";
  }

  if (typeof data === "string") {
    return data;
  }

  if (Array.isArray(data)) {
    return data.join(" ");
  }

  if (typeof data === "object") {
    const messages = Object.entries(data).flatMap(([field, value]) => {
      const normalizedValue = Array.isArray(value) ? value.join(" ") : String(value);
      return normalizedValue ? [`${field}: ${normalizedValue}`] : [];
    });

    if (messages.length > 0) {
      return messages.join(" | ");
    }
  }

  return error?.message || "Error al subir la actividad.";
};

export default function ModalImportarCsv({ isOpen, onClose }: ModalImportarCsvProps) {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<CsvRowData[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { upsertActividad, loadActividades } = useActividadStore();

  if (!isOpen) return null;

  // Descarga dinámica de la plantilla CSV de ejemplo
  const descargarPlantilla = () => {
    const headers = [
      "ot",
      "fecha_inicio",
      "fecha_fin_estimado",
      "responsable_cedula",
      "tipo_trabajo",
      "descripcion",
      "direccion",
      "nodo",
      "ots_hijas"
    ];

    const sampleRow1 = [
      "OT-2026-901",
      "2026-06-01",
      "2026-06-10",
      "1055837370",
      "MANTENIMIENTO",
      "Mantenimiento preventivo de transformadores",
      "Calle 45 # 23-45, Medellin",
      "N600",
      "OT-H101;OT-H102"
    ];

    const sampleRow2 = [
      "OT-2026-902",
      "2026-06-05",
      "2026-06-15",
      "1055837370",
      "INSTALACION",
      "Instalacion de nuevos nodos de red fibra optica",
      "Carrera 80 # 45-67, Medellin",
      "N400",
      ""
    ];

    const csvContent = [
      headers.join(","),
      sampleRow1.map(v => `"${v.replace(/"/g, '""')}"`).join(","),
      sampleRow2.map(v => `"${v.replace(/"/g, '""')}"`).join(",")
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "plantilla_actividades.csv";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success("Plantilla descargada con éxito");
  };

  // Procesa y valida el archivo CSV
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setRows([]);
    setIsProcessing(true);

    const reader = new FileReader();
    reader.onload = async (event) => {
      const content = event.target?.result as string;
      if (!content) {
        setIsProcessing(false);
        toast.error("El archivo está vacío");
        return;
      }

      const lines = content.split(/\r?\n/).filter(line => line.trim().length > 0);
      if (lines.length <= 1) {
        setIsProcessing(false);
        toast.error("El archivo no contiene filas de datos");
        return;
      }

      // Validar y normalizar cabeceras
      const delimiter = detectCsvDelimiter(lines[0]);
      const headers = parseCsvLine(lines[0].toLowerCase(), delimiter).map((value) =>
        value.replace(/^\uFEFF/, "").trim(),
      );

      const otIdx = headers.indexOf("ot");
      const fInicioIdx = headers.indexOf("fecha_inicio");
      const fFinIdx = headers.indexOf("fecha_fin_estimado");
      const cedulaIdx = headers.indexOf("responsable_cedula");
      const tipoIdx = headers.indexOf("tipo_trabajo");
      const descIdx = headers.indexOf("descripcion");
      const dirIdx = headers.indexOf("direccion");
      const nodoIdx = headers.indexOf("nodo");
      const hijasIdx = headers.indexOf("ots_hijas");

      if (otIdx === -1 || fInicioIdx === -1 || fFinIdx === -1 || cedulaIdx === -1 || dirIdx === -1 || tipoIdx === -1) {
        setIsProcessing(false);
        toast.error("El CSV no tiene las columnas obligatorias requeridas");
        return;
      }

      const parsedRows: CsvRowData[] = [];

      for (let i = 1; i < lines.length; i++) {
        const columns = parseCsvLine(lines[i], delimiter);
        if (!hasMeaningfulCsvValue(columns)) continue;

        const rowOt = columns[otIdx] || "";
        const rowFInicio = columns[fInicioIdx] || "";
        const rowFFin = columns[fFinIdx] || "";
        const rowCedula = columns[cedulaIdx] || "";
        const rowTipo = columns[tipoIdx] || "";
        const rowDesc = descIdx !== -1 ? columns[descIdx] || "" : "";
        const rowDir = columns[dirIdx] || "";
        const rowNodo = nodoIdx !== -1 ? columns[nodoIdx] || "" : "";
        const rowHijasRaw = hijasIdx !== -1 ? columns[hijasIdx] || "" : "";

        const listHijas = rowHijasRaw
          ? rowHijasRaw.split(";").map(o => o.trim()).filter(Boolean)
          : [];

        parsedRows.push({
          index: i,
          ot: rowOt,
          fecha_inicio: rowFInicio,
          fecha_fin_estimado: rowFFin,
          responsable_cedula: rowCedula,
          tipo_trabajo: rowTipo,
          descripcion: rowDesc,
          direccion: rowDir,
          nodo: rowNodo,
          ots_hijas: listHijas,
          status: "pending"
        });
      }

      // Validar fila por fila en caliente contra Zod y resolver cédulas
      const validatedRows: CsvRowData[] = [];
      for (const row of parsedRows) {
        let hasError = false;
        let errMsg = "";

        if (!row.ot) {
          hasError = true;
          errMsg = "La OT Padre es obligatoria. ";
        }
        if (!row.fecha_inicio || isNaN(Date.parse(row.fecha_inicio))) {
          hasError = true;
          errMsg += "Fecha inicio inválida (AAAA-MM-DD). ";
        }
        if (!row.fecha_fin_estimado || isNaN(Date.parse(row.fecha_fin_estimado))) {
          hasError = true;
          errMsg += "Fecha fin estimada inválida (AAAA-MM-DD). ";
        }
        if (
          row.fecha_inicio &&
          row.fecha_fin_estimado &&
          !isNaN(Date.parse(row.fecha_inicio)) &&
          !isNaN(Date.parse(row.fecha_fin_estimado)) &&
          new Date(row.fecha_fin_estimado) < new Date(row.fecha_inicio)
        ) {
          hasError = true;
          errMsg += "La fecha fin estimada no puede ser menor que la fecha inicio. ";
        }
        if (!row.responsable_cedula) {
          hasError = true;
          errMsg += "La cédula del responsable es obligatoria. ";
        }
        if (!row.tipo_trabajo) {
          hasError = true;
          errMsg += "El tipo de trabajo es obligatorio. ";
        }
        if (!row.direccion) {
          hasError = true;
          errMsg += "La dirección es obligatoria. ";
        }

        if (hasError) {
          validatedRows.push({ ...row, status: "error", errorMessage: errMsg.trim() });
          continue;
        }

        // Resolución asíncrona de cédula de empleado
        try {
          const empleado = await getEmpleadoByCedula(row.responsable_cedula);
          if (empleado) {
            validatedRows.push({
              ...row,
              status: "valid",
              responsable_id: empleado.id,
              responsable_nombre: `${empleado.nombre} ${empleado.apellido}`
            });
          } else {
            validatedRows.push({
              ...row,
              status: "error",
              errorMessage: `La cédula ${row.responsable_cedula} no está registrada en el sistema.`
            });
          }
        } catch (error) {
          validatedRows.push({
            ...row,
            status: "error",
            errorMessage: `Error validando cédula contra el servidor de empleados.`
          });
        }
      }

      setRows(validatedRows);
      setIsProcessing(false);
      const errorsCount = validatedRows.filter(r => r.status === "error").length;
      if (errorsCount > 0) {
        toast.warning(`CSV cargado con ${errorsCount} filas con errores de validación.`);
      } else {
        toast.success("CSV cargado y validado con éxito.");
      }
    };

    reader.onerror = () => {
      setIsProcessing(false);
      toast.error("Error al leer el archivo");
    };

    reader.readAsText(selectedFile, "UTF-8");
  };

  // Sube secuencialmente las actividades válidas
  const iniciarImportacion = async () => {
    const validRows = rows.filter(r => r.status === "valid");
    if (validRows.length === 0) {
      toast.error("No hay registros válidos para importar");
      return;
    }

    setIsProcessing(true);
    setProgress({ current: 0, total: validRows.length });

    let exitoCount = 0;
    let fallosCount = 0;

    const updatedRows = [...rows];

    for (let i = 0; i < validRows.length; i++) {
      const row = validRows[i];
      const rowIndex = updatedRows.findIndex(r => r.index === row.index);

      if (rowIndex !== -1) {
        updatedRows[rowIndex].status = "uploading";
        setRows([...updatedRows]);
      }

      // Curación por defecto: las OTs Hijas adoptan por defecto el mismo rango de fechas del Padre
      const listOtsPayload = [
        {
          ot: row.ot,
          fecha_inicio: row.fecha_inicio,
          fecha_fin: row.fecha_fin_estimado
        },
        ...row.ots_hijas.map(otHija => ({
          ot: otHija,
          fecha_inicio: row.fecha_inicio,
          fecha_fin: row.fecha_fin_estimado
        }))
      ];

      const payload = {
        ot: row.ot,
        ots: listOtsPayload,
        fecha_inicio: row.fecha_inicio,
        fecha_fin_estimado: row.fecha_fin_estimado,
        responsable_id: row.responsable_id,
        estado: "pendiente",
        detalle: {
          tipo_trabajo: row.tipo_trabajo,
          descripcion: row.descripcion || `Importación de OT Padre ${row.ot}`
        },
        ubicacion: {
          direccion: row.direccion,
          coordenada_x: "",
          coordenada_y: "",
          zona: "",
          nodo: row.nodo
        }
      };

      try {
        const res = await api.post("/operaciones/actividades/", payload);
        upsertActividad(res.data);
        exitoCount++;
        if (rowIndex !== -1) {
          updatedRows[rowIndex].status = "success";
        }
      } catch (err: any) {
        fallosCount++;
        if (rowIndex !== -1) {
          updatedRows[rowIndex].status = "error";
          updatedRows[rowIndex].errorMessage = formatApiError(err);
        }
      }

      setProgress({ current: i + 1, total: validRows.length });
      setRows([...updatedRows]);
    }

    setIsProcessing(false);
    
    if (exitoCount > 0) {
      try {
        await loadActividades();
      } catch (error) {
        console.error("Error al recargar actividades tras importación:", error);
      }
    }

    if (fallosCount === 0) {
      toast.success(`Importación finalizada. ${exitoCount} actividades creadas exitosamente.`);
      setTimeout(() => {
        onClose();
      }, 1500);
    } else {
      toast.warning(`Importación completada con observaciones. Éxito: ${exitoCount}, Errores: ${fallosCount}.`);
    }
  };

  const validCount = rows.filter(r => r.status === "valid").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs transition-opacity duration-300">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-800 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Cabecera */}
        <div className="p-6 border-b border-gray-150 dark:border-gray-800 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              Importar Actividades mediante CSV
            </h2>
            <p className="text-xs text-gray-500 mt-1">Crea múltiples actividades de forma masiva a través de un archivo de datos estructurado.</p>
          </div>
          <button 
            type="button" 
            onClick={onClose}
            disabled={isProcessing}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Cuerpo */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Zona de descarga e instrucciones */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center bg-gray-50/50 dark:bg-gray-800/40 p-5 rounded-2xl border border-gray-200/50 dark:border-gray-800">
            <div className="md:col-span-2 space-y-2">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">¿Cómo importar tus datos?</h3>
              <ul className="text-xs text-gray-500 dark:text-gray-400 space-y-1 list-disc pl-4">
                <li>Descarga nuestra plantilla CSV de ejemplo con la estructura adecuada.</li>
                <li>Completa los campos obligatorios: <span className="font-semibold text-gray-700 dark:text-gray-300">ot, fecha_inicio, fecha_fin_estimado, responsable_cedula y direccion</span>.</li>
                <li>Las OTs Hijas en la columna <span className="font-semibold text-gray-700 dark:text-gray-300">ots_hijas</span> deben separarse por punto y coma (ej. <span className="font-mono text-[10px]">OT-H1;OT-H2</span>).</li>
              </ul>
            </div>
            <div className="flex justify-start md:justify-end">
              <button
                type="button"
                onClick={descargarPlantilla}
                className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-md hover:shadow-indigo-500/20 active:scale-95"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Descargar Plantilla CSV
              </button>
            </div>
          </div>

          {/* Zona de Drop/Selección de Archivo */}
          <div 
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center cursor-pointer transition-all duration-300 ${
              file 
                ? "border-emerald-300 bg-emerald-50/10 dark:bg-emerald-950/5" 
                : "border-gray-300 dark:border-gray-700 hover:border-indigo-400 dark:hover:border-indigo-500 bg-gray-50/20 hover:bg-indigo-50/10 dark:hover:bg-indigo-950/5"
            } ${isProcessing ? "opacity-60 cursor-not-allowed" : ""}`}
          >
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleFileChange} 
              accept=".csv"
              disabled={isProcessing}
              className="hidden" 
            />
            
            <div className={`p-4 rounded-full mb-3 ${file ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400" : "bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400"}`}>
              {file ? (
                <svg className="w-8 h-8 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              )}
            </div>

            <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              {file ? file.name : "Selecciona o arrastra tu archivo CSV"}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              {file ? `${(file.size / 1024).toFixed(1)} KB` : "Solo archivos con extensión .csv"}
            </p>
          </div>

          {/* Vista previa de registros cargados */}
          {rows.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-gray-800 dark:text-gray-200 flex items-center justify-between">
                <span>Vista Previa de Registros ({rows.length} detectados)</span>
                <span className="text-xs font-normal text-gray-500">
                  {validCount} listos para importar | {rows.length - validCount} con errores
                </span>
              </h3>
              
              <div className="border border-gray-150 dark:border-gray-800 rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-50 dark:bg-gray-800/80 sticky top-0 z-10">
                    <tr className="border-b border-gray-150 dark:border-gray-800 text-[10px] font-bold text-gray-500 uppercase">
                      <th className="px-4 py-2.5">OT</th>
                      <th className="px-4 py-2.5">Fechas</th>
                      <th className="px-4 py-2.5">Responsable (Cédula)</th>
                      <th className="px-4 py-2.5">Dirección / Nodo</th>
                      <th className="px-4 py-2.5">Hijas</th>
                      <th className="px-4 py-2.5 text-right">Estado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-150 dark:divide-gray-800 text-xs text-gray-700 dark:text-gray-300">
                    {rows.map((row) => (
                      <tr 
                        key={row.index}
                        className={`hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors ${
                          row.status === "error" 
                            ? "bg-red-50/20 dark:bg-red-950/5" 
                            : row.status === "success" 
                              ? "bg-emerald-50/20 dark:bg-emerald-950/5" 
                              : ""
                        }`}
                      >
                        <td className="px-4 py-3 font-semibold font-mono">{row.ot || "-"}</td>
                        <td className="px-4 py-3">
                          <div className="font-mono text-[10px]">{row.fecha_inicio || "-"} al</div>
                          <div className="font-mono text-[10px] text-gray-400">{row.fecha_fin_estimado || "-"}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium">{row.responsable_nombre || "-"}</div>
                          <div className="text-[10px] text-gray-400 font-mono">{row.responsable_cedula || "-"}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="truncate max-w-[150px]" title={row.direccion}>{row.direccion || "-"}</div>
                          <div className="text-[10px] text-indigo-500 font-semibold">{row.nodo || "-"}</div>
                        </td>
                        <td className="px-4 py-3">
                          {row.ots_hijas.length > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
                              {row.ots_hijas.length} hijas
                            </span>
                          ) : (
                            <span className="text-gray-400 text-[10px]">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {row.status === "valid" && (
                            <span className="inline-flex px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                              Válido
                            </span>
                          )}
                          {row.status === "error" && (
                            <span 
                              className="inline-flex px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 cursor-help"
                              title={row.errorMessage}
                            >
                              Error
                            </span>
                          )}
                          {row.status === "uploading" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                              <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                              Subiendo
                            </span>
                          )}
                          {row.status === "success" && (
                            <span className="inline-flex px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500 text-white shadow-xs">
                              Guardado
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>

        {/* Barra de Progreso en Vivo */}
        {isProcessing && progress.total > 0 && (
          <div className="px-6 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-150 dark:border-gray-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 font-semibold">
              <span>Procesando e importando actividades a base de datos...</span>
              <span>{progress.current} de {progress.total} completadas</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 h-2 rounded-full overflow-hidden">
              <div 
                className="bg-indigo-600 h-full rounded-full transition-all duration-300 ease-out shadow-xs shadow-indigo-500/50"
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Pie del Modal */}
        <div className="p-6 border-t border-gray-150 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/20 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isProcessing}
            className="px-4 py-2 text-sm font-semibold rounded-xl border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 active:scale-95 transition-all duration-200 disabled:opacity-50"
          >
            Cerrar
          </button>
          
          <button
            type="button"
            onClick={iniciarImportacion}
            disabled={isProcessing || validCount === 0}
            className="flex items-center gap-2 px-5 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:dark:bg-gray-800 disabled:text-gray-400 disabled:dark:text-gray-600 disabled:shadow-none disabled:cursor-not-allowed rounded-xl transition-all shadow-md hover:shadow-indigo-500/25 active:scale-95"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
            </svg>
            Importar {validCount > 0 ? `${validCount} Actividades` : ""}
          </button>
        </div>

      </div>
    </div>
  );
}
