import { useForm } from "react-hook-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AlertOctagon, Lock, Save, SlidersHorizontal, Trash2 } from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { projectsApi } from "@/api/projects";
import { ApiError } from "@/api/client";
import { stripEmptyStrings } from "@/utils/forms";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, LoadingState } from "@/components/common/States";
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui/Primitives";
import type { ProjectStatus, ProjectUpdate } from "@/types/api";

const STATUSES: ProjectStatus[] = ["PLANNING", "ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED"];

export function Settings() {
  const projectId = useProjectId();
  const { project, canManage, isLoading } = useProject();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProjectUpdate>({
    values: project
      ? {
          name: project.name,
          description: project.description ?? "",
          status: project.status,
          client_name: project.client_name ?? "",
          location: project.location ?? "",
          planned_start: project.planned_start ?? "",
          planned_finish: project.planned_finish ?? "",
        }
      : undefined,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: ProjectUpdate) => projectsApi.update(projectId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      toast.success("Settings saved", "Everyone on this project sees the change immediately.");
    },
    onError: (err) =>
      toast.error("Could not save settings", err instanceof ApiError ? err.message : undefined),
  });

  const deleteMutation = useMutation({
    mutationFn: () => projectsApi.remove(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project deleted", project?.name ?? undefined);
      navigate("/projects");
    },
    onError: (err) =>
      toast.error("Could not delete project", err instanceof ApiError ? err.message : undefined),
  });

  if (isLoading) return <LoadingState label="Loading project settings…" />;

  if (!canManage) {
    return (
      <div>
        <PageHeader
          title="Settings"
          subtitle="Project metadata, status and lifecycle controls."
        />
        <EmptyState
          icon={<Lock className="h-5 w-5" />}
          title="Settings are manager-only"
          description="Only the project manager or an admin can change this project's settings. You can still see everything else in the project."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        subtitle="Project metadata and status — this is the header everyone else reads the project by."
      />

      <Card>
        <CardHeader
          title="Project details"
          subtitle="Blank optional fields are left untouched rather than cleared."
          icon={<SlidersHorizontal className="h-4 w-4" />}
        />
        <form
          className="space-y-4 p-4"
          onSubmit={handleSubmit((values) =>
            updateMutation.mutate(stripEmptyStrings(values) as ProjectUpdate),
          )}
        >
          <Field label="Name" error={errors.name?.message}>
            <Input placeholder="Pipeline PL-03 Expansion" {...register("name")} />
          </Field>

          <Field label="Description" hint="Scope, package or contract reference.">
            <Textarea rows={2} {...register("description")} />
          </Field>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Client name">
              <Input placeholder="Oil India Limited" {...register("client_name")} />
            </Field>
            <Field label="Location">
              <Input placeholder="Duliajan, Assam" {...register("location")} />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Status">
              <Select {...register("status")}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replaceAll("_", " ")}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Planned start">
              <Input type="date" {...register("planned_start")} />
            </Field>
            <Field label="Planned finish" hint="Cannot be before the start date.">
              <Input type="date" {...register("planned_finish")} />
            </Field>
          </div>

          <div className="flex justify-end border-t border-line pt-4">
            <Button type="submit" loading={updateMutation.isPending}>
              <Save className="h-4 w-4" />
              Save changes
            </Button>
          </div>
        </form>
      </Card>

      <Card className="border-rose-200/80">
        <CardHeader
          title="Danger zone"
          subtitle="Irreversible from the UI — handle with the care a live project deserves."
          icon={<AlertOctagon className="h-4 w-4 text-rose-600" />}
          className="border-rose-100"
        />
        <div className="flex flex-wrap items-center justify-between gap-4 p-4">
          <div className="max-w-md">
            <p className="text-xs font-medium text-content-1">Delete this project</p>
            <p className="mt-1 text-2xs leading-relaxed text-content-3">
              Soft-deletes the project and hides it from every member. Schedules, uploads and
              forecasts stay in the database, but nobody can reach them from here again.
            </p>
          </div>
          <Button
            variant="danger"
            loading={deleteMutation.isPending}
            onClick={() => {
              if (confirm(`Delete project "${project?.name}"? This cannot be undone.`)) {
                deleteMutation.mutate();
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
            Delete project
          </Button>
        </div>
      </Card>
    </div>
  );
}
