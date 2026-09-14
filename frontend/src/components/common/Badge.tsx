import clsx from "clsx";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CirclePause,
  Loader2,
  ShieldAlert,
  Sparkles,
  UserCheck,
  UserX,
  XCircle,
} from "lucide-react";
import type {
  ActivityStatus,
  GeneratedReportStatus,
  JobStatus,
  MatchStatus,
  ProjectStatus,
  RiskLevel,
} from "@/types/api";

// On a near-black ground a pale tint disappears, so each tone is a low-alpha
// wash of its own hue with the text lifted to the bright end of that ramp.
const TONES = {
  slate: "bg-overlay-1 text-content-2 ring-line-strong",
  green: "bg-teal-400/[0.14] text-teal-300 ring-teal-400/25",
  amber: "bg-amber-400/[0.14] text-amber-300 ring-amber-400/25",
  red: "bg-rose-500/[0.16] text-rose-300 ring-rose-500/30",
  blue: "bg-brand-500/[0.16] text-brand-300 ring-brand-500/30",
  violet: "bg-violet-500/[0.16] text-violet-300 ring-violet-500/30",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({
  children,
  tone = "slate",
  icon,
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-2xs font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

const ICON = "h-3 w-3";

export function RiskBadge({ level }: { level: RiskLevel | null | undefined }) {
  if (!level) return <Badge tone="slate">No forecast</Badge>;
  const map = {
    LOW: { tone: "green", icon: <CheckCircle2 className={ICON} /> },
    MEDIUM: { tone: "amber", icon: <AlertTriangle className={ICON} /> },
    HIGH: { tone: "red", icon: <AlertTriangle className={ICON} /> },
    CRITICAL: { tone: "red", icon: <ShieldAlert className={ICON} /> },
  } as const;
  const { tone, icon } = map[level];
  return (
    <Badge tone={tone} icon={icon} className={level === "CRITICAL" ? "font-semibold" : undefined}>
      {level}
    </Badge>
  );
}

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  const map = {
    AUTO_MATCHED: { tone: "green", icon: <Sparkles className={ICON} />, label: "Auto-matched" },
    NEEDS_REVIEW: { tone: "amber", icon: <AlertTriangle className={ICON} />, label: "Needs review" },
    UNMATCHED: { tone: "slate", icon: <CircleDashed className={ICON} />, label: "Unmatched" },
    MANUALLY_CONFIRMED: { tone: "blue", icon: <UserCheck className={ICON} />, label: "Confirmed" },
    MANUALLY_REJECTED: { tone: "red", icon: <UserX className={ICON} />, label: "Rejected" },
  } as const;
  const cfg = map[status] ?? { tone: "slate" as const, icon: null, label: String(status) };
  return (
    <Badge tone={cfg.tone} icon={cfg.icon}>
      {cfg.label}
    </Badge>
  );
}

export function ActivityStatusBadge({ status }: { status: ActivityStatus }) {
  const map = {
    NOT_STARTED: { tone: "slate", icon: <CircleDashed className={ICON} />, label: "Not started" },
    IN_PROGRESS: { tone: "amber", icon: <Loader2 className={ICON} />, label: "In progress" },
    COMPLETED: { tone: "green", icon: <CheckCircle2 className={ICON} />, label: "Completed" },
    SUSPENDED: { tone: "red", icon: <CirclePause className={ICON} />, label: "Suspended" },
  } as const;
  const cfg = map[status] ?? { tone: "slate" as const, icon: null, label: String(status) };
  return (
    <Badge tone={cfg.tone} icon={cfg.icon}>
      {cfg.label}
    </Badge>
  );
}

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  const map: Record<ProjectStatus, Tone> = {
    PLANNING: "slate",
    ACTIVE: "green",
    ON_HOLD: "amber",
    COMPLETED: "blue",
    CANCELLED: "red",
  };
  return (
    <Badge tone={map[status] ?? "slate"}>
      <span
        className={clsx(
          "mr-0.5 h-1.5 w-1.5 rounded-full",
          status === "ACTIVE" ? "bg-teal-400" : "bg-current opacity-50",
        )}
      />
      {String(status).replaceAll("_", " ")}
    </Badge>
  );
}

export function JobStatusBadge({ status }: { status: JobStatus | GeneratedReportStatus }) {
  const map: Record<string, { tone: Tone; icon: ReactNode }> = {
    PENDING: { tone: "slate", icon: <CircleDashed className={ICON} /> },
    PROCESSING: { tone: "amber", icon: <Loader2 className={clsx(ICON, "animate-spin")} /> },
    GENERATING: { tone: "amber", icon: <Loader2 className={clsx(ICON, "animate-spin")} /> },
    COMPLETED: { tone: "green", icon: <CheckCircle2 className={ICON} /> },
    FAILED: { tone: "red", icon: <XCircle className={ICON} /> },
  };
  const cfg = map[status] ?? { tone: "slate" as const, icon: null };
  return (
    <Badge tone={cfg.tone} icon={cfg.icon}>
      {String(status).toLowerCase()}
    </Badge>
  );
}

/**
 * Confidence is the whole point of the matching UI, so it gets a real visual
 * treatment: the bar is coloured by which side of the configured thresholds
 * the score falls on (auto ≥ 0.82, review ≥ 0.55), not by an arbitrary ramp.
 */
export function ConfidenceBar({
  value,
  width = "w-24",
  showLabel = true,
}: {
  value: number;
  width?: string;
  showLabel?: boolean;
}) {
  const pct = Math.round(value * 100);
  const tone =
    pct >= 82 ? "bg-teal-400" : pct >= 55 ? "bg-amber-400" : pct > 0 ? "bg-rose-400" : "bg-white/20";
  return (
    <div className="flex items-center gap-2">
      <div className={clsx("h-1.5 overflow-hidden rounded-full bg-overlay-2", width)}>
        <div
          className={clsx("h-full rounded-full transition-[width] duration-700 ease-out", tone)}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      {showLabel && <span className="tnum text-2xs font-medium text-content-2">{pct}%</span>}
    </div>
  );
}
