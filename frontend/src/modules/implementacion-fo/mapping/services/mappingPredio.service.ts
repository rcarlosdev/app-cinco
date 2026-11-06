import api from "@/lib/api";
import {
  MappingPredio,
  CuadraCheckResult,
  DireccionCheckResult,
  ImportResult,
  MappingPredioFiltros,
} from "../types";

const BASE_URL = "/implementacion-fo/mapping-predios";

export const mappingPredioService = {
  async listar(filtros?: MappingPredioFiltros): Promise<MappingPredio[]> {
    const res = await api.get(`${BASE_URL}/`, { params: filtros });
    return res.data?.results || res.data || [];
  },

  async obtenerPorId(id: number): Promise<MappingPredio> {
    const res = await api.get(`${BASE_URL}/${id}/`);
    return res.data;
  },

  async crear(data: Partial<MappingPredio>): Promise<MappingPredio> {
    const res = await api.post(`${BASE_URL}/`, data);
    return res.data;
  },

  async actualizar(id: number, data: Partial<MappingPredio>): Promise<MappingPredio> {
    const res = await api.patch(`${BASE_URL}/${id}/`, data);
    return res.data;
  },

  async eliminar(id: number): Promise<void> {
    await api.delete(`${BASE_URL}/${id}/`);
  },

  async verificarCuadra(
    barrio: string,
    loteAmp: string,
    nombreCalle?: string,
  ): Promise<CuadraCheckResult> {
    const res = await api.get(`${BASE_URL}/verificar-cuadra/`, {
      params: {
        barrio,
        lote_amp: loteAmp,
        nombre_calle: nombreCalle,
      },
    });
    return res.data;
  },

  async verificarDireccion(
    nombreCalle: string,
    placaUnidad: string,
    interior?: string,
    excludeId?: number,
  ): Promise<DireccionCheckResult> {
    const res = await api.get(`${BASE_URL}/verificar-direccion/`, {
      params: {
        nombre_calle: nombreCalle,
        placa_unidad: placaUnidad,
        interior,
        exclude_id: excludeId,
      },
    });
    return res.data;
  },

  async getBarriosSugeridos(q?: string): Promise<string[]> {
    const res = await api.get(`${BASE_URL}/barrios-sugeridos/`, {
      params: { q },
    });
    return res.data?.barrios || [];
  },

  async getPlanchasSugeridas(barrio?: string, q?: string): Promise<string[]> {
    const res = await api.get(`${BASE_URL}/planchas-sugeridas/`, {
      params: { barrio, q },
    });
    return res.data?.planchas || [];
  },

  async importarCsv(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append("archivo", file);
    const res = await api.post(`${BASE_URL}/importar-csv/`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return res.data;
  },

  async importarExcel(file: File): Promise<ImportResult> {
    return this.importarCsv(file);
  },

  async exportarExcel(filtros?: MappingPredioFiltros): Promise<Blob> {
    const res = await api.get(`${BASE_URL}/exportar-excel/`, {
      params: filtros,
      responseType: "blob",
    });
    return res.data;
  },

  async syncSharePoint(predioId: number): Promise<{ success: boolean; message?: string; error?: string }> {
    const res = await api.post(`${BASE_URL}/${predioId}/sync-sharepoint/`);
    return res.data;
  },

  async syncSharePointBarrio(barrio: string): Promise<{ success: boolean; count?: number; message?: string; error?: string }> {
    const res = await api.post(`${BASE_URL}/sync-sharepoint-barrio/`, { barrio });
    return res.data;
  },

  async testSharePointConexion(): Promise<{ success: boolean; message?: string; drives_count?: number; error?: string }> {
    const res = await api.get("/implementacion-fo/sharepoint-mapping/test-conexion/");
    return res.data;
  },

  async autoDescubrirBarriosSharePoint(): Promise<{
    success: boolean;
    listas?: { creadas?: number; actualizadas?: number; total_listas_encontradas?: number };
    archivos?: { creados?: number; actualizados?: number; total_archivos_encontrados?: number };
    error?: string;
  }> {
    const res = await api.post("/implementacion-fo/sharepoint-mapping/auto-descubrir/");
    return res.data;
  },

  async getBarriosSharePoint(): Promise<Array<{ barrio: string; descripcion?: string; sp_item_id?: string; tipo_destino?: string }>> {
    try {
      const res = await api.get("/implementacion-fo/sharepoint-mapping/?tipo_destino=LISTA");
      const data = res.data?.results || res.data || [];
      return data.filter((c: any) => c.activo !== false && (c.tipo_destino === "LISTA" || !c.tipo_destino));
    } catch {
      return [];
    }
  },
};


