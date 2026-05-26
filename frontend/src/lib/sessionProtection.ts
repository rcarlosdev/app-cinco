import { clearUser } from "@/utils/storage";

const SESSION_PROTECTION_EVENT_KEY = "auth.sessionProtectionEvent";

export const UNAUTHORIZED_DEVICE_DETAIL =
  "Token usado desde dispositivo no autorizado";

export type SessionProtectionReason = "unauthorized_device";

interface SessionProtectionEvent {
  reason: SessionProtectionReason;
  timestamp: number;
}

export const isUnauthorizedDeviceMessage = (
  ...messages: Array<string | null | undefined>
): boolean =>
  messages.some((message) =>
    String(message || "")
      .toLowerCase()
      .includes(UNAUTHORIZED_DEVICE_DETAIL.toLowerCase()),
  );

export const persistSessionProtectionEvent = (
  reason: SessionProtectionReason,
): void => {
  if (typeof window === "undefined") return;

  const payload: SessionProtectionEvent = {
    reason,
    timestamp: Date.now(),
  };

  sessionStorage.setItem(SESSION_PROTECTION_EVENT_KEY, JSON.stringify(payload));
};

export const consumeSessionProtectionEvent =
  (): SessionProtectionEvent | null => {
    if (typeof window === "undefined") return null;

    const raw = sessionStorage.getItem(SESSION_PROTECTION_EVENT_KEY);
    if (!raw) return null;

    sessionStorage.removeItem(SESSION_PROTECTION_EVENT_KEY);

    try {
      return JSON.parse(raw) as SessionProtectionEvent;
    } catch {
      return null;
    }
  };

export const clearProtectedSessionState = (): void => {
  clearUser();
};

export const getSessionProtectionMessage = (
  reason: SessionProtectionReason,
): string => {
  switch (reason) {
    case "unauthorized_device":
      return "Por seguridad, cerramos tu sesión porque detectamos uso del token desde un dispositivo no autorizado.";
    default:
      return "Por seguridad, cerramos tu sesión. Inicia sesión nuevamente.";
  }
};
