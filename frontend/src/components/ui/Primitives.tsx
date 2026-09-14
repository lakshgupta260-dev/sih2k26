import clsx from "clsx";
import { forwardRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

/* ------------------------------------------------------------------ button */

const BUTTON_VARIANTS = {
  primary:
    "bg-content-1 text-surface-base hover:opacity-90 active:opacity-80 disabled:bg-overlay-2 disabled:text-content-3",
  signal:
    "bg-signal-600 text-white hover:bg-signal-500 active:bg-signal-700 disabled:bg-overlay-2 disabled:text-content-3",
  secondary:
    "bg-overlay-1 text-content-1 ring-1 ring-inset ring-line-strong hover:bg-overlay-2 active:bg-overlay-3 disabled:text-content-3",
  ghost: "text-content-2 hover:bg-overlay-1 hover:text-content-1 disabled:text-content-3",
  danger:
    "bg-rose-600 text-white hover:bg-rose-500 active:bg-rose-700 disabled:bg-overlay-2 disabled:text-content-3",
  dark: "bg-overlay-1 text-content-1 hover:bg-overlay-2 active:bg-overlay-3 disabled:text-content-3",
} as const;

// The reference pads buttons generously and keeps the label at reading size —
// a small pill with a big horizontal inset, never a cramped chip.
const BUTTON_SIZES = {
  xs: "h-7 gap-1 px-3 text-2xs",
  sm: "h-8 gap-1.5 px-3.5 text-xs",
  md: "h-9 gap-2 px-5 text-sm",
  lg: "h-11 gap-2 px-7 text-sm",
  xl: "h-12 gap-2 px-8 text-base",
} as const;

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: keyof typeof BUTTON_VARIANTS;
    size?: keyof typeof BUTTON_SIZES;
    loading?: boolean;
  }
>(({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => (
  <button
    ref={ref}
    disabled={disabled || loading}
    className={clsx(
      "inline-flex select-none items-center justify-center whitespace-nowrap rounded-full font-normal",
      "transition-[background-color,color,opacity] duration-200",
      "active:opacity-80 disabled:cursor-not-allowed disabled:active:opacity-100",
      BUTTON_VARIANTS[variant],
      BUTTON_SIZES[size],
      className,
    )}
    {...props}
  >
    {loading && <Spinner className="h-3.5 w-3.5" />}
    {children}
  </button>
));
Button.displayName = "Button";

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={clsx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-90"
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* -------------------------------------------------------------------- card */

export function Card({
  children,
  className,
  interactive,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}) {
  return (
    <div
      className={clsx(
        "rounded-[18px] bg-surface-card ring-1 ring-line",
        interactive && "transition-colors duration-300 hover:bg-surface-raised",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  icon,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    // Wraps rather than crushes: a header carrying several filter menus used to
    // squeeze the title into a one-character column because the action block
    // was shrink-0 and won the fight for width.
    <div className={clsx("flex flex-wrap items-start justify-between gap-x-3 gap-y-2.5 border-b border-line px-6 py-4", className)}>
      <div className="flex min-w-[12rem] flex-1 items-start gap-2.5">
        {icon && (
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-overlay-1 text-content-1">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h3 className="type-display truncate text-[1.2rem] text-content-1">{title}</h3>
          {subtitle && <p className="mt-1 text-sm leading-relaxed text-content-3">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ inputs */

const FIELD_BASE =
  "w-full rounded-[12px] border border-line-strong bg-surface-raised px-3.5 text-sm text-content-1 placeholder:text-content-3 " +
  "transition-colors duration-200 hover:border-line-strong " +
  "focus:border-signal-500 focus:outline-none focus:ring-[3px] focus:ring-signal-500/20 " +
  "disabled:bg-overlay-1 disabled:text-content-3";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={clsx(FIELD_BASE, "h-10", className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={clsx(FIELD_BASE, "py-2 leading-relaxed", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={clsx(FIELD_BASE, "h-10 cursor-pointer pr-8", className)} {...props}>
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium text-content-2">
      {children}
    </label>
  );
}

export function Field({
  label,
  children,
  error,
  hint,
  className,
}: {
  label: string;
  children: ReactNode;
  error?: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label>{label}</Label>
      {children}
      {hint && !error && <p className="mt-1 text-2xs text-content-2">{hint}</p>}
      {error && <p className="mt-1 text-2xs font-medium text-rose-600">{error}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------- modal */

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  size?: "md" | "lg" | "xl";
}) {
  const widths = { md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/70 backdrop-blur-[3px]"
          />
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={clsx(
              "rounded-[18px] relative flex max-h-full w-full flex-col overflow-hidden bg-surface-card shadow-float ring-1 ring-line",
              widths[size],
            )}
          >
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4">
              <div>
                <h3 className="type-display text-lg text-content-1">{title}</h3>
                {subtitle && <p className="mt-0.5 text-xs text-content-3">{subtitle}</p>}
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="-m-1 rounded-full p-1.5 text-content-3 transition-colors hover:bg-surface-raised hover:text-content-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="scroll-slim overflow-y-auto px-5 py-4">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------- progress */

/** Determinate progress for uploads, with the percentage spelled out. */
export function ProgressBarInline({ value, label }: { value: number; label?: string }) {
  return (
    <div>
      {label && <p className="mb-1.5 text-2xs font-medium text-content-2">{label}</p>}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-overlay-2">
        <div
          className="h-full rounded-full bg-signal-500 transition-[width] duration-200 ease-out"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- skeletons */

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2.5">
      <div className="flex gap-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-8 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ layout */

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="type-display text-[2.1rem] text-content-1">{title}</h2>
        {subtitle && <p className="mt-2 max-w-2xl text-[1.05rem] leading-relaxed text-content-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Divider({ label }: { label?: string }) {
  if (!label) return <div className="h-px w-full bg-surface-raised" />;
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-surface-raised" />
      <span className="text-2xs font-medium text-content-2">{label}</span>
      <div className="h-px flex-1 bg-surface-raised" />
    </div>
  );
}
