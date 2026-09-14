import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, ClipboardList, HardHat, Smartphone, Workflow } from "lucide-react";
import { authApi } from "@/api/auth";
import { API_BASE_URL, ApiError } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import { Button, Field, Input } from "@/components/ui/Primitives";
import { NetworkMesh } from "@/components/ui/NetworkMesh";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { BrandMark } from "@/components/ui/BrandMark";

interface FormValues {
  full_name: string;
  email: string;
  phone?: string;
  password: string;
}

const HIGHLIGHTS = [
  {
    icon: HardHat,
    title: "Site supervisor access",
    body: "New accounts start as supervisors. A project manager grants anything beyond that.",
  },
  {
    icon: ClipboardList,
    title: "File progress as you write it",
    body: "DPRs, site diaries, Excel sheets — upload them as they are, in the format you already use.",
  },
  {
    icon: Workflow,
    title: "Matched to the baseline",
    body: "What you report is linked to the exact L1–L6 activity it belongs to, with a confidence score.",
  },
  {
    icon: Smartphone,
    title: "Alerts where you are",
    body: "Add a phone number and delay warnings reach you on WhatsApp, not just in the browser.",
  },
];

export function Register() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await authApi.register({
        full_name: values.full_name,
        email: values.email,
        phone: values.phone || null,
        password: values.password,
      });
      await login({ email: values.email, password: values.password });
      navigate("/projects", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "NETWORK_ERROR") {
        setServerError(
          `Can't reach the API at ${API_BASE_URL}. Check the backend is running and VITE_API_BASE_URL is correct.`,
        );
      } else if (err instanceof ApiError && err.status === 409) {
        setServerError("That email already has an account. Sign in instead.");
      } else {
        setServerError(err instanceof ApiError ? err.message : "Registration failed.");
      }
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Brand / value panel */}
      <div className="relative hidden w-[52%] flex-col justify-between overflow-hidden bg-ink-950 p-12 lg:flex">
        <div className="absolute inset-0 opacity-[0.07]" />
        <NetworkMesh />
        <div className="absolute -left-24 top-1/4 h-96 w-96 rounded-full bg-signal-900/30 blur-3xl" />
        <div className="absolute -right-16 bottom-0 h-80 w-80 rounded-full bg-teal-500/10 blur-3xl" />

        <div className="relative">
          <div className="flex items-center gap-3">
            <BrandMark size="xl" onDark />
            <p className="font-display text-2xl font-semibold tracking-[-0.02em] text-white">Plan2Progress</p>
          </div>
        </div>

        <div className="relative max-w-lg">
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="text-balance font-display text-[2.6rem] font-semibold leading-[1.08] tracking-[-0.03em] text-white"
          >
            You already report progress.
            <br />
            <span className="text-accent">Let it count against the plan.</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="mt-4 text-balance text-[0.95rem] leading-relaxed text-content-2"
          >
            Create a site supervisor account and the field reports you already write become
            schedule-linked, auditable progress against the Primavera or MS&nbsp;Project baseline.
          </motion.p>

          <div className="mt-9 grid gap-x-6 gap-y-5 sm:grid-cols-2">
            {HIGHLIGHTS.map((item, i) => {
              const Icon = item.icon;
              return (
                <motion.div
                  key={item.title}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.45, delay: 0.18 + i * 0.07, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-white/10 text-signal-300 ring-1 ring-inset ring-white/10">
                    <Icon className="h-4 w-4" />
                  </div>
                  <p className="mt-2.5 text-sm font-medium text-white">{item.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-content-2">{item.body}</p>
                </motion.div>
              );
            })}
          </div>
        </div>

        <p className="relative text-2xs text-content-3">
          Built for Oil India Limited · Smart Automation
        </p>
      </div>

      {/* Register */}
      <div className="relative flex w-full flex-col justify-center bg-surface-base px-5 py-12 lg:w-[48%] lg:px-12">
        <div className="absolute right-4 top-4">
          <ThemeToggle />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="rounded-[22px] relative mx-auto w-full max-w-md bg-surface-card p-8 shadow-float ring-1 ring-line sm:p-10"
        >
          <div className="mb-8 flex justify-center lg:hidden">
            <BrandMark size="lg" />
          </div>

          <h2 className="text-center font-display text-3xl font-semibold tracking-[-0.025em] text-content-1">
            Create your account
          </h2>
          <p className="mt-2 text-center text-base leading-relaxed text-content-3">
            Registers you as a site supervisor. Higher roles are granted by an admin.
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-5 [&_label]:mb-2 [&_label]:text-sm [&_label]:font-semibold [&_label]:text-content-1 [&_input]:h-12 [&_input]:rounded-[14px] [&_input]:px-4 [&_input]:text-base">
            <Field label="Full name" error={errors.full_name?.message}>
              <Input
                autoComplete="name"
                placeholder="Anita Barua"
                autoFocus
                {...register("full_name", { required: "Full name is required" })}
              />
            </Field>

            <Field label="Work email" error={errors.email?.message}>
              <Input
                type="email"
                autoComplete="username"
                placeholder="you@oil-india.example"
                {...register("email", { required: "Email is required" })}
              />
            </Field>

            <Field label="Phone" hint="Optional — used for WhatsApp and voice alerts.">
              <Input
                type="tel"
                autoComplete="tel"
                placeholder="+91 98765 43210"
                {...register("phone")}
              />
            </Field>

            <Field
              label="Password"
              error={errors.password?.message}
              hint="Min 8 characters, must mix letters and at least one number."
            >
              <Input
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                {...register("password", {
                  required: "Password is required",
                  minLength: { value: 8, message: "At least 8 characters" },
                })}
              />
            </Field>

            {serverError && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-[10px] border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
              >
                {serverError}
              </motion.div>
            )}

            <Button type="submit" size="xl" className="mt-2 w-full rounded-[14px] shadow-glow" loading={isSubmitting}>
              {isSubmitting ? "Creating account…" : "Create account"}
              {!isSubmitting && <ArrowRight className="h-4 w-4" />}
            </Button>
          </form>

          <p className="mt-7 text-center text-base text-content-3">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
