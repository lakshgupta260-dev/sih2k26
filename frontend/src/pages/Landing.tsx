import { Link } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  CalendarRange,
  GitCompareArrows,
  Image as ImageIcon,
  MessageSquare,
  FileText,
  ShieldAlert,
  TrendingUp,
  Upload,
} from "lucide-react";
import { Hero } from "./landing/Hero";
import { Reveal, Section, Spec } from "./landing/sections";
import { BrandMark } from "@/components/ui/BrandMark";

const PIPELINE = [
  { n: "01", title: "Baseline import", body: "Primavera or MS Project, mapped to your columns.", icon: <CalendarRange className="h-6 w-6" /> },
  { n: "02", title: "Field capture", body: "DPRs, diaries, scans, WhatsApp, voice calls.", icon: <Upload className="h-6 w-6" /> },
  { n: "03", title: "Extraction", body: "Parsed into dated, quantified activity events.", icon: <BrainCircuit className="h-6 w-6" /> },
  { n: "04", title: "Matching", body: "Linked to the activity it actually refers to.", icon: <GitCompareArrows className="h-6 w-6" /> },
  { n: "05", title: "Progress", body: "Quantity-weighted roll-up from L6 to L1.", icon: <TrendingUp className="h-6 w-6" /> },
  { n: "06", title: "Risk", body: "A delay forecast that names its own tier.", icon: <ShieldAlert className="h-6 w-6" /> },
];

export function Landing() {
  return (
    <div className="min-h-screen bg-surface-base font-sans antialiased">
      <Hero />

      {/* The problem ------------------------------------------------------ */}
      <Section
        id="problem"
        eyebrow="The problem"
        tone="white"
        title={<>Planned data is structured. Actual data is not.</>}
        lead="Reconciling the two is manual, slow, and usually weeks late."
      >
        <div className="grid overflow-hidden rounded-[22px] lg:grid-cols-2">
          <div className="bg-band-1 p-9 sm:p-11">
            <p className="eyebrow">What the plan holds</p>
            <div className="mt-7">
              <Spec label="Activity" value={<span className="font-mono">A1020</span>} />
              <Spec label="Name" value="Pipe Laying Segment A" />
              <Spec label="Planned finish" value={<span className="font-mono">2026-02-15</span>} />
              <Spec label="Budgeted" value="2,833 m" />
            </div>
          </div>

          <div className="bg-band-3 p-9 sm:p-11">
            <p className="eyebrow text-onband/60">What the site sends</p>
            <div className="mt-7 space-y-4">
              {[
                { icon: <MessageSquare className="h-4 w-4" />, src: "WhatsApp · 19:42", text: "“pipe laying seg A abt 80% today, welding starts tmrw”" },
                { icon: <FileText className="h-4 w-4" />, src: "DPR_10-09.pdf", text: "“Laying of pipeline in segment A progressed satisfactorily.”" },
                { icon: <ImageIcon className="h-4 w-4" />, src: "site_diary.jpg", text: "Handwritten page, photographed at an angle." },
              ].map((row) => (
                <div key={row.src} className="rounded-[14px] bg-onband/[0.08] p-5">
                  <div className="flex items-center gap-2 text-sm text-onband/60">
                    <span className="text-signal-400">{row.icon}</span>
                    {row.src}
                  </div>
                  <p className="mt-2.5 text-[1.05rem] leading-relaxed text-onband/85">{row.text}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 text-[1.05rem] leading-relaxed text-onband/65">
              None of it carries an activity code.
            </p>
          </div>
        </div>
      </Section>

      {/* How it works ----------------------------------------------------- */}
      <Section
        id="workflow"
        eyebrow="How it works"
        tone="dark"
        title={<>Six stages, baseline to board-level risk.</>}
        lead="Every stage states what it did — and what it could not use."
      >
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {PIPELINE.map((step, i) => (
            <Reveal key={step.n} delay={i * 0.07}>
              <div className="group h-full rounded-[22px] bg-onband/[0.07] p-9 transition-colors duration-300 hover:bg-onband/[0.12]">
                <div className="flex items-start justify-between">
                  <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-onband/12 text-onband transition-colors duration-300 group-hover:bg-signal-600 group-hover:text-white">
                    {step.icon}
                  </span>
                  <span className="text-[1.75rem] font-semibold tabular-nums text-onband/20">
                    {step.n}
                  </span>
                </div>
                <h3 className="type-display mt-7 text-[1.6rem] text-onband">{step.title}</h3>
                <p className="mt-3 text-[1.1rem] leading-[1.6] text-onband/65">{step.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* Matching --------------------------------------------------------- */}
      <Section
        id="matching"
        eyebrow="Activity matching"
        tone="white"
        title={<>Which line of the schedule did that sentence mean?</>}
        lead="Each event is scored against candidate activities. The score decides whether a human needs to look."
      >
        <div className="grid overflow-hidden rounded-[22px] lg:grid-cols-[1.1fr_0.9fr]">
          <div className="bg-band-1 p-9 sm:p-11">
            <div className="rounded-[14px] bg-surface-card p-6">
              <p className="text-sm text-content-3">Extracted from site</p>
              <p className="mt-2 text-[1.25rem] leading-relaxed text-content-1">
                “Segment A trenching completed 100%.”
              </p>
            </div>

            <div className="my-6 flex items-center gap-3">
              <ArrowRight className="h-5 w-5 text-accent" />
              <span className="text-sm text-content-3">scored against the baseline</span>
            </div>

            <div className="space-y-3">
              {[
                { code: "A1010", name: "Trenching Segment A", score: 87, chosen: true },
                { code: "A1030", name: "Welding Segment A", score: 44, chosen: false },
                { code: "A1020", name: "Pipe Laying Segment A", score: 36, chosen: false },
              ].map((c) => (
                <div
                  key={c.code}
                  className={`rounded-[14px] p-5 ${c.chosen ? "bg-teal-400/15 ring-1 ring-teal-400/40" : "bg-surface-card"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[1.05rem] text-content-1">
                      <span className="font-mono text-sm text-content-3">{c.code}</span> {c.name}
                    </p>
                    <span className="text-[1.05rem] font-semibold tabular-nums text-content-1">
                      {c.score}%
                    </span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-overlay-2">
                    <div
                      className={`h-full rounded-full ${c.chosen ? "bg-teal-400" : "bg-overlay-3"}`}
                      style={{ width: `${c.score}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-band-3 p-9 sm:p-11">
            <p className="eyebrow text-onband/60">Thresholds</p>
            <div className="mt-8 space-y-8">
              {[
                { t: "≥ 0.82", h: "Linked automatically", d: "Confident enough to book without review.", c: "text-teal-400" },
                { t: "≥ 0.55", h: "Queued for a human", d: "A person confirms, rejects or reassigns it.", c: "text-signal-400" },
                { t: "< 0.55", h: "Recorded as unmatched", d: "Kept and visible — never quietly discarded.", c: "text-paper-300" },
              ].map((row) => (
                <div key={row.t}>
                  <p className={`text-[1.6rem] font-semibold tabular-nums ${row.c}`}>{row.t}</p>
                  <p className="type-display mt-2 text-[1.3rem] text-onband">{row.h}</p>
                  <p className="mt-2 text-[1.05rem] leading-relaxed text-onband/65">{row.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* Risk ------------------------------------------------------------- */}
      <Section
        id="risk"
        eyebrow="Delay & risk"
        tone="near"
        title={<>A forecast that tells you when it doesn't know.</>}
        lead="Rule-based arithmetic always runs. A model is promoted only once it provably beats it."
      >
        <div className="mx-auto max-w-2xl rounded-[22px] bg-onband/[0.07] p-9 sm:p-11">
          <Spec dark label="Tier 1" value="Rule-based rate" />
          <Spec dark label="Tier 2" value="Random Forest" />
          <Spec dark label="Promotion rule" value="Must beat the baseline" />
          <Spec dark label="Tier named per prediction" value="Always" />
          <p className="mt-8 text-[1.1rem] leading-[1.6] text-onband/65">
            Early in a project, refusing to fit a model is the correct outcome — not an error.
          </p>
        </div>
      </Section>

      {/* CTA + footer ----------------------------------------------------- */}
      <section className="relative overflow-hidden bg-band-3 py-28 sm:py-36">
        <div className="relative mx-auto w-full max-w-[72rem] px-6 lg:px-8">
          <Reveal className="text-center">
            <h2 className="type-display mx-auto max-w-3xl text-[2.8rem] leading-[1.05] text-onband sm:text-[4rem]">
              Close the gap between the programme and the ground.
            </h2>
            <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
              <a
                href="#signin"
                className="inline-flex h-12 items-center gap-2 rounded-full bg-signal-600 px-8 text-[1.05rem] font-medium text-white transition-colors hover:bg-signal-500"
              >
                Sign in
                <ArrowRight className="h-4 w-4" />
              </a>
              <Link
                to="/register"
                className="inline-flex h-12 items-center gap-2 rounded-full px-6 text-[1.05rem] text-onband/80 transition-opacity hover:opacity-60"
              >
                Register as a supervisor
              </Link>
            </div>
          </Reveal>

          <footer className="mt-28 border-t border-onband/15 pt-9">
            <div className="flex flex-wrap items-center justify-between gap-5">
              <div className="flex items-center gap-3">
                <BrandMark size="md" onDark />
                <div>
                  <p className="text-[1.05rem] font-medium text-onband">Plan2Progress</p>
                  <p className="text-sm text-onband/55">Built for Oil India Limited</p>
                </div>
              </div>
              <p className="text-sm text-onband/55">
                Smart India Hackathon 2026 · Problem statement 26122
              </p>
            </div>
          </footer>
        </div>
      </section>
    </div>
  );
}
