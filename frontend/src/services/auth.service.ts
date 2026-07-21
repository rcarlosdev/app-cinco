import api from "@/lib/api";

export type AuthUser = {
  id: number;
  username: string;
  nombre?: string;
  apellido?: string;
  email?: string;
  is_superuser?: boolean;
  foto?: string;
  area?: string;
  carpeta?: string;
};

export type LoginPayload = {
  username: string;
  password: string;
};

export type LoginResponse = {
  user: AuthUser;
};

export type SessionResponse = {
  authenticated: boolean;
  user: AuthUser;
};

export const loginUser = async (
  payload: LoginPayload,
): Promise<LoginResponse> => {
  const response = await api.post<LoginResponse>("/auth/login/", payload);
  return response.data;
};

export const validateSession = async (): Promise<SessionResponse> => {
  const response = await api.get<SessionResponse>("/auth/session/");
  return response.data;
};

export const logoutUser = async (): Promise<void> => {
  await api.post("/auth/logout/");
};
