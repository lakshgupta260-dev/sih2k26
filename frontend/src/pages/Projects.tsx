import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpDown,
  Link as LinkIcon,
  Trash2,
  CalendarRange,
  FolderKanban,
  GitBranch,
  LayoutGrid,
  MapPin,
  MessageSquare,
  MoreVertical,
  Plus,
  Rows3,
  Search,
  Settings2,
  ShieldAlert,
  Users,
} from "lucide-react";
import { projectsApi } from "@/api/projects";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { stripEmptyStrings } from "@/utils/forms";
import { EmptyState, ErrorState } from "@/components/common/States";
import { ProjectStatusBadge } from "@/components/common/Badge";
import {
  Button,
  Card,
  Field,
  Input,
  Modal,
  PageHeader,
  Skeleton,
  Textarea,
} from "@/components/ui/Primitives";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import { TiltCard } from "@/components/ui/NetworkMesh";
import type { ProjectCreate, ProjectStatus, ProjectWithRole, UserRole } from "@/types/api";

const STATUS_OPTIONS: { value: ProjectStatus; label: string }[] = [
  { value: "PLANNING", label: "Planning" },
  { value: "ACTIVE", label: "Active" },
  { value: "ON_HOLD", label: "On hold" },
  { value: "COMPLETED", label: "Completed" },
  { value: "CANCELLED", label: "Cancelled" },
];

// `my_role` is the caller's membership role on that project, typed as UserRole.
const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "ADMIN", label: "Admin" },
  { value: "PROJECT_MANAGER", label: "Project manager" },
  { value: "SITE_SUPERVISOR", label: "Site supervisor" },
];

type SortKey = "name" | "code" | "status" | "start" | "finish";

const SORT_OPTIONS: { value: SortKey; label: string; hint?: string }[] = [
  { value: "code", label: "Project code" },
  { value: "name", label: "Name (A→Z)" },
  { value: "status", label: "Status" },
  { value: "start", label: "Planned start" },
  { value: "finish", label: "Planned finish" },
];

/** Undated projects sort last regardless of direction — a missing date is not "earliest". */
function compare(a: ProjectWithRole, b: ProjectWithRole, key: SortKey): number {
  const byDate = (x: string | null | undefined, y: string | null | undefined) => {
    if (!x && !y) return 0;
    if (!x) return 1;
    if (!y) return -1;
    return x.localeCompare(y);
  };
  switch (key) {
    case "name":
      return a.name.localeCompare(b.name);
    case "status":
      return a.status.localeCompare(b.status) || a.code.localeCompare(b.code);
    case "start":
      return byDate(a.planned_start, b.planned_start);
    case "finish":
      return byDate(a.planned_finish, b.planned_finish);
    default:
      return a.code.localeCompare(b.code);
  }
}

export function Projects() {
  const { user } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statuses, setStatuses] = useState<ProjectStatus[]>([]);
  const [roles, setRoles] = useState<UserRole[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("code");
  const [descending, setDescending] = useState(false);
  const [view, setView] = useState<"grid" | "list">("grid");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list({ limit: 100 }),
  });

  const canCreate = user?.role === "ADMIN" || user?.role === "PROJECT_MANAGER";
  // The API allows a soft delete for administrators and project managers; the
  // menu entry is hidden for everyone else rather than offered and refused.
  const canManageProjects = canCreate;
  const [pendingDelete, setPendingDelete] = useState<ProjectWithRole | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = (data?.items ?? []).filter((p) => {
      const matchesText =
        !q ||
        `${p.name} ${p.code} ${p.client_name ?? ""} ${p.location ?? ""}`.toLowerCase().includes(q);
      const matchesStatus = statuses.length === 0 || statuses.includes(p.status);
      const matchesRole = roles.length === 0 || roles.includes(p.my_role);
      return matchesText && matchesStatus && matchesRole;
    });
    const sorted = [...rows].sort((a, b) => compare(a, b, sortKey));
    return descending ? sorted.reverse() : sorted;
  }, [data, query, statuses, roles, sortKey, descending]);

  const activeFilters = statuses.length + roles.length + (query.trim() ? 1 : 0);

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Infrastructure projects you can access — from the planned L1–L6 baseline through to delay risk."
        actions={
          <>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-2" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter projects…"
                className="w-56 pl-8"
              />
            </div>
            {canCreate && (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                New project
              </Button>
            )}
          </>
        }
      />

      {/* Filter bar — every control below narrows the same real project list. */}
      <div className="mb-4 flex flex-wrap items-center gap-2 border-y border-line py-2.5">
        <MultiSelectMenu<ProjectStatus>
          label="Status"
          icon={<FolderKanban className="h-3.5 w-3.5 text-content-2" />}
          options={STATUS_OPTIONS}
          selected={statuses}
          onChange={setStatuses}
        />
        <MultiSelectMenu<UserRole>
          label="My role"
          icon={<Users className="h-3.5 w-3.5 text-content-2" />}
          options={ROLE_OPTIONS}
          selected={roles}
          onChange={setRoles}
        />
        <SelectMenu<SortKey>
          prefix="Sort"
          icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
          value={sortKey}
          options={SORT_OPTIONS}
          onChange={(v) => v && setSortKey(v)}
        />
        <Dropdown
          label={descending ? "Descending" : "Ascending"}
          width="w-44"
          icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
        >
          {(close) => (
            <>
              <DropdownItem
                selected={!descending}
                onSelect={() => {
                  setDescending(false);
                  close();
                }}
              >
                Ascending
              </DropdownItem>
              <DropdownItem
                selected={descending}
                onSelect={() => {
                  setDescending(true);
                  close();
                }}
              >
                Descending
              </DropdownItem>
            </>
          )}
        </Dropdown>
        <Dropdown
          label={view === "grid" ? "Cards" : "Rows"}
          width="w-44"
          icon={
            view === "grid" ? (
              <LayoutGrid className="h-3.5 w-3.5 text-content-2" />
            ) : (
              <Rows3 className="h-3.5 w-3.5 text-content-2" />
            )
          }
        >
          {(close) => (
            <>
              <DropdownLabel>Layout</DropdownLabel>
              <DropdownItem
                icon={<LayoutGrid className="h-3.5 w-3.5" />}
                selected={view === "grid"}
                onSelect={() => {
                  setView("grid");
                  close();
                }}
              >
                Cards
              </DropdownItem>
              <DropdownItem
                icon={<Rows3 className="h-3.5 w-3.5" />}
                selected={view === "list"}
                onSelect={() => {
                  setView("list");
                  close();
                }}
              >
                Rows
              </DropdownItem>
            </>
          )}
        </Dropdown>

        <span className="ml-auto text-2xs text-content-3">
          {filtered.length} of {data?.total ?? 0}
        </span>
        {activeFilters > 0 && (
          <button
            type="button"
            onClick={() => {
              setStatuses([]);
              setRoles([]);
              setQuery("");
            }}
            className="text-2xs font-medium text-accent hover:underline"
          >
            Reset filters
          </button>
        )}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="p-5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="mt-2 h-3 w-24" />
              <Skeleton className="mt-5 h-3 w-full" />
              <Skeleton className="mt-2 h-3 w-2/3" />
            </Card>
          ))}
        </div>
      )}

      {error && <ErrorState error={error} onRetry={() => refetch()} />}

      {data && data.items.length === 0 && (
        <EmptyState
          icon={<FolderKanban className="h-5 w-5" />}
          title="No projects yet"
          description={
            canCreate
              ? "Create your first project, then upload a baseline schedule to start tracking planned versus actual progress."
              : "You're not a member of any project yet. Ask a project manager to add you."
          }
          action={
            canCreate && (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                New project
              </Button>
            )
          }
        />
      )}

      {data && data.items.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon={<Search className="h-5 w-5" />}
          title={`No project matches “${query}”`}
          description="Try a different name, code, client or location."
        />
      )}

      {filtered.length > 0 && view === "grid" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((project, i) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.05, 0.3), ease: [0.16, 1, 0.3, 1] }}
            >
              <TiltCard className="h-full">
                <Card
                  interactive
                  className="group relative h-full overflow-hidden p-5 transition-transform duration-200 hover:-translate-y-0.5"
                >
                  {/* The jump menu sits outside the link so it can be opened without navigating. */}
                  <div className="absolute right-2.5 top-2.5 z-10">
                    <ProjectActionsMenu
                      project={project}
                      canDelete={canManageProjects}
                      onDelete={setPendingDelete}
                    />
                  </div>

                  <Link to={`/projects/${project.id}`} className="block">
                    <div className="flex items-start justify-between gap-3 pr-7">
                      <div className="min-w-0">
                        <h3 className="truncate font-display text-[1.05rem] font-semibold tracking-[-0.02em] text-content-1">
                          {project.name}
                        </h3>
                        <p className="mt-0.5 text-2xs text-accent">
                          {project.code}
                        </p>
                      </div>
                    </div>

                    <div className="mt-2">
                      <ProjectStatusBadge status={project.status} />
                    </div>

                    {project.description && (
                      <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-content-3">
                        {project.description}
                      </p>
                    )}

                    <div className="mt-4 space-y-1.5">
                      {project.client_name && (
                        <p className="flex items-center gap-1.5 text-xs text-content-2">
                          <FolderKanban className="h-3.5 w-3.5 text-content-2" />
                          {project.client_name}
                        </p>
                      )}
                      {project.location && (
                        <p className="flex items-center gap-1.5 text-xs text-content-2">
                          <MapPin className="h-3.5 w-3.5 text-content-2" />
                          {project.location}
                        </p>
                      )}
                      {(project.planned_start || project.planned_finish) && (
                        <p className="flex items-center gap-1.5 font-mono text-xs text-content-2">
                          <CalendarRange className="h-3.5 w-3.5 text-content-2" />
                          {project.planned_start ?? "—"} → {project.planned_finish ?? "—"}
                        </p>
                      )}
                    </div>

                    <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
                      <span className="text-2xs text-content-3">
                        {project.my_role.replaceAll("_", " ")}
                      </span>
                      <span className="flex items-center gap-1 text-2xs font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
                        Open <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                  </Link>
                </Card>
              </TiltCard>
            </motion.div>
          ))}
        </div>
      )}

      {filtered.length > 0 && view === "list" && (
        <Card className="overflow-hidden">
          <table className="w-full text-left">
            <thead className="border-b border-line bg-surface-base/60">
              <tr className="text-2xs text-content-3">
                <th className="px-4 py-2.5 font-medium">Code</th>
                <th className="px-4 py-2.5 font-medium">Project</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Client</th>
                <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Location</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Planned window</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="w-10 px-2 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filtered.map((project) => (
                <tr key={project.id} className="group transition-colors hover:bg-signal-600/25/40">
                  <td className="px-4 py-2.5">
                    <Link
                      to={`/projects/${project.id}`}
                      className="font-mono text-2xs font-medium uppercase text-accent hover:underline"
                    >
                      {project.code}
                    </Link>
                  </td>
                  <td className="max-w-[22rem] px-4 py-2.5">
                    <Link
                      to={`/projects/${project.id}`}
                      className="block truncate text-xs font-medium text-content-1 hover:text-accent"
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">
                    <ProjectStatusBadge status={project.status} />
                  </td>
                  <td className="hidden truncate px-4 py-2.5 text-xs text-content-2 lg:table-cell">
                    {project.client_name ?? "—"}
                  </td>
                  <td className="hidden truncate px-4 py-2.5 text-xs text-content-2 lg:table-cell">
                    {project.location ?? "—"}
                  </td>
                  <td className="hidden whitespace-nowrap px-4 py-2.5 font-mono text-2xs text-content-2 md:table-cell">
                    {project.planned_start ?? "—"} → {project.planned_finish ?? "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-2xs text-content-2">
                    {project.my_role.replaceAll("_", " ")}
                  </td>
                  <td className="px-2 py-2.5">
                    <ProjectActionsMenu
                      project={project}
                      canDelete={canManageProjects}
                      onDelete={setPendingDelete}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <DeleteProjectModal project={pendingDelete} onClose={() => setPendingDelete(null)} />
    </div>
  );
}

/**
 * Jump menu on a project card/row. Every entry is a route that exists in the
 * router; the copy action uses the clipboard API with a visible fallback path.
 */
function ProjectActionsMenu({
  project,
  onDelete,
  canDelete,
}: {
  project: ProjectWithRole;
  onDelete: (p: ProjectWithRole) => void;
  canDelete: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const base = `/projects/${project.id}`;

  const go = (path: string, close: () => void) => {
    close();
    navigate(path);
  };

  return (
    <Dropdown
      variant="ghost"
      align="right"
      width="w-56"
      title={`Actions for ${project.code}`}
      label={<span className="sr-only">Open project menu</span>}
      icon={<MoreVertical className="h-4 w-4" />}
      panelClassName="text-left"
      className="[&>button>svg:last-child]:hidden"
    >
      {(close) => (
        <>
          <DropdownLabel>{project.code}</DropdownLabel>
          <DropdownItem icon={<LayoutGrid className="h-3.5 w-3.5" />} onSelect={() => go(base, close)}>
            Overview
          </DropdownItem>
          <DropdownItem
            icon={<GitBranch className="h-3.5 w-3.5" />}
            onSelect={() => go(`${base}/schedule`, close)}
          >
            Baselines &amp; WBS
          </DropdownItem>
          <DropdownItem
            icon={<ShieldAlert className="h-3.5 w-3.5" />}
            onSelect={() => go(`${base}/risks`, close)}
          >
            Delay risk
          </DropdownItem>
          <DropdownItem
            icon={<MessageSquare className="h-3.5 w-3.5" />}
            onSelect={() => go(`${base}/channels`, close)}
          >
            WhatsApp &amp; voice
          </DropdownItem>
          <DropdownItem
            icon={<Users className="h-3.5 w-3.5" />}
            onSelect={() => go(`${base}/members`, close)}
          >
            Members
          </DropdownItem>
          <DropdownSeparator />
          <DropdownItem
            icon={<Settings2 className="h-3.5 w-3.5" />}
            onSelect={() => go(`${base}/settings`, close)}
          >
            Settings
          </DropdownItem>
          <DropdownItem
            icon={<LinkIcon className="h-3.5 w-3.5" />}
            onSelect={() => {
              const url = `${window.location.origin}${base}`;
              navigator.clipboard
                ?.writeText(url)
                .then(() => toast.success("Link copied", url))
                .catch(() => toast.error("Could not copy", url));
              close();
            }}
          >
            Copy link
          </DropdownItem>
          {canDelete && (
            <>
              <DropdownSeparator />
              <DropdownItem
                danger
                icon={<Trash2 className="h-3.5 w-3.5" />}
                onSelect={() => {
                  close();
                  onDelete(project);
                }}
              >
                Delete project
              </DropdownItem>
            </>
          )}
        </>
      )}
    </Dropdown>
  );
}

function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProjectCreate>();

  const mutation = useMutation({
    mutationFn: (payload: ProjectCreate) => projectsApi.create(payload),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      reset();
      onClose();
      toast.success("Project created", `${created.code} — ${created.name}`);
    },
    onError: (err) =>
      toast.error(
        "Could not create project",
        err instanceof ApiError
          ? err.code === "CONFLICT"
            ? "That project code is already taken."
            : err.message
          : undefined,
      ),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New project"
      subtitle="A short unique code plus a name is all that's required."
    >
      <form
        onSubmit={handleSubmit((values) =>
          mutation.mutate(stripEmptyStrings(values) as unknown as ProjectCreate),
        )}
        className="space-y-4"
      >
        <div className="grid grid-cols-3 gap-3">
          <Field label="Code" error={errors.code?.message}>
            <Input
              placeholder="OIL-PL-03"
              {...register("code", {
                required: "Required",
                pattern: {
                  value: /^[A-Za-z0-9][A-Za-z0-9._-]*$/,
                  message: "Letters, digits, . _ - only",
                },
              })}
            />
          </Field>
          <Field label="Name" error={errors.name?.message} className="col-span-2">
            <Input placeholder="Pipeline PL-03 Expansion" {...register("name", { required: "Required" })} />
          </Field>
        </div>

        <Field label="Description">
          <Textarea rows={2} placeholder="Scope, package, contract reference…" {...register("description")} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Client">
            <Input placeholder="Oil India Limited" {...register("client_name")} />
          </Field>
          <Field label="Location">
            <Input placeholder="Duliajan, Assam" {...register("location")} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Planned start">
            <Input type="date" {...register("planned_start")} />
          </Field>
          <Field label="Planned finish" hint="Cannot be before the start date.">
            <Input type="date" {...register("planned_finish")} />
          </Field>
        </div>

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Create project
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Confirmation for deleting a project.
 *
 * The backend performs a *soft* delete, so the wording says removed-from-view
 * rather than implying the data is destroyed — and the project code has to be
 * typed back, because this is one click away from a list of live projects.
 */
function DeleteProjectModal({
  project,
  onClose,
}: {
  project: ProjectWithRole | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => {
    setConfirmText("");
  }, [project?.id]);

  const mutation = useMutation({
    mutationFn: (id: string) => projectsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project deleted", `${project?.code} no longer appears in your list.`);
      onClose();
    },
    onError: (err) =>
      toast.error(
        "Could not delete project",
        err instanceof ApiError
          ? err.status === 403
            ? "You need to be an administrator or project manager."
            : err.message
          : undefined,
      ),
  });

  const matches = project != null && confirmText.trim() === project.code;

  return (
    <Modal
      open={project != null}
      onClose={onClose}
      title="Delete project"
      subtitle={project ? `${project.code} — ${project.name}` : undefined}
    >
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-content-2">
          This removes the project from every member's list, along with its schedules, uploads
          and forecasts. It is a soft delete — the rows stay in the database and an administrator
          can restore them — but nobody will be able to reach it from the app.
        </p>

        <Field label={`Type ${project?.code ?? ""} to confirm`}>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={project?.code}
            autoComplete="off"
          />
        </Field>

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={!matches}
            loading={mutation.isPending}
            onClick={() => project && mutation.mutate(project.id)}
          >
            <Trash2 className="h-4 w-4" />
            Delete project
          </Button>
        </div>
      </div>
    </Modal>
  );
}
