import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Binary,
  BrainCircuit,
  CalendarClock,
  ArrowUpDown,
  ChevronDown,
  Copy,
  Download,
  Filter,
  Info,
  Play,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { predictionApi } from "@/api/prediction";
import { activitiesApi } from "@/api/activities";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Badge, RiskBadge } from "@/components/common/Badge";
import { Button, Card, CardHeader, Modal, PageHeader } from "@/components/ui/Primitives";
import { MetricTile } from "@/components/ui/Metric";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import type { PredictionDetail, RiskLevel, TrainingOutcome } from "@/types/api";

const REFUSAL_COPY: Record<string, string> = {
  INSUFFICIENT_SAMPLES:
    "Not enough completed activities to fit a model yet. The rule-based forecast is being used instead.",
  INSUFFICIENT_MINORITY_CLASS:
    "Too few late-finishing activities to learn from — a model trained on this would just predict 'on time' for everything.",
  BELOW_ACCURACY_FLOOR:
    "The fitted model did not clear the held-out accuracy floor, so it was not promoted.",
  NOT_BETTER_THAN_BASELINE:
    "The fitted model did not beat the simple rate-based arithmetic by enough to justify using it.",
};

type SortKey = "probability" | "slip" | "finish" | "activity";

export function Risks() {
  const projectId = useProjectId();
  const { canManage, selectedSchedule: schedule, schedulesLoading } = useProject();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [lastTraining, setLastTraining] = useState<TrainingOutcome | null>(null);
  const [riskFilter, setRiskFilter] = useState<RiskLevel[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("probability");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const modelsQuery = useQuery({
    queryKey: ["ml-models", projectId],
    queryFn: () => predictionApi.listModels(projectId),
  });
  const riskQuery = useQuery({
    queryKey: ["risk-summary", projectId, schedule?.id],
    queryFn: () => predictionApi.riskSummary(projectId, schedule!.id),
    enabled: !!schedule,
  });
  // What each model input means, in plain language, straight from the backend —
  // so the drivers named in an explanation can actually be looked up.
  const featuresQuery = useQuery({
    queryKey: ["ml-features", projectId],
    queryFn: () => predictionApi.featureReference(projectId),
    staleTime: 5 * 60_000,
  });

  const predictionsQuery = useQuery({
    queryKey: ["predictions", projectId, schedule?.id],
    queryFn: () => predictionApi.listPredictions(projectId, schedule!.id),
    enabled: !!schedule,
  });

  // The prediction list returns activity ids only, so the schedule's activities
  // are fetched alongside to give each row a code and a name a planner can read.
  const activitiesQuery = useQuery({
    queryKey: ["activities-flat", schedule?.id],
    queryFn: () => activitiesApi.listAll(schedule!.id),
    enabled: !!schedule,
    staleTime: 5 * 60_000,
  });

  const activityById = useMemo(() => {
    const map = new Map<string, { activity_code: string; name: string }>();
    for (const a of activitiesQuery.data?.items ?? [])
      map.set(a.id, { activity_code: a.activity_code, name: a.name });
    return map;
  }, [activitiesQuery.data]);

  const trainMutation = useMutation({
    mutationFn: () => predictionApi.train(projectId, {}),
    onSuccess: (outcome) => {
      setLastTraining(outcome);
      queryClient.invalidateQueries({ queryKey: ["ml-models", projectId] });
      if (outcome.trained) {
        toast.success(
          `Model ${outcome.version} promoted`,
          `ROC AUC ${outcome.metrics?.roc_auc?.toFixed(3) ?? "—"} vs baseline ${outcome.baseline_roc_auc?.toFixed(3) ?? "—"}.`,
        );
      } else {
        toast.info("No model promoted", outcome.detail);
      }
    },
    onError: (err) => toast.error("Training failed", err instanceof ApiError ? err.message : undefined),
  });

  const predictMutation = useMutation({
    mutationFn: () => predictionApi.predict(projectId, schedule!.id, {}),
    onSuccess: (summary) => {
      queryClient.invalidateQueries({ queryKey: ["risk-summary", projectId, schedule?.id] });
      queryClient.invalidateQueries({ queryKey: ["predictions", projectId, schedule?.id] });
      toast.success(
        `Scored ${summary.activities_scored} activities`,
        `${summary.method.replaceAll("_", " ").toLowerCase()}${summary.not_forecastable ? ` · ${summary.not_forecastable} had no finish date to be late against` : ""}.`,
      );
    },
    onError: (err) => toast.error("Prediction failed", err instanceof ApiError ? err.message : undefined),
  });

  if (schedulesLoading) return <LoadingRows rows={4} />;
  if (!schedule) {
    return (
      <EmptyState
        icon={<ShieldAlert className="h-5 w-5" />}
        title="No schedule to forecast against"
        description="Delay prediction needs a baseline schedule with planned finish dates."
      />
    );
  }

  const risk = riskQuery.data;
  const activeModel = modelsQuery.data?.find((m) => m.is_active);
  const allPredictions = predictionsQuery.data ?? [];

  const predictions = (() => {
    const rows = riskFilter.length
      ? allPredictions.filter((p) => riskFilter.includes(p.risk_level))
      : allPredictions;
    const dir = order === "asc" ? -1 : 1;
    return [...rows].sort((a, b) => {
      switch (sortKey) {
        case "slip":
          // A prediction with no forecast slip is not "zero slip" — park it last.
          if (a.forecast_slip_days == null && b.forecast_slip_days == null) return 0;
          if (a.forecast_slip_days == null) return 1;
          if (b.forecast_slip_days == null) return -1;
          return (b.forecast_slip_days - a.forecast_slip_days) * dir;
        case "finish":
          if (!a.planned_finish && !b.planned_finish) return 0;
          if (!a.planned_finish) return 1;
          if (!b.planned_finish) return -1;
          return a.planned_finish.localeCompare(b.planned_finish) * dir * -1;
        case "activity":
          return (
            (activityById.get(a.activity_id)?.activity_code ?? "").localeCompare(
              activityById.get(b.activity_id)?.activity_code ?? "",
            ) *
            dir *
            -1
          );
        default:
          return (b.probability - a.probability) * dir;
      }
    });
  })();

  /** Rows the table is showing, flattened for clipboard/CSV export. */
  const exportRows = predictions.map((p) => {
    const act = activityById.get(p.activity_id);
    return [
      act?.activity_code ?? p.activity_id,
      act?.name ?? "",
      p.risk_level,
      (p.probability * 100).toFixed(1),
      p.planned_finish ?? "",
      p.forecast_finish ?? "",
      p.forecast_slip_days != null ? String(p.forecast_slip_days) : "",
      p.as_of,
    ];
  });

  const EXPORT_HEADERS = [
    "Activity code",
    "Activity name",
    "Risk level",
    "Probability %",
    "Planned finish",
    "Forecast finish",
    "Slip days",
    "As of",
  ];

  const toCsv = () =>
    [EXPORT_HEADERS, ...exportRows]
      .map((r) => r.map((c) => (/[",\n]/.test(c) ? `"${c.replaceAll('"', '""')}"` : c)).join(","))
      .join("\n");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Delay & risk prediction"
        subtitle="A two-tier forecast: deterministic rate-based arithmetic always available, upgraded to a Random Forest only once one provably beats it. Every prediction states which tier produced it."
        actions={
          canManage && (
            <>
              <Button variant="secondary" onClick={() => trainMutation.mutate()} loading={trainMutation.isPending}>
                <BrainCircuit className="h-4 w-4" />
                Train model
              </Button>
              <Button onClick={() => predictMutation.mutate()} loading={predictMutation.isPending}>
                <Play className="h-4 w-4" />
                Run prediction
              </Button>
            </>
          )
        }
      />

      {/* Honest reporting of a refusal to train. */}
      {lastTraining && !lastTraining.trained && (
        <div className="flex gap-3 rounded-[14px] border border-amber-200 bg-amber-50/70 p-4">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <p className="text-sm font-medium text-amber-900">
              No model promoted — {lastTraining.reason?.replaceAll("_", " ").toLowerCase()}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-amber-800">
              {REFUSAL_COPY[lastTraining.reason ?? ""] ?? lastTraining.detail}
            </p>
            <p className="mt-1.5 text-2xs text-amber-700">
              {lastTraining.labelled_activities} labelled activities · {lastTraining.late_samples} late ·{" "}
              {lastTraining.on_time_samples} on time. This is a normal early-project outcome, not an error —
              the rule-based forecast continues to run.
            </p>
          </div>
        </div>
      )}
      {lastTraining?.trained && (
        <div className="flex gap-3 rounded-[14px] border border-teal-200 bg-teal-50/70 p-4">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
          <div>
            <p className="text-sm font-medium text-teal-900">
              Model {lastTraining.version} promoted ({lastTraining.kind})
            </p>
            <p className="mt-1 text-xs text-teal-800">
              Cross-validated ROC AUC {lastTraining.metrics?.roc_auc?.toFixed(3)} — beat the rule-based
              baseline of {lastTraining.baseline_roc_auc?.toFixed(3)}.
            </p>
          </div>
        </div>
      )}

      {risk && risk.total_predictions > 0 && (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          <MetricTile
            label="Activities scored"
            value={risk.total_predictions}
            icon={<Binary className="h-4 w-4" />}
            hint={risk.as_of ? `as at ${risk.as_of}` : undefined}
          />
          <MetricTile
            label="Predicted late"
            value={risk.predicted_late}
            tone={risk.predicted_late ? "warning" : "positive"}
            icon={<CalendarClock className="h-4 w-4" />}
            delay={0.05}
          />
          <MetricTile
            label="Worst forecast slip"
            value={risk.worst_forecast_slip_days ?? "—"}
            unit={risk.worst_forecast_slip_days != null ? " d" : undefined}
            tone={risk.worst_forecast_slip_days ? "critical" : "default"}
            delay={0.1}
          />
          <MetricTile
            label="Forecast tier"
            value={
              <span className="text-base leading-tight">
                {(risk.method ?? "—").replaceAll("_", " ").toLowerCase()}
              </span>
            }
            icon={<BrainCircuit className="h-4 w-4" />}
            hint={risk.model_version ?? "deterministic"}
            delay={0.15}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Predicted finishes"
            subtitle="Highest probability of finishing late first"
            icon={<ShieldAlert className="h-4 w-4" />}
            action={
              allPredictions.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <MultiSelectMenu<RiskLevel>
                    label="Risk level"
                    icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
                    selected={riskFilter}
                    onChange={setRiskFilter}
                    options={(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as RiskLevel[]).map((lv) => ({
                      value: lv,
                      label: lv.toLowerCase(),
                      hint: String(allPredictions.filter((p) => p.risk_level === lv).length),
                    }))}
                  />
                  <SelectMenu<SortKey>
                    prefix="Sort"
                    icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
                    value={sortKey}
                    width="w-56"
                    align="right"
                    options={[
                      { value: "probability", label: "Probability late" },
                      { value: "slip", label: "Forecast slip" },
                      { value: "finish", label: "Planned finish" },
                      { value: "activity", label: "Activity code" },
                    ]}
                    onChange={(v) => v && setSortKey(v)}
                  />
                  <Dropdown
                    label={order === "desc" ? "Worst first" : "Best first"}
                    align="right"
                    width="w-48"
                    icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
                  >
                    {(close) => (
                      <>
                        <DropdownLabel>Direction</DropdownLabel>
                        <DropdownItem
                          selected={order === "desc"}
                          onSelect={() => {
                            setOrder("desc");
                            close();
                          }}
                        >
                          Worst first
                        </DropdownItem>
                        <DropdownItem
                          selected={order === "asc"}
                          onSelect={() => {
                            setOrder("asc");
                            close();
                          }}
                        >
                          Best first
                        </DropdownItem>
                      </>
                    )}
                  </Dropdown>
                  <Dropdown
                    label="Export"
                    align="right"
                    width="w-64"
                    icon={<Download className="h-3.5 w-3.5 text-content-2" />}
                  >
                    {(close) => (
                      <>
                        <DropdownLabel>{predictions.length} visible rows</DropdownLabel>
                        <DropdownItem
                          icon={<Download className="h-3.5 w-3.5" />}
                          onSelect={() => {
                            const blob = new Blob([toCsv()], { type: "text/csv;charset=utf-8" });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `${schedule.name.replace(/\W+/g, "-").toLowerCase()}-delay-forecast.csv`;
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                            URL.revokeObjectURL(url);
                            close();
                          }}
                        >
                          Download as CSV
                        </DropdownItem>
                        <DropdownItem
                          icon={<Copy className="h-3.5 w-3.5" />}
                          onSelect={() => {
                            const tsv = [EXPORT_HEADERS, ...exportRows]
                              .map((r) => r.join("\t"))
                              .join("\n");
                            navigator.clipboard
                              ?.writeText(tsv)
                              .then(() =>
                                toast.success(
                                  "Copied for spreadsheets",
                                  `${predictions.length} rows on the clipboard.`,
                                ),
                              )
                              .catch(() => toast.error("Could not copy to clipboard"));
                            close();
                          }}
                        >
                          Copy as spreadsheet rows
                        </DropdownItem>
                        <DropdownSeparator />
                        <DropdownItem
                          onSelect={() => {
                            setSortKey("probability");
                            setOrder("desc");
                            setRiskFilter([]);
                            close();
                          }}
                        >
                          Reset filter &amp; sort
                        </DropdownItem>
                      </>
                    )}
                  </Dropdown>
                </div>
              ) : undefined
            }
          />
          <div className="p-2">
            {predictionsQuery.isLoading && <LoadingRows />}
            {predictionsQuery.error && <ErrorState error={predictionsQuery.error} />}
            {predictions.length === 0 && allPredictions.length > 0 && (
              <EmptyState
                compact
                icon={<Filter className="h-5 w-5" />}
                title="No activity at that risk level"
                description="Clear or widen the filter to see the rest."
              />
            )}
            {allPredictions.length === 0 && !predictionsQuery.isLoading && (
              <EmptyState
                icon={<ShieldAlert className="h-5 w-5" />}
                title="Nothing forecast yet"
                description={canManage ? "Run a prediction to score every activity in this schedule." : undefined}
                action={
                  canManage ? (
                    <Button size="sm" onClick={() => predictMutation.mutate()} loading={predictMutation.isPending}>
                      Run prediction
                    </Button>
                  ) : undefined
                }
              />
            )}
            {predictions.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-2xs text-content-3">
                      <th className="px-3 py-2 font-medium">Activity</th>
                      <th className="px-3 py-2 font-medium">Risk</th>
                      <th className="px-3 py-2 font-medium">Probability</th>
                      <th className="px-3 py-2 font-medium">Planned finish</th>
                      <th className="px-3 py-2 font-medium">Forecast</th>
                      <th className="px-3 py-2 font-medium">Slip</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {predictions.map((p) => {
                      const act = activityById.get(p.activity_id);
                      return (
                        <tr
                          key={p.id}
                          onClick={() => setSelected(p.activity_id)}
                          className="cursor-pointer transition-colors hover:bg-signal-600/25/40"
                        >
                          <td className="max-w-[16rem] px-3 py-2.5">
                            <p className="truncate font-mono text-2xs font-medium uppercase text-accent">
                              {act?.activity_code ?? "—"}
                            </p>
                            <p className="mt-0.5 truncate text-xs text-content-1">
                              {act?.name ?? (activitiesQuery.isLoading ? "loading…" : p.activity_id)}
                            </p>
                          </td>
                          <td className="px-3 py-2.5">
                            <RiskBadge level={p.risk_level} />
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-raised">
                                <div
                                  className={clsx(
                                    "h-full rounded-full",
                                    p.probability >= 0.8
                                      ? "bg-rose-500"
                                      : p.probability >= 0.6
                                        ? "bg-orange-500"
                                        : p.probability >= 0.35
                                          ? "bg-amber-400"
                                          : "bg-teal-500",
                                  )}
                                  style={{ width: `${Math.max(p.probability * 100, 2)}%` }}
                                />
                              </div>
                              <span className="tnum text-xs font-medium text-content-1">
                                {(p.probability * 100).toFixed(0)}%
                              </span>
                            </div>
                          </td>
                          <td className="tnum px-3 py-2.5 text-xs text-content-2">{p.planned_finish ?? "—"}</td>
                          <td className="tnum px-3 py-2.5 text-xs text-content-2">{p.forecast_finish ?? "—"}</td>
                          <td className="tnum px-3 py-2.5 text-xs font-medium text-content-1">
                            {p.forecast_slip_days != null ? `${p.forecast_slip_days} d` : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <span className="text-2xs font-medium text-accent">Explain</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Model registry" subtitle="Newest first" icon={<BrainCircuit className="h-4 w-4" />} />
          <div className="p-4">
            {modelsQuery.isLoading && <LoadingRows rows={2} />}
            {modelsQuery.data?.length === 0 && (
              <div className="rounded-[10px] border border-line bg-surface-raised/60 p-3">
                <p className="text-xs font-medium text-content-1">No fitted model yet</p>
                <p className="mt-1 text-2xs leading-relaxed text-content-3">
                  Forecasts use the rule-based rate tier, which is always available and states its own
                  arithmetic. A Random Forest is promoted only once it beats that baseline on held-out data.
                </p>
              </div>
            )}
            {modelsQuery.data && modelsQuery.data.length > 0 && (
              <div className="space-y-2">
                {modelsQuery.data.map((m) => (
                  <div
                    key={m.id}
                    className={clsx(
                      "rounded-[10px] border p-2.5",
                      m.is_active ? "border-teal-200 bg-teal-50/50" : "border-line",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-2xs text-content-1">{m.version}</span>
                      {m.is_active && <Badge tone="green">active</Badge>}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-content-3">
                      <span>ROC AUC {m.roc_auc?.toFixed(3) ?? "—"}</span>
                      <span>baseline {m.baseline_roc_auc?.toFixed(3) ?? "—"}</span>
                      <span>{m.training_samples} activities</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeModel && activeModel.feature_importances?.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-2xs font-medium text-content-2">
                  What the model weighs
                </p>
                <div className="space-y-1.5">
                  {activeModel.feature_importances.slice(0, 6).map((f, i) => {
                    const name = String(f.feature ?? f.name ?? `feature ${i + 1}`);
                    const importance = Number(f.importance ?? 0);
                    return (
                      <div key={name}>
                        <div className="flex items-center justify-between text-2xs">
                          <span className="truncate text-content-2">{name.replaceAll("_", " ")}</span>
                          <span className="tnum text-content-3">{(importance * 100).toFixed(0)}%</span>
                        </div>
                        <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-surface-raised">
                          <div className="h-full rounded-full bg-signal-500" style={{ width: `${importance * 100}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {risk?.note && (
              <p className="mt-4 flex gap-1.5 rounded-[10px] bg-surface-raised p-2.5 text-2xs leading-relaxed text-content-2">
                <Info className="mt-0.5 h-3 w-3 shrink-0" />
                {risk.note}
              </p>
            )}

            {(featuresQuery.data?.length ?? 0) > 0 && (
              <details className="group mt-4">
                <summary className="flex cursor-pointer list-none items-center justify-between rounded-[10px] bg-surface-raised px-2.5 py-2 text-2xs font-medium text-content-2 transition-colors hover:bg-surface-raised">
                  <span>What the {featuresQuery.data?.length} model inputs mean</span>
                  <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
                </summary>
                <dl className="mt-2 max-h-64 space-y-1.5 overflow-y-auto pr-1 scroll-slim">
                  {featuresQuery.data?.map((f) => (
                    <div key={String(f.feature)} className="rounded-[10px] border border-line px-2.5 py-1.5">
                      <dt className="font-mono text-2xs text-content-3">{String(f.feature)}</dt>
                      <dd className="mt-0.5 text-2xs text-content-1">{String(f.label)}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            )}
          </div>
        </Card>
      </div>

      {selected && (
        <PredictionDrawer
          projectId={projectId}
          scheduleId={schedule.id}
          activityId={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function PredictionDrawer({
  projectId,
  scheduleId,
  activityId,
  onClose,
}: {
  projectId: string;
  scheduleId: string;
  activityId: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["prediction", projectId, scheduleId, activityId],
    queryFn: () => predictionApi.getPrediction(projectId, scheduleId, activityId),
  });

  return (
    <Modal open onClose={onClose} title="Why this activity is flagged" size="lg">
      {isLoading && <LoadingRows rows={4} />}
      {error && <ErrorState error={error} />}
      {data && <Explanation prediction={data} />}
    </Modal>
  );
}

function Explanation({ prediction }: { prediction: PredictionDetail }) {
  const drivers = (prediction.explanation?.drivers as Array<Record<string, unknown>> | undefined) ?? [];
  const notable =
    (prediction.explanation?.notable_features as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-2xs text-content-3">{prediction.activity_code}</p>
        <h4 className="mt-0.5 text-base font-semibold text-content-1">{prediction.activity_name}</h4>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <RiskBadge level={prediction.risk_level} />
          <span className="tnum text-sm font-medium text-content-1">
            {(prediction.probability * 100).toFixed(0)}% chance of finishing late
          </span>
          <Badge tone="slate">{prediction.method.replaceAll("_", " ").toLowerCase()}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Fact label="Planned finish" value={prediction.planned_finish ?? "—"} />
        <Fact label="Forecast finish" value={prediction.forecast_finish ?? "not projectable"} />
        <Fact
          label="Slip"
          value={prediction.forecast_slip_days != null ? `${prediction.forecast_slip_days} days` : "—"}
        />
      </div>

      {drivers.length > 0 && (
        <div>
          <p className="mb-2 text-2xs font-medium text-content-2">
            What's driving this
          </p>
          <div className="space-y-2">
            {drivers.map((d, i) => (
              <div key={i} className="rounded-[10px] border border-line p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-content-1">{String(d.factor ?? "factor")}</span>
                  <Badge tone={String(d.direction ?? "").includes("increase") ? "red" : "green"}>
                    {String(d.direction ?? "")}
                  </Badge>
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-content-2">{String(d.detail ?? "")}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {notable.length > 0 && (
        <div>
          <p className="mb-2 text-2xs font-medium text-content-2">
            Inputs that stand out for this activity
          </p>
          <div className="flex flex-wrap gap-1.5">
            {notable.map((f, i) => (
              <span
                key={i}
                className="rounded-[10px] bg-surface-raised px-2 py-1 text-2xs text-content-2 ring-1 ring-inset ring-line"
              >
                {String(f.feature ?? f.name ?? "")} {f.value != null ? `= ${String(f.value)}` : ""}
              </span>
            ))}
          </div>
          <p className="mt-1.5 text-2xs text-content-2">
            These are inputs that are both influential and unusual here — an indication of what stands out,
            not a decomposition of the probability.
          </p>
        </div>
      )}

      {prediction.caveats?.length > 0 && (
        <div className="rounded-[10px] border border-amber-200 bg-amber-50/70 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-2xs font-medium text-amber-800">
            <TriangleAlert className="h-3 w-3" /> Where this forecast is thin
          </p>
          {prediction.caveats.map((c, i) => (
            <p key={i} className="text-2xs leading-relaxed text-amber-800">
              {c}
            </p>
          ))}
        </div>
      )}

      <p className="border-t border-line pt-3 text-2xs leading-relaxed text-content-2">
        A delay forecast is a risk signal to act on, not a guarantee. It is computed from reported progress
        to date against the planned window — it does not know about anything nobody has reported.
      </p>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] bg-surface-raised p-2.5">
      <p className="text-2xs text-content-3">{label}</p>
      <p className="tnum mt-0.5 text-xs font-medium text-content-1">{value}</p>
    </div>
  );
}
