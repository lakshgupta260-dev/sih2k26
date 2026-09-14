import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRightLeft,
  CalendarRange,
  ClipboardCheck,
  History,
  Ruler,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { activitiesApi } from "@/api/activities";
import { progressApi } from "@/api/progress";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { ActivityStatusBadge, Badge } from "@/components/common/Badge";
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
import { MetricTile } from "@/components/ui/Metric";
import type { ActivityStatus, ActualProgressCreate } from "@/types/api";

export function ActivityDetail() {
  const projectId = useProjectId();
  const { canManage } = useProject();
  const { scheduleId, activityId } = useParams<{ scheduleId: string; activityId: string }>();
  const sid = scheduleId as string;
  const aid = activityId as string;
  const queryClient = useQueryClient();
  const toast = useToast();

  const activityQuery = useQuery({
    queryKey: ["activity", sid, aid],
    queryFn: () => activitiesApi.get(sid, aid),
  });
  const historyQuery = useQuery({
    queryKey: ["progress-history", projectId, sid, aid],
    queryFn: () => progressApi.history(projectId, sid, aid),
  });

  const today = new Date().toISOString().slice(0, 10);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ActualProgressCreate>({
    defaultValues: { reporting_date: today, status: "IN_PROGRESS" },
  });

  const recordMutation = useMutation({
    mutationFn: (payload: ActualProgressCreate) => progressApi.record(projectId, sid, aid, payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["progress-history", projectId, sid, aid] });
      queryClient.invalidateQueries({ queryKey: ["progress-rollup", projectId, sid] });
      queryClient.invalidateQueries({ queryKey: ["analytics-summary", projectId] });
      queryClient.invalidateQueries({ queryKey: ["s-curve", projectId] });
      reset({ reporting_date: today, status: "IN_PROGRESS", percent_complete: null, actual_quantity: null, notes: "" });
      toast.success(
        "Progress recorded",
        `${saved.reporting_date} · ${saved.percent_complete ?? 0}% — one record per activity per date, so this corrects that day if it already existed.`,
      );
    },
    onError: (err) =>
      toast.error("Could not record progress", err instanceof ApiError ? err.message : undefined),
  });

  if (activityQuery.isLoading) return <LoadingRows rows={5} />;
  if (activityQuery.error || !activityQuery.data) return <ErrorState error={activityQuery.error} />;

  const activity = activityQuery.data;
  const latest = historyQuery.data?.[0];

  return (
    <div className="space-y-5">
      <div>
        <Link
          to={`/projects/${projectId}/schedule/${sid}`}
          className="mb-2 inline-flex items-center gap-1.5 text-2xs font-medium text-content-2 transition-colors hover:text-content-1"
        >
          <ArrowLeft className="h-3 w-3" />
          Back to hierarchy
        </Link>
        <PageHeader
          title={activity.name}
          subtitle={`${activity.activity_code} · WBS ${activity.wbs_path} · Level ${activity.level}${activity.discipline ? ` · ${activity.discipline}` : ""}`}
          actions={latest ? <ActivityStatusBadge status={latest.status} /> : undefined}
        />
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <MetricTile
          label="Planned start"
          value={<span className="text-lg">{activity.planned_start ?? "—"}</span>}
          icon={<CalendarRange className="h-4 w-4" />}
        />
        <MetricTile
          label="Planned finish"
          value={<span className="text-lg">{activity.planned_finish ?? "—"}</span>}
          icon={<CalendarRange className="h-4 w-4" />}
          delay={0.05}
        />
        <MetricTile
          label="Latest reported"
          value={latest?.percent_complete != null ? latest.percent_complete : "—"}
          unit={latest?.percent_complete != null ? "%" : undefined}
          hint={latest ? `as at ${latest.reporting_date}` : "nothing booked yet"}
          icon={<ClipboardCheck className="h-4 w-4" />}
          delay={0.1}
        />
        <MetricTile
          label="Budgeted quantity"
          value={
            activity.budgeted_quantity != null ? (
              <span className="text-lg">
                {activity.budgeted_quantity} {activity.uom ?? ""}
              </span>
            ) : (
              "—"
            )
          }
          icon={<Ruler className="h-4 w-4" />}
          delay={0.15}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Dependencies"
            subtitle="Logic links carried over from the programme"
            icon={<ArrowRightLeft className="h-4 w-4" />}
          />
          <div className="grid grid-cols-2 gap-4 p-4">
            <div>
              <p className="mb-2 text-2xs font-medium text-content-2">
                Predecessors
              </p>
              {activity.predecessors.length === 0 ? (
                <p className="text-xs text-content-2">None</p>
              ) : (
                <ul className="space-y-1">
                  {activity.predecessors.map((d) => (
                    <li key={d.id} className="flex items-center gap-2 text-xs text-content-1">
                      <Badge tone="slate">{d.dependency_type}</Badge>
                      <span className="tnum text-content-3">lag {d.lag}d</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="mb-2 text-2xs font-medium text-content-2">Successors</p>
              {activity.successors.length === 0 ? (
                <p className="text-xs text-content-2">None</p>
              ) : (
                <ul className="space-y-1">
                  {activity.successors.map((d) => (
                    <li key={d.id} className="flex items-center gap-2 text-xs text-content-1">
                      <Badge tone="slate">{d.dependency_type}</Badge>
                      <span className="tnum text-content-3">lag {d.lag}d</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>

        {canManage ? (
          <Card>
            <CardHeader
              title="Record progress"
              subtitle="One record per activity per reporting date — posting the same date again corrects it, and the superseded figure stays in the audit trail."
              icon={<ClipboardCheck className="h-4 w-4" />}
            />
            <form
              className="space-y-3 p-4"
              onSubmit={handleSubmit((values) =>
                recordMutation.mutate({
                  ...values,
                  percent_complete:
                    values.percent_complete === null || values.percent_complete === undefined || (values.percent_complete as unknown as string) === ""
                      ? null
                      : Number(values.percent_complete),
                  actual_quantity:
                    values.actual_quantity === null || values.actual_quantity === undefined || (values.actual_quantity as unknown as string) === ""
                      ? null
                      : Number(values.actual_quantity),
                }),
              )}
            >
              <div className="grid grid-cols-2 gap-3">
                <Field label="Reporting date" error={errors.reporting_date?.message}>
                  <Input type="date" max={today} {...register("reporting_date", { required: "Required" })} />
                </Field>
                <Field label="Status">
                  <Select {...register("status")}>
                    {(["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "SUSPENDED"] as ActivityStatus[]).map((s) => (
                      <option key={s} value={s}>
                        {s.replaceAll("_", " ").toLowerCase()}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="% complete">
                  <Input type="number" step="0.1" min={0} max={100} placeholder="0–100" {...register("percent_complete")} />
                </Field>
                <Field label={`Quantity${activity.uom ? ` (${activity.uom})` : ""}`}>
                  <Input type="number" step="0.01" min={0} placeholder="Cumulative to date" {...register("actual_quantity")} />
                </Field>
              </div>
              <Field label="Notes">
                <Textarea rows={2} placeholder="What happened on site" {...register("notes")} />
              </Field>
              <Button type="submit" loading={recordMutation.isPending}>
                Save progress
              </Button>
            </form>
          </Card>
        ) : (
          <Card className="flex items-center justify-center p-8">
            <p className="max-w-xs text-center text-xs text-content-3">
              Recording progress is a project-manager action. You can see everything booked against this
              activity below.
            </p>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader title="Progress history" subtitle="Newest first" icon={<History className="h-4 w-4" />} />
        <div className="p-3">
          {historyQuery.isLoading && <LoadingRows rows={3} />}
          {historyQuery.data?.length === 0 && (
            <EmptyState title="No progress recorded yet" description="Nothing has been booked against this activity." compact />
          )}
          {historyQuery.data && historyQuery.data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-2xs text-content-2">
                    <th className="px-3 py-2 font-medium">Date</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">% complete</th>
                    <th className="px-3 py-2 font-medium">Quantity</th>
                    <th className="px-3 py-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {historyQuery.data.map((p) => (
                    <tr key={p.id}>
                      <td className="tnum px-3 py-2.5 text-xs text-content-1">{p.reporting_date}</td>
                      <td className="px-3 py-2.5">
                        <ActivityStatusBadge status={p.status} />
                      </td>
                      <td className="tnum px-3 py-2.5 text-xs text-content-1">
                        {p.percent_complete != null ? `${p.percent_complete}%` : "—"}
                      </td>
                      <td className="tnum px-3 py-2.5 text-xs text-content-1">{p.actual_quantity ?? "—"}</td>
                      <td className="max-w-xs px-3 py-2.5 text-xs text-content-3">
                        <span className="line-clamp-2">{p.notes ?? "—"}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
