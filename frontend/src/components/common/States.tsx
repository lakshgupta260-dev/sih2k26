import type { ReactNode } from "react";
import clsx from "clsx";
import { AlertCircle, Inbox, Lock, RotateCw, SearchX, WifiOff } from "lucide-react";
import { ApiError } from "@/api/client";
import { Button, Skeleton } from "@/components/ui/Primitives";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-16 text-sm text-content-3">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-signal-500" />
      {label}
    </div>
  );
}

/** Card-shaped skeleton for dashboards — closer to the final layout than a spinner. */
export function LoadingCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-[14px] border border-line bg-surface-card p-4 shadow-card">
          <Skeleton className="h-2.5 w-20" />
          <Skeleton className="mt-3 h-7 w-24" />
          <Skeleton className="mt-3 h-2 w-28" />
        </div>
      ))}
    </div>
  );
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-1">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

/**
 * Distinguishes the cases that actually need different words from the user's
 * point of view. The backend answers "you are not a member of this project"
 * with 404 by design (so project ids can't be probed), so a 404 under a
 * project route is reported as access, not as a missing page.
 */
export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error?: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const apiError = error instanceof ApiError ? error : undefined;
  const status = apiError?.status;
  const message =
    apiError?.message ?? (error instanceof Error ? error.message : "Please try again.");

  let icon = <AlertCircle className="h-5 w-5" />;
  let heading = title ?? "Something went wrong";
  let detail = message;
  let canRetry = true;

  if (status === undefined && apiError?.code === "NETWORK_ERROR") {
    icon = <WifiOff className="h-5 w-5" />;
    heading = "Can't reach the server";
    detail = "The API didn't respond. Check that the backend is running, then retry.";
  } else if (status === 404) {
    icon = <SearchX className="h-5 w-5" />;
    heading = "Not found, or not shared with you";
    detail =
      "This either doesn't exist or isn't visible to your account. Ask a project manager to add you as a member.";
    canRetry = false;
  } else if (status === 403) {
    icon = <Lock className="h-5 w-5" />;
    heading = "You don't have permission";
    detail = message;
    canRetry = false;
  } else if (status === 429) {
    heading = "Too many requests";
    detail = message;
  }

  return (
    <div className="flex flex-col items-center gap-3 rounded-[14px] border border-rose-200/70 bg-rose-50/50 px-6 py-10 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-100 text-rose-600">
        {icon}
      </span>
      <div>
        <p className="text-sm font-semibold text-rose-900">{heading}</p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-rose-700/90">{detail}</p>
      </div>
      {onRetry && canRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <RotateCw className="h-3.5 w-3.5" />
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  compact,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex flex-col items-center gap-3 rounded-[14px] border border-dashed border-line text-center",
        compact ? "px-4 py-8" : "px-6 py-14",
      )}
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-[14px] bg-surface-card text-content-2 shadow-card ring-1 ring-line">
        {icon ?? <Inbox className="h-5 w-5" />}
      </span>
      <div>
        <p className="text-sm font-medium text-content-1">{title}</p>
        {description && (
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-content-3">{description}</p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
