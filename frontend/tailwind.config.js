/** @type {import('tailwindcss').Config} */

/**
 * Palette sampled from apple.com/iphone-18-pro: a neutral graphite system where
 * the only grounds are #000, #1d1d1f, #f5f5f7 and white, text steps down through
 * #6e6e73 to #86868b, and colour is reserved for the product itself. The accent
 * is Burgundy — one of the iPhone 18 Pro finishes — so the one saturated colour
 * in the interface is a deep wine rather than the blue-violet every generated
 * dashboard reaches for.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral graphite. 900 is Apple's near-black, 950 is true black.
        ink: {
          50: "#fafafc",
          100: "#f5f5f7",
          200: "#e8e8ed",
          300: "#d2d2d7",
          400: "#a1a1a6",
          500: "#86868b",
          600: "#6e6e73",
          700: "#424245",
          800: "#2d2d30",
          900: "#1d1d1f",
          950: "#000000",
        },
        // Burgundy — the accent, used for interaction and emphasis only.
        signal: {
          50: "#fbf4f5",
          100: "#f6e6e8",
          200: "#eccdd2",
          300: "#dba5ae",
          400: "#c47886",
          500: "#a4485a",
          600: "#8a3446",
          700: "#7b2c3b",
          800: "#66252f",
          900: "#55212a",
          950: "#2f1015",
        },
        // Interior surfaces and text, resolved from CSS variables so one
        // attribute on <html> swaps the whole interior between themes. A
        // component names the role, never the colour.
        surface: {
          base: "rgb(var(--surface-base) / <alpha-value>)",
          card: "rgb(var(--surface-card) / <alpha-value>)",
          raised: "rgb(var(--surface-raised) / <alpha-value>)",
          hover: "rgb(var(--surface-hover) / <alpha-value>)",
        },
        content: {
          1: "rgb(var(--content-1) / <alpha-value>)",
          2: "rgb(var(--content-2) / <alpha-value>)",
          3: "rgb(var(--content-3) / <alpha-value>)",
        },
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
        },
        overlay: {
          1: "var(--overlay-1)",
          2: "var(--overlay-2)",
          3: "var(--overlay-3)",
        },
        band: {
          1: "rgb(var(--band-1) / <alpha-value>)",
          2: "rgb(var(--band-2) / <alpha-value>)",
          3: "rgb(var(--band-3) / <alpha-value>)",
          4: "rgb(var(--band-4) / <alpha-value>)",
        },
        onband: "rgb(var(--on-band) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          solid: "rgb(var(--accent-solid) / <alpha-value>)",
          contrast: "rgb(var(--accent-contrast) / <alpha-value>)",
        },
        // Cool greys for large light surfaces — the #f5f5f7 family.
        paper: {
          50: "#fafafc",
          100: "#f5f5f7",
          200: "#e8e8ed",
          300: "#d2d2d7",
          400: "#a1a1a6",
          500: "#86868b",
        },
        // Status green, tuned to Apple's system green rather than a bright mint.
        teal: {
          50: "#eef9f1",
          100: "#d6f0dd",
          200: "#aee0bd",
          300: "#77cb92",
          400: "#43b268",
          500: "#248a3d",
          600: "#1d7233",
          700: "#195c2b",
          800: "#164a24",
          900: "#123d1f",
          950: "#06210f",
        },
        // Kept so legacy blue references resolve; unused in the new scheme.
        brand: {
          50: "#f0f7ff",
          100: "#dceeff",
          200: "#bfe0ff",
          300: "#8fcaff",
          400: "#54adfc",
          500: "#2997ff",
          600: "#0071e3",
          700: "#0059b8",
          800: "#054a94",
          900: "#0a3f79",
          950: "#07284d",
        },
      },
      fontFamily: {
        // -apple-system resolves to the real SF Pro on macOS and iOS, which is
        // what gives the type its exact reference feel; Inter is the fallback
        // everywhere else.
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Text"',
          '"Inter var"',
          "Inter",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Display"',
          '"Inter var"',
          "Inter",
          "sans-serif",
        ],
        mono: ['"SF Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // The whole interior is built on these three steps, so lifting them
        // scales every table, card and label together.
        "2xs": ["0.8125rem", { lineHeight: "1.2rem" }],
        xs: ["0.875rem", { lineHeight: "1.3rem" }],
        sm: ["1rem", { lineHeight: "1.5rem" }],
        // The reference sets headlines at 64/68 with -0.009em tracking.
        headline: ["4rem", { lineHeight: "1.0625", letterSpacing: "-0.009em" }],
        "headline-sm": ["2.75rem", { lineHeight: "1.08", letterSpacing: "-0.008em" }],
      },
      boxShadow: {
        // Elevation is almost absent in the reference — surfaces separate by
        // ground colour, not by drop shadow.
        card: "0 1px 2px 0 rgb(0 0 0 / 0.03)",
        lift: "0 4px 16px -4px rgb(0 0 0 / 0.10)",
        float: "0 12px 32px -8px rgb(0 0 0 / 0.18)",
        glow: "0 0 0 1px rgb(176 72 98 / 0.25)",
        inset: "inset 0 1px 0 0 rgb(255 255 255 / 0.06)",
      },
      backgroundImage: {
        // Flat grounds only. The one gradient is the soft vignette behind the
        // dark hero, which the reference uses to lift the product off black.
        "hero-vignette":
          "radial-gradient(ellipse 70% 55% at 50% 0%, rgb(255 255 255 / 0.09), transparent 70%)",
        sheen: "linear-gradient(180deg, rgb(255 255 255 / 0.06) 0%, transparent 60%)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        "flow-dash": {
          to: { strokeDashoffset: "-16" },
        },
        "sweep-x": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        "draw-line": {
          from: { strokeDashoffset: "1000" },
          to: { strokeDashoffset: "0" },
        },
        "drift-a": {
          "0%,100%": { transform: "translate3d(-8%, -6%, 0) scale(1)" },
          "50%": { transform: "translate3d(10%, 8%, 0) scale(1.25)" },
        },
        "drift-b": {
          "0%,100%": { transform: "translate3d(6%, 10%, 0) scale(1.15)" },
          "50%": { transform: "translate3d(-10%, -8%, 0) scale(1)" },
        },
        "drift-c": {
          "0%,100%": { transform: "translate3d(0, 6%, 0) scale(1.1)" },
          "50%": { transform: "translate3d(8%, -10%, 0) scale(0.95)" },
        },
      },
      animation: {
        // Apple's easing: a long, soft settle rather than a bounce.
        "fade-up": "fade-up 0.7s cubic-bezier(0.28, 0.11, 0.32, 1) both",
        "fade-in": "fade-in 0.5s ease-out both",
        shimmer: "shimmer 1.8s infinite",
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "flow-dash": "flow-dash 0.7s linear infinite",
        "sweep-x": "sweep-x 3.5s ease-in-out infinite",
        "draw-line": "draw-line 2.4s ease-out forwards",
        // Long periods, deliberately out of sync, so the motion never reads as
        // a loop behind dense data.
        "drift-a": "drift-a 34s ease-in-out infinite",
        "drift-b": "drift-b 44s ease-in-out infinite",
        "drift-c": "drift-c 52s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
