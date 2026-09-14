import { apiClient } from "./client";
import type { Page, UserAdminCreate, UserRead, UserRole } from "@/types/api";

export const usersApi = {
  list: (params: { skip?: number; limit?: number } = {}) =>
    apiClient.get<Page<UserRead>>("/users", { params }).then((r) => r.data),

  create: (payload: UserAdminCreate) =>
    apiClient.post<UserRead>("/users", payload).then((r) => r.data),

  get: (userId: string) =>
    apiClient.get<UserRead>(`/users/${userId}`).then((r) => r.data),

  changeRole: (userId: string, role: UserRole) =>
    apiClient.patch<UserRead>(`/users/${userId}/role`, { role }).then((r) => r.data),

  setStatus: (userId: string, isActive: boolean) =>
    apiClient
      .patch<UserRead>(`/users/${userId}/status`, { is_active: isActive })
      .then((r) => r.data),
};
