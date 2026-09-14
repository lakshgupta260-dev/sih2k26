import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  ClipboardList,
  Gauge,
  ShieldAlert,
  TimerOff,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { analyticsApi } from "@/api/analytics";
import { predictionApi } from "@/api/prediction";
import { matchingApi } from "@/api/matching";
import { reportsApi } from "@/api/reports";
import { EmptyState, ErrorState, LoadingCards, LoadingRows } from "@/components/common/States";
import { Button, Card, CardHeader } from "@/components/ui/Primitives";
import { MetricTile, ProgressMeter } from "@/components/ui/Metric";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import { RiskBadge } from "@/components/common/Badge";
import { PIPELINE_ICONS, PipelineFlow, type PipelineStage } from "@/components/dashboard/PipelineFlow";

export function ProjectOverview() {
  const projectId = useProjectId();
  const { canManage, selectedSchedule: schedule, schedulesLoading } = useProject();
  const navigate = useNavigate();
  const [curveWindow, setCurveWindow] = useState<"all" | "90d" | "30d">("all");
  const [series, setSeries] = useState<("planned" | "actual")[]>(["planned", "actual"]);
  const [riskFocus, setRiskFocus] = useState<"top" | "critical">("top");

  const summaryQuery = useQuery({
    queryKey: ["analytics-summary", projectId, schedule?.id],
    queryFn: () => analyticsApi.summary(projectId, schedule!.id),
    enabled: !!schedule,
  });
  const sCurveQuery = useQuery({
    queryKey: ["s-curve", projectId, schedule?.id],
    queryFn: () => analyticsApi.sCurve(projectId, schedule!.id),
    enabled: !!schedule,
  });
  const riskQuery = useQuery({
    queryKey: ["risk-summary", projectId, schedule?.id],
    queryFn: () => predictionApi.riskSummary(projectId, schedule!.id),
    enabled: !!schedule,
  });
  const statsQuery = useQuery({
    queryKey: ["match-stats", projectId],
    queryFn: () => matchingApi.stats(projectId),
  });
  const reportsQuery = useQuery({
    queryKey: ["progress-reports", projectId, "recent"],
    queryFn: () => reportsApi.list(projectId, { limit: 5 }),
  });

  const summary = summaryQuery.data;
  const risk = riskQuery.data;
  const stats = statsQuery.data;

  const stages = useMemo<PipelineStage[]>(() => {
    const base = `/projects/${projectId}`;
    const criticalCount =
      risk?.by_risk_level
        .filter((b) => b.risk_level === "HIGH" || b.risk_level === "CRITICAL")
        .reduce((sum, b) => sum + b.count, 0) ?? null;

    return [
      {
        key: "plan",
        label: "Planned",
        value: summary?.total_activities ?? null,
        caption: "activities in baseline",
        to: `${base}/schedule`,
        icon: PIPELINE_ICONS.schedule,
        state: summary?.total_activities ? "active" : "empty",
      },
      {
        key: "site",
        label: "Site reports",
        value: reportsQuery.data?.total ?? null,
        caption: "documents ingested",
        to: `${base}/uploads`,
        icon: PIPELINE_ICONS.upload,
        state: reportsQuery.data?.total ? "active" : "empty",
      },
      {
        key: "extract",
        label: "AI extracted",
        value: stats?.total ?? null,
        caption: "field items found",
        to: `${base}/matching`,
        icon: PIPELINE_ICONS.extract,
        state: stats?.total ? "active" : "empty",
      },
      {
        key: "match",
        label: "Matched",
        value: stats ? stats.auto_matched + stats.manually_confirmed : null,
        caption: stats?.needs_review ? `${stats.needs_review} awaiting review` : "linked to activities",
        to: `${base}/matching`,
        icon: PIPELINE_ICONS.match,
        state: stats?.needs_review ? "attention" : stats?.total ? "active" : "empty",
      },
      {
        key: "progress",
        label: "Progress",
        value: summary ? Number(summary.overall_completion_percentage.toFixed(1)) : null,
        unit: "%",
        caption: "quantity-weighted",
        to: `${base}/schedule`,
        icon: PIPELINE_ICONS.progress,
        state: summary?.activities_with_progress ? "active" : "empty",
      },
      {
        key: "risk",
        label: "At risk",
        value: criticalCount,
        caption: "high or critical",
        to: `${base}/risks`,
        icon: PIPELINE_ICONS.risk,
        state: criticalCount ? "attention" : risk?.total_predictions ? "active" : "empty",
      },
    ];
  }, [projectId, summary, stats, risk, reportsQuery.data]);

  if (schedulesLoading) return <LoadingCards />;

  if (!schedule) {
    return (
      <EmptyState
        icon={<CalendarRange className="h-5 w-5" />}
        title="No baseline schedule yet"
        description="Upload a Primavera or MS Project export (Excel/CSV) to unlock planned-vs-actual analytics, AI matching and delay prediction for this project."
        action={
          canManage ? (
            <Link to={`/projects/${projectId}/schedule`}>
              <Button>
                Upload a schedule
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          ) : (
            <p className="text-xs text-content-3">Ask your project manager to upload the baseline.</p>
          )
        }
      />
    );
  }

  const variance = summary?.schedule_variance;
  const behind = variance != null && variance < 0;

  // The window trims the series client-side; it never fabricates points, so a
  // window with no reported dates simply shows the planned curve alone.
  const curve = (() => {
    const rows = sCurveQuery.data ?? [];
    if (curveWindow === "all" || rows.length === 0) return rows;
    const days = curveWindow === "90d" ? 90 : 30;
    const last = new Date(rows[rows.length - 1].reporting_date);
    const cutoff = new Date(last);
    cutoff.setDate(cutoff.getDate() - days);
    const iso = cutoff.toISOString().slice(0, 10);
    const trimmed = rows.filter((p) => p.reporting_date >= iso);
    return trimmed.length >= 2 ? trimmed : rows;
  })();

  // A single reported date renders as a lone dot — Recharts needs two points to
  // draw a line — so say how many there are rather than leaving it looking broken.
  const actualPoints = curve.filter((p) => p.actual_percentage != null).length;

  return (
    <div className="space-y-6">
      {summaryQuery.error && <ErrorState error={summaryQuery.error} title="Could not load analytics" />}

      {/* Headline metrics */}
      {summaryQuery.isLoading && <LoadingCards />}
      {summary && (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          <MetricTile
            label="Actual completion"
            value={Number(summary.overall_completion_percentage.toFixed(1))}
            unit="%"
            icon={<Gauge className="h-4 w-4" />}
            hint={`as of ${summary.as_of}`}
            delay={0}
          />
          <MetricTile
            label="Planned completion"
            value={
              summary.planned_completion_percentage != null
                ? Number(summary.planned_completion_percentage.toFixed(1))
                : "—"
            }
            unit={summary.planned_completion_percentage != null ? "%" : undefined}
            icon={<CalendarRange className="h-4 w-4" />}
            hint={summary.planned_completion_percentage == null ? "plan carries no dates" : "where the plan says we should be"}
            delay={0.05}
          />
          <MetricTile
            label="Schedule variance"
            value={variance != null ? Number(variance.toFixed(1)) : "—"}
            // "pp" is percentage points, not percent: it is the gap between two
            // percentages (actual minus planned), so calling it "%" would read
            // as a relative change and overstate or understate the slip.
            unit={variance != null ? " pts" : undefined}
            hint={
              variance != null
                ? `actual ${summary.overall_completion_percentage?.toFixed(1) ?? "—"}% vs planned ${summary.planned_completion_percentage?.toFixed(1) ?? "—"}%`
                : undefined
            }
            tone={behind ? "critical" : variance != null ? "positive" : "default"}
            icon={behind ? <TrendingDown className="h-4 w-4" /> : <TrendingUp className="h-4 w-4" />}
            trend={
              variance != null
                ? { direction: behind ? "down" : "up", label: behind ? "behind plan" : "on or ahead", good: !behind }
                : undefined
            }
            delay={0.1}
          />
          <MetricTile
            label="Delayed activities"
            value={summary.delayed_activities}
            tone={summary.delayed_activities > 0 ? "warning" : "positive"}
            icon={<TimerOff className="h-4 w-4" />}
            hint={`of ${summary.leaf_activities} leaf activities`}
            delay={0.15}
          />
        </div>
      )}

      {/* Signature pipeline */}
      <PipelineFlow stages={stages} />

      {/* Charts + risk */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Planned vs actual"
            subtitle={`Cumulative completion · ${schedule.name}`}
            icon={<TrendingUp className="h-4 w-4" />}
            action={
              <div className="flex items-center gap-2">
                {actualPoints > 0 && (
                  <span className="hidden font-mono text-2xs text-content-2 sm:inline">
                    {actualPoints} reporting date{actualPoints === 1 ? "" : "s"}
                  </span>
                )}
                <SelectMenu<"all" | "90d" | "30d">
                  value={curveWindow}
                  width="w-48"
                  align="right"
                  options={[
                    { value: "all", label: "Whole baseline" },
                    { value: "90d", label: "Last 90 days" },
                    { value: "30d", label: "Last 30 days" },
                  ]}
                  onChange={(v) => v && setCurveWindow(v)}
                />
                <MultiSelectMenu<"planned" | "actual">
                  label="Series"
                  width="w-44"
                  options={[
                    { value: "planned", label: "Planned" },
                    { value: "actual", label: "Actual" },
                  ]}
                  selected={series}
                  onChange={(next) => setSeries(next.length === 0 ? ["planned", "actual"] : next)}
                />
              </div>
            }
          />
          <div className="p-4">
            {sCurveQuery.isLoading && <LoadingRows rows={4} />}
            {sCurveQuery.error && <ErrorState error={sCurveQuery.error} />}
            {curve.length > 0 ? (
              <>
                <SCurve
                  data={curve}
                  soloActual={actualPoints === 1}
                  showPlanned={series.includes("planned")}
                  showActual={series.includes("actual")}
                />
                {actualPoints === 1 && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-[10px] bg-surface-raised px-2.5 py-2 text-2xs leading-relaxed text-content-2">
                    <TrendingUp className="mt-0.5 h-3 w-3 shrink-0 text-teal-600" />
                    Progress has been reported on a single date so far, so actual shows as one point
                    rather than a curve. Book progress on more dates — or ingest site reports spanning
                    several days — and the line will draw.
                  </p>
                )}
                {actualPoints === 0 && (
                  <p className="mt-2 rounded-[10px] bg-surface-raised px-2.5 py-2 text-2xs leading-relaxed text-content-2">
                    Only the planned curve is shown: no progress has been booked against this schedule
                    yet, and an unmeasured period is left blank rather than drawn as 0%.
                  </p>
                )}
              </>
            ) : (
              !sCurveQuery.isLoading &&
              !sCurveQuery.error && (
                <EmptyState
                  compact
                  icon={<TrendingUp className="h-5 w-5" />}
                  title="No progress recorded yet"
                  description="The curve appears once site progress is booked against this schedule."
                />
              )
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Delay risk"
            subtitle={
              risk?.method
                ? `${risk.method.replaceAll("_", " ").toLowerCase()}${risk.model_version ? ` · ${risk.model_version}` : ""}`
                : "no forecast yet"
            }
            icon={<ShieldAlert className="h-4 w-4" />}
            action={
              <Dropdown
                variant="ghost"
                align="right"
                width="w-60"
                label="View"
                icon={<ShieldAlert className="h-3.5 w-3.5 text-content-2" />}
              >
                {(close) => (
                  <>
                    <DropdownLabel>Show in this card</DropdownLabel>
                    <DropdownItem
                      selected={riskFocus === "top"}
                      onSelect={() => {
                        setRiskFocus("top");
                        close();
                      }}
                    >
                      Highest probability
                    </DropdownItem>
                    <DropdownItem
                      selected={riskFocus === "critical"}
                      hint={String(
                        (risk?.top_risks ?? []).filter(
                          (r) => r.risk_level === "HIGH" || r.risk_level === "CRITICAL",
                        ).length,
                      )}
                      onSelect={() => {
                        setRiskFocus("critical");
                        close();
                      }}
                    >
                      High &amp; critical only
                    </DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem
                      icon={<ArrowRight className="h-3.5 w-3.5" />}
                      onSelect={() => {
                        close();
                        navigate(`/projects/${projectId}/risks`);
                      }}
                    >
                      Open the full forecast
                    </DropdownItem>
                  </>
                )}
              </Dropdown>
            }
          />
          <div className="p-4">
            {riskQuery.isLoading && <LoadingRows rows={3} />}
            {risk && risk.total_predictions > 0 ? (
              <div className="space-y-4">
                <RiskDistribution buckets={risk.by_risk_level} total={risk.total_predictions} />
                <div className="space-y-2">
                  {(riskFocus === "critical"
                    ? risk.top_risks.filter(
                        (r) => r.risk_level === "HIGH" || r.risk_level === "CRITICAL",
                      )
                    : risk.top_risks
                  )
                    .slice(0, 4)
                    .map((r) => (
                    <Link
                      key={r.id}
                      to={`/projects/${projectId}/risks`}
                      className="flex items-center gap-2.5 rounded-[10px] border border-line p-2 transition-colors hover:border-line hover:bg-surface-raised"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-content-1">
                          {r.activity_code ?? "Activity"}{" "}
                          <span className="font-normal text-content-3">{r.activity_name}</span>
                        </p>
                        <p className="tnum mt-0.5 text-2xs text-content-3">
                          {(r.probability * 100).toFixed(0)}% late
                          {r.forecast_slip_days ? ` · ${r.forecast_slip_days}d slip` : ""}
                        </p>
                      </div>
                      <RiskBadge level={r.risk_level} />
                    </Link>
                  ))}
                </div>
                <p className="text-2xs leading-relaxed text-content-2">{risk.note}</p>
              </div>
            ) : (
              !riskQuery.isLoading && (
                <EmptyState
                  compact
                  icon={<ShieldAlert className="h-5 w-5" />}
                  title="No forecast yet"
                  description={
                    canManage
                      ? "Run a prediction from the Risk & Delay tab."
                      : "A project manager can run the delay forecast."
                  }
                  action={
                    canManage ? (
                      <Link to={`/projects/${projectId}/risks`}>
                        <Button size="sm" variant="secondary">
                          Run prediction
                        </Button>
                      </Link>
                    ) : undefined
                  }
                />
              )
            )}
          </div>
        </Card>
      </div>

      {/* Matching + recent site reports */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="AI matching queue"
            subtitle="Field reports linked to schedule activities"
            icon={<ClipboardList className="h-4 w-4" />}
            action={
              <Link to={`/projects/${projectId}/matching`} className="text-2xs font-medium text-accent hover:underline">
                Open
              </Link>
            }
          />
          <div className="p-4">
            {statsQuery.isLoading && <LoadingRows rows={3} />}
            {stats && stats.total > 0 ? (
              <div className="space-y-3">
                <MatchBar stats={stats} />
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MiniStat label="Auto-matched" value={stats.auto_matched} tone="text-teal-700" />
                  <MiniStat label="Needs review" value={stats.needs_review} tone="text-amber-700" />
                  <MiniStat label="Confirmed" value={stats.manually_confirmed} tone="text-accent" />
                  <MiniStat label="Unmatched" value={stats.unmatched} tone="text-content-3" />
                </div>
                {stats.auto_precision != null && (
                  <p className="flex items-center gap-1.5 rounded-[10px] bg-teal-50 px-2.5 py-2 text-2xs text-teal-800">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    Of the automatic links a human has ruled on, {(stats.auto_precision * 100).toFixed(0)}% were upheld
                    <span className="text-teal-600">({stats.reviewed_count} reviewed)</span>
                  </p>
                )}
              </div>
            ) : (
              !statsQuery.isLoading && (
                <EmptyState
                  compact
                  title="Nothing matched yet"
                  description="Upload a site report, then run matching."
                />
              )
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Recent site reports"
            subtitle="Newest field data reaching the platform"
            icon={<ClipboardList className="h-4 w-4" />}
            action={
              <Link to={`/projects/${projectId}/uploads`} className="text-2xs font-medium text-accent hover:underline">
                Open
              </Link>
            }
          />
          <div className="p-4">
            {reportsQuery.isLoading && <LoadingRows rows={3} />}
            {reportsQuery.data && reportsQuery.data.items.length > 0 ? (
              <ul className="space-y-2">
                {reportsQuery.data.items.map((r) => (
                  <li key={r.id} className="rounded-[10px] border border-line p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-content-1">
                        {r.report_date ?? "Undated report"}
                      </span>
                      <span className="text-2xs text-content-2">
                        {new Date(r.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-2xs leading-relaxed text-content-3">{r.raw_text}</p>
                  </li>
                ))}
              </ul>
            ) : (
              !reportsQuery.isLoading && (
                <EmptyState compact title="No site reports yet" description="Uploads and WhatsApp messages appear here." />
              )
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function SCurve({
  data,
  soloActual,
  showPlanned = true,
  showActual = true,
}: {
  data: Array<{ reporting_date: string; planned_percentage: number; actual_percentage: number | null }>;
  soloActual?: boolean;
  showPlanned?: boolean;
  showActual?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={290}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="plannedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e8e8ed" stopOpacity={0.12} />
            <stop offset="100%" stopColor="#e8e8ed" stopOpacity={0.01} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.08)" vertical={false} />
        <XAxis
          dataKey="reporting_date"
          tick={{ fontSize: 11, fill: "#86868b" }}
          tickLine={false}
          axisLine={{ stroke: "rgba(255,255,255,0.14)" }}
          minTickGap={40}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#86868b" }}
          tickLine={false}
          axisLine={false}
          unit="%"
          domain={[0, 100]}
        />
        <Tooltip
          cursor={{ stroke: "#c47886", strokeWidth: 1, strokeDasharray: "3 3" }}
          contentStyle={{
            borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.12)",
            background: "#1c1c1f",
            color: "#f5f5f7",
            boxShadow: "0 12px 32px -8px rgb(0 0 0 / 0.6)",
            fontSize: 12,
            
          }}
          formatter={(value, name) => [
            value == null ? "not measured" : `${Number(value).toFixed(1)}%`,
            String(name),
          ]}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="line" />
        {showPlanned && (
          <Area
            type="monotone"
            dataKey="planned_percentage"
            name="Planned"
            stroke="#e8e8ed"
            strokeWidth={1.75}
            strokeDasharray="5 4"
            fill="url(#plannedFill)"
            dot={false}
          />
        )}
        {showActual && (
          <Line
            type="monotone"
            dataKey="actual_percentage"
            name="Actual"
            stroke="#c47886"
            strokeWidth={2.5}
            dot={{
              // One reported date has no line to sit on, so the point itself has
              // to carry the reading.
              r: soloActual ? 6 : 2.5,
              fill: "#c47886",
              stroke: soloActual ? "#0a0a0b" : undefined,
              strokeWidth: soloActual ? 2 : 0,
            }}
            activeDot={{ r: 6 }}
            connectNulls
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RiskDistribution({
  buckets,
  total,
}: {
  buckets: Array<{ risk_level: string; count: number }>;
  total: number;
}) {
  const colors: Record<string, string> = {
    LOW: "bg-teal-500",
    MEDIUM: "bg-amber-400",
    HIGH: "bg-orange-500",
    CRITICAL: "bg-rose-600",
  };
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-raised">
        {buckets.map((b) =>
          b.count > 0 ? (
            <div
              key={b.risk_level}
              className={colors[b.risk_level] ?? "bg-ink-300"}
              style={{ width: `${(b.count / total) * 100}%` }}
              title={`${b.risk_level}: ${b.count}`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {buckets.map((b) => (
          <span key={b.risk_level} className="flex items-center gap-1.5 text-2xs text-content-2">
            <span className={`h-2 w-2 rounded-sm ${colors[b.risk_level] ?? "bg-ink-300"}`} />
            {b.risk_level.toLowerCase()} <span className="tnum font-medium text-content-1">{b.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function MatchBar({
  stats,
}: {
  stats: { total: number; auto_matched: number; needs_review: number; unmatched: number; manually_confirmed: number };
}) {
  const linked = stats.auto_matched + stats.manually_confirmed;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-2xs text-content-3">Linked to a schedule activity</span>
        <span className="tnum text-xs font-semibold text-content-1">
          {linked} / {stats.total}
        </span>
      </div>
      <ProgressMeter value={linked} max={stats.total} tone="teal" className="mt-1.5" />
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-[10px] bg-surface-raised px-2.5 py-2">
      <p className={`tnum text-base font-semibold ${tone}`}>{value}</p>
      <p className="mt-0.5 text-2xs text-content-3">{label}</p>
    </div>
  );
}
