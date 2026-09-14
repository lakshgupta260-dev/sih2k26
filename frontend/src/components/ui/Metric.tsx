import { useEffect, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { motion } from "framer-motion";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

/**
 * Counts up to `value`. The animation is decoration; the number is data.
 *
 * State is seeded with the real value and a watchdog snaps to it if the
 * animation cannot finish, because `requestAnimationFrame` does not fire in a
 * hidden or backgrounded tab — an rAF-driven counter left mid-flight there
 * would sit at its starting figure and silently show a wrong metric.
 * Reduced-motion users skip the animation entirely.
 */
export function AnimatedNumber({
  value,
  decimals = 0,
  suffix = "",
  prefix = "",
  duration = 700,
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
}) {
  const [display, setDisplay] = useState(value);
  const frame = useRef<number>();
  const watchdog = useRef<ReturnType<typeof setTimeout>>();
  const from = useRef(0);

  useEffect(() => {
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const hidden = typeof document !== "undefined" && document.visibilityState === "hidden";

    if (reduceMotion || hidden) {
      from.current = value;
      setDisplay(value);
      return;
    }

    const origin = from.current;
    const delta = value - origin;
    if (delta === 0) {
      setDisplay(value);
      return;
    }

    const start = performance.now();
    setDisplay(origin);

    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      // easeOutExpo — fast settle, no long tail.
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      setDisplay(origin + delta * eased);
      if (t < 1) {
        frame.current = requestAnimationFrame(tick);
      } else {
        from.current = value;
      }
    };
    frame.current = requestAnimationFrame(tick);

    // If the frames never arrive, land on the truth anyway.
    watchdog.current = setTimeout(() => {
      if (frame.current) cancelAnimationFrame(frame.current);
      from.current = value;
      setDisplay(value);
    }, duration + 250);

    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
      if (watchdog.current) clearTimeout(watchdog.current);
    };
  }, [value, duration]);

  return (
    <span className="tnum">
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

export function MetricTile({
  label,
  value,
  unit,
  hint,
  icon,
  tone = "default",
  trend,
  delay = 0,
  onClick,
}: {
  label: string;
  /** Pass a number to animate it; pass a node for "—" / non-numeric states. */
  value: number | ReactNode;
  unit?: string;
  hint?: string;
  icon?: ReactNode;
  tone?: "default" | "positive" | "warning" | "critical";
  trend?: { direction: "up" | "down" | "flat"; label: string; good?: boolean };
  delay?: number;
  onClick?: () => void;
}) {
  const tones = {
    default: { accent: "bg-overlay-1 text-content-1", value: "text-content-1" },
    positive: { accent: "bg-teal-400/15 text-teal-300", value: "text-content-1" },
    warning: { accent: "bg-amber-400/15 text-amber-300", value: "text-amber-300" },
    critical: { accent: "bg-rose-500/15 text-rose-300", value: "text-rose-300" },
  } as const;
  const t = tones[tone];

  const TrendIcon =
    trend?.direction === "up" ? TrendingUp : trend?.direction === "down" ? TrendingDown : Minus;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.16, 1, 0.3, 1] }}
      onClick={onClick}
      className={clsx(
        "group relative overflow-hidden rounded-[18px] bg-surface-card p-5 ring-1 ring-line",
        onClick && "cursor-pointer transition-colors hover:bg-surface-raised",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-content-2">{label}</p>
        {icon && (
          <span className={clsx("flex h-9 w-9 items-center justify-center rounded-full", t.accent)}>
            {icon}
          </span>
        )}
      </div>

      <p className={clsx("mt-3 type-display text-[2.6rem] leading-none tabular-nums", t.value)}>
        {typeof value === "number" ? (
          <>
            <AnimatedNumber value={value} decimals={Number.isInteger(value) ? 0 : 1} />
            {unit && <span className="ml-1 text-2xl font-medium text-content-2">{unit}</span>}
          </>
        ) : (
          value
        )}
      </p>

      {(hint || trend) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {trend && (
            <span
              className={clsx(
                "inline-flex shrink-0 items-center gap-1 text-sm font-medium",
                trend.good === undefined
                  ? "text-content-2"
                  : trend.good
                    ? "text-teal-300"
                    : "text-rose-300",
              )}
            >
              <TrendIcon className="h-3 w-3" />
              {trend.label}
            </span>
          )}
          {hint && <span className="truncate text-sm text-content-2">{hint}</span>}
        </div>
      )}
    </motion.div>
  );
}

/** Thin progress meter used inside cards and table rows. */
export function ProgressMeter({
  value,
  max = 100,
  tone = "brand",
  className,
}: {
  value: number;
  max?: number;
  tone?: "brand" | "teal" | "amber" | "rose";
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tones = {
    brand: "bg-signal-500",
    teal: "bg-teal-500",
    amber: "bg-amber-500",
    rose: "bg-rose-500",
  };
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-overlay-2", className)}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className={clsx("h-full rounded-full", tones[tone])}
      />
    </div>
  );
}
