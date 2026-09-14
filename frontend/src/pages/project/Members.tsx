import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Filter,
  Mail,
  MoreVertical,
  Search,
  ShieldCheck,
  UserPlus,
  Users,
  UserMinus,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { projectsApi } from "@/api/projects";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Badge } from "@/components/common/Badge";
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Modal,
  PageHeader,
} from "@/components/ui/Primitives";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  MultiSelectMenu,
  SelectMenu,
} from "@/components/ui/Dropdown";
import type { MemberAdd, MemberDetail, UserRole } from "@/types/api";

const ROLES: UserRole[] = ["SITE_SUPERVISOR", "PROJECT_MANAGER", "ADMIN"];

const ROLE_OPTIONS = ROLES.map((r) => ({ value: r, label: r.replaceAll("_", " ").toLowerCase() }));

const ROLE_BLURB: Record<UserRole, string> = {
  SITE_SUPERVISOR: "Uploads field reports and confirms matches.",
  PROJECT_MANAGER: "Everything a supervisor can do, plus schedules, members and settings.",
  ADMIN: "Full administrative control of this project.",
};

function humanRole(role: UserRole) {
  return role.replaceAll("_", " ").toLowerCase();
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function Members() {
  const projectId = useProjectId();
  const { canManage } = useProject();
  const queryClient = useQueryClient();
  const toast = useToast();

  const membersQuery = useQuery({
    queryKey: ["members", projectId],
    queryFn: () => projectsApi.listMembers(projectId),
  });

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<MemberAdd>({ defaultValues: { role: "SITE_SUPERVISOR" } });

  const pendingRole = (watch("role") ?? "SITE_SUPERVISOR") as UserRole;

  const addMutation = useMutation({
    mutationFn: (payload: MemberAdd) => projectsApi.addMember(projectId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", projectId] });
      reset({ role: "SITE_SUPERVISOR", email: "" });
      toast.success("Member added", "They can see this project the next time they sign in.");
    },
    onError: (err) =>
      toast.error("Could not add member", err instanceof ApiError ? err.message : undefined),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      projectsApi.changeMemberRole(projectId, userId, { role }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["members", projectId] });
      toast.success("Role updated", `Now a ${humanRole(variables.role)} on this project.`);
    },
    onError: (err) =>
      toast.error("Could not change role", err instanceof ApiError ? err.message : undefined),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => projectsApi.removeMember(projectId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", projectId] });
      toast.success("Member removed", "They no longer have access to this project.");
    },
    onError: (err) =>
      toast.error("Could not remove member", err instanceof ApiError ? err.message : undefined),
  });

  const [roleFilter, setRoleFilter] = useState<UserRole[]>([]);
  const [activity, setActivity] = useState<"all" | "active" | "inactive">("all");
  const [search, setSearch] = useState("");
  const [confirmRemove, setConfirmRemove] = useState<MemberDetail | null>(null);

  const all = membersQuery.data ?? [];
  const members = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter(
      (m) =>
        (roleFilter.length === 0 || roleFilter.includes(m.role)) &&
        (activity === "all" || (activity === "active" ? m.is_active : !m.is_active)) &&
        (!q || `${m.full_name} ${m.email}`.toLowerCase().includes(q)),
    );
  }, [all, roleFilter, activity, search]);

  const copyEmails = () => {
    const list = members.map((m) => m.email).join(", ");
    navigator.clipboard
      ?.writeText(list)
      .then(() => toast.success(`${members.length} addresses copied`, list))
      .catch(() => toast.error("Could not copy to clipboard"));
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Members"
        subtitle="Project-level roles decide who can write progress and who can administer this project."
        actions={
          all.length > 0 ? (
            <Badge tone="slate" icon={<Users className="h-3 w-3" />}>
              {all.length} {all.length === 1 ? "member" : "members"}
            </Badge>
          ) : undefined
        }
      />

      {canManage && (
        <Card>
          <CardHeader
            title="Add a member"
            subtitle={ROLE_BLURB[pendingRole] ?? "Invite someone who already has an account."}
            icon={<UserPlus className="h-4 w-4" />}
          />
          <form
            className="grid grid-cols-1 items-end gap-4 p-4 sm:grid-cols-[2fr,1fr,auto]"
            onSubmit={handleSubmit((values) =>
              addMutation.mutate({ email: values.email || undefined, role: values.role }),
            )}
          >
            <Field
              label="Email"
              error={errors.email?.message}
              hint="Must match an existing Plan2Progress account."
            >
              <Input
                type="email"
                placeholder="supervisor@oil-india.example"
                {...register("email", { required: "Enter the member's email" })}
              />
            </Field>
            <Field label="Project role">
              {/* Registered as a native select so react-hook-form keeps the ref,
                  but styled to match the rest of the menu system. */}
              <select
                {...register("role")}
                className="h-9 w-full cursor-pointer rounded-[10px] border border-line bg-surface-card px-3 pr-8 text-sm capitalize text-content-1 transition-colors hover:border-line-strong focus:border-signal-500 focus:outline-none focus:ring-4 focus:ring-signal-500/12"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {humanRole(r)}
                  </option>
                ))}
              </select>
            </Field>
            <Button type="submit" variant="signal" loading={addMutation.isPending}>
              <UserPlus className="h-4 w-4" />
              Add member
            </Button>
          </form>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Current members"
          subtitle="Everyone with access to this project's schedules, uploads and forecasts."
          icon={<ShieldCheck className="h-4 w-4" />}
          action={
            <span className="text-2xs text-content-3">
              {members.length}/{all.length}
            </span>
          }
        />

        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-base/50 px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-2" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name or email…"
              className="h-8 w-52 rounded-[10px] border border-line bg-surface-card pl-7 pr-2 text-xs text-content-1 placeholder:text-content-2 focus:border-signal-500 focus:outline-none focus:ring-4 focus:ring-signal-500/12"
            />
          </div>
          <MultiSelectMenu<UserRole>
            label="Role"
            icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
            options={ROLE_OPTIONS}
            selected={roleFilter}
            onChange={setRoleFilter}
          />
          <SelectMenu<"all" | "active" | "inactive">
            prefix="Account"
            value={activity}
            width="w-48"
            options={[
              { value: "all", label: "Any" },
              { value: "active", label: "Active only" },
              { value: "inactive", label: "Inactive only" },
            ]}
            onChange={(v) => v && setActivity(v)}
          />
          <Dropdown label="Bulk" width="w-56" align="left">
            {(close) => (
              <>
                <DropdownLabel>Visible members</DropdownLabel>
                <DropdownItem
                  icon={<Copy className="h-3.5 w-3.5" />}
                  disabled={members.length === 0}
                  onSelect={() => {
                    copyEmails();
                    close();
                  }}
                >
                  Copy {members.length} email addresses
                </DropdownItem>
                <DropdownSeparator />
                <DropdownItem
                  onSelect={() => {
                    setRoleFilter([]);
                    setActivity("all");
                    setSearch("");
                    close();
                  }}
                >
                  Clear all filters
                </DropdownItem>
              </>
            )}
          </Dropdown>
        </div>

        <div className="p-3">
          {membersQuery.isLoading && <LoadingRows />}

          {membersQuery.error && (
            <ErrorState error={membersQuery.error} onRetry={() => membersQuery.refetch()} />
          )}

          {membersQuery.data && all.length > 0 && members.length === 0 && (
            <EmptyState
              icon={<Filter className="h-5 w-5" />}
              title="No member matches these filters"
              description="Clear the role, account or search filter."
              compact
            />
          )}

          {membersQuery.data && all.length === 0 && (
            <EmptyState
              icon={<Users className="h-5 w-5" />}
              title="No members yet"
              description={
                canManage
                  ? "Add the site supervisors who will be filing progress from the field."
                  : "Ask a project manager to add the team to this project."
              }
              compact
            />
          )}

          {members.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-2xs text-content-2">
                    <th className="px-3 py-2 font-medium">Member</th>
                    <th className="px-3 py-2 font-medium">Project role</th>
                    <th className="px-3 py-2 font-medium">Account</th>
                    <th className="px-3 py-2 font-medium">Added</th>
                    {canManage && <th className="px-3 py-2" />}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {members.map((m) => (
                    <tr key={m.id} className="transition-colors hover:bg-surface-raised/60">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-raised text-2xs font-semibold text-content-2">
                            {initials(m.full_name)}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-content-1">{m.full_name}</p>
                            <p className="mt-0.5 flex items-center gap-1 truncate text-2xs text-content-2">
                              <Mail className="h-3 w-3" />
                              {m.email}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        {canManage ? (
                          <Dropdown
                            width="w-64"
                            disabled={roleMutation.isPending}
                            label={<span className="capitalize">{humanRole(m.role)}</span>}
                            icon={<ShieldCheck className="h-3.5 w-3.5 text-content-2" />}
                          >
                            {(close) => (
                              <>
                                <DropdownLabel>Project role</DropdownLabel>
                                {ROLES.map((r) => (
                                  <DropdownItem
                                    key={r}
                                    selected={r === m.role}
                                    hint={r === m.role ? "current" : undefined}
                                    onSelect={() => {
                                      close();
                                      if (r !== m.role)
                                        roleMutation.mutate({ userId: m.user_id, role: r });
                                    }}
                                  >
                                    <span className="capitalize">{humanRole(r)}</span>
                                  </DropdownItem>
                                ))}
                                <DropdownSeparator />
                                <p className="px-2 pb-1 text-2xs leading-relaxed text-content-3">
                                  {ROLE_BLURB[m.role]}
                                </p>
                              </>
                            )}
                          </Dropdown>
                        ) : (
                          <span className="text-xs capitalize text-content-2">{humanRole(m.role)}</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge tone={m.is_active ? "green" : "slate"}>
                          {m.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td className="tnum px-3 py-2.5 text-2xs text-content-2">
                        {new Date(m.created_at).toLocaleDateString()}
                      </td>
                      {canManage && (
                        <td className="px-3 py-2.5 text-right">
                          <Dropdown
                            variant="ghost"
                            align="right"
                            width="w-56"
                            title={`Actions for ${m.full_name}`}
                            label={<span className="sr-only">Member actions</span>}
                            icon={<MoreVertical className="h-4 w-4" />}
                            className="inline-block [&>button>svg:last-child]:hidden"
                          >
                            {(close) => (
                              <>
                                <DropdownLabel>{m.full_name}</DropdownLabel>
                                <DropdownItem
                                  icon={<Copy className="h-3.5 w-3.5" />}
                                  onSelect={() => {
                                    navigator.clipboard
                                      ?.writeText(m.email)
                                      .then(() => toast.success("Email copied", m.email))
                                      .catch(() => toast.error("Could not copy to clipboard"));
                                    close();
                                  }}
                                >
                                  Copy email
                                </DropdownItem>
                                <DropdownItem
                                  icon={<Mail className="h-3.5 w-3.5" />}
                                  onSelect={() => {
                                    close();
                                    window.location.href = `mailto:${m.email}`;
                                  }}
                                >
                                  Compose email
                                </DropdownItem>
                                <DropdownSeparator />
                                <DropdownItem
                                  danger
                                  icon={<UserMinus className="h-3.5 w-3.5" />}
                                  onSelect={() => {
                                    close();
                                    setConfirmRemove(m);
                                  }}
                                >
                                  Remove from project
                                </DropdownItem>
                              </>
                            )}
                          </Dropdown>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* Removing access is not reversible from this screen, so it is confirmed. */}
      <Modal
        open={!!confirmRemove}
        onClose={() => setConfirmRemove(null)}
        title="Remove member"
        subtitle={confirmRemove ? `${confirmRemove.full_name} · ${confirmRemove.email}` : undefined}
      >
        <p className="text-sm leading-relaxed text-content-2">
          They will immediately lose access to this project's schedules, uploads, matches and
          forecasts. Their account and anything they already filed stay intact — re-adding them
          restores access.
        </p>
        <div className="mt-5 flex justify-end gap-2 border-t border-line pt-4">
          <Button variant="secondary" onClick={() => setConfirmRemove(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={removeMutation.isPending}
            onClick={() => {
              if (!confirmRemove) return;
              removeMutation.mutate(confirmRemove.user_id, {
                onSettled: () => setConfirmRemove(null),
              });
            }}
          >
            <UserMinus className="h-4 w-4" />
            Remove access
          </Button>
        </div>
      </Modal>
    </div>
  );
}
