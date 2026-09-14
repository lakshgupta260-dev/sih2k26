import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import { Check, ChevronDown } from "lucide-react";

/* ------------------------------------------------------------------ shell */

interface DropdownProps {
  /** Rendered inside the trigger button. */
  label: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  /** Width of the floating panel. */
  width?: string;
  icon?: ReactNode;
  /** Small count/《state》 pill on the trigger. */
  badge?: ReactNode;
  variant?: "button" | "ghost" | "bare";
  className?: string;
  panelClassName?: string;
  disabled?: boolean;
  title?: string;
}

/**
 * A floating menu with the keyboard behaviour people expect: Escape closes,
 * arrows move through items, Enter activates, Tab or an outside click
 * dismisses. Focus returns to the trigger on close so keyboard users don't get
 * dropped at the top of the document.
 */
export function Dropdown({
  label,
  children,
  align = "left",
  width = "w-56",
  icon,
  badge,
  variant = "button",
  className,
  panelClassName,
  disabled,
  title,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const items = Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>("[data-menu-item]:not([disabled])") ?? [],
      );
      if (items.length === 0) return;
      e.preventDefault();
      const current = items.indexOf(document.activeElement as HTMLElement);
      const next =
        e.key === "ArrowDown"
          ? items[(current + 1 + items.length) % items.length]
          : items[(current - 1 + items.length) % items.length];
      next?.focus();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [open, close]);

  const variants = {
    button:
      "h-8 rounded-full border border-line-strong bg-overlay-1 px-3 text-content-1 hover:border-white/25 hover:bg-overlay-2",
    ghost: "h-8 rounded-full px-2.5 text-content-2 hover:bg-overlay-1 hover:text-content-1",
    bare: "rounded-full",
  };

  return (
    <div ref={rootRef} className={clsx("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        title={title}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={clsx(
          "inline-flex max-w-full items-center gap-1.5 text-2xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
          variants[variant],
        )}
      >
        {icon}
        <span className="truncate">{label}</span>
        {badge}
        {variant !== "bare" && (
          <ChevronDown
            className={clsx("h-3 w-3 shrink-0 text-content-2 transition-transform", open && "rotate-180")}
          />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            id={menuId}
            role="menu"
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
            className={clsx(
              "absolute z-50 mt-1.5 origin-top overflow-hidden rounded-[14px] border border-line bg-surface-raised p-1 shadow-float",
              align === "right" ? "right-0" : "left-0",
              width,
              panelClassName,
            )}
          >
            {children(close)}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ items */

export function DropdownItem({
  children,
  onSelect,
  icon,
  selected,
  danger,
  hint,
  disabled,
}: {
  children: ReactNode;
  onSelect?: () => void;
  icon?: ReactNode;
  selected?: boolean;
  danger?: boolean;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      data-menu-item
      disabled={disabled}
      onClick={onSelect}
      className={clsx(
        "flex w-full items-center gap-2 rounded-[10px] px-2 py-1.5 text-left text-xs transition-colors",
        "focus:outline-none focus-visible:ring-0",
        disabled && "cursor-not-allowed opacity-40",
        danger
          ? "text-rose-700 hover:bg-rose-50 focus:bg-rose-50"
          : selected
            ? "bg-signal-600/25 text-accent"
            : "text-content-1 hover:bg-surface-raised focus:bg-surface-raised",
      )}
    >
      {icon && <span className={clsx("shrink-0", danger ? "text-rose-400" : "text-content-2")}>{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint && <span className="shrink-0 text-2xs text-content-2">{hint}</span>}
      {selected && <Check className="h-3.5 w-3.5 shrink-0 text-accent" />}
    </button>
  );
}

export function DropdownLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-2 pb-1 pt-1.5 text-2xs font-medium text-content-2">
      {children}
    </p>
  );
}

export function DropdownSeparator() {
  return <div className="my-1 h-px bg-surface-raised" />;
}

/* ------------------------------------------------------- select helpers */

export interface Option<T extends string> {
  value: T;
  label: string;
  hint?: string;
  icon?: ReactNode;
}

/** Single-choice dropdown that reads as a labelled value, not a raw <select>. */
export function SelectMenu<T extends string>({
  value,
  options,
  onChange,
  prefix,
  icon,
  width = "w-52",
  align = "left",
  placeholder = "Choose…",
  variant = "button",
}: {
  value: T | "";
  options: Option<T>[];
  onChange: (value: T | "") => void;
  prefix?: string;
  icon?: ReactNode;
  width?: string;
  align?: "left" | "right";
  placeholder?: string;
  variant?: "button" | "ghost";
}) {
  const current = options.find((o) => o.value === value);
  return (
    <Dropdown
      variant={variant}
      icon={icon}
      align={align}
      width={width}
      label={
        <>
          {prefix && <span className="text-content-2">{prefix} </span>}
          <span className="text-content-1">{current?.label ?? placeholder}</span>
        </>
      }
    >
      {(close) => (
        <>
          {options.map((opt) => (
            <DropdownItem
              key={opt.value}
              icon={opt.icon}
              hint={opt.hint}
              selected={opt.value === value}
              onSelect={() => {
                onChange(opt.value);
                close();
              }}
            >
              {opt.label}
            </DropdownItem>
          ))}
        </>
      )}
    </Dropdown>
  );
}

/** Multi-choice filter. An empty selection means "everything", not "nothing". */
export function MultiSelectMenu<T extends string>({
  selected,
  options,
  onChange,
  label,
  icon,
  width = "w-56",
}: {
  selected: T[];
  options: Option<T>[];
  onChange: (next: T[]) => void;
  label: string;
  icon?: ReactNode;
  width?: string;
}) {
  const toggle = (v: T) =>
    onChange(selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v]);

  return (
    <Dropdown
      icon={icon}
      width={width}
      label={label}
      badge={
        selected.length > 0 ? (
          <span className="rounded-full bg-signal-500 px-1.5 py-0.5 text-2xs font-semibold text-white">
            {selected.length}
          </span>
        ) : undefined
      }
    >
      {() => (
        <>
          <div className="max-h-64 overflow-y-auto scroll-slim">
            {options.map((opt) => (
              <DropdownItem
                key={opt.value}
                selected={selected.includes(opt.value)}
                hint={opt.hint}
                onSelect={() => toggle(opt.value)}
              >
                {opt.label}
              </DropdownItem>
            ))}
          </div>
          {selected.length > 0 && (
            <>
              <DropdownSeparator />
              <DropdownItem onSelect={() => onChange([])}>Clear selection</DropdownItem>
            </>
          )}
        </>
      )}
    </Dropdown>
  );
}
