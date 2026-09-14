import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bell,
  ChevronsLeft,
  ChevronsRight,
  FolderKanban,
  LayoutGrid,
  LogOut,
  Menu,
  Search,
  UserCog,
  User as UserIcon,
  X,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { notificationsApi } from "@/api/notifications";
import { projectsApi } from "@/api/projects";
import { Dropdown, DropdownItem, DropdownLabel, DropdownSeparator } from "@/components/ui/Dropdown";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { healthApi } from "@/api/health";
import { API_BASE_URL } from "@/api/client";
import type { UserRole } from "@/types/api";
import { BrandMark } from "@/components/ui/BrandMark";

const NAV: Array<{ to: string; label: string; icon: typeof FolderKanban; roles?: UserRole[] }> = [
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/admin/users", label: "Users", icon: UserCog, roles: ["ADMIN"] },
  { to: "/profile", label: "Profile", icon: UserIcon },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  // Below lg the rail is an overlay drawer — a 15rem fixed rail would eat most
  // of a phone screen and squeeze the content into an unreadable column.
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  // Collapsing is a desktop affordance; the mobile drawer is always full width,
  // so labels must not be hidden inside it.
  const railCollapsed = drawerOpen ? false : collapsed;

  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 30_000,
  });

  const health = useQuery({
    queryKey: ["health"],
    queryFn: healthApi.live,
    refetchInterval: 30_000,
    retry: 1,
  });

  const initials = (user?.full_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="relative flex min-h-screen">
      {/* Ambient drift behind the whole shell. Purely decorative: no pointer
          events, and the stylesheet removes it under prefers-reduced-motion. */}
      <div className="app-aurora" aria-hidden>
        <span className="a" />
        <span className="b" />
        <span className="c" />
      </div>

      {/* Backdrop for the mobile drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setDrawerOpen(false)}
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-[3px] lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* Command rail — persistent from lg up, off-canvas drawer below it */}
      <aside
        className={clsx(
          "relative z-10 flex h-screen flex-col border-r border-line bg-surface-base/70 text-content-1 backdrop-blur-xl",
          "fixed inset-y-0 left-0 z-50 w-64 transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
          "lg:sticky lg:top-0 lg:z-auto lg:shrink-0 lg:translate-x-0 lg:transition-[width]",
          collapsed ? "lg:w-[4.75rem]" : "lg:w-64",
        )}
      >
        <button
          onClick={() => setDrawerOpen(false)}
          aria-label="Close navigation"
          className="absolute right-3 top-4 rounded-[10px] p-1.5 text-content-2 transition-colors hover:bg-overlay-2 hover:text-content-1 lg:hidden"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="flex items-center gap-3 px-5 py-6">
          <BrandMark size="lg" className="relative z-10" />
          {!railCollapsed && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="relative z-10 min-w-0 truncate type-display text-[1.35rem] text-content-1"
            >
              Plan2Progress
            </motion.p>
          )}
        </div>

        <nav className="relative z-10 flex-1 space-y-1 px-3">
          {NAV.filter((item) => !item.roles || (user && item.roles.includes(user.role))).map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                title={railCollapsed ? item.label : undefined}
                className={({ isActive }) =>
                  clsx(
                    "group relative flex items-center gap-3.5 rounded-[12px] px-3.5 py-2.5 text-[1.05rem] font-medium transition-colors",
                    isActive ? "text-surface-base" : "text-content-2 hover:bg-overlay-1 hover:text-content-1",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        layoutId="rail-active"
                        className="absolute inset-0 rounded-[12px] bg-content-1"
                        transition={{ duration: 0.3, ease: [0.28, 0.11, 0.32, 1] }}
                      />
                    )}
                    <Icon className="relative h-[1.3rem] w-[1.3rem] shrink-0" />
                    {!railCollapsed && <span className="relative flex-1 truncate">{item.label}</span>}
                    {item.label === "Notifications" && !!unread?.count && (
                      <span
                        className={clsx(
                          "relative rounded-full bg-signal-600 text-center text-2xs font-semibold text-content-1",
                          collapsed
                            ? "absolute right-1.5 top-1.5 h-1.5 w-1.5 p-0"
                            : "min-w-[1.25rem] px-1.5 py-0.5",
                        )}
                      >
                        {railCollapsed ? "" : unread.count}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Backend health — a demo that silently lost its API is worse than one
            that says so. */}
        <div className="relative z-10 px-3 pb-2">
          <div
            title={health.isError ? `No response from ${API_BASE_URL}` : `Connected to ${API_BASE_URL}`}
            className={clsx(
              "flex items-center gap-2.5 rounded-[12px] px-3.5 py-2.5 text-sm",
              health.isError ? "bg-rose-500/15 text-rose-200" : "text-content-2",
            )}
          >
            <span className="relative flex h-2 w-2 shrink-0">
              <span
                className={clsx(
                  "absolute inline-flex h-full w-full rounded-full",
                  health.isError ? "bg-rose-400" : "animate-pulse-ring bg-teal-400",
                )}
              />
              <span
                className={clsx(
                  "relative inline-flex h-2 w-2 rounded-full",
                  health.isError ? "bg-rose-400" : "bg-teal-400",
                )}
              />
            </span>
            {!railCollapsed && (
              <span className="truncate">
                {health.isError ? "API unreachable" : `API ${health.data?.environment ?? "online"}`}
              </span>
            )}
          </div>
        </div>

        <div className="relative z-10 border-t border-line-strong p-3">
          <div className={clsx("flex items-center gap-3 rounded-[12px] px-2.5 py-2", railCollapsed && "justify-center px-0")}>
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-card/10 text-sm font-semibold text-content-1">
              {initials}
            </span>
            {!railCollapsed && (
              <div className="min-w-0 flex-1">
                <p className="truncate text-[1rem] font-medium text-content-1">{user?.full_name}</p>
                <p className="truncate text-sm text-content-2">
                  {user?.role.replaceAll("_", " ").toLowerCase()}
                </p>
              </div>
            )}
            {!railCollapsed && (
              <button
                onClick={async () => {
                  await logout();
                  navigate("/login");
                }}
                title="Sign out"
                className="rounded-full p-2 text-content-2 transition-colors hover:bg-overlay-2 hover:text-content-1"
              >
                <LogOut className="h-[1.15rem] w-[1.15rem]" />
              </button>
            )}
          </div>

          <button
            onClick={() => setCollapsed((c) => !c)}
            className="mt-1.5 hidden w-full items-center justify-center gap-2 rounded-[12px] px-2 py-2 text-sm text-content-2 transition-colors hover:bg-overlay-1 hover:text-content-1 lg:flex"
          >
            {railCollapsed ? <ChevronsRight className="h-3.5 w-3.5" /> : <ChevronsLeft className="h-3.5 w-3.5" />}
            {!railCollapsed && "Collapse"}
          </button>
        </div>
      </aside>

      {/* Content */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line px-4 sm:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              className="-ml-1 shrink-0 rounded-[10px] p-2 text-content-2 transition-colors hover:bg-surface-raised lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
              className="group flex h-8 w-full max-w-xs items-center gap-2 rounded-[10px] border border-line bg-surface-card px-2.5 text-left text-xs text-content-2 transition-colors hover:border-line-strong hover:text-content-2"
            >
              <Search className="h-3.5 w-3.5 shrink-0" />
              <span className="flex-1 truncate">Search…</span>
              <kbd className="hidden shrink-0 rounded border border-line px-1 py-0.5 text-2xs text-content-2 group-hover:border-line-strong sm:block">
                ⌘K
              </kbd>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <ProjectSwitcher />
            <ThemeToggle />
            <NotificationsMenu count={unread?.count ?? 0} />
            <UserMenu />
          </div>
        </header>

        <main className="min-w-0 flex-1">
          <div className="mx-auto w-full max-w-[88rem] px-4 py-5 sm:px-6 sm:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- header menus */

/** Jump between projects without going back to the list first. */
function ProjectSwitcher() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId?: string }>();
  const { data, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list({ limit: 100 }),
    staleTime: 60_000,
  });

  const projects = data?.items ?? [];
  const current = projects.find((p) => p.id === projectId);

  return (
    <Dropdown
      icon={<FolderKanban className="h-3.5 w-3.5 text-content-2" />}
      label={current ? current.code : "Projects"}
      width="w-72"
      align="right"
      title="Switch project"
    >
      {(close) => (
        <>
          <DropdownLabel>Switch to</DropdownLabel>
          {isLoading && <p className="px-2 py-2 text-2xs text-content-2">Loading…</p>}
          {!isLoading && projects.length === 0 && (
            <p className="px-2 py-2 text-2xs text-content-2">No projects yet.</p>
          )}
          <div className="max-h-72 overflow-y-auto scroll-slim">
            {projects.map((p) => (
              <DropdownItem
                key={p.id}
                selected={p.id === projectId}
                hint={p.code}
                onSelect={() => {
                  navigate(`/projects/${p.id}`);
                  close();
                }}
              >
                {p.name}
              </DropdownItem>
            ))}
          </div>
          <DropdownSeparator />
          <DropdownItem
            icon={<LayoutGrid className="h-3.5 w-3.5" />}
            onSelect={() => {
              navigate("/projects");
              close();
            }}
          >
            All projects
          </DropdownItem>
        </>
      )}
    </Dropdown>
  );
}

/** Recent notifications inline, so the bell answers "what changed?" in place. */
function NotificationsMenu({ count }: { count: number }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => notificationsApi.list({ limit: 6 }),
    refetchInterval: 60_000,
  });

  const markAll = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const items = data?.items ?? [];

  return (
    <Dropdown
      variant="ghost"
      align="right"
      width="w-80"
      title="Notifications"
      label={
        <span className="relative flex items-center">
          <Bell className="h-4 w-4" />
          {count > 0 && (
            <span className="absolute -right-1 -top-1 h-1.5 w-1.5 bg-signal-500 ring-2 ring-white" />
          )}
        </span>
      }
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between px-2 pb-1 pt-1.5">
            <span className="text-2xs font-medium text-content-2">
              Notifications
            </span>
            {count > 0 && (
              <button
                onClick={() => markAll.mutate()}
                className="text-2xs font-medium text-accent hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>
          {isLoading && <p className="px-2 py-3 text-2xs text-content-2">Loading…</p>}
          {!isLoading && items.length === 0 && (
            <p className="px-2 py-4 text-center text-2xs text-content-2">Nothing yet.</p>
          )}
          <div className="max-h-80 overflow-y-auto scroll-slim">
            {items.map((n) => (
              <div
                key={n.id}
                className={clsx(
                  "rounded-[10px] px-2 py-2",
                  !n.read_at && "bg-signal-600/25/50",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-xs font-medium text-content-1">{n.title}</p>
                  <span className="shrink-0 text-2xs text-content-2">
                    {new Date(n.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="mt-0.5 line-clamp-2 text-2xs leading-relaxed text-content-3">{n.body}</p>
              </div>
            ))}
          </div>
          <DropdownSeparator />
          <DropdownItem
            onSelect={() => {
              navigate("/notifications");
              close();
            }}
          >
            See all notifications
          </DropdownItem>
        </>
      )}
    </Dropdown>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const initials = (user?.full_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <Dropdown
      variant="bare"
      align="right"
      width="w-56"
      title={user?.full_name}
      label={
        <span className="flex h-8 w-8 items-center justify-center bg-ink-950 font-mono text-2xs font-semibold text-accent">
          {initials}
        </span>
      }
    >
      {(close) => (
        <>
          <div className="px-2 pb-1.5 pt-1">
            <p className="truncate text-xs font-medium text-content-1">{user?.full_name}</p>
            <p className="truncate text-2xs text-content-3">{user?.email}</p>
            <p className="mt-1 inline-block rounded bg-surface-raised px-1.5 py-0.5 text-2xs font-medium text-content-2">
              {user?.role.replaceAll("_", " ").toLowerCase()}
            </p>
          </div>
          <DropdownSeparator />
          <DropdownItem
            icon={<UserIcon className="h-3.5 w-3.5" />}
            onSelect={() => {
              navigate("/profile");
              close();
            }}
          >
            Profile &amp; password
          </DropdownItem>
          {user?.role === "ADMIN" && (
            <DropdownItem
              icon={<UserCog className="h-3.5 w-3.5" />}
              onSelect={() => {
                navigate("/admin/users");
                close();
              }}
            >
              User administration
            </DropdownItem>
          )}
          <DropdownSeparator />
          <DropdownItem
            danger
            icon={<LogOut className="h-3.5 w-3.5" />}
            onSelect={async () => {
              close();
              await logout();
              navigate("/login");
            }}
          >
            Sign out
          </DropdownItem>
        </>
      )}
    </Dropdown>
  );
}
