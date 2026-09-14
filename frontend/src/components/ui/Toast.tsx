import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import clsx from "clsx";

type ToastKind = "success" | "error" | "info" | "warning";

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface ToastContextValue {
  push: (toast: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const STYLES: Record<ToastKind, { icon: ReactNode; ring: string; iconColor: string }> = {
  success: { icon: <CheckCircle2 className="h-4 w-4" />, ring: "ring-teal-200", iconColor: "text-teal-600" },
  error: { icon: <XCircle className="h-4 w-4" />, ring: "ring-rose-200", iconColor: "text-rose-600" },
  warning: { icon: <AlertTriangle className="h-4 w-4" />, ring: "ring-amber-200", iconColor: "text-amber-600" },
  info: { icon: <Info className="h-4 w-4" />, ring: "ring-signal-500/40", iconColor: "text-accent" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = Date.now() + Math.random();
      setToasts((all) => [...all, { ...toast, id }]);
      setTimeout(() => dismiss(id), toast.kind === "error" ? 7000 : 4500);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, description) => push({ kind: "success", title, description }),
      error: (title, description) => push({ kind: "error", title, description }),
      info: (title, description) => push({ kind: "info", title, description }),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => {
            const style = STYLES[toast.kind];
            return (
              <motion.div
                key={toast.id}
                layout
                initial={{ opacity: 0, y: 16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24, scale: 0.96 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                className={clsx(
                  "pointer-events-auto flex items-start gap-3 rounded-[14px] bg-surface-card p-3 shadow-float ring-1",
                  style.ring,
                )}
              >
                <span className={clsx("mt-0.5 shrink-0", style.iconColor)}>{style.icon}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-content-1">{toast.title}</p>
                  {toast.description && (
                    <p className="mt-0.5 break-words text-xs leading-relaxed text-content-3">
                      {toast.description}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => dismiss(toast.id)}
                  aria-label="Dismiss"
                  className="-m-0.5 rounded p-0.5 text-content-2 transition-colors hover:bg-surface-raised hover:text-content-1"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
