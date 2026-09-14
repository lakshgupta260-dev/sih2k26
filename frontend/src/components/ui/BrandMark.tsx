import clsx from "clsx";

const SIZES = {
  sm: "h-7 w-7 rounded-[8px] text-[0.6rem]",
  md: "h-9 w-9 rounded-[10px] text-[0.7rem]",
  lg: "h-11 w-11 rounded-[12px] text-[0.85rem]",
  xl: "h-12 w-12 rounded-[14px] text-[0.9rem]",
} as const;

/**
 * The product mark.
 *
 * It is always inverted against whatever it sits on rather than carrying a
 * fixed fill, which is what keeps it crisp in both themes: a burgundy tile went
 * muddy on the near-black shell, and any single colour would fail on either the
 * white cards or the black landing bands.
 *
 * `onDark` is for the surfaces that stay dark regardless of theme — the landing
 * nav and its emphasis bands — where the theme-following tokens would resolve
 * to dark-on-dark.
 */
export function BrandMark({
  size = "lg",
  onDark = false,
  className,
}: {
  size?: keyof typeof SIZES;
  onDark?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={clsx(
        "inline-flex shrink-0 items-center justify-center font-semibold tracking-[-0.02em]",
        SIZES[size],
        onDark ? "bg-onband text-band-3" : "bg-content-1 text-surface-base",
        className,
      )}
    >
      P2P
    </span>
  );
}
