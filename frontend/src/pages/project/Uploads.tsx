import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowUpDown,
  ChevronDown,
  Copy,
  FileText,
  FileUp,
  Filter,
  Inbox,
  Info,
  MessageSquare,
  MoreVertical,
  PhoneCall,
  ScanLine,
  Upload as UploadIcon,
} from "lucide-react";
import { useProjectId } from "@/context/ProjectContext";
import { documentsApi } from "@/api/documents";
import { reportsApi } from "@/api/reports";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Badge, JobStatusBadge } from "@/components/common/Badge";
import {
  Button,
  Card,
  CardHeader,
  Modal,
  PageHeader,
  ProgressBarInline,
  Select,
} from "@/components/ui/Primitives";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import type {
  Discipline,
  DocumentType,
  JobStatus,
  ProgressReportRead,
  UploadedFileRead,
} from "@/types/api";

const DOC_TYPES: DocumentType[] = [
  "DAILY_PROGRESS_REPORT",
  "SITE_DIARY",
  "DISCIPLINE_SHEET",
  "SCHEDULE",
  "OTHER",
];

const DOC_TYPE_OPTIONS = DOC_TYPES.map((t) => ({
  value: t,
  label: t.replaceAll("_", " ").toLowerCase(),
}));

type SourceKey = "WHATSAPP" | "VOICE" | "UPLOAD";

const SOURCE_OPTIONS: { value: SourceKey; label: string }[] = [
  { value: "UPLOAD", label: "Uploaded file" },
  { value: "WHATSAPP", label: "WhatsApp" },
  { value: "VOICE", label: "Voice call" },
];

type FileSort = "newest" | "oldest" | "largest" | "name";

const FILE_SORTS: { value: FileSort; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "largest", label: "Largest first" },
  { value: "name", label: "Filename (A→Z)" },
];

/** Where a file came from, inferred from the name the ingest path gives it. */
function sourceOf(file: UploadedFileRead) {
  if (file.original_filename === "whatsapp_message.txt")
    return {
      key: "WHATSAPP" as SourceKey,
      label: "WhatsApp",
      icon: <MessageSquare className="h-3 w-3" />,
      tone: "green" as const,
    };
  if (file.original_filename === "vapi_call_transcript.txt")
    return {
      key: "VOICE" as SourceKey,
      label: "Voice call",
      icon: <PhoneCall className="h-3 w-3" />,
      tone: "violet" as const,
    };
  return {
    key: "UPLOAD" as SourceKey,
    label: "Upload",
    icon: <FileUp className="h-3 w-3" />,
    tone: "slate" as const,
  };
}

export function Uploads() {
  const projectId = useProjectId();
  const toast = useToast();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [inspecting, setInspecting] = useState<UploadedFileRead | null>(null);

  const [docTypes, setDocTypes] = useState<DocumentType[]>([]);
  const [sources, setSources] = useState<SourceKey[]>([]);
  const [fileSort, setFileSort] = useState<FileSort>("newest");

  const [disciplines, setDisciplines] = useState<Discipline[]>([]);
  const [datedOnly, setDatedOnly] = useState<"all" | "dated" | "undated">("all");
  const [expandAll, setExpandAll] = useState(false);

  const docsQuery = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => documentsApi.list(projectId, { limit: 100 }),
  });
  const reportsQuery = useQuery({
    queryKey: ["progress-reports", projectId],
    queryFn: () => reportsApi.list(projectId, { limit: 100 }),
  });

  const files = useMemo(() => {
    const rows = (docsQuery.data?.items ?? []).filter((f) => {
      const okType = docTypes.length === 0 || docTypes.includes(f.document_type);
      const okSource = sources.length === 0 || sources.includes(sourceOf(f).key);
      return okType && okSource;
    });
    return [...rows].sort((a, b) => {
      switch (fileSort) {
        case "oldest":
          return a.created_at.localeCompare(b.created_at);
        case "largest":
          return b.size_bytes - a.size_bytes;
        case "name":
          return a.original_filename.localeCompare(b.original_filename);
        default:
          return b.created_at.localeCompare(a.created_at);
      }
    });
  }, [docsQuery.data, docTypes, sources, fileSort]);

  // Disciplines offered are the ones actually present on parsed reports, so the
  // menu can never offer a filter that matches nothing.
  const disciplineOptions = useMemo(() => {
    const seen = new Set<Discipline>();
    for (const r of reportsQuery.data?.items ?? []) if (r.discipline) seen.add(r.discipline);
    return [...seen].sort().map((d) => ({ value: d, label: d.toLowerCase() }));
  }, [reportsQuery.data]);

  const reports = useMemo(() => {
    return (reportsQuery.data?.items ?? []).filter((r) => {
      const okDiscipline =
        disciplines.length === 0 || (r.discipline != null && disciplines.includes(r.discipline));
      const okDated =
        datedOnly === "all" ||
        (datedOnly === "dated" ? r.report_date != null : r.report_date == null);
      return okDiscipline && okDated;
    });
  }, [reportsQuery.data, disciplines, datedOnly]);

  const copy = (text: string, what: string) =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(`${what} copied`, text))
      .catch(() => toast.error("Could not copy to clipboard"));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Site reports"
        subtitle="Actual progress as the field files it — DPRs, site diaries, discipline sheets, scans, WhatsApp messages and call transcripts. Everything here is parsed and queued for AI extraction."
        actions={
          <Button onClick={() => setUploadOpen(true)}>
            <UploadIcon className="h-4 w-4" />
            Upload document
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Ingested files"
            subtitle="Everything that reached this project, however it arrived"
            icon={<Inbox className="h-4 w-4" />}
            action={
              docsQuery.data ? (
                <span className="text-2xs text-content-3">
                  {files.length}/{docsQuery.data.total}
                </span>
              ) : undefined
            }
          />

          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-base/50 px-3 py-2">
            <MultiSelectMenu<DocumentType>
              label="Type"
              icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
              options={DOC_TYPE_OPTIONS}
              selected={docTypes}
              onChange={setDocTypes}
            />
            <MultiSelectMenu<SourceKey>
              label="Source"
              icon={<MessageSquare className="h-3.5 w-3.5 text-content-2" />}
              options={SOURCE_OPTIONS}
              selected={sources}
              onChange={setSources}
              width="w-48"
            />
            <SelectMenu<FileSort>
              prefix="Sort"
              icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
              value={fileSort}
              options={FILE_SORTS}
              onChange={(v) => v && setFileSort(v)}
              width="w-48"
            />
          </div>

          <div className="p-3">
            {docsQuery.isLoading && <LoadingRows />}
            {docsQuery.error && <ErrorState error={docsQuery.error} onRetry={() => docsQuery.refetch()} />}
            {docsQuery.data?.items.length === 0 && (
              <EmptyState
                icon={<FileUp className="h-5 w-5" />}
                title="No documents yet"
                description="Upload a daily progress report, or have a supervisor send one over WhatsApp."
                compact
              />
            )}
            {docsQuery.data && docsQuery.data.items.length > 0 && files.length === 0 && (
              <EmptyState
                icon={<Filter className="h-5 w-5" />}
                title="No file matches these filters"
                description="Clear the type or source filter to see the rest of the intake."
                compact
              />
            )}
            {files.length > 0 && (
              <ul className="space-y-1.5">
                {files.map((f) => {
                  const src = sourceOf(f);
                  return (
                    <li
                      key={f.id}
                      className="flex items-center gap-3 rounded-[10px] border border-line px-3 py-2.5 transition-colors hover:border-signal-500/40 hover:bg-signal-600/25/30"
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-ink-950 text-accent">
                        <FileText className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-content-1">{f.original_filename}</p>
                        <p className="mt-0.5 font-mono text-2xs text-content-2">
                          {f.document_type.replaceAll("_", " ").toLowerCase()} ·{" "}
                          {(f.size_bytes / 1024).toFixed(1)} KB ·{" "}
                          {new Date(f.created_at).toLocaleString()}
                        </p>
                      </div>
                      <Badge tone={src.tone} icon={src.icon}>
                        {src.label}
                      </Badge>
                      <Dropdown
                        variant="ghost"
                        align="right"
                        width="w-56"
                        title={`Actions for ${f.original_filename}`}
                        label={<span className="sr-only">File actions</span>}
                        icon={<MoreVertical className="h-4 w-4" />}
                        className="[&>button>svg:last-child]:hidden"
                      >
                        {(close) => (
                          <>
                            <DropdownLabel>{src.label}</DropdownLabel>
                            <DropdownItem
                              icon={<Info className="h-3.5 w-3.5" />}
                              onSelect={() => {
                                setInspecting(f);
                                close();
                              }}
                            >
                              File details
                            </DropdownItem>
                            <DropdownItem
                              icon={<Copy className="h-3.5 w-3.5" />}
                              onSelect={() => {
                                copy(f.original_filename, "Filename");
                                close();
                              }}
                            >
                              Copy filename
                            </DropdownItem>
                            <DropdownItem
                              icon={<Copy className="h-3.5 w-3.5" />}
                              onSelect={() => {
                                copy(f.sha256, "Checksum");
                                close();
                              }}
                            >
                              Copy SHA-256
                            </DropdownItem>
                            <DropdownSeparator />
                            <DropdownItem
                              icon={<ScanLine className="h-3.5 w-3.5" />}
                              disabled={
                                !(reportsQuery.data?.items ?? []).some((r) => r.uploaded_file_id === f.id)
                              }
                              onSelect={() => {
                                const match = (reportsQuery.data?.items ?? []).find(
                                  (r) => r.uploaded_file_id === f.id,
                                );
                                close();
                                if (match) {
                                  setDisciplines(match.discipline ? [match.discipline] : []);
                                  setDatedOnly(match.report_date ? "dated" : "undated");
                                  setExpandAll(true);
                                }
                              }}
                            >
                              Show its parsed report
                            </DropdownItem>
                          </>
                        )}
                      </Dropdown>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Parsed progress reports"
            subtitle="Text extracted from those files, ready for matching"
            icon={<ScanLine className="h-4 w-4" />}
            action={
              reportsQuery.data ? (
                <span className="text-2xs text-content-3">
                  {reports.length}/{reportsQuery.data.total}
                </span>
              ) : undefined
            }
          />

          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-base/50 px-3 py-2">
            <MultiSelectMenu<Discipline>
              label="Discipline"
              icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
              options={disciplineOptions}
              selected={disciplines}
              onChange={setDisciplines}
            />
            <SelectMenu<"all" | "dated" | "undated">
              prefix="Event date"
              value={datedOnly}
              width="w-56"
              options={[
                { value: "all", label: "Any" },
                { value: "dated", label: "Dated only", hint: "bookable" },
                { value: "undated", label: "Undated only", hint: "skipped" },
              ]}
              onChange={(v) => v && setDatedOnly(v)}
            />
            <Dropdown
              label={expandAll ? "Full text" : "Preview"}
              width="w-44"
              icon={<ChevronDown className="h-3.5 w-3.5 text-content-2" />}
            >
              {(close) => (
                <>
                  <DropdownLabel>Raw text</DropdownLabel>
                  <DropdownItem
                    selected={!expandAll}
                    onSelect={() => {
                      setExpandAll(false);
                      close();
                    }}
                  >
                    Preview (3 lines)
                  </DropdownItem>
                  <DropdownItem
                    selected={expandAll}
                    onSelect={() => {
                      setExpandAll(true);
                      close();
                    }}
                  >
                    Full text
                  </DropdownItem>
                </>
              )}
            </Dropdown>
          </div>

          <div className="p-3">
            {reportsQuery.isLoading && <LoadingRows />}
            {reportsQuery.error && (
              <ErrorState error={reportsQuery.error} onRetry={() => reportsQuery.refetch()} />
            )}
            {reportsQuery.data?.items.length === 0 && (
              <EmptyState
                icon={<ScanLine className="h-5 w-5" />}
                title="Nothing parsed yet"
                description="A report appears here once its file finishes processing in the background worker."
                compact
              />
            )}
            {reportsQuery.data && reportsQuery.data.items.length > 0 && reports.length === 0 && (
              <EmptyState
                icon={<Filter className="h-5 w-5" />}
                title="No report matches these filters"
                description="Widen the discipline or event-date filter."
                compact
              />
            )}
            {reports.length > 0 && (
              <ul className="space-y-1.5">
                {reports.map((r) => (
                  <ReportRow key={r.id} report={r} expanded={expandAll} onCopy={copy} />
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <FileDetailsModal file={inspecting} onClose={() => setInspecting(null)} />
      <UploadDocumentModal open={uploadOpen} onClose={() => setUploadOpen(false)} projectId={projectId} />
    </div>
  );
}

/** One parsed report. Undated reports are called out because the backend will
 *  not book progress from them — it returns `skipped_missing_event_date`. */
function ReportRow({
  report,
  expanded,
  onCopy,
}: {
  report: ProgressReportRead;
  expanded: boolean;
  onCopy: (text: string, what: string) => void;
}) {
  const [open, setOpen] = useState(expanded);
  useEffect(() => setOpen(expanded), [expanded]);

  return (
    <li className="rounded-[10px] border border-line p-3 transition-colors hover:border-signal-500/40">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-xs font-medium text-content-1">
          <span className="font-mono">{report.report_date ?? "Undated"}</span>
          {report.discipline && (
            <Badge tone="slate">{report.discipline.toLowerCase()}</Badge>
          )}
          {!report.report_date && (
            <Badge tone="amber">no event date</Badge>
          )}
        </span>
        <Dropdown
          variant="ghost"
          align="right"
          width="w-52"
          title="Report actions"
          label={<span className="sr-only">Report actions</span>}
          icon={<MoreVertical className="h-4 w-4" />}
          className="[&>button>svg:last-child]:hidden"
        >
          {(close) => (
            <>
              <DropdownItem
                onSelect={() => {
                  setOpen((o) => !o);
                  close();
                }}
              >
                {open ? "Collapse text" : "Expand full text"}
              </DropdownItem>
              <DropdownItem
                icon={<Copy className="h-3.5 w-3.5" />}
                onSelect={() => {
                  onCopy(report.raw_text, "Report text");
                  close();
                }}
              >
                Copy raw text
              </DropdownItem>
              <DropdownItem
                icon={<Copy className="h-3.5 w-3.5" />}
                onSelect={() => {
                  onCopy(report.uploaded_file_id, "Source file id");
                  close();
                }}
              >
                Copy source file id
              </DropdownItem>
            </>
          )}
        </Dropdown>
      </div>
      <p
        className={clsx(
          "mt-1.5 whitespace-pre-wrap text-2xs leading-relaxed text-content-2",
          !open && "line-clamp-3",
        )}
      >
        {report.raw_text}
      </p>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-1.5 text-2xs font-medium text-accent hover:underline"
      >
        {open ? "Show less" : "Show full text"}
      </button>
    </li>
  );
}

/** Straight read-back of the stored file record — no derived or invented fields. */
function FileDetailsModal({ file, onClose }: { file: UploadedFileRead | null; onClose: () => void }) {
  const rows: [string, string][] = file
    ? [
        ["Filename", file.original_filename],
        ["Document type", file.document_type.replaceAll("_", " ").toLowerCase()],
        ["Content type", file.content_type],
        ["Size", `${file.size_bytes.toLocaleString()} bytes`],
        ["SHA-256", file.sha256],
        ["File id", file.id],
        ["Uploaded by", file.uploaded_by_id ?? "— (arrived over a webhook)"],
        ["Received", new Date(file.created_at).toLocaleString()],
      ]
    : [];

  return (
    <Modal open={!!file} onClose={onClose} title="File details" subtitle="Stored intake record">
      <dl className="divide-y divide-line">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-3 gap-3 py-2">
            <dt className="text-2xs text-content-3">{k}</dt>
            <dd className="col-span-2 break-all font-mono text-xs text-content-1">{v}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}

const PIPELINE_COPY: Record<JobStatus, string> = {
  PENDING: "Queued for the background worker",
  PROCESSING: "Extracting text from the document",
  COMPLETED: "Parsed — ready for AI matching",
  FAILED: "Processing failed",
};

function UploadDocumentModal({
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
  const [docType, setDocType] = useState<DocumentType>("DAILY_PROGRESS_REPORT");
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const notified = useRef(false);

  // Processing is asynchronous, so upload success is not completion — poll the
  // job until it actually settles.
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => documentsApi.getJob(jobId as string),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "COMPLETED" || s === "FAILED" ? false : 1500;
    },
  });

  const status = jobQuery.data?.status;

  useEffect(() => {
    if (!status || notified.current) return;
    if (status === "COMPLETED") {
      notified.current = true;
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
      queryClient.invalidateQueries({ queryKey: ["progress-reports", projectId] });
      toast.success("Document processed", "The extracted text is ready for AI matching.");
    } else if (status === "FAILED") {
      notified.current = true;
      toast.error("Processing failed", jobQuery.data?.error_message ?? undefined);
    }
  }, [status, jobQuery.data, projectId, queryClient, toast]);

  const reset = () => {
    setFile(null);
    setProgress(0);
    setJobId(null);
    setFileError(null);
    notified.current = false;
  };

  const ALLOWED = [".pdf", ".xlsx", ".xls", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".xer", ".xml"];
  const MAX_MB = 50;

  const pickFile = (picked: File | null) => {
    setFileError(null);
    if (!picked) return setFile(null);
    const ext = picked.name.slice(picked.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setFileError(`Allowed types: ${ALLOWED.join(" ")}`);
      return setFile(null);
    }
    if (picked.size > MAX_MB * 1024 * 1024) {
      setFileError(`That file is ${(picked.size / 1024 / 1024).toFixed(1)} MB — the limit is ${MAX_MB} MB.`);
      return setFile(null);
    }
    setFile(picked);
  };

  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file first.");
      return documentsApi.upload(projectId, file, docType, setProgress);
    },
    onSuccess: (accepted) => {
      setJobId(accepted.job.id);
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
    onError: (err) => {
      setProgress(0);
      toast.error("Upload failed", err instanceof ApiError ? err.message : undefined);
    },
  });

  const done = status === "COMPLETED" || status === "FAILED";

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Upload a site report"
      subtitle="PDF, Excel, CSV, text or a scan. Processing runs in the background — you'll see it move through the pipeline."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
        className="space-y-4"
      >
        <div>
          <label className="mb-1.5 block text-xs font-medium text-content-2">Document type</label>
          <Select value={docType} onChange={(e) => setDocType(e.target.value as DocumentType)}>
            {DOC_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replaceAll("_", " ").toLowerCase()}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-content-2">File</label>
          <label
            className={clsx(
              "flex cursor-pointer items-center gap-3 rounded-[14px] border-2 border-dashed p-4 transition-colors",
              file ? "border-signal-500/40 bg-signal-600/25/40" : "border-line hover:border-line-strong hover:bg-surface-raised",
            )}
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-surface-card text-content-3 shadow-card">
              <FileUp className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-content-1">
                {file ? file.name : "Choose a file"}
              </span>
              <span className="block text-2xs text-content-3">
                {file ? `${(file.size / 1024).toFixed(0)} KB` : `Max ${MAX_MB} MB · ${ALLOWED.join(" ")}`}
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

        {mutation.isPending && <ProgressBarInline value={progress} label={`Uploading… ${progress}%`} />}

        {jobId && (
          <div className="rounded-[14px] border border-line bg-surface-raised/60 p-3">
            <div className="flex items-center justify-between">
              <span className="text-2xs font-medium text-content-3">
                Processing status
              </span>
              {status && <JobStatusBadge status={status} />}
            </div>
            <p className="mt-1.5 text-xs text-content-2">
              {status ? PIPELINE_COPY[status] : "Waiting for the worker…"}
            </p>
            {status === "FAILED" && jobQuery.data?.error_message && (
              <p className="mt-1 text-2xs text-rose-600">{jobQuery.data.error_message}</p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            {done ? "Close" : "Cancel"}
          </Button>
          {!jobId && (
            <Button type="submit" disabled={!file} loading={mutation.isPending}>
              Upload
            </Button>
          )}
          {done && (
            <Button
              type="button"
              onClick={() => {
                reset();
              }}
            >
              Upload another
            </Button>
          )}
        </div>
      </form>
    </Modal>
  );
}
