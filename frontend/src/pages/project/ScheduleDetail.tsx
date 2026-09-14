import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import clsx from "clsx";
import {
  AlertTriangle,
  ChevronRight,
  Layers,
  ChevronLeft,
  ClipboardCopy,
  Download,
  FileSpreadsheet,
  Filter,
  ListTree,
  Search,
  Table2,
} from "lucide-react";
import { useProjectId } from "@/context/ProjectContext";
import { schedulesApi } from "@/api/schedules";
import { activitiesApi } from "@/api/activities";
import { progressApi } from "@/api/progress";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Card, CardHeader, Input, PageHeader } from "@/components/ui/Primitives";
import { Dropdown, DropdownItem, DropdownLabel, DropdownSeparator, MultiSelectMenu } from "@/components/ui/Dropdown";
import { Badge, JobStatusBadge } from "@/components/common/Badge";
import { MetricTile } from "@/components/ui/Metric";
import type { ActivityProgressRollup, ActivityRead, ActivityTreeNode } from "@/types/api";

type RollupMap = Map<string, ActivityProgressRollup>;

export function ScheduleDetail() {
  const projectId = useProjectId();
  const { scheduleId } = useParams<{ scheduleId: string }>();
  const sid = scheduleId as string;
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<"tree" | "table">("tree");

  const scheduleQuery = useQuery({
    queryKey: ["schedule", projectId, sid],
    queryFn: () => schedulesApi.get(projectId, sid),
  });
  const treeQuery = useQuery({
    queryKey: ["activity-tree", sid],
    queryFn: () => activitiesApi.tree(sid),
  });
  const rollupQuery = useQuery({
    queryKey: ["progress-rollup", projectId, sid],
    queryFn: () => progressApi.rollup(projectId, sid),
  });

  const rollup: RollupMap = useMemo(
    () => new Map((rollupQuery.data ?? []).map((r) => [r.activity_id, r])),
    [rollupQuery.data],
  );

  const summary = scheduleQuery.data?.parse_summary ?? {};
  const dropped =
    Number(summary.dates_unparsed ?? 0) +
    Number(summary.predecessors_unresolved ?? 0) +
    Number(summary.rows_skipped_blank ?? 0);

  const counts = useMemo(() => {
    let total = 0;
    let delayed = 0;
    const walk = (nodes: ActivityTreeNode[]) => {
      for (const n of nodes) {
        total += 1;
        if (rollup.get(n.id)?.is_delayed) delayed += 1;
        walk(n.children);
      }
    };
    walk(treeQuery.data ?? []);
    return { total, delayed };
  }, [treeQuery.data, rollup]);

  if (scheduleQuery.isLoading) return <LoadingRows rows={5} />;
  if (scheduleQuery.error) return <ErrorState error={scheduleQuery.error} />;

  return (
    <div className="space-y-5">
      <PageHeader
        title={scheduleQuery.data?.name ?? "Schedule"}
        subtitle="Work breakdown from L1 down to the activities progress is booked against. Completion is quantity-weighted, so a large pour counts for more than a small one."
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <MetricTile label="Activities" value={counts.total} icon={<Layers className="h-4 w-4" />} />
        <MetricTile
          label="Delayed"
          value={counts.delayed}
          tone={counts.delayed ? "warning" : "positive"}
          delay={0.05}
        />
        <MetricTile label="Rows read" value={Number(summary.rows_read ?? 0)} delay={0.1} />
        <MetricTile
          label="Not imported"
          value={dropped}
          tone={dropped ? "warning" : "default"}
          hint={dropped ? "dates or dependencies dropped" : "everything parsed"}
          delay={0.15}
        />
      </div>

      {scheduleQuery.data && scheduleQuery.data.status !== "COMPLETED" && (
        <div className="flex items-center gap-2 rounded-[14px] border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          This import is <JobStatusBadge status={scheduleQuery.data.status} /> — the hierarchy below may be
          incomplete.
        </div>
      )}

      <Card>
        <CardHeader
          title={view === "tree" ? "Activity hierarchy" : "All activities"}
          subtitle={
            view === "tree"
              ? "Click an activity for its dependencies, progress history and risk"
              : "Every activity in the schedule, a page at a time"
          }
          icon={view === "tree" ? <ListTree className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
          action={
            <div className="flex items-center gap-2">
              {view === "tree" && (
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-2" />
                  <Input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Filter by code or name…"
                    className="w-56 pl-8"
                  />
                </div>
              )}
              <div className="flex rounded-[10px] border border-line bg-surface-raised p-0.5">
                {([
                  { id: "tree" as const, label: "Hierarchy", icon: ListTree },
                  { id: "table" as const, label: "Table", icon: Table2 },
                ]).map((opt) => {
                  const Icon = opt.icon;
                  return (
                    <button
                      key={opt.id}
                      onClick={() => setView(opt.id)}
                      className={clsx(
                        "flex items-center gap-1.5 rounded-[10px] px-2.5 py-1 text-2xs font-medium transition-colors",
                        view === opt.id ? "bg-surface-card text-content-1 shadow-card" : "text-content-3 hover:text-content-1",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          }
        />

        {view === "table" ? (
          <ActivityTable projectId={projectId} scheduleId={sid} rollup={rollup} />
        ) : (
        <>

        <div className="border-b border-line bg-surface-raised/60 px-4 py-1.5">
          <div className="flex items-center gap-3 text-2xs font-medium text-content-2">
            <span className="flex-1">Activity</span>
            <span className="hidden w-24 shrink-0 sm:block">Discipline</span>
            <span className="hidden w-32 shrink-0 md:block">Planned finish</span>
            <span className="w-28 shrink-0 text-right">Completion</span>
            <span className="w-20 shrink-0" />
          </div>
        </div>

        <div className="scroll-slim max-h-[62vh] overflow-y-auto p-1.5">
          {treeQuery.isLoading && <LoadingRows rows={6} />}
          {treeQuery.error && <ErrorState error={treeQuery.error} title="Could not load activities" />}
          {treeQuery.data?.length === 0 && (
            <EmptyState title="No activities parsed from this file" compact />
          )}
          {treeQuery.data?.map((node) => (
            <TreeRow
              key={node.id}
              node={node}
              projectId={projectId}
              scheduleId={sid}
              depth={0}
              rollup={rollup}
              filter={filter.trim().toLowerCase()}
            />
          ))}
        </div>
        </>
        )}
      </Card>
    </div>
  );
}

function matches(node: ActivityTreeNode, filter: string): boolean {
  if (!filter) return true;
  if (`${node.activity_code} ${node.name}`.toLowerCase().includes(filter)) return true;
  return node.children.some((c) => matches(c, filter));
}

function TreeRow({
  node,
  projectId,
  scheduleId,
  depth,
  rollup,
  filter,
}: {
  node: ActivityTreeNode;
  projectId: string;
  scheduleId: string;
  depth: number;
  rollup: RollupMap;
  filter: string;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  const prog = rollup.get(node.id);

  if (!matches(node, filter)) return null;
  // A filtered search is only useful if the matches are actually visible.
  const expanded = filter ? true : open;

  const pct = prog?.completion_percentage ?? 0;

  return (
    <div>
      <div
        className="group flex items-center gap-3 rounded-[10px] px-2.5 py-1.5 transition-colors hover:bg-surface-raised"
        style={{ paddingLeft: depth * 20 + 10 }}
      >
        {hasChildren ? (
          <button
            onClick={() => setOpen((o) => !o)}
            className="shrink-0 rounded p-0.5 text-content-2 transition-colors hover:bg-ink-200/60 hover:text-content-1"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            <ChevronRight className={clsx("h-3.5 w-3.5 transition-transform", expanded && "rotate-90")} />
          </button>
        ) : (
          <span className="w-[1.125rem] shrink-0" />
        )}

        <Link
          to={`/projects/${projectId}/activities/${scheduleId}/${node.id}`}
          className="flex min-w-0 flex-1 items-center gap-2"
        >
          <span
            className={clsx(
              "shrink-0 rounded px-1 py-0.5 font-mono text-2xs font-medium",
              node.level <= 2 ? "bg-ink-200/70 text-content-1" : "bg-surface-raised text-content-3",
            )}
          >
            L{node.level}
          </span>
          <span className="shrink-0 font-mono text-2xs text-content-2">{node.activity_code}</span>
          <span
            className={clsx(
              "truncate text-xs group-hover:text-accent",
              node.level <= 2 ? "font-medium text-content-1" : "text-content-1",
            )}
          >
            {node.name}
          </span>
        </Link>

        <span className="hidden w-24 shrink-0 truncate text-2xs text-content-2 sm:block">
          {node.discipline ?? "—"}
        </span>
        <span className="tnum hidden w-32 shrink-0 text-2xs text-content-3 md:block">
          {node.planned_finish ?? "—"}
        </span>

        <span className="flex w-28 shrink-0 items-center justify-end gap-2">
          <span className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-raised">
            <span
              className={clsx(
                "block h-full rounded-full",
                pct >= 100 ? "bg-teal-500" : pct > 0 ? "bg-signal-500" : "bg-ink-200",
              )}
              style={{ width: `${Math.max(pct, 2)}%` }}
            />
          </span>
          <span className="tnum w-9 text-right text-2xs font-medium text-content-1">{pct.toFixed(0)}%</span>
        </span>

        <span className="w-20 shrink-0 text-right">
          {prog?.is_delayed ? (
            <Badge tone="red">delayed</Badge>
          ) : prog?.status === "COMPLETED" ? (
            <Badge tone="green">done</Badge>
          ) : null}
        </span>
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeRow
              key={child.id}
              node={child}
              projectId={projectId}
              scheduleId={scheduleId}
              depth={depth + 1}
              rollup={rollup}
              filter={filter}
            />
          ))}
        </div>
      )}
    </div>
  );
}

type SortKey = "activity_code" | "name" | "level" | "discipline" | "planned_start" | "planned_finish";

const COLUMNS: Array<{ key: SortKey | null; label: string; className?: string }> = [
  { key: "activity_code", label: "Code", className: "w-28" },
  { key: "name", label: "Activity" },
  { key: "level", label: "Level", className: "w-16" },
  { key: "discipline", label: "Discipline", className: "w-32" },
  { key: "planned_start", label: "Planned start", className: "w-32" },
  { key: "planned_finish", label: "Planned finish", className: "w-32" },
  { key: null, label: "Quantity", className: "w-28" },
  { key: null, label: "Completion", className: "w-36" },
];

/**
 * The flat, paginated view of a schedule — the counterpart to the tree.
 *
 * Paging is genuinely server-side (the endpoint takes skip/limit and returns a
 * total), but it accepts no filter or ordering parameters, so sorting can only
 * ever apply to the rows currently loaded. The header says so rather than
 * implying the whole schedule was sorted.
 */
function ActivityTable({
  projectId,
  scheduleId,
  rollup,
}: {
  projectId: string;
  scheduleId: string;
  rollup: RollupMap;
}) {
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(50);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [levels, setLevels] = useState<string[]>([]);
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "activity_code",
    dir: "asc",
  });

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["activities-page", scheduleId, page, limit],
    queryFn: () => activitiesApi.list(scheduleId, { skip: page * limit, limit }),
    placeholderData: (prev) => prev,
  });

  const rows = useMemo(() => {
    let items = [...(data?.items ?? [])];
    if (disciplines.length) items = items.filter((a) => a.discipline && disciplines.includes(a.discipline));
    if (levels.length) items = items.filter((a) => levels.includes(String(a.level)));
    const { key, dir } = sort;
    items.sort((a, b) => {
      const av = a[key] ?? "";
      const bv = b[key] ?? "";
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv), undefined, { numeric: true });
      return dir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [data, sort, disciplines, levels]);

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const from = total === 0 ? 0 : page * limit + 1;
  const to = Math.min(total, page * limit + (data?.items.length ?? 0));

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));

  if (isLoading) return <div className="p-4"><LoadingRows rows={8} /></div>;
  if (error) return <div className="p-4"><ErrorState error={error} onRetry={() => refetch()} /></div>;
  if (total === 0) {
    return <div className="p-4"><EmptyState title="No activities in this schedule" compact /></div>;
  }

  const disciplineOptions = Array.from(
    new Set((data?.items ?? []).map((a) => a.discipline).filter(Boolean) as string[]),
  ).sort();
  const levelOptions = Array.from(new Set((data?.items ?? []).map((a) => String(a.level)))).sort();
  const filtered = disciplines.length > 0 || levels.length > 0;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-raised/50 px-3 py-2">
        <MultiSelectMenu
          label="Discipline"
          icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
          selected={disciplines}
          onChange={setDisciplines}
          options={disciplineOptions.map((d) => ({ value: d, label: d.replaceAll("_", " ").toLowerCase() }))}
        />
        <MultiSelectMenu
          label="Level"
          width="w-40"
          selected={levels}
          onChange={setLevels}
          options={levelOptions.map((l) => ({ value: l, label: `L${l}` }))}
        />
        {filtered && (
          <button
            onClick={() => {
              setDisciplines([]);
              setLevels([]);
            }}
            className="text-2xs font-medium text-accent hover:underline"
          >
            Clear filters
          </button>
        )}
        <Dropdown
          className="ml-auto"
          icon={<Download className="h-3.5 w-3.5 text-content-2" />}
          label="Export"
          align="right"
          width="w-60"
        >
          {(close) => (
            <>
              <DropdownLabel>This page ({rows.length} rows)</DropdownLabel>
              <DropdownItem
                icon={<FileSpreadsheet className="h-3.5 w-3.5" />}
                onSelect={() => {
                  exportCsv(rows, rollup);
                  close();
                }}
              >
                Download as CSV
              </DropdownItem>
              <DropdownItem
                icon={<ClipboardCopy className="h-3.5 w-3.5" />}
                onSelect={() => {
                  void navigator.clipboard?.writeText(toTsv(rows, rollup));
                  close();
                }}
              >
                Copy for spreadsheet
              </DropdownItem>
              <DropdownSeparator />
              <DropdownLabel>Row height</DropdownLabel>
              {(["comfortable", "compact"] as const).map((d) => (
                <DropdownItem
                  key={d}
                  selected={density === d}
                  onSelect={() => {
                    setDensity(d);
                    close();
                  }}
                >
                  {d === "comfortable" ? "Comfortable" : "Compact"}
                </DropdownItem>
              ))}
            </>
          )}
        </Dropdown>

        <span className="text-2xs text-content-2">
          {filtered
            ? `${rows.length} of ${data?.items.length ?? 0} rows on this page`
            : "filters and sorting apply to the loaded page"}
        </span>
      </div>

      <div className="scroll-slim max-h-[62vh] overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 bg-surface-raised/95 backdrop-blur">
            <tr className="border-b border-line text-2xs text-content-2">
              {COLUMNS.map((col) => (
                <th key={col.label} className={clsx("px-3 py-2 font-medium", col.className)}>
                  {col.key ? (
                    <button
                      onClick={() => toggleSort(col.key as SortKey)}
                      className="inline-flex items-center gap-1 transition-colors hover:text-content-1"
                    >
                      {col.label}
                      {sort.key === col.key && (
                        <ChevronRight
                          className={clsx("h-3 w-3", sort.dir === "asc" ? "-rotate-90" : "rotate-90")}
                        />
                      )}
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-xs text-content-2">
                  No activity on this page matches the filters.
                </td>
              </tr>
            )}
            {rows.map((a) => {
              const prog = rollup.get(a.id);
              const pct = prog?.completion_percentage ?? 0;
              return (
                <tr key={a.id} className={clsx("group transition-colors hover:bg-signal-500/[0.06]", density === "compact" ? "[&>td]:py-1" : "")}>
                  <td className="px-3 py-2">
                    <Link
                      to={`/projects/${projectId}/activities/${scheduleId}/${a.id}`}
                      className="font-mono text-2xs text-accent hover:underline"
                    >
                      {a.activity_code}
                    </Link>
                  </td>
                  <td className="max-w-xs px-3 py-2">
                    <Link
                      to={`/projects/${projectId}/activities/${scheduleId}/${a.id}`}
                      className="block truncate text-xs text-content-1 hover:text-accent"
                    >
                      {a.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-surface-raised px-1 py-0.5 font-mono text-2xs text-content-2">
                      L{a.level}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-2xs text-content-3">{a.discipline ?? "—"}</td>
                  <td className="tnum px-3 py-2 text-2xs text-content-2">{a.planned_start ?? "—"}</td>
                  <td className="tnum px-3 py-2 text-2xs text-content-2">{a.planned_finish ?? "—"}</td>
                  <td className="tnum px-3 py-2 text-2xs text-content-2">
                    {a.budgeted_quantity != null ? `${a.budgeted_quantity} ${a.uom ?? ""}` : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-raised">
                        <span
                          className={clsx(
                            "block h-full rounded-full",
                            pct >= 100 ? "bg-teal-500" : pct > 0 ? "bg-signal-500" : "bg-ink-200",
                          )}
                          style={{ width: `${Math.max(pct, 2)}%` }}
                        />
                      </span>
                      <span className="tnum w-9 text-2xs font-medium text-content-1">{pct.toFixed(0)}%</span>
                      {prog?.is_delayed && <Badge tone="red">late</Badge>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-2.5">
        <p className="text-2xs text-content-3">
          Showing <span className="tnum font-medium text-content-1">{from}–{to}</span> of{" "}
          <span className="tnum font-medium text-content-1">{total}</span>
          {isFetching && <span className="ml-2 text-content-2">updating…</span>}
          <span className="ml-2 text-content-2">· sorting applies to this page</span>
        </p>

        <div className="flex items-center gap-2">
          <select
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value));
              setPage(0);
            }}
            className="rounded-[10px] border border-line bg-surface-card px-2 py-1 text-2xs text-content-1"
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n} per page
              </option>
            ))}
          </select>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-[10px] border border-line p-1 text-content-2 transition-colors hover:bg-surface-raised disabled:opacity-40"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="tnum text-2xs text-content-2">
            {page + 1} / {pageCount}
          </span>
          <button
            onClick={() => setPage((p) => (p + 1 < pageCount ? p + 1 : p))}
            disabled={page + 1 >= pageCount}
            className="rounded-[10px] border border-line p-1 text-content-2 transition-colors hover:bg-surface-raised disabled:opacity-40"
            aria-label="Next page"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}


/** Rows currently on screen, as the user sees them (filters and sort applied). */
function tableRows(rows: ActivityRead[], rollup: RollupMap) {
  return rows.map((a) => {
    const prog = rollup.get(a.id);
    return [
      a.activity_code,
      a.name,
      `L${a.level}`,
      a.wbs_path,
      a.discipline ?? "",
      a.planned_start ?? "",
      a.planned_finish ?? "",
      a.budgeted_quantity != null ? String(a.budgeted_quantity) : "",
      a.uom ?? "",
      (prog?.completion_percentage ?? 0).toFixed(1),
      prog?.is_delayed ? "delayed" : "",
    ];
  });
}

const EXPORT_HEADERS = [
  "Activity code", "Name", "Level", "WBS", "Discipline",
  "Planned start", "Planned finish", "Quantity", "UOM", "Completion %", "Flag",
];

function toTsv(rows: ActivityRead[], rollup: RollupMap) {
  return [EXPORT_HEADERS, ...tableRows(rows, rollup)].map((r) => r.join("\t")).join("\n");
}

function exportCsv(rows: ActivityRead[], rollup: RollupMap) {
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v);
  const csv = [EXPORT_HEADERS, ...tableRows(rows, rollup)]
    .map((r) => r.map(esc).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `activities-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
