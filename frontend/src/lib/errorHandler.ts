/**
 * Tipos y utilidades para manejar errores de la API
 */

import { API_BASE_URL } from "@/lib/apiConfig";
import { shouldExposeTechnicalDetails } from "@/lib/environment";
import { ZodError } from "zod";

export enum ApiErrorType {
  VALIDATION = "VALIDATION",
  AUTHENTICATION = "AUTHENTICATION",
  AUTHORIZATION = "AUTHORIZATION",
  NOT_FOUND = "NOT_FOUND",
  CONFLICT = "CONFLICT",
  RATE_LIMIT = "RATE_LIMIT",
  SERVER_ERROR = "SERVER_ERROR",
  NETWORK_ERROR = "NETWORK_ERROR",
  TIMEOUT = "TIMEOUT",
  UNKNOWN = "UNKNOWN",
}

export interface ApiErrorDetail {
  type: ApiErrorType;
  status: number;
  message: string;
  detail?: string;
  errors?: Record<string, string[]>;
  timestamp?: string;
}

export interface ApiError extends Error {
  type: ApiErrorType;
  status: number;
  originalError: any;
  errors?: Record<string, string[]>;
}

const getNetworkErrorMessage = (): string => {
  if (shouldExposeTechnicalDetails()) {
    return `No se pudo conectar con el backend (${API_BASE_URL}). Verifica que Django este corriendo y que la BD/VPN este disponible.`;
  }

  return "No fue posible conectar con el servicio. Intenta nuevamente en unos minutos.";
};

const getRawErrorMessage = (error: any): string => {
  if (!error) return "";
  if (typeof error.message === "string") return error.message;
  return String(error);
};

/**
 * Clasifica el tipo de error basado en el estado HTTP y contenido
 */
export function classifyError(error: any): ApiErrorDetail {
  if (
    error &&
    typeof error === "object" &&
    error.type &&
    error.status !== undefined
  ) {
    return error as ApiErrorDetail;
  }

  const status = error?.response?.status || 0;
  const data = error?.response?.data;
  const rawMessage =
    data?.message || data?.detail || getRawErrorMessage(error) || "Error desconocido";

  let type: ApiErrorType = ApiErrorType.UNKNOWN;

  if (error instanceof ZodError) {
    type = ApiErrorType.VALIDATION;
  } else if (error?.code === "ECONNABORTED") {
    type = ApiErrorType.TIMEOUT;
  } else if (!error?.response) {
    type = ApiErrorType.NETWORK_ERROR;
  } else {
    switch (status) {
      case 400:
        type = ApiErrorType.VALIDATION;
        break;
      case 401:
        type = ApiErrorType.AUTHENTICATION;
        break;
      case 403:
        type = ApiErrorType.AUTHORIZATION;
        break;
      case 404:
        type = ApiErrorType.NOT_FOUND;
        break;
      case 409:
        type = ApiErrorType.CONFLICT;
        break;
      case 429:
        type = ApiErrorType.RATE_LIMIT;
        break;
      case 500:
      case 502:
      case 503:
      case 504:
        type = ApiErrorType.SERVER_ERROR;
        break;
    }
  }

  const message =
    error instanceof ZodError
      ? "Se recibieron actividades con un formato inesperado del backend."
      : type === ApiErrorType.NETWORK_ERROR ||
    rawMessage === "Network Error" ||
    rawMessage === "Failed to fetch"
      ? getNetworkErrorMessage()
      : rawMessage;

  return {
    type,
    status,
    message,
    detail: data?.detail,
    errors:
      data?.errors ||
      (typeof data === "object" && !data?.detail && !data?.message
        ? data
        : undefined),
    timestamp: new Date().toISOString(),
  };
}

/**
 * Crea una instancia de ApiError tipada
 */
export function createApiError(error: any): ApiError {
  const classified = classifyError(error);
  const apiError: ApiError = new Error(classified.message) as ApiError;

  apiError.type = classified.type;
  apiError.status = classified.status;
  apiError.originalError = error;
  apiError.errors = classified.errors;
  apiError.name = "ApiError";

  return apiError;
}

/**
 * Obtiene el mensaje de error mas apropiado segun el tipo
 * Prioriza mensajes especificos del backend (Django)
 */
export function getErrorMessage(errorDetail: ApiErrorDetail): string {
  if (errorDetail.detail) {
    return errorDetail.detail;
  }
  if (errorDetail.message && errorDetail.message !== "Error desconocido") {
    return errorDetail.message;
  }

  switch (errorDetail.type) {
    case ApiErrorType.VALIDATION:
      return "Por favor, revisa los datos ingresados";
    case ApiErrorType.AUTHENTICATION:
      return "Credenciales invalidas o sesion expirada";
    case ApiErrorType.AUTHORIZATION:
      return "No tienes permisos para realizar esta accion";
    case ApiErrorType.NOT_FOUND:
      return "El recurso solicitado no fue encontrado";
    case ApiErrorType.CONFLICT:
      return "Existe un conflicto con los datos. Recarga e intenta nuevamente";
    case ApiErrorType.RATE_LIMIT:
      return "Has realizado demasiadas solicitudes. Intenta mas tarde";
    case ApiErrorType.SERVER_ERROR:
      return "Error en el servidor. Intenta mas tarde";
    case ApiErrorType.NETWORK_ERROR:
      return getNetworkErrorMessage();
    case ApiErrorType.TIMEOUT:
      return "La solicitud tardo demasiado tiempo. Intenta nuevamente";
    default:
      return "Ocurrio un error inesperado";
  }
}

/**
 * Extrae errores de validacion formateados para mostrar en formularios
 */
export function extractValidationErrors(
  apiError: ApiErrorDetail,
): Record<string, string> {
  if (!apiError.errors) {
    return {};
  }

  const formatted: Record<string, string> = {};

  if (typeof apiError.errors === "object") {
    Object.entries(apiError.errors).forEach(([field, messages]) => {
      if (Array.isArray(messages)) {
        formatted[field] = messages[0] || "Error de validacion";
      } else if (typeof messages === "string") {
        formatted[field] = messages;
      }
    });
  }

  return formatted;
}
