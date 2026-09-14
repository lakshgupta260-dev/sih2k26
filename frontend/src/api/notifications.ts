import { apiClient } from "./client";
import type { NotificationCreate, NotificationRead, Page } from "@/types/api";

export const notificationsApi = {
  list: (params: { skip?: number; limit?: number } = {}) =>
    apiClient.get<Page<NotificationRead>>("/notifications", { params }).then((r) => r.data),

  unreadCount: () =>
    apiClient.get<{ count: number }>("/notifications/unread-count").then((r) => r.data),

  markRead: (notificationId: string) =>
    apiClient
      .patch<NotificationRead>(`/notifications/${notificationId}/read`)
      .then((r) => r.data),

  markAllRead: () =>
    apiClient.post<{ count: number }>("/notifications/read-all").then((r) => r.data),

  sendProjectNotification: (projectId: string, payload: NotificationCreate) =>
    apiClient
      .post<NotificationRead>(`/projects/${projectId}/notifications`, payload)
      .then((r) => r.data),
};
