import { NavLink, Outlet, Link, useLocation } from "react-router-dom";
import clsx from "clsx";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  CalendarRange,
  ChevronRight,
  FileBarChart,
  GitCompareArrows,
  Layers,
  LayoutDashboard,
  MapPin,
  Radio,
  Settings as SettingsIcon,
  ShieldAlert,
  Upload,
  Users,
} from "lucide-react";
import { ProjectProvider, useProject } from "@/context/ProjectContext";
import { ErrorState, LoadingCards } from "@/components/common/States";
import { ProjectStatusBadge } from "@/components/common/Badge";
import { Skeleton } from "@/components/ui/Primitives";

// Screens whose content depends on which baseline is selected.
const SCHEDULE_SCOPED = new Set(["", "risks", "matching"]);

const TABS = [
  { to: "", label: "Overview", end: true, icon: LayoutDashboard },
  { to: "schedule", label: "Schedule", icon: CalendarRange },
  { to: "uploads", label: "Site Reports", icon: Upload },
  { to: "matching", label: "AI Matching", icon: GitCompareArrows },
  { to: "risks", label: "Risk & Delay", icon: ShieldAlert },
  { to: "reports", label: "Reports", icon: FileBarChart },
  { to: "channels", label: "Voice & WhatsApp", icon: Radio },
  { to: "members", label: "Members", icon: Users },
  { to: "settings", label: "Settings", icon: SettingsIcon },
] as const;

/** The tab that owns the current URL, so the breadcrumb can name where you are.
 *  `activities/...` has no tab of its own — it belongs under Schedule. */
function resolveActiveTab(pathname: string, projectId: string | undefined) {
  if (!projectId) return undefined;
  const rest = pathname.split(`/projects/${projectId}`)[1]?.replace(/^\//, "") ?? "";
  if (!rest) return undefined; // Overview is the index route; no third crumb.
  const segment = rest.split("/")[0];
  if (segment === "activities") return TABS.find((t) => t.to === "schedule");
  return TABS.find((t) => t.to === segment);
}

function ProjectLayoutInner() {
  const { project, isLoading, error, schedules, selectedSchedule, selectSchedule } = useProject();
  const location = useLocation();
  const activeTab = resolveActiveTab(location.pathname, project?.id);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-6 w-72" />
          <Skeleton className="h-3 w-52" />
        </div>
        <Skeleton className="h-9 w-full" />
        <LoadingCards />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="space-y-4">
        <Link
          to="/projects"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-content-3 hover:text-content-1"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          All projects
        </Link>
        <ErrorState error={error} title="Project unavailable" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {/* Breadcrumb, not a bare back link: landing on a tab from a dashboard
              card previously left "All projects" as the only way out, which
              exits the project entirely. The project name returns to Overview. */}
          <nav aria-label="Breadcrumb" className="mb-1.5 flex flex-wrap items-center gap-1.5 text-2xs font-medium">
            <Link
              to="/projects"
              className="inline-flex items-center gap-1.5 text-content-2 transition-colors hover:text-content-1"
            >
              <ArrowLeft className="h-3 w-3" />
              All projects
            </Link>
            {activeTab && (
              <>
                <ChevronRight className="h-3 w-3 text-content-2" aria-hidden />
                <Link
                  to={`/projects/${project.id}`}
                  className="max-w-[16rem] truncate text-content-2 transition-colors hover:text-content-1"
                >
                  {project.name}
                </Link>
                <ChevronRight className="h-3 w-3 text-content-2" aria-hidden />
                <span className="text-content-1" aria-current="page">
                  {activeTab.label}
                </span>
              </>
            )}
          </nav>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-balance font-display text-base font-semibold tracking-[-0.02em] text-content-1 sm:text-2xl">
              {project.name}
            </h1>
            <ProjectStatusBadge status={project.status} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-content-3">
            <span className="text-2xs text-accent">{project.code}</span>
            {project.client_name && <span>{project.client_name}</span>}
            {project.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {project.location}
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Only the schedule-scoped screens read from a baseline, so the
              picker appears only where it changes what you're looking at. */}
          {SCHEDULE_SCOPED.has(activeTab?.to ?? "") && schedules.length > 0 && (
            <label className="flex items-center gap-1.5 rounded-[10px] bg-surface-card px-2.5 py-1.5 text-2xs font-medium text-content-2 shadow-card ring-1 ring-line">
              <Layers className="h-3.5 w-3.5 text-content-2" />
              <span className="text-content-3">Baseline</span>
              <select
                value={selectedSchedule?.id ?? ""}
                onChange={(e) => selectSchedule(e.target.value)}
                className="max-w-[13rem] cursor-pointer truncate bg-transparent text-2xs font-medium text-content-1 focus:outline-none"
              >
                {schedules.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className="rounded-[10px] bg-surface-card px-2.5 py-1.5 text-2xs font-medium text-content-2 shadow-card ring-1 ring-line">
            Your role ·{" "}
            <span className="text-content-1">{project.my_role.replaceAll("_", " ").toLowerCase()}</span>
          </span>
        </div>
      </div>

      <div className="scroll-slim mb-6 -mx-1 overflow-x-auto px-1 pb-1">
        <div className="flex min-w-max gap-0.5 rounded-[14px] border border-line bg-surface-card p-1 shadow-card">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <NavLink
                key={tab.label}
                to={tab.to}
                end={"end" in tab ? tab.end : false}
                className={({ isActive }) =>
                  clsx(
                    "relative flex items-center gap-1.5 whitespace-nowrap rounded-[10px] px-3 py-1.5 text-xs font-medium transition-colors",
                    isActive ? "text-content-1" : "text-content-3 hover:text-content-1",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        layoutId="project-tab"
                        className="absolute inset-0 rounded-[10px] bg-signal-500/12 ring-1 ring-inset ring-signal-500/35"
                        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                      />
                    )}
                    <Icon className="relative h-3.5 w-3.5" />
                    <span className="relative">{tab.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </div>
      </div>

      {/* Re-keying on pathname gives each screen its own entry transition. */}
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      >
        <Outlet />
      </motion.div>
    </div>
  );
}

export function ProjectLayout() {
  return (
    <ProjectProvider>
      <ProjectLayoutInner />
    </ProjectProvider>
  );
}
