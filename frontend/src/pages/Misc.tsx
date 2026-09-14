import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Compass, LifeBuoy, ShieldAlert } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { BrandMark } from "@/components/ui/BrandMark";

function MiscShell({
  icon,
  tone,
  eyebrow,
  title,
  body,
  footer,
}: {
  icon: ReactNode;
  tone: "amber" | "slate";
  eyebrow: string;
  title: string;
  body: string;
  footer?: ReactNode;
}) {
  const accent =
    tone === "amber" ? "bg-amber-50 text-amber-600 ring-amber-100" : "bg-surface-raised text-content-3 ring-ink-100";

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-raised/60 px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md"
      >
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <BrandMark size="md" />
          <p className="text-sm font-semibold text-content-1">Plan2Progress</p>
        </div>

        <Card className="p-8 text-center shadow-lift">
          <span
            className={`mx-auto flex h-12 w-12 items-center justify-center rounded-[14px] ring-8 ${accent}`}
          >
            {icon}
          </span>

          <p className="mt-5 text-2xs font-medium text-content-2">{eyebrow}</p>
          <h1 className="mt-1.5 text-lg font-semibold tracking-[-0.01em] text-content-1">{title}</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-content-3">{body}</p>

          <div className="mt-6 flex justify-center">
            <Link to="/projects">
              <Button variant="dark">
                <ArrowLeft className="h-4 w-4" />
                Back to projects
              </Button>
            </Link>
          </div>

          {footer && <div className="mt-5 border-t border-line pt-4">{footer}</div>}
        </Card>
      </motion.div>
    </div>
  );
}

export function Unauthorized() {
  return (
    <MiscShell
      icon={<ShieldAlert className="h-6 w-6" />}
      tone="amber"
      eyebrow="403 · Not authorized"
      title="Your role doesn't open this door"
      body="This page is limited to a role your account doesn't hold. Nothing is broken — you simply aren't cleared for it."
      footer={
        <p className="flex items-center justify-center gap-1.5 text-2xs text-content-2">
          <LifeBuoy className="h-3.5 w-3.5" />
          Need access? Ask an administrator to change your role.
        </p>
      }
    />
  );
}

export function NotFound() {
  return (
    <MiscShell
      icon={<Compass className="h-6 w-6" />}
      tone="slate"
      eyebrow="404 · Page not found"
      title="There's nothing at this address"
      body="The link may be out of date, or the project it pointed at has since been removed. Your projects list is the safest way back."
    />
  );
}
