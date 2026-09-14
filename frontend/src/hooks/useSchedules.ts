import { useQuery } from "@tanstack/react-query";
import { schedulesApi } from "@/api/schedules";

export function useSchedules(projectId: string) {
  return useQuery({
    queryKey: ["schedules", projectId],
    queryFn: () => schedulesApi.list(projectId),
    enabled: !!projectId,
  });
}
