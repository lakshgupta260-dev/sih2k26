import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ArrowUpDown,
  Bell,
  BellOff,
  Check,
  CheckCheck,
  Filter,
  Mail,
  MessageSquare,
  Monitor,
  PhoneCall,
} from "lucide-react";
import type { ReactNode } from "react";
import { notificationsApi } from "@/api/notifications";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/States";
import { Badge } from "@/components/common/Badge";
import { Button, Card, PageHeader } from "@/components/ui/Primitives";
import { MultiSelectMenu, SelectMenu } from "@/components/ui/Dropdown";
import type { NotificationChannel } from "@/types/api";

const CHANNEL_ICON: Record<NotificationChannel, ReactNode> = {
  IN_APP: <Monitor className="h-3.5 w-3.5" />,
  EMAIL: <Mail className="h-3.5 w-3.5" />,
  WHATSAPP: <MessageSquare className="h-3.5 w-3.5" />,
  VAPI: <PhoneCall className="h-3.5 w-3.5" />,
};

const CHANNEL_LABEL: Record<NotificationChannel, string> = {
  IN_APP: "In-app",
  EMAIL: "Email",
  WHATSAPP: "WhatsApp",
  VAPI: "Voice",
};

export function Notifications() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [readState, setReadState] = useState<"all" | "unread" | "read">("all");
  const [order, setOrder] = useState<"newest" | "oldest">("newest");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => notificationsApi.list({ limit: 100 }),
  });

  const markAllMutation = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      toast.success(
        "All caught up",
        res.count > 0
          ? `${res.count} notification${res.count === 1 ? "" : "s"} marked as read.`
          : "There was nothing left unread.",
      );
    },
    onError: (err) =>
      toast.error("Could not mark all read", err instanceof ApiError ? err.message : undefined),
  });

  const markOneMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (err) =>
      toast.error("Could not mark as read", err instanceof ApiError ? err.message : undefined),
  });

  const all = data?.items ?? [];
  const unread = all.filter((n) => !n.read_at).length;

  // Only channels and types that actually appear are offered as filters.
  const typeOptions = useMemo(() => {
    const seen = new Set(all.map((n) => n.notification_type).filter(Boolean) as string[]);
    return [...seen].sort().map((t) => ({ value: t, label: t.replaceAll("_", " ") }));
  }, [all]);

  const items = useMemo(
    () =>
      all
        .filter(
          (n) =>
            (channels.length === 0 || channels.includes(n.channel)) &&
            (types.length === 0 || (n.notification_type != null && types.includes(n.notification_type))) &&
            (readState === "all" || (readState === "unread" ? !n.read_at : !!n.read_at)),
        )
        .sort((a, b) =>
          order === "oldest"
            ? a.created_at.localeCompare(b.created_at)
            : b.created_at.localeCompare(a.created_at),
        ),
    [all, channels, types, readState, order],
  );

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="Delay alerts, upload outcomes and project events — everything the platform wanted you to know."
        actions={
          <>
            {unread > 0 && (
              <Badge tone="amber" icon={<Bell className="h-3 w-3" />}>
                {unread} unread
              </Badge>
            )}
            <Button
              variant="secondary"
              onClick={() => markAllMutation.mutate()}
              loading={markAllMutation.isPending}
              disabled={unread === 0}
            >
              <CheckCheck className="h-4 w-4" />
              Mark all read
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2 border-y border-line py-2.5">
        <MultiSelectMenu<NotificationChannel>
          label="Channel"
          icon={<Filter className="h-3.5 w-3.5 text-content-2" />}
          options={(Object.keys(CHANNEL_LABEL) as NotificationChannel[]).map((c) => ({
            value: c,
            label: CHANNEL_LABEL[c],
            icon: CHANNEL_ICON[c],
          }))}
          selected={channels}
          onChange={setChannels}
        />
        <MultiSelectMenu
          label="Event"
          options={typeOptions}
          selected={types}
          onChange={setTypes}
          width="w-64"
        />
        <SelectMenu<"all" | "unread" | "read">
          prefix="Show"
          value={readState}
          width="w-48"
          options={[
            { value: "all", label: "Everything" },
            { value: "unread", label: "Unread only", hint: String(unread) },
            { value: "read", label: "Read only" },
          ]}
          onChange={(v) => v && setReadState(v)}
        />
        <SelectMenu<"newest" | "oldest">
          prefix="Order"
          icon={<ArrowUpDown className="h-3.5 w-3.5 text-content-2" />}
          value={order}
          width="w-44"
          options={[
            { value: "newest", label: "Newest first" },
            { value: "oldest", label: "Oldest first" },
          ]}
          onChange={(v) => v && setOrder(v)}
        />
        <span className="ml-auto text-2xs text-content-3">
          {items.length}/{all.length}
        </span>
      </div>

      {isLoading && (
        <Card className="p-3">
          <LoadingRows rows={5} />
        </Card>
      )}

      {error && <ErrorState error={error} onRetry={() => refetch()} />}

      {data && all.length > 0 && items.length === 0 && (
        <EmptyState
          icon={<Filter className="h-5 w-5" />}
          title="No notification matches these filters"
          description="Widen the channel, event, read-state or order filter."
        />
      )}

      {data && all.length === 0 && (
        <EmptyState
          icon={<BellOff className="h-5 w-5" />}
          title="No notifications"
          description="When a forecast turns critical, an upload finishes processing, or a manager sends word from a project, it lands here."
        />
      )}

      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((n, i) => {
            const isUnread = !n.read_at;
            return (
              <motion.div
                key={n.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.3,
                  delay: Math.min(i * 0.03, 0.24),
                  ease: [0.16, 1, 0.3, 1],
                }}
              >
                <Card className={isUnread ? "border-signal-500/40 bg-signal-600/25/40" : undefined}>
                  <div className="flex items-start gap-3 p-3.5">
                    <span
                      className={
                        isUnread
                          ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-signal-600/30 text-accent"
                          : "flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-surface-raised text-content-2"
                      }
                    >
                      {CHANNEL_ICON[n.channel] ?? <Bell className="h-3.5 w-3.5" />}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-content-1">{n.title}</p>
                        <Badge tone={isUnread ? "amber" : "slate"}>
                          {CHANNEL_LABEL[n.channel] ?? n.channel}
                        </Badge>
                        {n.notification_type && (
                          <span className="text-2xs text-content-2">
                            {n.notification_type.replaceAll("_", " ")}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-content-2">{n.body}</p>
                      <p className="tnum mt-1.5 text-2xs text-content-2">
                        {new Date(n.created_at).toLocaleString()}
                        {n.read_at && " · read"}
                      </p>
                    </div>

                    {isUnread && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={markOneMutation.isPending}
                        onClick={() => markOneMutation.mutate(n.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Mark read
                      </Button>
                    )}
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
