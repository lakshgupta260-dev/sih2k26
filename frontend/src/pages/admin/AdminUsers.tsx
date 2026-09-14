import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpDown,
  Copy,
  Filter,
  Mail,
  MoreVertical,
  Power,
  Search,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { usersApi } from "@/api/users";
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
import type { UserAdminCreate, UserRole } from "@/types/api";

const ROLES: UserRole[] = ["SITE_SUPERVISOR", "PROJECT_MANAGER", "ADMIN"];

const ROLE_OPTIONS = ROLES.map((r) => ({ value: r, label: r.replaceAll("_", " ").toLowerCase() }));

type UserSort = "name" | "role" | "recent" | "joined";

const USER_SORTS: { value: UserSort; label: string }[] = [
  { value: "name", label: "Name (A→Z)" },
  { value: "role", label: "System role" },
  { value: "recent", label: "Last login" },
  { value: "joined", label: "Newest account" },
];

function humanRole(role: UserRole) {
  return role.replaceAll("_", " ").toLowerCase();
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function AdminUsers() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRole[]>([]);
  const [activity, setActivity] = useState<"all" | "active" | "inactive">("all");
  const [sort, setSort] = useState<UserSort>("name");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => usersApi.list({ limit: 200 }),
  });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => usersApi.changeRole(id, role),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success("Role updated", `${updated.full_name} is now a ${humanRole(updated.role)}.`);
    },
    onError: (err) =>
      toast.error("Could not change role", err instanceof ApiError ? err.message : undefined),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      usersApi.setStatus(id, isActive),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success(
        updated.is_active ? "Account activated" : "Account deactivated",
        updated.is_active
          ? `${updated.full_name} can sign in again.`
          : `${updated.full_name} can no longer sign in.`,
      );
    },
    onError: (err) =>
      toast.error("Could not update account", err instanceof ApiError ? err.message : undefined),
  });

  const users = data?.items ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = users.filter(
      (u) =>
        (!q || `${u.full_name} ${u.email} ${u.role}`.toLowerCase().includes(q)) &&
        (roleFilter.length === 0 || roleFilter.includes(u.role)) &&
        (activity === "all" || (activity === "active" ? u.is_active : !u.is_active)),
    );
    return [...rows].sort((a, b) => {
      switch (sort) {
        case "role":
          return a.role.localeCompare(b.role) || a.full_name.localeCompare(b.full_name);
        case "recent":
          // Never-signed-in accounts sort last rather than pretending to be oldest.
          if (!a.last_login_at && !b.last_login_at) return a.full_name.localeCompare(b.full_name);
          if (!a.last_login_at) return 1;
          if (!b.last_login_at) return -1;
          return b.last_login_at.localeCompare(a.last_login_at);
        case "joined":
          return b.created_at.localeCompare(a.created_at);
        default:
          return a.full_name.localeCompare(b.full_name);
      }
    });
  }, [users, query, roleFilter, activity, sort]);

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="System-wide roles and account status. Project-level roles are set inside each project."
        actions={
          <>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-2" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter users…"
                className="w-56 pl-8"
              />
            </div>
            <Button onClick={() => setCreateOpen(true)}>
              <UserPlus className="h-4 w-4" />
              New user
            </Button>
          </>
        }
      />

      <Card>
        <CardHeader
          title="All users"
          subtitle={
            data ? `${users.length} account${users.length === 1 ? "" : "s"} on this deployment` : undefined
          }
          icon={<ShieldCheck className="h-4 w-4" />}
          action={
            <span className="text-2xs text-content-3">
              {filtered.length}/{users.length}
            </span>
          }
        />

        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-base/50 px-3 py-2">
          <MultiSelectMenu<UserRole>
            label="System role"
            icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
            options={ROLE_OPTIONS}
            selected={roleFilter}
            onChange={setRoleFilter}
          />
          <SelectMenu<"all" | "active" | "inactive">
            prefix="Status"
            value={activity}
            width="w-48"
            options={[
              { value: "all", label: "Any" },
              { value: "active", label: "Active only" },
              { value: "inactive", label: "Deactivated only" },
            ]}
            onChange={(v) => v && setActivity(v)}
          />
          <SelectMenu<UserSort>
            prefix="Sort"
            icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
            value={sort}
            width="w-48"
            options={USER_SORTS}
            onChange={(v) => v && setSort(v)}
          />
          <Dropdown label="Bulk" width="w-60">
            {(close) => (
              <>
                <DropdownLabel>Visible users</DropdownLabel>
                <DropdownItem
                  icon={<Copy className="h-3.5 w-3.5" />}
                  disabled={filtered.length === 0}
                  onSelect={() => {
                    const list = filtered.map((u) => u.email).join(", ");
                    navigator.clipboard
                      ?.writeText(list)
                      .then(() => toast.success(`${filtered.length} addresses copied`, list))
                      .catch(() => toast.error("Could not copy to clipboard"));
                    close();
                  }}
                >
                  Copy {filtered.length} email addresses
                </DropdownItem>
                <DropdownSeparator />
                <DropdownItem
                  onSelect={() => {
                    setRoleFilter([]);
                    setActivity("all");
                    setQuery("");
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
          {isLoading && <LoadingRows rows={6} />}

          {error && <ErrorState error={error} onRetry={() => refetch()} />}

          {data && users.length === 0 && (
            <EmptyState
              icon={<Users className="h-5 w-5" />}
              title="No users yet"
              description="Create the first account — an admin or a project manager who can then set up projects."
              action={
                <Button size="sm" onClick={() => setCreateOpen(true)}>
                  <UserPlus className="h-4 w-4" />
                  New user
                </Button>
              }
              compact
            />
          )}

          {data && users.length > 0 && filtered.length === 0 && (
            <EmptyState
              icon={<Search className="h-5 w-5" />}
              title="No user matches these filters"
              description={
                query.trim()
                  ? `Nothing matches “${query}” with the current role and status filters.`
                  : "Clear the role or status filter to see the rest of the directory."
              }
              compact
            />
          )}

          {filtered.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-2xs text-content-2">
                    <th className="px-3 py-2 font-medium">User</th>
                    <th className="px-3 py-2 font-medium">System role</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Last login</th>
                    <th className="px-3 py-2 font-medium">Joined</th>
                    <th className="w-10 px-2 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {filtered.map((u) => (
                    <tr key={u.id} className="transition-colors hover:bg-surface-raised/60">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-raised text-2xs font-semibold text-content-2">
                            {initials(u.full_name)}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-content-1">{u.full_name}</p>
                            <p className="mt-0.5 truncate text-2xs text-content-2">{u.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <Dropdown
                          width="w-56"
                          disabled={roleMutation.isPending}
                          label={<span className="capitalize">{humanRole(u.role)}</span>}
                          icon={<ShieldCheck className="h-3.5 w-3.5 text-content-2" />}
                        >
                          {(close) => (
                            <>
                              <DropdownLabel>System role</DropdownLabel>
                              {ROLES.map((r) => (
                                <DropdownItem
                                  key={r}
                                  selected={r === u.role}
                                  hint={r === u.role ? "current" : undefined}
                                  onSelect={() => {
                                    close();
                                    if (r !== u.role) roleMutation.mutate({ id: u.id, role: r });
                                  }}
                                >
                                  <span className="capitalize">{humanRole(r)}</span>
                                </DropdownItem>
                              ))}
                            </>
                          )}
                        </Dropdown>
                      </td>
                      <td className="px-3 py-2.5">
                        <button
                          type="button"
                          disabled={statusMutation.isPending}
                          title={u.is_active ? "Deactivate this account" : "Activate this account"}
                          onClick={() => statusMutation.mutate({ id: u.id, isActive: !u.is_active })}
                          className="rounded-[10px] transition-opacity hover:opacity-75 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Badge tone={u.is_active ? "green" : "slate"}>
                            {u.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </button>
                      </td>
                      <td className="tnum px-3 py-2.5 text-2xs text-content-3">
                        {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                      </td>
                      <td className="tnum px-3 py-2.5 text-2xs text-content-2">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-2 py-2.5 text-right">
                        <Dropdown
                          variant="ghost"
                          align="right"
                          width="w-60"
                          title={`Actions for ${u.full_name}`}
                          label={<span className="sr-only">User actions</span>}
                          icon={<MoreVertical className="h-4 w-4" />}
                          className="inline-block [&>button>svg:last-child]:hidden"
                        >
                          {(close) => (
                            <>
                              <DropdownLabel>{u.email}</DropdownLabel>
                              <DropdownItem
                                icon={<Copy className="h-3.5 w-3.5" />}
                                onSelect={() => {
                                  navigator.clipboard
                                    ?.writeText(u.email)
                                    .then(() => toast.success("Email copied", u.email))
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
                                  window.location.href = `mailto:${u.email}`;
                                }}
                              >
                                Compose email
                              </DropdownItem>
                              <DropdownSeparator />
                              <DropdownItem
                                danger={u.is_active}
                                icon={<Power className="h-3.5 w-3.5" />}
                                disabled={statusMutation.isPending}
                                onSelect={() => {
                                  close();
                                  statusMutation.mutate({ id: u.id, isActive: !u.is_active });
                                }}
                              >
                                {u.is_active ? "Deactivate account" : "Activate account"}
                              </DropdownItem>
                            </>
                          )}
                        </Dropdown>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      <CreateUserModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UserAdminCreate>({ defaultValues: { role: "SITE_SUPERVISOR" } });

  const mutation = useMutation({
    mutationFn: (payload: UserAdminCreate) => usersApi.create(payload),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      reset();
      onClose();
      toast.success("User created", `${created.full_name} · ${created.email}`);
    },
    onError: (err) =>
      toast.error(
        "Could not create user",
        err instanceof ApiError
          ? err.code === "CONFLICT"
            ? "That email already has an account."
            : err.message
          : undefined,
      ),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New user"
      subtitle="Creates the account directly — the person signs in with the temporary password you set."
    >
      <form className="space-y-4" onSubmit={handleSubmit((values) => mutation.mutate(values))}>
        <Field label="Full name" error={errors.full_name?.message}>
          <Input placeholder="Anita Barua" {...register("full_name", { required: "Required" })} />
        </Field>

        <Field label="Email" error={errors.email?.message}>
          <Input
            type="email"
            placeholder="anita@oil-india.example"
            {...register("email", { required: "Required" })}
          />
        </Field>

        <Field
          label="Temporary password"
          error={errors.password?.message}
          hint="At least 8 characters. Ask them to change it after the first sign-in."
        >
          <Input
            type="password"
            placeholder="••••••••"
            {...register("password", {
              required: "Required",
              minLength: { value: 8, message: "At least 8 characters" },
            })}
          />
        </Field>

        <Field label="System role">
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

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Create user
          </Button>
        </div>
      </form>
    </Modal>
  );
}
