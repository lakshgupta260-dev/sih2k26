import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, ChevronDown } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL, ApiError } from "@/api/client";
import { Button, Field, Input } from "@/components/ui/Primitives";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BrandMark } from "@/components/ui/BrandMark";

/**
 * The product shot. Planned durations sit as hairline outlines, reported
 * progress fills over the top, and the gap between the two is the entire
 * pitch — shown once, large, on black, the way a hero image would be.
 */
function ScheduleMotif() {
  const bars = [
    { label: "Mobilisation", plan: 22, actual: 22 },
    { label: "Trenching", plan: 46, actual: 44 },
    { label: "Pipe laying", plan: 68, actual: 51 },
    { label: "Welding / NDT", plan: 84, actual: 47 },
    { label: "Hydrotest", plan: 100, actual: 0 },
  ];
  return (
    <div className="mx-auto w-full max-w-3xl rounded-[28px] bg-white/[0.05] p-7 sm:p-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[0.95rem] text-ink-400">Baseline vs reported</p>
        <span className="flex items-center gap-5 text-[0.9rem]">
          <span className="flex items-center gap-2 text-ink-400">
            <span className="h-2.5 w-5 rounded-full border border-ink-500" /> Plan
          </span>
          <span className="flex items-center gap-2 text-paper-200">
            <span className="h-2.5 w-5 rounded-full bg-signal-500" /> Actual
          </span>
        </span>
      </div>

      <div className="mt-8 space-y-5">
        {bars.map((bar, i) => (
          <div key={bar.label}>
            <div className="flex items-baseline justify-between">
              <span className="text-[1.05rem] text-paper-200">{bar.label}</span>
              <span className="text-[0.95rem] tabular-nums text-ink-400">
                {bar.actual}/{bar.plan}%
              </span>
            </div>
            <div className="relative mt-2 h-3.5">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${bar.plan}%` }}
                transition={{ duration: 1.1, delay: 0.3 + i * 0.1, ease: [0.28, 0.11, 0.32, 1] }}
                className="absolute inset-y-0 left-0 rounded-full border border-ink-600"
              />
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${bar.actual}%` }}
                transition={{ duration: 1.2, delay: 0.6 + i * 0.1, ease: [0.28, 0.11, 0.32, 1] }}
                className="absolute inset-y-[3px] left-0 rounded-full bg-signal-500"
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between border-t border-white/10 pt-5">
        <span className="text-[1.05rem] text-ink-400">Variance to plan</span>
        <span className="text-[1.3rem] font-medium tabular-nums text-paper-100">−18.4 pp</span>
      </div>
    </div>
  );
}

interface FormValues {
  email: string;
  password: string;
}

export function Hero() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await login(values);
      navigate(location.state?.from ?? "/projects", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setServerError("Those credentials weren't accepted. Check the email and password.");
      } else if (err instanceof ApiError && err.status === 429) {
        setServerError("Too many sign-in attempts. Wait a minute and try again.");
      } else if (err instanceof ApiError && err.code === "NETWORK_ERROR") {
        setServerError(`Can't reach the API at ${API_BASE_URL}. Is the backend running?`);
      } else {
        setServerError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
      }
    }
  };

  return (
    <>
      {/* Translucent global bar, pinned — the reference's one piece of chrome. */}
      <nav className="glass-dark sticky top-0 z-50 border-b border-white/10">
        <div className="mx-auto flex h-14 w-full max-w-[72rem] items-center justify-between px-6 lg:px-8">
          <a href="#top" className="flex items-center gap-2.5">
            <BrandMark size="sm" onDark />
            <span className="text-[1rem] font-medium text-paper-100">Plan2Progress</span>
          </a>

          <div className="hidden items-center gap-9 text-[0.95rem] text-paper-200 md:flex">
            <a href="#problem" className="transition-opacity hover:opacity-60">Problem</a>
            <a href="#workflow" className="transition-opacity hover:opacity-60">Workflow</a>
            <a href="#matching" className="transition-opacity hover:opacity-60">Matching</a>
            <a href="#risk" className="transition-opacity hover:opacity-60">Risk</a>
          </div>

          <div className="flex items-center gap-1.5">
            {/* The bar is always dark, so the toggle is pinned to light-on-dark
                styling here rather than following the theme tokens. */}
            <div className="text-paper-200 [&_button]:text-paper-200 [&_button:hover]:bg-white/10 [&_button:hover]:text-white">
              <ThemeToggle />
            </div>
            <a
              href="#signin"
              className="rounded-full bg-signal-600 px-5 py-2 text-[0.9rem] font-medium text-white transition-colors hover:bg-signal-500"
            >
              Sign in
            </a>
          </div>
        </div>
      </nav>

      {/* Hero — one statement, centred, on black. */}
      <header id="top" className="relative overflow-hidden bg-ink-950">
        <div className="pointer-events-none absolute inset-0 bg-hero-vignette" />

        <div className="relative mx-auto w-full max-w-[70rem] px-6 pb-28 pt-24 text-center lg:px-8 lg:pt-28">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.28, 0.11, 0.32, 1] }}
          >
            <p className="text-[1.05rem] text-ink-400">Plan2Progress</p>

            <h1 className="type-display mx-auto mt-3 max-w-4xl text-[3.4rem] leading-[1.02] text-paper-100 sm:text-[5rem] lg:text-[6rem]">
              The plan says one thing.
              <br />
              <span className="text-ink-500">The site says another.</span>
            </h1>

            <p className="mx-auto mt-8 max-w-2xl text-[1.45rem] leading-[1.5] text-ink-400">
              Progress arrives as reports, spreadsheets and WhatsApp messages. Plan2Progress links
              every line back to the exact schedule activity it belongs to.
            </p>

            <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
              <a
                href="#signin"
                className="inline-flex h-12 items-center gap-2 rounded-full bg-signal-600 px-8 text-[1.05rem] font-medium text-white transition-colors hover:bg-signal-500"
              >
                Sign in
                <ArrowRight className="h-4 w-4" />
              </a>
              <a
                href="#problem"
                className="inline-flex h-12 items-center gap-1.5 rounded-full px-6 text-[1.05rem] text-paper-200 transition-opacity hover:opacity-60"
              >
                See how it works
                <ChevronDown className="h-4 w-4" />
              </a>
            </div>
          </motion.div>

          <motion.dl
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.12, ease: [0.28, 0.11, 0.32, 1] }}
            className="mx-auto mt-20 grid max-w-2xl grid-cols-3 gap-8"
          >
            {[
              { k: "Activity hierarchy", v: "L1–L6" },
              { k: "Auto-match above", v: "0.82" },
              { k: "Forecast tiers", v: "2" },
            ].map((s) => (
              <div key={s.k}>
                <dd className="type-display text-[2.75rem] text-paper-100">{s.v}</dd>
                <dt className="mt-1.5 text-[0.95rem] text-ink-400">{s.k}</dt>
              </div>
            ))}
          </motion.dl>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.2, ease: [0.28, 0.11, 0.32, 1] }}
            className="mt-20"
          >
            <ScheduleMotif />
          </motion.div>
        </div>
      </header>

      {/* Sign in — a single floating card on the light ground. */}
      <section id="signin" className="bg-surface-base py-24 sm:py-32">
        <div className="mx-auto w-full max-w-[27rem] px-6">
          <div className="rounded-[26px] bg-surface-card p-9 shadow-lift ring-1 ring-line sm:p-11">
            <div className="text-center">
              <BrandMark size="xl" className="mx-auto" />
              <h2 className="type-display mt-6 text-[2.1rem] leading-[1.1] text-content-1">
                Welcome back.
              </h2>
              <p className="mt-3 text-[1.05rem] leading-relaxed text-content-2">
                Sign in to your project command centre.
              </p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="mt-9 space-y-5">
              <Field label="Work email" error={errors.email?.message}>
                <Input
                  type="email"
                  autoComplete="username"
                  placeholder="you@oil-india.example"
                  className="h-12 text-base"
                  {...register("email", { required: "Email is required" })}
                />
              </Field>

              <Field label="Password" error={errors.password?.message}>
                <Input
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className="h-12 text-base"
                  {...register("password", { required: "Password is required" })}
                />
              </Field>

              {serverError && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-[14px] bg-rose-50 px-4 py-3 text-[0.95rem] leading-relaxed text-rose-700"
                >
                  {serverError}
                </motion.div>
              )}

              <Button type="submit" variant="signal" size="xl" loading={isSubmitting} className="w-full">
                {isSubmitting ? "Signing in…" : "Sign in"}
                {!isSubmitting && <ArrowRight className="h-4 w-4" />}
              </Button>
            </form>

            <p className="mt-8 border-t border-line pt-7 text-center text-[1rem] text-content-2">
              No account yet?{" "}
              <Link to="/register" className="font-medium text-accent hover:underline">
                Register as a site supervisor
              </Link>
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
