import { create } from "zustand";
import { clearUser, getUser, saveUser } from "@/utils/storage";
import {
  AuthUser,
  LoginResponse,
  logoutUser,
  validateSession,
} from "@/services/auth.service";
import { ApiErrorDetail, classifyError } from "@/lib/errorHandler";
import { logDevelopmentError } from "@/lib/environment";

interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isCheckingSession: boolean;
  authError: ApiErrorDetail | null;
  login: (data: LoginResponse) => void;
  logout: () => Promise<void>;
  setAuthenticated: (isAuthenticated: boolean, user?: AuthUser | null) => void;
  hydrateFromStorage: () => void;
  validateCurrentSession: () => Promise<AuthUser | null>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isCheckingSession: false,
  authError: null,

  login: (data) => {
    if (data?.user) {
      saveUser(data.user);
      set({
        user: data.user,
        isAuthenticated: true,
        authError: null,
      });
    }
  },

  logout: async () => {
    try {
      await logoutUser();
    } catch (error) {
      logDevelopmentError("Error al cerrar sesion:", error);
    } finally {
      clearUser();
      set({
        user: null,
        isAuthenticated: false,
        isCheckingSession: false,
        authError: null,
      });
    }
  },

  setAuthenticated: (isAuthenticated, user = null) => {
    if (isAuthenticated && user) {
      saveUser(user);
    } else if (!isAuthenticated) {
      clearUser();
    }

    set({
      isAuthenticated,
      user,
      authError: null,
    });
  },

  hydrateFromStorage: () => {
    const storedUser = getUser();

    if (storedUser) {
      set({
        user: storedUser,
        isAuthenticated: true,
      });
      return;
    }

    set({
      user: null,
      isAuthenticated: false,
    });
  },

  validateCurrentSession: async () => {
    set({
      isCheckingSession: true,
      authError: null,
    });

    try {
      const session = await validateSession();

      if (session?.authenticated && session.user) {
        saveUser(session.user);
        set({
          user: session.user,
          isAuthenticated: true,
          isCheckingSession: false,
          authError: null,
        });
        return session.user;
      }

      clearUser();
      set({
        user: null,
        isAuthenticated: false,
        isCheckingSession: false,
      });
      return null;
    } catch (error: any) {
      const classifiedError = classifyError(error);
      clearUser();
      set({
        user: null,
        isAuthenticated: false,
        isCheckingSession: false,
        authError: classifiedError,
      });
      return null;
    }
  },
}));
