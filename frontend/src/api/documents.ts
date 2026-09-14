import { apiClient } from "./client";
import type { DocumentType, Page, ProcessingJobRead, UploadAccepted, UploadedFileRead } from "@/types/api";

export const documentsApi = {
  list: (projectId: string, params: { skip?: number; limit?: number } = {}) =>
    apiClient
      .get<Page<UploadedFileRead>>(`/projects/${projectId}/documents`, { params })
      .then((r) => r.data),

  upload: (
    projectId: string,
    file: File,
    documentType: DocumentType = "OTHER",
    onProgress?: (percent: number) => void,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", documentType);
    return apiClient
      .post<UploadAccepted>(`/projects/${projectId}/documents`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (onProgress && evt.total) {
            onProgress(Math.round((evt.loaded / evt.total) * 100));
          }
        },
      })
      .then((r) => r.data);
  },

  get: (projectId: string, fileId: string) =>
    apiClient
      .get<UploadedFileRead>(`/projects/${projectId}/documents/${fileId}`)
      .then((r) => r.data),

  getJob: (jobId: string) =>
    apiClient.get<ProcessingJobRead>(`/jobs/${jobId}`).then((r) => r.data),
};
