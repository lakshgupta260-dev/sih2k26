import { motion } from "framer-motion";
import clsx from "clsx";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  CalendarRange,
  GitCompareArrows,
  ShieldAlert,
  TrendingUp,
  Upload,
} from "lucide-react";
import type { ReactNode } from "react";

export interface PipelineStage {
  key: string;
  label: string;
  /** The live figure for this stage, or null when nothing has happened yet. */
  value: number | null;
  unit?: string;
  caption: string;
  to: string;
  icon: ReactNode;
  state: "empty" | "active" | "attention";
}

/**
 * The end-to-end path this platform exists to close: what was planned, what
 * the site actually reported, what the matcher linked, and what that implies
 * for delivery risk. Each stage links to the screen that owns it, and shows a
 * real count so it doubles as a progress indicator for the whole workflow.
 */
export function PipelineFlow({ stages }: { stages: PipelineStage[] }) {
  return (
    <div className="relative overflow-hidden rounded-[14px] border border-line bg-surface-card shadow-card">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div>
          <h3 className="text-sm font-semibold text-content-1">Plan-to-progress pipeline</h3>
          <p className="mt-0.5 text-xs text-content-3">
            Every stage below is a live count from this project — click through to the detail.
          </p>
        </div>
      </div>

      <div className="scroll-slim overflow-x-auto px-5 py-5">
        <div className="flex min-w-max items-stretch gap-1">
          {stages.map((stage, i) => (
            <div key={stage.key} className="flex items-stretch gap-1">
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}
              >
                <Link
                  to={stage.to}
                  className={clsx(
                    "group flex h-full w-[9.5rem] flex-col rounded-[14px] border p-3 transition-all duration-200",
                    stage.state === "empty" && "border-dashed border-line bg-surface-raised/40 hover:border-line-strong",
                    stage.state === "active" && "border-line bg-surface-card hover:-translate-y-0.5 hover:shadow-lift",
                    stage.state === "attention" &&
                      "border-amber-200 bg-amber-50/50 hover:-translate-y-0.5 hover:shadow-lift",
                  )}
                >
                  <span
                    className={clsx(
                      "flex h-8 w-8 items-center justify-center rounded-[10px]",
                      stage.state === "empty" && "bg-surface-raised text-content-2",
                      stage.state === "active" && "bg-signal-600/25 text-accent",
                      stage.state === "attention" && "bg-amber-100 text-amber-700",
                    )}
                  >
                    {stage.icon}
                  </span>

                  <p className="mt-2.5 text-2xs font-medium text-content-3">
                    {stage.label}
                  </p>

                  <p
                    className={clsx(
                      "tnum mt-1 text-xl font-semibold leading-none",
                      stage.value === null ? "text-content-2" : "text-content-1",
                    )}
                  >
                    {stage.value === null ? "—" : stage.value}
                    {stage.unit && stage.value !== null && (
                      <span className="ml-0.5 text-sm font-medium text-content-2">{stage.unit}</span>
                    )}
                  </p>

                  <p className="mt-1.5 text-2xs leading-snug text-content-2">{stage.caption}</p>
                </Link>
              </motion.div>

              {i < stages.length - 1 && (
                <div className="flex w-6 items-center justify-center">
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.07 + 0.15 }}
                    className={clsx(
                      stages[i + 1].state === "empty" ? "text-content-1" : "text-accent",
                    )}
                  >
                    <ArrowRight className="h-4 w-4" />
                  </motion.span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export const PIPELINE_ICONS = {
  schedule: <CalendarRange className="h-4 w-4" />,
  upload: <Upload className="h-4 w-4" />,
  extract: <BrainCircuit className="h-4 w-4" />,
  match: <GitCompareArrows className="h-4 w-4" />,
  progress: <TrendingUp className="h-4 w-4" />,
  risk: <ShieldAlert className="h-4 w-4" />,
};
