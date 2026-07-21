// src/utils/permission.ts
import { AuthUser } from "@/services/auth.service";

/**
 * Normaliza cadenas removiendo tildes, caracteres especiales,
 * espacios innecesarios y convirtiendo a mayúsculas.
 */
const normalizeText = (str?: string | null): string => {
  if (!str) return "";
  return str
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase();
};

/**
 * Evalúa si un usuario tiene permiso para acceder al módulo de generación
 * de certificados laborales.
 *
 * Condiciones:
 * 1. Es superusuario (`is_superuser: true`).
 * 2. O pertenece al área 'GESTION HUMANA' Y a la carpeta 'GESTION HUMANA'.
 */
export const hasCertificadosPermission = (
  user: AuthUser | null | undefined,
): boolean => {
  if (!user) return false;
  if (user.is_superuser) return true;

  const area = normalizeText(user.area);
  const carpeta = normalizeText(user.carpeta);

  const isGestionHumanaArea =
    area.includes("GESTION HUMANA") ||
    area.includes("GESTION DE PERSONAL") ||
    area.includes("RECURSOS HUMANOS") ||
    area.includes("RRHH");

  const isGestionHumanaCarpeta =
    carpeta.includes("GESTION HUMANA") ||
    carpeta.includes("GESTION DE PERSONAL") ||
    carpeta.includes("RECURSOS HUMANOS") ||
    carpeta.includes("RRHH");

  // Cumple la condición si pertenece estrictamente a AMBAS (área Y carpeta de Gestión Humana)
  return isGestionHumanaArea && isGestionHumanaCarpeta;
};
