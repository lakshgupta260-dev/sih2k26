import { apiClient } from "./client";
import type { GeneratedReportCreate, GeneratedReportRead, Page } from "@/types/api";

export const generatedReportsApi = {
  request: (projectId: string, payload: GeneratedReportCreate) =>
    apiClient
      .post<GeneratedReportRead>(`/projects/${projectId}/generated-reports`, payload)
      .then((r) => r.data),

  list: (projectId: string, params: { skip?: number; limit?: number } = {}) =>
    apiClient
      .get<Page<GeneratedReportRead>>(`/projects/${projectId}/generated-reports`, { params })
      .then((r) => r.data),

  get: (projectId: string, reportId: string) =>
    apiClient
      .get<GeneratedReportRead>(`/projects/${projectId}/generated-reports/${reportId}`)
      .then((r) => r.data),

  download: (projectId: string, reportId: string) =>
    apiClient
      .get(`/projects/${projectId}/generated-reports/${reportId}/download`, {
        responseType: "blob",
      })
      .then((r) => r),
};
