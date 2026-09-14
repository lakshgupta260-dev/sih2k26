import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Braces,
  Copy,
  Download,
  FileBarChart,
  FileSpreadsheet,
  FileText,
  Filter,
  MoreVertical,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { useProjectId } from "@/context/ProjectContext";
import { generatedReportsApi } from "@/api/generatedReports";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { JobStatusBadge } from "@/components/common/Badge";
import { Button, Card, CardHeader, Field, Input, Modal, PageHeader } from "@/components/ui/Primitives";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import type {
  GeneratedReportFormat,
  GeneratedReportRead,
  GeneratedReportStatus,
} from "@/types/api";

type ReportTypeKey = "executive_overview" | "monthly_progress" | "delay_risk";

const REPORT_TYPES: {
  value: ReportTypeKey;
  label: string;
  blurb: string;
  icon: JSX.Element;
}[] = [
  {
    value: "executive_overview",
    label: "Executive overview",
    blurb: "Headline progress, variance and the worst delay risks — for a sponsor review.",
    icon: <Sparkles className="h-3.5 w-3.5" />,
  },
  {
    value: "monthly_progress",
    label: "Monthly progress",
    blurb: "Planned versus actual across the WBS for the reporting period.",
    icon: <TrendingUp className="h-3.5 w-3.5" />,
  },
  {
    value: "delay_risk",
    label: "Delay & risk",
    blurb: "Every forecast late finish with its drivers, worst first.",
    icon: <ShieldAlert className="h-3.5 w-3.5" />,
  },
];

const STATUS_OPTIONS: { value: GeneratedReportStatus; label: string }[] = [
  { value: "PENDING", label: "Pending" },
  { value: "GENERATING", label: "Generating" },
  { value: "COMPLETED", label: "Completed" },
  { value: "FAILED", label: "Failed" },
];

export function Reports() {
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [reportType, setReportType] = useState<ReportTypeKey>(REPORT_TYPES[0].value);
  const [format, setFormat] = useState<GeneratedReportFormat>("PDF");
  const [asOf, setAsOf] = useState("");
  const [downloading, setDownloading] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [formatFilter, setFormatFilter] = useState<GeneratedReportFormat[]>([]);
  const [statusFilter, setStatusFilter] = useState<GeneratedReportStatus[]>([]);
  const [snapshotOf, setSnapshotOf] = useState<GeneratedReportRead | null>(null);

  const listQuery = useQuery({
    queryKey: ["generated-reports", projectId],
    queryFn: () => generatedReportsApi.list(projectId, { limit: 50 }),
    // Generation can be asynchronous — keep polling only while something is in flight.
    refetchInterval: (q) =>
      q.state.data?.items.some((r) => r.status === "PENDING" || r.status === "GENERATING") ? 2500 : false,
  });

  const requestMutation = useMutation({
    mutationFn: (override?: { report_type: string; output_format: GeneratedReportFormat; as_of: string | null }) =>
      generatedReportsApi.request(
        projectId,
        override ?? {
          report_type: reportType,
          output_format: format,
          as_of: asOf || null,
        },
      ),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["generated-reports", projectId] });
      toast.success(
        "Report requested",
        report.status === "COMPLETED"
          ? "Ready to download."
          : "Generating in the background — the row updates when it's ready.",
      );
    },
    onError: (err) =>
      toast.error("Could not request report", err instanceof ApiError ? err.message : undefined),
  });

  const download = async (reportId: string, filename: string | null) => {
    setDownloading(reportId);
    try {
      const res = await generatedReportsApi.download(projectId, reportId);
      // Axios types a header value as string | number | boolean | string[] | AxiosHeaders.
      const contentType = res.headers["content-type"];
      const blob = new Blob([res.data], {
        type: typeof contentType === "string" ? contentType : "application/octet-stream",
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename ?? "plan2progress-report";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Download started", filename ?? undefined);
    } catch (err) {
      toast.error("Download failed", err instanceof ApiError ? err.message : undefined);
    } finally {
      setDownloading(null);
    }
  };

  const selected = REPORT_TYPES.find((t) => t.value === reportType);

  const history = useMemo(
    () =>
      (listQuery.data?.items ?? []).filter(
        (r) =>
          (typeFilter.length === 0 || typeFilter.includes(r.report_type)) &&
          (formatFilter.length === 0 || formatFilter.includes(r.output_format)) &&
          (statusFilter.length === 0 || statusFilter.includes(r.status)),
      ),
    [listQuery.data, typeFilter, formatFilter, statusFilter],
  );

  // Every type that has actually been generated, so the filter can't offer a
  // value with no rows behind it.
  const typeOptions = useMemo(() => {
    const seen = new Set((listQuery.data?.items ?? []).map((r) => r.report_type));
    return [...seen].sort().map((t) => ({ value: t, label: t.replaceAll("_", " ") }));
  }, [listQuery.data]);

  const copy = (text: string, what: string) =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(`${what} copied`, text))
      .catch(() => toast.error("Could not copy to clipboard"));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Generated reports"
        subtitle="PDF and Excel artifacts built by the backend from this project's real data — the same figures shown on the dashboard, not a separate calculation."
      />

      <Card>
        <CardHeader
          title="Request a report"
          subtitle={selected?.blurb}
          icon={<Sparkles className="h-4 w-4" />}
        />
        <form
          className="grid grid-cols-1 items-end gap-4 p-4 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            requestMutation.mutate();
          }}
        >
          <Field label="Report type">
            <SelectMenu<ReportTypeKey>
              value={reportType}
              width="w-72"
              options={REPORT_TYPES.map((t) => ({ value: t.value, label: t.label, icon: t.icon }))}
              onChange={(v) => v && setReportType(v)}
            />
          </Field>
          <Field label="Format">
            <SelectMenu<GeneratedReportFormat>
              value={format}
              width="w-52"
              options={[
                { value: "PDF", label: "PDF", icon: <FileText className="h-3.5 w-3.5" /> },
                {
                  value: "XLSX",
                  label: "Excel (.xlsx)",
                  icon: <FileSpreadsheet className="h-3.5 w-3.5" />,
                },
              ]}
              onChange={(v) => v && setFormat(v)}
            />
          </Field>
          <Field label="As of" hint="Defaults to today">
            <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </Field>
          <Button type="submit" variant="signal" loading={requestMutation.isPending}>
            <FileBarChart className="h-4 w-4" />
            Generate
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="Report history"
          subtitle="Newest first"
          action={
            listQuery.data ? (
              <span className="text-2xs text-content-3">
                {history.length}/{listQuery.data.total}
              </span>
            ) : undefined
          }
        />

        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-base/50 px-3 py-2">
          <MultiSelectMenu
            label="Type"
            icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
            options={typeOptions}
            selected={typeFilter}
            onChange={setTypeFilter}
          />
          <MultiSelectMenu<GeneratedReportFormat>
            label="Format"
            width="w-44"
            options={[
              { value: "PDF", label: "PDF" },
              { value: "XLSX", label: "XLSX" },
            ]}
            selected={formatFilter}
            onChange={setFormatFilter}
          />
          <MultiSelectMenu<GeneratedReportStatus>
            label="Status"
            width="w-44"
            options={STATUS_OPTIONS}
            selected={statusFilter}
            onChange={setStatusFilter}
          />
          {(typeFilter.length || formatFilter.length || statusFilter.length) > 0 && (
            <button
              type="button"
              onClick={() => {
                setTypeFilter([]);
                setFormatFilter([]);
                setStatusFilter([]);
              }}
              className="text-2xs font-medium text-accent hover:underline"
            >
              Reset
            </button>
          )}
        </div>

        <div className="p-3">
          {listQuery.isLoading && <LoadingRows />}
          {listQuery.error && <ErrorState error={listQuery.error} onRetry={() => listQuery.refetch()} />}
          {listQuery.data?.items.length === 0 && (
            <EmptyState
              icon={<FileBarChart className="h-5 w-5" />}
              title="No reports generated yet"
              description="Request one above — it's built from live project data at the moment you ask for it."
              compact
            />
          )}
          {listQuery.data && listQuery.data.items.length > 0 && history.length === 0 && (
            <EmptyState
              icon={<Filter className="h-5 w-5" />}
              title="No report matches these filters"
              description="Reset the type, format or status filter."
              compact
            />
          )}
          {history.length > 0 && (
            <ul className="space-y-1.5">
              {history.map((r) => (
                <li
                  key={r.id}
                  className="flex flex-wrap items-center gap-3 rounded-[10px] border border-line px-3 py-2.5 transition-colors hover:border-signal-500/40"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-ink-950 text-accent">
                    {r.output_format === "PDF" ? (
                      <FileText className="h-4 w-4" />
                    ) : (
                      <FileSpreadsheet className="h-4 w-4" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-content-1">
                      {r.report_type.replaceAll("_", " ")}
                    </p>
                    <p className="mt-0.5 font-mono text-2xs text-content-2">
                      {r.output_format}
                      {r.size_bytes ? ` · ${(r.size_bytes / 1024).toFixed(0)} KB` : ""} ·{" "}
                      {new Date(r.created_at).toLocaleString()}
                    </p>
                    {r.status === "FAILED" && r.error_message && (
                      <p className="mt-0.5 text-2xs text-rose-600">{r.error_message}</p>
                    )}
                  </div>
                  <JobStatusBadge status={r.status} />
                  {r.status === "COMPLETED" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={downloading === r.id}
                      onClick={() => download(r.id, r.filename)}
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download
                    </Button>
                  )}
                  <Dropdown
                    variant="ghost"
                    align="right"
                    width="w-60"
                    title="Report actions"
                    label={<span className="sr-only">Report actions</span>}
                    icon={<MoreVertical className="h-4 w-4" />}
                    className="[&>button>svg:last-child]:hidden"
                  >
                    {(close) => (
                      <>
                        <DropdownLabel>{r.report_type.replaceAll("_", " ")}</DropdownLabel>
                        <DropdownItem
                          icon={<Download className="h-3.5 w-3.5" />}
                          disabled={r.status !== "COMPLETED"}
                          onSelect={() => {
                            close();
                            download(r.id, r.filename);
                          }}
                        >
                          Download file
                        </DropdownItem>
                        <DropdownItem
                          icon={<RefreshCw className="h-3.5 w-3.5" />}
                          onSelect={() => {
                            close();
                            requestMutation.mutate({
                              report_type: r.report_type,
                              output_format: r.output_format,
                              as_of:
                                typeof r.parameters?.as_of === "string"
                                  ? (r.parameters.as_of as string)
                                  : null,
                            });
                          }}
                        >
                          Regenerate with same settings
                        </DropdownItem>
                        <DropdownItem
                          icon={<Braces className="h-3.5 w-3.5" />}
                          onSelect={() => {
                            setSnapshotOf(r);
                            close();
                          }}
                        >
                          Inspect data snapshot
                        </DropdownItem>
                        <DropdownSeparator />
                        <DropdownItem
                          icon={<Copy className="h-3.5 w-3.5" />}
                          disabled={!r.filename}
                          onSelect={() => {
                            if (r.filename) copy(r.filename, "Filename");
                            close();
                          }}
                        >
                          Copy filename
                        </DropdownItem>
                        <DropdownItem
                          icon={<Copy className="h-3.5 w-3.5" />}
                          onSelect={() => {
                            copy(r.id, "Report id");
                            close();
                          }}
                        >
                          Copy report id
                        </DropdownItem>
                      </>
                    )}
                  </Dropdown>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {/* The snapshot is the exact figure set the backend froze into the file. */}
      <Modal
        open={!!snapshotOf}
        onClose={() => setSnapshotOf(null)}
        size="lg"
        title="Data snapshot"
        subtitle={
          snapshotOf
            ? `${snapshotOf.report_type.replaceAll("_", " ")} · generated ${
                snapshotOf.generated_at
                  ? new Date(snapshotOf.generated_at).toLocaleString()
                  : "not yet"
              }`
            : undefined
        }
      >
        <pre className="scroll-slim max-h-[60vh] overflow-auto rounded-[10px] bg-ink-950 p-3 font-mono text-2xs leading-relaxed text-paper-100">
          {snapshotOf ? JSON.stringify({ parameters: snapshotOf.parameters, snapshot: snapshotOf.snapshot }, null, 2) : ""}
        </pre>
      </Modal>
    </div>
  );
}
