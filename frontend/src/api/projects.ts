import { apiClient } from "./client";
import type {
  MemberAdd,
  MemberDetail,
  MemberRoleUpdatePayload,
  Page,
  ProjectCreate,
  ProjectRead,
  ProjectUpdate,
  ProjectWithRole,
} from "@/types/api";

export const projectsApi = {
  list: (params: { skip?: number; limit?: number } = {}) =>
    apiClient.get<Page<ProjectWithRole>>("/projects", { params }).then((r) => r.data),

  create: (payload: ProjectCreate) =>
    apiClient.post<ProjectRead>("/projects", payload).then((r) => r.data),

  get: (projectId: string) =>
    apiClient.get<ProjectWithRole>(`/projects/${projectId}`).then((r) => r.data),

  update: (projectId: string, payload: ProjectUpdate) =>
    apiClient.patch<ProjectRead>(`/projects/${projectId}`, payload).then((r) => r.data),

  remove: (projectId: string) =>
    apiClient.delete<void>(`/projects/${projectId}`).then((r) => r.data),

  listMembers: (projectId: string) =>
    apiClient
      .get<Page<MemberDetail>>(`/projects/${projectId}/members`, { params: { limit: 200 } })
      .then((r) => r.data.items),

  addMember: (projectId: string, payload: MemberAdd) =>
    apiClient
      .post<MemberDetail>(`/projects/${projectId}/members`, payload)
      .then((r) => r.data),

  changeMemberRole: (projectId: string, userId: string, payload: MemberRoleUpdatePayload) =>
    apiClient
      .patch<MemberDetail>(`/projects/${projectId}/members/${userId}`, payload)
      .then((r) => r.data),

  removeMember: (projectId: string, userId: string) =>
    apiClient.delete<void>(`/projects/${projectId}/members/${userId}`).then((r) => r.data),
};
