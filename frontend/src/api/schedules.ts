import { apiClient } from "./client";
import type { Page, ScheduleColumnMapping, ScheduleRead } from "@/types/api";

export const schedulesApi = {
  // The backend returns the standard Page envelope here, despite docs/API.md
  // describing this endpoint as returning a plain array — verified against
  // a live response (see FRONTEND_API_INTEGRATION.md).
  list: (projectId: string) =>
    apiClient
      .get<Page<ScheduleRead>>(`/projects/${projectId}/schedules`)
      .then((r) => r.data.items),

  get: (projectId: string, scheduleId: string) =>
    apiClient
      .get<ScheduleRead>(`/projects/${projectId}/schedules/${scheduleId}`)
      .then((r) => r.data),

  upload: (
    projectId: string,
    file: File,
    name: string,
    mapping: ScheduleColumnMapping,
    onProgress?: (percent: number) => void,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    form.append("mapping", JSON.stringify(mapping));
    return apiClient
      .post<ScheduleRead>(`/projects/${projectId}/schedules`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (onProgress && evt.total) {
            onProgress(Math.round((evt.loaded / evt.total) * 100));
          }
        },
      })
      .then((r) => r.data);
  },
};
