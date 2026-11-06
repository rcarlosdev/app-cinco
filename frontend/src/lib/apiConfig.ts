export const normalizeApiBaseUrl = (url: string): string => {
  const trimmedUrl = url.trim();
  return trimmedUrl.endsWith("/") ? trimmedUrl : `${trimmedUrl}/`;
};

export const getApiBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    // Si se accede a través del túnel de Cloudflare o un host que no sea localhost directo:
    // Usamos el proxy de Next.js en el mismo origen (/api/) para:
    // 1. Evitar errores de Mixed Content (HTTPS -> HTTP)
    // 2. Permitir que las cookies HttpOnly funcionen como First-Party (mismo dominio)
    // 3. Permitir que cualquier dispositivo externo (móvil, otra PC) acceda al backend
    if (
      host.includes("trycloudflare.com") ||
      host.includes("cloudflare") ||
      (host !== "localhost" && host !== "127.0.0.1")
    ) {
      return `${window.location.origin}/api/`;
    }
  }

  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;
  if (configuredUrl) {
    return normalizeApiBaseUrl(configuredUrl);
  }

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000/`;
  }

  return "http://localhost:8000/";
};

export const API_BASE_URL = normalizeApiBaseUrl(
  typeof window !== "undefined"
    ? getApiBaseUrl()
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/",
);

