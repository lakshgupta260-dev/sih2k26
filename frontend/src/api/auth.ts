import { apiClient } from "./client";
import type {
  LoginRequest,
  LoginResponse,
  PasswordChange,
  UserCreate,
  UserRead,
  UserUpdate,
} from "@/types/api";

export const authApi = {
  register: (payload: UserCreate) =>
    apiClient.post<UserRead>("/auth/register", payload).then((r) => r.data),

  login: (payload: LoginRequest) =>
    apiClient.post<LoginResponse>("/auth/login", payload).then((r) => r.data),

  logout: (refreshToken?: string) =>
    apiClient
      .post<void>("/auth/logout", refreshToken ? { refresh_token: refreshToken } : {})
      .then((r) => r.data),

  me: () => apiClient.get<UserRead>("/auth/me").then((r) => r.data),

  changePassword: (payload: PasswordChange) =>
    apiClient.post<void>("/auth/change-password", payload).then((r) => r.data),

  updateProfile: (userId: string, payload: UserUpdate) =>
    apiClient.patch<UserRead>(`/users/${userId}`, payload).then((r) => r.data),
};
