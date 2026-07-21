// src/types/empleado.ts
export interface Empleado {
  id: number;
  cedula: string;
  nombre: string;
  apellido: string;
  area?: string;
  carpeta?: string;
  cargo?: string;
  movil?: string;
  supervisor?: string;
  estado: string;
  link_foto?: string;
  fecha_ingreso?: string;
  fecha_egreso?: string;
  genero?: string;
}

export interface EmpleadoSearchResult {
  id: number;
  cedula: string;
  nombre: string;
  apellido: string;
  cargo?: string;
  movil?: string;
  link_foto?: string;
}
