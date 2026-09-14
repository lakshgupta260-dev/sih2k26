import { apiClient } from "./client";
import type { AnalyticsSummary, SCurvePoint } from "@/types/api";

export const analyticsApi = {
  summary: (projectId: string, scheduleId: string) =>
    apiClient
      .get<AnalyticsSummary>(`/projects/${projectId}/schedules/${scheduleId}/analytics/summary`)
      .then((r) => r.data),

  sCurve: (projectId: string, scheduleId: string) =>
    apiClient
      .get<SCurvePoint[]>(`/projects/${projectId}/schedules/${scheduleId}/analytics/s-curve`)
      .then((r) => r.data),
};
