import { apiClient } from "./client";
import type {
  ActivityProgressRollup,
  ActualProgressCreate,
  ActualProgressRead,
  MatchApplicationSummary,
} from "@/types/api";

export const progressApi = {
  record: (
    projectId: string,
    scheduleId: string,
    activityId: string,
    payload: ActualProgressCreate,
  ) =>
    apiClient
      .post<ActualProgressRead>(
        `/projects/${projectId}/schedules/${scheduleId}/activities/${activityId}/progress`,
        payload,
      )
      .then((r) => r.data),

  history: (projectId: string, scheduleId: string, activityId: string) =>
    apiClient
      .get<ActualProgressRead[]>(
        `/projects/${projectId}/schedules/${scheduleId}/activities/${activityId}/progress`,
      )
      .then((r) => r.data),

  rollup: (projectId: string, scheduleId: string) =>
    apiClient
      .get<ActivityProgressRollup[]>(
        `/projects/${projectId}/schedules/${scheduleId}/progress/rollup`,
      )
      .then((r) => r.data),

  applyMatches: (projectId: string, scheduleId: string) =>
    apiClient
      .post<MatchApplicationSummary>(
        `/projects/${projectId}/schedules/${scheduleId}/progress/apply-matches`,
      )
      .then((r) => r.data),
};
