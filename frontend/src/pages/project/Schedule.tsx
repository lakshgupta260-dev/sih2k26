import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpDown,
  CalendarRange,
  Copy,
  FileSpreadsheet,
  Filter,
  Layers,
  MoreVertical,
  Target,
  Upload as UploadIcon,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { useSchedules } from "@/hooks/useSchedules";
import { schedulesApi } from "@/api/schedules";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { JobStatusBadge } from "@/components/common/Badge";
import {
  Button,
  Card,
  Field,
  Input,
  Modal,
  PageHeader,
  ProgressBarInline,
} from "@/components/ui/Primitives";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import type { JobStatus, ScheduleColumnMapping, ScheduleRead } from "@/types/api";

const MAPPING_FIELDS: Array<{
  key: keyof ScheduleColumnMapping;
  label: string;
  placeholder: string;
  required?: boolean;
}> = [
  { key: "activity_code", label: "Activity ID / code", placeholder: "Activity ID", required: true },
  { key: "name", label: "Activity name", placeholder: "Activity Name", required: true },
  { key: "wbs_path", label: "WBS path", placeholder: "WBS" },
  { key: "level", label: "Level (L1–L6)", placeholder: "Level" },
  { key: "discipline", label: "Discipline", placeholder: "Discipline" },
  { key: "planned_start", label: "Planned start", placeholder: "Start" },
  { key: "planned_finish", label: "Planned finish", placeholder: "Finish" },
  { key: "budgeted_quantity", label: "Budgeted quantity", placeholder: "Qty" },
  { key: "uom", label: "Unit of measure", placeholder: "UOM" },
  { key: "predecessors", label: "Predecessors (inline)", placeholder: "Predecessors" },
];

export function Schedule() {
  const projectId = useProjectId();
  const { canManage, selectedSchedule, selectSchedule } = useProject();
  const { data, isLoading, error, refetch } = useSchedules(projectId);
  const toast = useToast();
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<JobStatus[]>([]);
  const [order, setOrder] = useState<"newest" | "oldest" | "name">("newest");
  const [importReport, setImportReport] = useState<ScheduleRead | null>(null);

  const schedules = useMemo(() => {
    const rows = (data ?? []).filter(
      (s) => statusFilter.length === 0 || statusFilter.includes(s.status),
    );
    return [...rows].sort((a, b) =>
      order === "name"
        ? a.name.localeCompare(b.name)
        : order === "oldest"
          ? a.created_at.localeCompare(b.created_at)
          : b.created_at.localeCompare(a.created_at),
    );
  }, [data, statusFilter, order]);

  return (
    <div>
      <PageHeader
        title="Baseline schedules"
        subtitle="The planned side of the equation — L1–L6 activity hierarchies imported from Primavera P6 or MS Project exports."
        actions={
          canManage && (
            <Button onClick={() => setUploadOpen(true)}>
              <UploadIcon className="h-4 w-4" />
              Upload schedule
            </Button>
          )
        }
      />

      {data && data.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 border-y border-line py-2.5">
          <MultiSelectMenu<JobStatus>
            label="Import status"
            icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
            width="w-52"
            options={[
              { value: "PENDING", label: "Pending" },
              { value: "PROCESSING", label: "Processing" },
              { value: "COMPLETED", label: "Completed" },
              { value: "FAILED", label: "Failed" },
            ]}
            selected={statusFilter}
            onChange={setStatusFilter}
          />
          <SelectMenu<"newest" | "oldest" | "name">
            prefix="Sort"
            icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
            value={order}
            width="w-48"
            options={[
              { value: "newest", label: "Newest upload" },
              { value: "oldest", label: "Oldest upload" },
              { value: "name", label: "Name (A→Z)" },
            ]}
            onChange={(v) => v && setOrder(v)}
          />
          <span className="ml-auto text-2xs text-content-3">
            {schedules.length}/{data.length} · active&nbsp;
            <span className="text-accent">{selectedSchedule?.name ?? "none"}</span>
          </span>
        </div>
      )}

      {isLoading && <LoadingRows rows={3} />}
      {error && <ErrorState error={error} onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <EmptyState
          icon={<CalendarRange className="h-5 w-5" />}
          title="No baseline uploaded"
          description={
            canManage
              ? "Upload an Excel or CSV export of the programme. You'll map your column headers to our fields, so no particular layout is required."
              : "The project manager hasn't uploaded a baseline schedule yet."
          }
          action={
            canManage && (
              <Button onClick={() => setUploadOpen(true)}>
                <UploadIcon className="h-4 w-4" />
                Upload schedule
              </Button>
            )
          }
        />
      )}

      {data && data.length > 0 && schedules.length === 0 && (
        <EmptyState
          icon={<Filter className="h-5 w-5" />}
          title="No baseline matches this filter"
          description="Clear the import-status filter to see every upload."
          compact
        />
      )}

      {schedules.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {schedules.map((s, i) => {
            const summary = s.parse_summary ?? {};
            const created = Number(summary.activities_created ?? 0);
            const rows = Number(summary.rows_read ?? 0);
            const warnings = Array.isArray(summary.warnings) ? summary.warnings.length : 0;
            const dropped =
              Number(summary.dates_unparsed ?? 0) +
              Number(summary.predecessors_unresolved ?? 0) +
              Number(summary.rows_skipped_blank ?? 0);

            return (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.05 }}
              >
                <Card interactive className="group relative h-full p-5">
                  <div className="absolute right-2.5 top-2.5 z-10">
                    <Dropdown
                      variant="ghost"
                      align="right"
                      width="w-60"
                      title={`Actions for ${s.name}`}
                      label={<span className="sr-only">Baseline actions</span>}
                      icon={<MoreVertical className="h-4 w-4" />}
                      className="[&>button>svg:last-child]:hidden"
                    >
                      {(close) => (
                        <>
                          <DropdownLabel>{s.name}</DropdownLabel>
                          <DropdownItem
                            icon={<Layers className="h-3.5 w-3.5" />}
                            onSelect={() => {
                              close();
                              navigate(`/projects/${projectId}/schedule/${s.id}`);
                            }}
                          >
                            Open hierarchy
                          </DropdownItem>
                          <DropdownItem
                            icon={<Target className="h-3.5 w-3.5" />}
                            selected={selectedSchedule?.id === s.id}
                            disabled={s.status !== "COMPLETED"}
                            onSelect={() => {
                              close();
                              selectSchedule(s.id);
                              toast.success(
                                "Active baseline switched",
                                `Dashboards now read from “${s.name}”.`,
                              );
                            }}
                          >
                            Use as active baseline
                          </DropdownItem>
                          <DropdownItem
                            icon={<AlertTriangle className="h-3.5 w-3.5" />}
                            onSelect={() => {
                              setImportReport(s);
                              close();
                            }}
                          >
                            Import report
                          </DropdownItem>
                          <DropdownSeparator />
                          <DropdownItem
                            icon={<Copy className="h-3.5 w-3.5" />}
                            onSelect={() => {
                              navigator.clipboard
                                ?.writeText(s.id)
                                .then(() => toast.success("Schedule id copied", s.id))
                                .catch(() => toast.error("Could not copy to clipboard"));
                              close();
                            }}
                          >
                            Copy schedule id
                          </DropdownItem>
                        </>
                      )}
                    </Dropdown>
                  </div>

                  <Link to={s.id} className="block h-full">
                    <div className="flex items-start justify-between gap-3 pr-8">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-ink-950 text-accent">
                          <Layers className="h-4 w-4" />
                        </span>
                        <div className="min-w-0">
                          <h3 className="truncate font-display text-[0.95rem] font-semibold tracking-[-0.01em] text-content-1">
                            {s.name}
                          </h3>
                          <p className="mt-0.5 font-mono text-2xs text-content-2">
                            Uploaded {new Date(s.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <JobStatusBadge status={s.status} />
                      {selectedSchedule?.id === s.id && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-signal-500/12 px-1.5 py-0.5 font-mono text-2xs font-medium uppercase tracking-wide text-accent ring-1 ring-inset ring-signal-500/35">
                          <Target className="h-3 w-3" />
                          active baseline
                        </span>
                      )}
                    </div>

                    {s.description && (
                      <p className="mt-3 line-clamp-2 text-xs text-content-3">{s.description}</p>
                    )}

                    <div className="mt-4 grid grid-cols-3 gap-2">
                      <Stat label="Activities" value={created} />
                      <Stat label="Rows read" value={rows} />
                      <Stat label="Not imported" value={dropped} tone={dropped ? "warn" : undefined} />
                    </div>

                    {(dropped > 0 || warnings > 0) && (
                      <p className="mt-3 flex items-start gap-1.5 rounded-[10px] bg-amber-50 p-2 text-2xs leading-relaxed text-amber-800">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                        The import states exactly what it could not use — open the schedule to see which
                        rows, dates or dependencies were dropped.
                      </p>
                    )}

                    <p className="mt-3 flex items-center gap-1 text-2xs font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
                      Open hierarchy <ArrowRight className="h-3 w-3" />
                    </p>
                  </Link>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Verbatim parse summary from the importer — what it read, created and
          could not use. Nothing here is recomputed on the client. */}
      <Modal
        open={!!importReport}
        onClose={() => setImportReport(null)}
        size="lg"
        title="Import report"
        subtitle={importReport?.name}
      >
        {importReport && Object.keys(importReport.parse_summary ?? {}).length === 0 ? (
          <p className="text-sm text-content-3">
            This upload recorded no parse summary — it either failed before parsing or predates
            summary capture.
          </p>
        ) : (
          <dl className="divide-y divide-line">
            {Object.entries(importReport?.parse_summary ?? {}).map(([k, v]) => (
              <div key={k} className="grid grid-cols-3 gap-3 py-2">
                <dt className="text-2xs text-content-3">
                  {k.replaceAll("_", " ")}
                </dt>
                <dd className="col-span-2 whitespace-pre-wrap break-words font-mono text-xs text-content-1">
                  {Array.isArray(v)
                    ? v.length === 0
                      ? "none"
                      : v.map(String).join("\n")
                    : String(v)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </Modal>

      <UploadScheduleModal open={uploadOpen} onClose={() => setUploadOpen(false)} projectId={projectId} />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "warn" }) {
  return (
    <div className="rounded-[10px] bg-surface-raised px-2.5 py-2">
      <p className={`tnum text-base font-semibold ${tone === "warn" ? "text-amber-700" : "text-content-1"}`}>
        {value}
      </p>
      <p className="mt-0.5 text-2xs text-content-3">{label}</p>
    </div>
  );
}

const ALLOWED = [".csv", ".xls", ".xlsx", ".xlsm"];

function UploadScheduleModal({
  open,
  onClose,
  projectId,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [progress, setProgress] = useState(0);
  const [fileError, setFileError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setName("");
    setMapping({});
    setProgress(0);
    setFileError(null);
  };

  const pickFile = (picked: File | null) => {
    setFileError(null);
    if (!picked) return setFile(null);
    const ext = picked.name.slice(picked.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setFileError(`A schedule must be one of ${ALLOWED.join(", ")} — got ${ext || "no extension"}.`);
      setFile(null);
      return;
    }
    setFile(picked);
    if (!name) setName(picked.name.replace(/\.[^.]+$/, ""));
  };

  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file first.");
      const cleaned: Record<string, string> = {
        activity_code: mapping.activity_code ?? "",
        name: mapping.name ?? "",
      };
      for (const f of MAPPING_FIELDS) {
        if (f.key !== "activity_code" && f.key !== "name" && mapping[f.key]) {
          cleaned[f.key] = mapping[f.key];
        }
      }
      return schedulesApi.upload(
        projectId,
        file,
        name || file.name,
        cleaned as unknown as ScheduleColumnMapping,
        setProgress,
      );
    },
    onSuccess: (schedule) => {
      queryClient.invalidateQueries({ queryKey: ["schedules", projectId] });
      const created = Number(schedule.parse_summary?.activities_created ?? 0);
      toast.success(
        `Imported ${created} activities`,
        `“${schedule.name}” parsed with status ${schedule.status}.`,
      );
      reset();
      onClose();
    },
    onError: (err) => {
      setProgress(0);
      toast.error(
        "Schedule import failed",
        err instanceof ApiError
          ? err.code === "INVALID_COLUMN_MAPPING"
            ? "The column mapping doesn't match the file's headers. Check the exact header spellings."
            : err.message
          : undefined,
      );
    },
  });

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Upload a baseline schedule"
      subtitle="Real schedules never share a column layout, so you tell us which of your columns holds each field."
      size="lg"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
        className="space-y-4"
      >
        <Field label="Schedule name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Baseline Rev 0" />
        </Field>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-content-2">Programme file</label>
          <label
            className={`flex cursor-pointer items-center gap-3 rounded-[14px] border-2 border-dashed p-4 transition-colors ${
              file ? "border-signal-500/40 bg-signal-600/25/40" : "border-line hover:border-line-strong hover:bg-surface-raised"
            }`}
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-surface-card text-content-3 shadow-card">
              <FileSpreadsheet className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-content-1">
                {file ? file.name : "Choose an Excel or CSV export"}
              </span>
              <span className="block text-2xs text-content-3">
                {file ? `${(file.size / 1024).toFixed(0)} KB` : ALLOWED.join(" · ")}
              </span>
            </span>
            <input
              type="file"
              accept={ALLOWED.join(",")}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {fileError && <p className="mt-1 text-2xs font-medium text-rose-600">{fileError}</p>}
        </div>

        <div className="rounded-[14px] border border-line bg-surface-raised/60 p-3">
          <p className="mb-2.5 text-2xs font-medium text-content-3">
            Column mapping · our field → your header
          </p>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {MAPPING_FIELDS.map((f) => (
              <Field key={f.key} label={f.required ? `${f.label} *` : f.label}>
                <Input
                  placeholder={f.placeholder}
                  value={mapping[f.key] ?? ""}
                  onChange={(e) => setMapping((m) => ({ ...m, [f.key]: e.target.value }))}
                  required={f.required}
                />
              </Field>
            ))}
          </div>
        </div>

        {mutation.isPending && <ProgressBarInline value={progress} label={`Uploading… ${progress}%`} />}

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={!file} loading={mutation.isPending}>
            Import schedule
          </Button>
        </div>
      </form>
    </Modal>
  );
}
