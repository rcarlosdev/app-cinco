// src/services/empleado.service.ts
import api from "@/lib/api";
import { Empleado } from "@/types/empleado";
import { cache } from "@/lib/cache";

const CACHE_TTL = {
  ALL_EMPLOYEES: 10 * 60 * 1000, // 10 minutos para lista completa
  SEARCH: 5 * 60 * 1000, // 5 minutos para búsquedas
  SINGLE: 15 * 60 * 1000, // 15 minutos para empleado individual
};

export const getEmpleados = async (): Promise<Empleado[]> => {
  return cache.getOrFetch(
    "empleados:all",
    async () => {
      const res = await api.get("/empleados/empleados/");
      return res.data;
    },
    CACHE_TTL.ALL_EMPLOYEES,
  );
};

export const searchEmpleados = async (
  query: string,
  includeInactive = false,
): Promise<Empleado[]> => {
  const cacheKey = `empleados:search:${query.toLowerCase().trim()}:${includeInactive}`;

  return cache.getOrFetch(
    cacheKey,
    async () => {
      const params: any = { search: query };
      if (includeInactive) {
        params.estado = "all";
      }
      const res = await api.get("/empleados/empleados/", { params });
      return res.data;
    },
    CACHE_TTL.SEARCH,
  );
};

export const getEmpleadoByCedula = async (
  cedula: string,
): Promise<Empleado> => {
  const cacheKey = `empleados:cedula:${cedula}`;

  return cache.getOrFetch(
    cacheKey,
    async () => {
      // Buscar empleado por cédula usando el endpoint de búsqueda
      const res = await api.get("/empleados/empleados/", {
        params: { search: cedula },
      });
      
      // Buscar el empleado que coincida exactamente con la cédula
      const empleado = res.data.find((emp: Empleado) => emp.cedula === cedula);
      
      if (!empleado) {
        throw new Error(`Empleado con cédula ${cedula} no encontrado`);
      }
      
      return empleado;
    },
    CACHE_TTL.SINGLE,
  );
};

export const getEmpleadoById = async (id: number): Promise<Empleado> => {
  const cacheKey = `empleados:id:${id}`;

  return cache.getOrFetch(
    cacheKey,
    async () => {
      const res = await api.get(`/empleados/empleados/${id}/`);
      return res.data;
    },
    CACHE_TTL.SINGLE,
  );
};

export const downloadCertificadoLaboral = async (
  id: number,
  documentType?: "CC" | "PT" | "TI" | "CE",
): Promise<{ blob: Blob; filename: string }> => {
  const response = await api.get(
    `/empleados/empleados/${id}/certificado-laboral/`,
    {
      params: documentType ? { document_type: documentType } : undefined,
      responseType: "blob",
    },
  );

  const contentDisposition = String(
    response.headers["content-disposition"] || "",
  );
  const filenameMatch = contentDisposition.match(/filename="([^"]+)"/i);

  return {
    blob: response.data as Blob,
    filename: filenameMatch?.[1] || `certificado_laboral_${id}.pdf`,
  };
};

/**
 * Limpiar el caché de empleados
 * Útil cuando se actualiza, crea o elimina un empleado
 */
export const clearEmpleadosCache = (): void => {
  // Obtener todas las claves del caché
  const stats = cache.getStats();

  // Eliminar todas las claves que comiencen con "empleados:"
  stats.keys.forEach((key) => {
    if (key.startsWith("empleados:")) {
      cache.delete(key);
    }
  });
};
