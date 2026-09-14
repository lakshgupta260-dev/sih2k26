import { apiClient } from "./client";
import type {
  ActivityMatchDetail,
  ActivityMatchRead,
  AuditEntryRead,
  ExtractedActivityRead,
  MatchReviewDecision,
  MatchRunRequest,
  MatchRunSummary,
  MatchStatsRead,
  MatchStatus,
  Page,
} from "@/types/api";

export const matchingApi = {
  run: (projectId: string, payload: MatchRunRequest = {}) =>
    apiClient
      .post<MatchRunSummary>(`/projects/${projectId}/matching/run`, payload)
      .then((r) => r.data),

  listExtracted: (projectId: string, params: { skip?: number; limit?: number } = {}) =>
    apiClient
      .get<Page<ExtractedActivityRead>>(`/projects/${projectId}/matching/extracted`, { params })
      .then((r) => r.data),

  /**
   * Every extracted item, paged out to completion.
   *
   * The match list carries only `extracted_activity_id`, so the queue has to
   * join the field text client-side. The API caps a page at 200 and a busy
   * project has far more than that, so fetching one page left most rows
   * showing a "not in page" placeholder instead of the sentence the match was
   * made from. The cap stops a runaway loop on an unexpectedly huge project.
   */
  listAllExtracted: async (projectId: string, max = 2000) => {
    const PAGE = 200;
    const items: ExtractedActivityRead[] = [];
    let skip = 0;
    let total = 0;
    do {
      const page = await apiClient
        .get<Page<ExtractedActivityRead>>(`/projects/${projectId}/matching/extracted`, {
          params: { skip, limit: PAGE },
        })
        .then((r) => r.data);
      items.push(...page.items);
      total = page.total;
      skip += PAGE;
      if (page.items.length === 0) break;
    } while (items.length < Math.min(total, max));
    return { items, total };
  },

  listMatches: (
    projectId: string,
    params: { status?: MatchStatus; skip?: number; limit?: number } = {},
  ) =>
    apiClient
      .get<Page<ActivityMatchRead>>(`/projects/${projectId}/matching/matches`, { params })
      .then((r) => r.data),

  getMatch: (projectId: string, matchId: string) =>
    apiClient
      .get<ActivityMatchDetail>(`/projects/${projectId}/matching/matches/${matchId}`)
      .then((r) => r.data),

  matchHistory: (projectId: string, matchId: string) =>
    apiClient
      .get<AuditEntryRead[]>(`/projects/${projectId}/matching/matches/${matchId}/history`)
      .then((r) => r.data),

  review: (projectId: string, matchId: string, payload: MatchReviewDecision) =>
    apiClient
      .post<ActivityMatchRead>(`/projects/${projectId}/matching/matches/${matchId}/review`, payload)
      .then((r) => r.data),

  stats: (projectId: string) =>
    apiClient.get<MatchStatsRead>(`/projects/${projectId}/matching/stats`).then((r) => r.data),
};
