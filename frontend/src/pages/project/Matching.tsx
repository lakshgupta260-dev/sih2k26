import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import clsx from "clsx";
import {
  ArrowRight,
  Check,
  FileText,
  GitCompareArrows,
  History,
  ArrowUpDown,
  Filter,
  Play,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { matchingApi } from "@/api/matching";
import { progressApi } from "@/api/progress";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Badge, ConfidenceBar, MatchStatusBadge } from "@/components/common/Badge";
import {
  Button,
  Card,
  CardHeader,
  Modal,
  PageHeader,
  Textarea,
} from "@/components/ui/Primitives";
import { MultiSelectMenu, SelectMenu } from "@/components/ui/Dropdown";
import { MetricTile } from "@/components/ui/Metric";
import type { ActivityMatchRead, ExtractedActivityRead, MatchStatus } from "@/types/api";

type Tab = "queue" | "extracted";

/** The bands are the backend's own decision thresholds, not an arbitrary ramp. */
type ConfidenceBand = "auto" | "review" | "low";
type QueueSort = "score-desc" | "score-asc" | "newest" | "reviewed";

const BAND_OPTIONS: { value: ConfidenceBand; label: string; hint: string }[] = [
  { value: "auto", label: "Auto band", hint: "≥ 0.82" },
  { value: "review", label: "Review band", hint: "0.55–0.82" },
  { value: "low", label: "Below review", hint: "< 0.55" },
];

function bandOf(score: number): ConfidenceBand {
  return score >= 0.82 ? "auto" : score >= 0.55 ? "review" : "low";
}

export function Matching() {
  const projectId = useProjectId();
  const { canManage, selectedSchedule: schedule } = useProject();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("queue");
  const [statusFilter, setStatusFilter] = useState<MatchStatus | "">("");
  const [band, setBand] = useState<ConfidenceBand[]>([]);
  const [queueSort, setQueueSort] = useState<QueueSort>("score-desc");
  const [selectedMatch, setSelectedMatch] = useState<string | null>(null);


  const statsQuery = useQuery({
    queryKey: ["match-stats", projectId],
    queryFn: () => matchingApi.stats(projectId),
  });
  const matchesQuery = useQuery({
    queryKey: ["matches", projectId, statusFilter],
    queryFn: () => matchingApi.listMatches(projectId, { status: statusFilter || undefined, limit: 100 }),
    enabled: tab === "queue",
  });
  // Fetched for both tabs: the queue needs it to show the site text that each
  // proposed link came from, not just a confidence score with no subject.
  const extractedQuery = useQuery({
    queryKey: ["extracted", projectId],
    queryFn: () => matchingApi.listAllExtracted(projectId),
  });

  const extractedById = useMemo(() => {
    const map = new Map<string, ExtractedActivityRead>();
    for (const e of extractedQuery.data?.items ?? []) map.set(e.id, e);
    return map;
  }, [extractedQuery.data]);

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["matches", projectId] });
    queryClient.invalidateQueries({ queryKey: ["extracted", projectId] });
    queryClient.invalidateQueries({ queryKey: ["match-stats", projectId] });
  };

  const runMutation = useMutation({
    mutationFn: () => matchingApi.run(projectId, {}),
    onSuccess: (summary) => {
      invalidateAll();
      toast.success(
        `Matched ${summary.items_extracted} item${summary.items_extracted === 1 ? "" : "s"}`,
        `${summary.auto_matched} auto-matched · ${summary.needs_review} need review · ${summary.unmatched} unmatched — via ${summary.extractors_used.join(", ")}${summary.llm_available ? " with LLM" : " (no LLM configured)"}.`,
      );
    },
    onError: (err) =>
      toast.error("Matching run failed", err instanceof ApiError ? err.message : undefined),
  });

  const applyMutation = useMutation({
    mutationFn: () => {
      if (!schedule) throw new Error("No schedule to apply matches against.");
      return progressApi.applyMatches(projectId, schedule.id);
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["progress-rollup", projectId] });
      queryClient.invalidateQueries({ queryKey: ["analytics-summary", projectId] });
      queryClient.invalidateQueries({ queryKey: ["s-curve", projectId] });
      const booked = result.records_created + result.records_updated;
      const skipped =
        result.skipped_not_an_actual_event +
        result.skipped_missing_event_date +
        result.skipped_other_schedule;
      toast.success(
        `Booked ${booked} progress record${booked === 1 ? "" : "s"}`,
        skipped > 0
          ? `${skipped} confirmed match${skipped === 1 ? "" : "es"} skipped: ${result.skipped_not_an_actual_event} not an actual event, ${result.skipped_missing_event_date} undated, ${result.skipped_other_schedule} on another schedule.`
          : `From ${result.matches_considered} confirmed matches.`,
      );
    },
    onError: (err) =>
      toast.error("Could not apply matches", err instanceof ApiError ? err.message : undefined),
  });

  const stats = statsQuery.data;

  // The status filter is applied server-side; band and sort are client-side over
  // the returned page, so the row count shown always matches what is listed.
  const queueRows = useMemo(() => {
    const rows = (matchesQuery.data?.items ?? []).filter(
      (m) => band.length === 0 || band.includes(bandOf(m.score)),
    );
    return [...rows].sort((a, b) => {
      switch (queueSort) {
        case "score-asc":
          return a.score - b.score;
        case "newest":
          return b.created_at.localeCompare(a.created_at);
        case "reviewed":
          if (!a.reviewed_at && !b.reviewed_at) return 0;
          if (!a.reviewed_at) return 1;
          if (!b.reviewed_at) return -1;
          return b.reviewed_at.localeCompare(a.reviewed_at);
        default:
          return b.score - a.score;
      }
    });
  }, [matchesQuery.data, band, queueSort]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI activity matching"
        subtitle="The bridge the problem statement asks for: a line of field text becomes an extracted event, gets linked to the schedule activity it actually refers to, and carries a confidence score a human can overrule."
        actions={
          canManage && (
            <>
              <Button
                variant="secondary"
                onClick={() => applyMutation.mutate()}
                disabled={!schedule}
                loading={applyMutation.isPending}
              >
                <Target className="h-4 w-4" />
                Apply confirmed
              </Button>
              <Button onClick={() => runMutation.mutate()} loading={runMutation.isPending}>
                <Play className="h-4 w-4" />
                Run matching
              </Button>
            </>
          )
        }
      />

      {/* The funnel, stated as numbers. */}
      {statsQuery.isLoading && <LoadingRows rows={2} />}
      {stats && stats.total > 0 && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-5">
          <MetricTile label="Extracted" value={stats.total} icon={<Sparkles className="h-4 w-4" />} />
          <MetricTile label="Auto-matched" value={stats.auto_matched} tone="positive" delay={0.05} />
          <MetricTile
            label="Needs review"
            value={stats.needs_review}
            tone={stats.needs_review ? "warning" : "default"}
            delay={0.1}
            onClick={() => {
              setTab("queue");
              setStatusFilter("NEEDS_REVIEW");
            }}
          />
          <MetricTile label="Unmatched" value={stats.unmatched} delay={0.15} />
          <MetricTile
            label="Auto precision"
            value={stats.auto_precision != null ? Number((stats.auto_precision * 100).toFixed(0)) : "—"}
            unit={stats.auto_precision != null ? "%" : undefined}
            hint={stats.reviewed_count ? `${stats.reviewed_count} human decisions` : "no reviews yet"}
            delay={0.2}
          />
        </div>
      )}

      <div className="flex items-center gap-0.5 rounded-[14px] border border-line bg-surface-card p-1 shadow-card">
        {([
          { id: "queue" as Tab, label: "Match queue", icon: GitCompareArrows },
          { id: "extracted" as Tab, label: "Extracted items", icon: FileText },
        ]).map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "relative flex items-center gap-1.5 rounded-[10px] px-3 py-1.5 text-xs font-medium transition-colors",
                tab === t.id ? "text-content-1" : "text-content-3 hover:text-content-1",
              )}
            >
              {tab === t.id && (
                <motion.span
                  layoutId="matching-tab"
                  className="absolute inset-0 rounded-[10px] bg-signal-500/12 ring-1 ring-inset ring-signal-500/35"
                  transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
              <Icon className="relative h-3.5 w-3.5" />
              <span className="relative">{t.label}</span>
            </button>
          );
        })}
      </div>

      {tab === "queue" && (
        <Card>
          <CardHeader
            title="Proposed links"
            subtitle="Auto-matched above 0.82 · queued for review above 0.55 · below that, recorded as unmatched"
            action={
              <div className="flex flex-wrap items-center gap-2">
                <SelectMenu<MatchStatus>
                  prefix="Status"
                  icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
                  align="right"
                  width="w-56"
                  value={statusFilter}
                  placeholder="All statuses"
                  onChange={(v) => setStatusFilter(v)}
                  options={[
                    { value: "" as MatchStatus, label: "All statuses" },
                    { value: "NEEDS_REVIEW", label: "Needs review", hint: "queued" },
                    { value: "AUTO_MATCHED", label: "Auto-matched", hint: "≥ 0.82" },
                    { value: "MANUALLY_CONFIRMED", label: "Confirmed", hint: "by a human" },
                    { value: "MANUALLY_REJECTED", label: "Rejected", hint: "by a human" },
                    { value: "UNMATCHED", label: "Unmatched", hint: "< 0.55" },
                  ]}
                />
                <MultiSelectMenu<ConfidenceBand>
                  label="Confidence"
                  width="w-56"
                  options={BAND_OPTIONS.map((b) => ({
                    ...b,
                    hint: `${b.hint} · ${
                      (matchesQuery.data?.items ?? []).filter((m) => bandOf(m.score) === b.value)
                        .length
                    }`,
                  }))}
                  selected={band}
                  onChange={setBand}
                />
                <SelectMenu<QueueSort>
                  prefix="Sort"
                  icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
                  align="right"
                  width="w-56"
                  value={queueSort}
                  options={[
                    { value: "score-desc", label: "Confidence, high first" },
                    { value: "score-asc", label: "Confidence, low first" },
                    { value: "newest", label: "Newest first" },
                    { value: "reviewed", label: "Recently reviewed" },
                  ]}
                  onChange={(v) => v && setQueueSort(v)}
                />
              </div>
            }
          />
          <div className="p-2">
            {matchesQuery.isLoading && <LoadingRows />}
            {matchesQuery.error && <ErrorState error={matchesQuery.error} onRetry={() => matchesQuery.refetch()} />}
            {matchesQuery.data?.items.length === 0 && (
              <EmptyState
                icon={<GitCompareArrows className="h-5 w-5" />}
                title={statusFilter ? "Nothing with that status" : "No matches yet"}
                description={
                  statusFilter
                    ? "Try a different status filter."
                    : "Upload a site report, then run matching to link it to the schedule."
                }
              />
            )}
            {matchesQuery.data && matchesQuery.data.items.length > 0 && queueRows.length === 0 && (
              <EmptyState
                compact
                icon={<Filter className="h-5 w-5" />}
                title="No match in that confidence band"
                description="Clear the confidence filter to see the rest of the queue."
              />
            )}
            {queueRows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-2xs text-content-3">
                      <th className="px-3 py-2 font-medium">Reported on site</th>
                      <th className="px-3 py-2 font-medium">Linked activity</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Confidence</th>
                      <th className="hidden px-3 py-2 font-medium lg:table-cell">Method</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {queueRows.map((m: ActivityMatchRead) => {
                      const item = extractedById.get(m.extracted_activity_id);
                      // The linked activity is whichever candidate the match
                      // actually points at; falling back to the best candidate
                      // only when nothing has been linked yet.
                      const linked =
                        m.candidates.find((c) => c.activity_id === m.activity_id) ??
                        (m.activity_id ? undefined : m.candidates[0]);
                      return (
                        <tr
                          key={m.id}
                          onClick={() => setSelectedMatch(m.id)}
                          className="cursor-pointer transition-colors hover:bg-signal-600/25/40"
                        >
                          <td className="max-w-[20rem] px-3 py-2.5">
                            <p className="truncate text-xs text-content-1">
                              {item?.raw_text ??
                                (extractedQuery.isLoading ? "loading…" : "(source item unavailable)")}
                            </p>
                            <p className="mt-0.5 truncate font-mono text-2xs text-content-2">
                              {[item?.event_date, item?.discipline, item?.activity_code]
                                .filter(Boolean)
                                .join(" · ") || "no date or code parsed"}
                            </p>
                          </td>
                          <td className="max-w-[16rem] px-3 py-2.5">
                            {linked ? (
                              <>
                                <p className="truncate font-mono text-2xs font-medium uppercase text-accent">
                                  {linked.activity_code}
                                </p>
                                <p className="mt-0.5 truncate text-xs text-content-1">
                                  {linked.activity_name}
                                </p>
                              </>
                            ) : (
                              <span className="text-2xs text-content-2">not linked</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5">
                            <MatchStatusBadge status={m.status} />
                          </td>
                          <td className="px-3 py-2.5">
                            <ConfidenceBar value={m.score} />
                          </td>
                          <td className="hidden px-3 py-2.5 lg:table-cell">
                            <span className="font-mono text-2xs text-content-3">{m.method}</span>
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <span className="inline-flex items-center gap-1 text-2xs font-medium text-accent">
                              Review <ArrowRight className="h-3 w-3" />
                            </span>
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
      )}

      {tab === "extracted" && (
        <Card>
          <CardHeader
            title="Extracted field items"
            subtitle="Everything the extractor found, including lines it judged not to be progress events"
          />
          <div className="p-4">
            {extractedQuery.isLoading && <LoadingRows />}
            {extractedQuery.data?.items.length === 0 && (
              <EmptyState title="Nothing extracted yet" description="Run matching after a site report is processed." />
            )}
            {extractedQuery.data && extractedQuery.data.items.length > 0 && (
              <div className="space-y-2">
                {extractedQuery.data.items.map((it) => (
                  <div key={it.id} className="rounded-[10px] border border-line p-3 transition-colors hover:border-line">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge tone={it.event_type === "PROGRESS" ? "blue" : "slate"}>
                          {it.event_type.toLowerCase()}
                        </Badge>
                        {it.activity_code && (
                          <span className="font-mono text-2xs text-content-3">{it.activity_code}</span>
                        )}
                        {it.discipline && <span className="text-2xs text-content-2">{it.discipline}</span>}
                      </div>
                      <ConfidenceBar value={it.extraction_confidence} />
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-content-1">{it.raw_text}</p>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 text-2xs text-content-2">
                      <span>via {it.extractor}</span>
                      {it.event_date && <span>{it.event_date}</span>}
                      {it.percent_complete != null && <span>{it.percent_complete}% complete</span>}
                      {it.quantity != null && (
                        <span>
                          {it.quantity} {it.uom ?? ""}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {selectedMatch && (
        <MatchReviewDrawer
          projectId={projectId}
          matchId={selectedMatch}
          canManage={canManage}
          onClose={() => setSelectedMatch(null)}
          onReviewed={invalidateAll}
        />
      )}
    </div>
  );
}

function MatchReviewDrawer({
  projectId,
  matchId,
  canManage,
  onClose,
  onReviewed,
}: {
  projectId: string;
  matchId: string;
  canManage: boolean;
  onClose: () => void;
  onReviewed: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [reassignTo, setReassignTo] = useState("");

  const detailQuery = useQuery({
    queryKey: ["match", projectId, matchId],
    queryFn: () => matchingApi.getMatch(projectId, matchId),
  });
  const historyQuery = useQuery({
    queryKey: ["match-history", projectId, matchId],
    queryFn: () => matchingApi.matchHistory(projectId, matchId),
  });

  const reviewMutation = useMutation({
    mutationFn: (decision: "confirm" | "reject" | "reassign") =>
      matchingApi.review(projectId, matchId, {
        decision,
        activity_id: decision === "reassign" ? reassignTo : undefined,
        note: note || undefined,
      }),
    onSuccess: (_res, decision) => {
      queryClient.invalidateQueries({ queryKey: ["match", projectId, matchId] });
      onReviewed();
      toast.success(
        decision === "confirm" ? "Match confirmed" : decision === "reject" ? "Match rejected" : "Match reassigned",
        "Recorded in the review history with your name against it.",
      );
      onClose();
    },
    onError: (err) => toast.error("Review failed", err instanceof ApiError ? err.message : undefined),
  });

  const match = detailQuery.data;
  const chosen = match?.candidates?.find((c) => c.activity_id === match.activity_id);

  return (
    <Modal open onClose={onClose} title="Review proposed match" size="lg">
      {detailQuery.isLoading && <LoadingRows rows={4} />}
      {detailQuery.error && <ErrorState error={detailQuery.error} />}
      {match && (
        <div className="space-y-5">
          {/* The chain, made literal. */}
          <div className="rounded-[14px] border border-line bg-surface-raised/60 p-3">
            <div className="flex flex-col gap-2.5 sm:flex-row sm:items-stretch">
              <div className="flex-1 rounded-[10px] bg-surface-card p-3 shadow-card">
                <p className="mb-1 text-2xs font-medium text-content-2">
                  What the site reported
                </p>
                <p className="text-sm leading-relaxed text-content-1">{match.extracted.raw_text}</p>
                <p className="mt-1.5 text-2xs text-content-2">
                  {match.extracted.event_type.toLowerCase()}
                  {match.extracted.event_date ? ` · ${match.extracted.event_date}` : ""}
                  {match.extracted.percent_complete != null
                    ? ` · ${match.extracted.percent_complete}%`
                    : ""}
                </p>
              </div>

              <div className="flex items-center justify-center px-1 text-content-2">
                <ArrowRight className="h-4 w-4 rotate-90 sm:rotate-0" />
              </div>

              <div className="flex-1 rounded-[10px] bg-surface-card p-3 shadow-card">
                <p className="mb-1 text-2xs font-medium text-content-2">
                  Linked schedule activity
                </p>
                {chosen ? (
                  <>
                    <p className="text-sm font-medium text-content-1">
                      <span className="font-mono text-2xs text-content-3">{chosen.activity_code}</span>{" "}
                      {chosen.activity_name}
                    </p>
                    <p className="mt-1 font-mono text-2xs text-content-2">
                      WBS {chosen.wbs_path} · L{chosen.level}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-content-2">
                    No activity linked — the matcher found nothing above the threshold.
                  </p>
                )}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-2.5">
              <MatchStatusBadge status={match.status} />
              <ConfidenceBar value={match.score} width="w-32" />
              <span className="font-mono text-2xs text-content-2">{match.method}</span>
              {match.embedding_provider && (
                <span className="text-2xs text-content-2">embeddings: {match.embedding_provider}</span>
              )}
            </div>
            {match.reason && <p className="mt-2 text-2xs leading-relaxed text-content-3">{match.reason}</p>}
          </div>

          {/* Why this one and not the others. */}
          {match.candidates?.length > 0 && (
            <div>
              <p className="mb-2 text-2xs font-medium text-content-2">
                Candidates the matcher weighed
              </p>
              <div className="space-y-1.5">
                {match.candidates.map((c) => {
                  const isChosen = c.activity_id === match.activity_id;
                  return (
                    <div
                      key={c.activity_id}
                      className={clsx(
                        "rounded-[10px] border p-2.5",
                        isChosen ? "border-signal-500/40 bg-signal-600/25/50" : "border-line",
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate text-xs text-content-1">
                          <span className="font-mono text-2xs text-content-3">{c.activity_code}</span>{" "}
                          {c.activity_name}
                          {isChosen && (
                            <Badge tone="blue" className="ml-2">
                              chosen
                            </Badge>
                          )}
                        </p>
                        <ConfidenceBar value={c.score} width="w-20" />
                      </div>
                      {c.explanation?.length > 0 && (
                        <p className="mt-1 text-2xs text-content-3">{c.explanation.join(" · ")}</p>
                      )}
                      {!!c.signals && Object.keys(c.signals).length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {Object.entries(c.signals)
                            .filter(([, v]) => typeof v === "number" && v > 0)
                            .map(([k, v]) => (
                              <span
                                key={k}
                                className="rounded bg-surface-card px-1.5 py-0.5 text-2xs text-content-3 ring-1 ring-inset ring-line"
                              >
                                {k.replaceAll("_", " ")} {(v as number).toFixed(2)}
                              </span>
                            ))}
                        </div>
                      )}
                      {canManage && !isChosen && (
                        <button
                          onClick={() => setReassignTo(c.activity_id)}
                          className={clsx(
                            "mt-1.5 text-2xs font-medium",
                            reassignTo === c.activity_id ? "text-accent" : "text-content-2 hover:text-accent",
                          )}
                        >
                          {reassignTo === c.activity_id ? "✓ selected for reassignment" : "Reassign to this"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {historyQuery.data && historyQuery.data.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-content-2">
                <History className="h-3 w-3" /> Review history
              </p>
              <ul className="space-y-1">
                {historyQuery.data.map((h, i) => (
                  <li key={i} className="flex gap-2 text-2xs text-content-3">
                    <span className="tnum shrink-0 text-content-2">
                      {new Date(h.created_at).toLocaleString()}
                    </span>
                    <span className="font-medium text-content-1">{h.action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {canManage ? (
            <div className="space-y-2.5 border-t border-line pt-4">
              <Textarea
                rows={2}
                placeholder="Review note (optional) — kept in the audit trail"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => reviewMutation.mutate("confirm")} loading={reviewMutation.isPending}>
                  <Check className="h-4 w-4" />
                  Confirm
                </Button>
                <Button
                  variant="danger"
                  onClick={() => reviewMutation.mutate("reject")}
                  loading={reviewMutation.isPending}
                >
                  <X className="h-4 w-4" />
                  Reject
                </Button>
                <Button
                  variant="secondary"
                  disabled={!reassignTo}
                  onClick={() => reviewMutation.mutate("reassign")}
                  loading={reviewMutation.isPending}
                >
                  Reassign to selected
                </Button>
              </div>
              <p className="text-2xs text-content-2">
                Confirming books this line against the activity the next time matches are applied.
              </p>
            </div>
          ) : (
            <p className="border-t border-line pt-4 text-2xs text-content-3">
              Reviewing matches is a project-manager action. You're seeing this queue read-only.
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
