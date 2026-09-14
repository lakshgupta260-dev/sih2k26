import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { projectsApi } from "@/api/projects";
import { schedulesApi } from "@/api/schedules";
import type { ProjectWithRole, ScheduleRead } from "@/types/api";

interface ProjectContextValue {
  project: ProjectWithRole | undefined;
  isLoading: boolean;
  error: unknown;
  canManage: boolean;
  /** Every baseline on the project, newest first. */
  schedules: ScheduleRead[];
  schedulesLoading: boolean;
  /** The baseline the schedule-scoped screens read from. */
  selectedSchedule: ScheduleRead | undefined;
  selectSchedule: (scheduleId: string) => void;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId as string),
    enabled: !!projectId,
  });

  const schedulesQuery = useQuery({
    queryKey: ["schedules", projectId],
    queryFn: () => schedulesApi.list(projectId as string),
    enabled: !!projectId,
  });

  // Explicit choice wins; otherwise fall back to the newest baseline. Uploading
  // a new revision used to silently move every dashboard onto it, stranding the
  // progress booked against the previous one with no way to get back.
  const [chosenId, setChosenId] = useState<string | null>(null);

  const schedules = useMemo(
    () =>
      [...(schedulesQuery.data ?? [])].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [schedulesQuery.data],
  );

  const selectedSchedule =
    schedules.find((s) => s.id === chosenId) ?? schedules[0];

  const canManage = data ? data.my_role === "ADMIN" || data.my_role === "PROJECT_MANAGER" : false;

  const value = useMemo(
    () => ({
      project: data,
      isLoading,
      error,
      canManage,
      schedules,
      schedulesLoading: schedulesQuery.isLoading,
      selectedSchedule,
      selectSchedule: setChosenId,
    }),
    [data, isLoading, error, canManage, schedules, schedulesQuery.isLoading, selectedSchedule],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}

export function useProjectId(): string {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) throw new Error("projectId param missing");
  return projectId;
}
