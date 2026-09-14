import type { ReactNode } from "react";
import clsx from "clsx";
import { motion } from "framer-motion";

/**
 * Landing furniture in the Apple product-page idiom: full-bleed sections whose
 * only separator is a change of ground colour, a small muted eyebrow, and one
 * very large centred statement. No rules, no numbering, no outlined panels —
 * the whitespace and the type size carry the hierarchy.
 */

/**
 * Scroll reveal. Driven by framer-motion rather than `animation-timeline: view()`
 * so it runs in every browser, and `once` means content that has appeared stays
 * put instead of flickering back out when the user scrolls up.
 */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 36 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.85, delay, ease: [0.28, 0.11, 0.32, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function Section({
  id,
  eyebrow,
  title,
  lead,
  children,
  tone = "light",
  align = "center",
  className,
}: {
  id?: string;
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
  tone?: "light" | "white" | "dark" | "near";
  align?: "center" | "left";
  className?: string;
}) {
  // Every band is theme-aware. The emphasis bands are the darkest thing on a
  // light page and the *lightest* on a dark one, so the alternation that gives
  // the page its rhythm survives in both.
  const tones = {
    light: "bg-band-1 text-content-1",
    white: "bg-band-2 text-content-1",
    dark: "bg-band-3 text-onband",
    near: "bg-band-4 text-onband",
  };
  const dark = tone === "dark" || tone === "near";
  const centred = align === "center";

  return (
    <section id={id} className={clsx("relative overflow-hidden py-28 sm:py-36", tones[tone], className)}>
      <div className="mx-auto w-full max-w-[72rem] px-6 lg:px-8">
        <Reveal className={clsx(centred && "text-center")}>
          {eyebrow && <p className={clsx("eyebrow", dark && "text-onband/60")}>{eyebrow}</p>}

          <h2
            className={clsx(
              "type-display mt-3 text-[2.8rem] leading-[1.05] sm:text-[4rem]",
              centred ? "mx-auto max-w-4xl" : "max-w-4xl",
              dark ? "text-onband" : "text-content-1",
            )}
          >
            {title}
          </h2>

          {lead && (
            <p
              className={clsx(
                "mt-7 text-[1.3rem] leading-[1.55]",
                centred ? "mx-auto max-w-2xl" : "max-w-2xl",
                dark ? "text-onband/65" : "text-content-2",
              )}
            >
              {lead}
            </p>
          )}
        </Reveal>

        {children && <Reveal delay={0.1} className="mt-16">{children}</Reveal>}
      </div>
    </section>
  );
}

/** A soft, borderless surface. Separation comes from ground colour, not outline. */
export function Panel({
  children,
  className,
  dark,
  interactive,
}: {
  children: ReactNode;
  className?: string;
  dark?: boolean;
  interactive?: boolean;
}) {
  return (
    <div
      className={clsx(
        "relative rounded-[22px]",
        dark ? "bg-onband/[0.07]" : "bg-surface-card",
        interactive &&
          "transition-[transform,box-shadow] duration-500 ease-[cubic-bezier(0.28,0.11,0.32,1)] hover:-translate-y-1 hover:shadow-lift",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Key/value line used in the spec blocks under a statement. */
export function Spec({
  label,
  value,
  dark,
}: {
  label: string;
  value: ReactNode;
  dark?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex items-baseline justify-between gap-4 border-b py-3.5 last:border-b-0",
        dark ? "border-onband/15" : "border-line",
      )}
    >
      <span className={clsx("text-sm", dark ? "text-onband/60" : "text-content-3")}>{label}</span>
      <span
        className={clsx(
          "text-right text-[1.05rem] font-medium tabular-nums",
          dark ? "text-onband" : "text-content-1",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function FeatureRow({
  items,
  dark,
  columns = 3,
}: {
  items: Array<{ icon: ReactNode; title: string; body: string }>;
  dark?: boolean;
  columns?: 2 | 3 | 4;
}) {
  const cols = {
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
  };
  return (
    <div className={clsx("grid gap-5", cols[columns])}>
      {items.map((item, i) => (
        <Reveal key={item.title} delay={i * 0.08}>
          <div
            className={clsx(
              "group h-full rounded-[22px] p-9 transition-colors duration-300",
              dark ? "bg-onband/[0.07] hover:bg-onband/[0.11]" : "bg-surface-card hover:bg-surface-hover",
            )}
          >
            <span
              className={clsx(
                "inline-flex h-14 w-14 items-center justify-center rounded-full transition-colors duration-300",
                dark
                  ? "bg-onband/12 text-onband group-hover:bg-signal-600 group-hover:text-white"
                  : "bg-overlay-2 text-content-1 group-hover:bg-signal-600 group-hover:text-white",
              )}
            >
              {item.icon}
            </span>
            <h3
              className={clsx(
                "type-display mt-7 text-[1.6rem]",
                dark ? "text-onband" : "text-content-1",
              )}
            >
              {item.title}
            </h3>
            <p
              className={clsx(
                "mt-3.5 text-[1.1rem] leading-[1.6]",
                dark ? "text-onband/65" : "text-content-2",
              )}
            >
              {item.body}
            </p>
          </div>
        </Reveal>
      ))}
    </div>
  );
}
