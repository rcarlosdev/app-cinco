export interface MappingPredio {
  id: number;
  nombre_conjunto: string;
  nombre_calle: string;
  placa_unidad: string;
  barrio: string;
  interior: string;
  num_casas: number;
  num_apartamentos: number;
  num_locales: number;
  num_pisos: number;
  calle_alterna_2: string;
  placa_alterna_2: string;
  calle_alterna_3: string;
  placa_alterna_3: string;
  distribucion: string;
  lote_amp: string;
  latitud: number | string | null;
  longitud: number | string | null;
  observaciones: string;
  total_unidades: number;
  direccion_completa: string;
  created_at: string;
  created_by: number | null;
  created_by_nombre?: string;
  updated_at: string;
  sp_synced?: boolean;
  sp_synced_at?: string | null;
  sp_sync_error?: string;
}

export interface SharePointMappingConfig {
  id: number;
  barrio: string;
  descripcion: string;
  tipo_destino: "EXCEL" | "LISTA";
  sp_drive_id: string;
  sp_item_id: string;
  sp_table_name: string;
  sp_list_id: string;
  activo: boolean;
  created_at: string;
  updated_at: string;
}


export interface MappingPredioFormData {
  nombre_conjunto: string;
  tipo_via: string;
  numero_via: string;
  nombre_calle: string;
  placa_unidad: string;
  barrio: string;
  interior: string;
  num_casas: number;
  num_apartamentos: number;
  num_locales: number;
  num_pisos: number;
  calle_alterna_2: string;
  placa_alterna_2: string;
  calle_alterna_3: string;
  placa_alterna_3: string;
  distribucion: string;
  lote_amp: string;
  latitud: string | number;
  longitud: string | number;
  observaciones: string;
}

export interface CuadraCheckResult {
  tiene_registros: boolean;
  total_predios: number;
  ultimo_registro_fecha: string | null;
  ultimo_recolector: string | null;
  mensaje: string;
  predios_recientes: MappingPredio[];
}

export interface DireccionCheckResult {
  existe_exacta: boolean;
  total_coincidencias: number;
  coincidencias: MappingPredio[];
  mensaje: string | null;
}

export interface ImportResult {
  total_procesados: number;
  total_creados: number;
  total_errores: number;
  errores: string[];
}

export interface MappingPredioFiltros {
  barrio?: string;
  lote_amp?: string;
  nombre_calle?: string;
  buscar?: string;
}
