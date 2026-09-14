import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import {
  Bell,
  CalendarRange,
  CornerDownLeft,
  FileBarChart,
  FolderKanban,
  GitCompareArrows,
  Search,
  ShieldAlert,
  Upload,
  UserCog,
  User as UserIcon,
  Radio,
} from "lucide-react";
import { projectsApi } from "@/api/projects";
import { useAuth } from "@/context/AuthContext";
import type { ReactNode } from "react";

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon: ReactNode;
  to: string;
}

const ICON = "h-4 w-4";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list({ limit: 100 }),
    enabled: isAuthenticated,
    staleTime: 60_000,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // Focus after the entry animation starts so the caret doesn't jump.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const base: Command[] = [
      { id: "projects", label: "All projects", group: "Navigate", icon: <FolderKanban className={ICON} />, to: "/projects" },
      { id: "notifications", label: "Notifications", group: "Navigate", icon: <Bell className={ICON} />, to: "/notifications" },
      { id: "profile", label: "Profile & password", group: "Navigate", icon: <UserIcon className={ICON} />, to: "/profile" },
    ];
    if (user?.role === "ADMIN") {
      base.push({ id: "users", label: "User administration", group: "Navigate", icon: <UserCog className={ICON} />, to: "/admin/users" });
    }

    for (const p of projects?.items ?? []) {
      const prefix = `/projects/${p.id}`;
      base.push(
        { id: `${p.id}-overview`, label: p.name, hint: `${p.code} · overview`, group: "Projects", icon: <FolderKanban className={ICON} />, to: prefix },
        { id: `${p.id}-schedule`, label: `${p.name} — Schedule`, hint: p.code, group: "Projects", icon: <CalendarRange className={ICON} />, to: `${prefix}/schedule` },
        { id: `${p.id}-uploads`, label: `${p.name} — Site reports`, hint: p.code, group: "Projects", icon: <Upload className={ICON} />, to: `${prefix}/uploads` },
        { id: `${p.id}-matching`, label: `${p.name} — AI matching`, hint: p.code, group: "Projects", icon: <GitCompareArrows className={ICON} />, to: `${prefix}/matching` },
        { id: `${p.id}-risks`, label: `${p.name} — Risk & delay`, hint: p.code, group: "Projects", icon: <ShieldAlert className={ICON} />, to: `${prefix}/risks` },
        { id: `${p.id}-reports`, label: `${p.name} — Reports`, hint: p.code, group: "Projects", icon: <FileBarChart className={ICON} />, to: `${prefix}/reports` },
        { id: `${p.id}-channels`, label: `${p.name} — Voice & WhatsApp`, hint: p.code, group: "Projects", icon: <Radio className={ICON} />, to: `${prefix}/channels` },
      );
    }
    return base;
  }, [projects, user]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands.slice(0, 12);
    return commands
      .filter((c) => `${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q))
      .slice(0, 40);
  }, [commands, query]);

  useEffect(() => setCursor(0), [query]);

  const run = (cmd: Command) => {
    setOpen(false);
    navigate(cmd.to);
  };

  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter" && filtered[cursor]) {
      e.preventDefault();
      run(filtered[cursor]);
    }
  };

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!isAuthenticated) return null;

  let lastGroup = "";

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[70] flex items-start justify-center p-4 pt-[12vh]">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-ink-950/40 backdrop-blur-[2px]"
          />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-xl overflow-hidden rounded-[14px] bg-surface-card shadow-float"
          >
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Search className="h-4 w-4 shrink-0 text-content-2" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder="Jump to a project, schedule, matching queue…"
                className="h-12 w-full bg-transparent text-sm text-content-1 placeholder:text-content-2 focus:outline-none"
              />
              <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-2xs text-content-2 sm:block">
                esc
              </kbd>
            </div>

            <div ref={listRef} className="scroll-slim max-h-80 overflow-y-auto p-1.5">
              {filtered.length === 0 && (
                <p className="px-3 py-8 text-center text-sm text-content-2">
                  No matches for “{query}”
                </p>
              )}
              {filtered.map((cmd, i) => {
                const showGroup = cmd.group !== lastGroup;
                lastGroup = cmd.group;
                return (
                  <div key={cmd.id}>
                    {showGroup && (
                      <p className="px-2.5 pb-1 pt-2.5 text-2xs font-medium text-content-2">
                        {cmd.group}
                      </p>
                    )}
                    <button
                      data-index={i}
                      onMouseEnter={() => setCursor(i)}
                      onClick={() => run(cmd)}
                      className={clsx(
                        "flex w-full items-center gap-3 rounded-[10px] px-2.5 py-2 text-left transition-colors",
                        i === cursor ? "bg-signal-600/25 text-accent" : "text-content-1 hover:bg-surface-raised",
                      )}
                    >
                      <span className={i === cursor ? "text-accent" : "text-content-2"}>{cmd.icon}</span>
                      <span className="flex-1 truncate text-sm">{cmd.label}</span>
                      {cmd.hint && <span className="truncate text-2xs text-content-2">{cmd.hint}</span>}
                      {i === cursor && <CornerDownLeft className="h-3.5 w-3.5 text-accent" />}
                    </button>
                  </div>
                );
              })}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
