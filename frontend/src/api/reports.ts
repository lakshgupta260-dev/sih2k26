import { apiClient } from "./client";
import type { Page, ProgressReportRead } from "@/types/api";

export const reportsApi = {
  list: (projectId: string, params: { skip?: number; limit?: number } = {}) =>
    apiClient
      .get<Page<ProgressReportRead>>(`/projects/${projectId}/reports`, { params })
      .then((r) => r.data),

  get: (projectId: string, reportId: string) =>
    apiClient
      .get<ProgressReportRead>(`/projects/${projectId}/reports/${reportId}`)
      .then((r) => r.data),
};
