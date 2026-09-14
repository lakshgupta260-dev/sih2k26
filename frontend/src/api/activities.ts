import { apiClient } from "./client";
import type { ActivityTreeNode, ActivityWithDependencies, Page, ActivityRead } from "@/types/api";

export const activitiesApi = {
  list: (scheduleId: string, params: { skip?: number; limit?: number } = {}) =>
    apiClient
      .get<Page<ActivityRead>>(`/schedules/${scheduleId}/activities`, { params })
      .then((r) => r.data),

  /**
   * Every activity in a schedule, paged out to completion.
   *
   * The API caps a page at 200 and rejects anything larger with a 500, so a
   * single `limit: 500` call failed outright and left the risk table showing
   * "—" for every activity code. A real baseline routinely exceeds 200 rows,
   * so paging is the correct shape here, not a bigger number.
   */
  listAll: async (scheduleId: string, max = 3000) => {
    const PAGE = 200;
    const items: ActivityRead[] = [];
    let skip = 0;
    let total = 0;
    do {
      const page = await apiClient
        .get<Page<ActivityRead>>(`/schedules/${scheduleId}/activities`, {
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

  tree: (scheduleId: string) =>
    apiClient
      .get<ActivityTreeNode[]>(`/schedules/${scheduleId}/activities/tree`)
      .then((r) => r.data),

  get: (scheduleId: string, activityId: string) =>
    apiClient
      .get<ActivityWithDependencies>(`/schedules/${scheduleId}/activities/${activityId}`)
      .then((r) => r.data),
};
