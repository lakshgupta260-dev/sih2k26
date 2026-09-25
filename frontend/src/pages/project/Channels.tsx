import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  Copy,
  Mail,
  MessageSquare,
  Monitor,
  Phone,
  PhoneCall,
  Send,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useProject, useProjectId } from "@/context/ProjectContext";
import { documentsApi } from "@/api/documents";
import { notificationsApi } from "@/api/notifications";
import { projectsApi } from "@/api/projects";
import { ApiError, API_BASE_URL } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { Badge } from "@/components/common/Badge";
import { EmptyState, LoadingRows } from "@/components/common/States";
import { Button, Card, CardHeader, Field, Input, PageHeader, Textarea } from "@/components/ui/Primitives";
import { Dropdown, DropdownItem, DropdownLabel, SelectMenu } from "@/components/ui/Dropdown";
import { MetricTile } from "@/components/ui/Metric";
import type { NotificationChannel, UploadedFileRead } from "@/types/api";

const WHATSAPP_FILENAME = "whatsapp_message.txt";
const VAPI_FILENAME = "vapi_call_transcript.txt";

/**
 * The two field-facing channels. Everything shown here is derived from real
 * rows the webhooks created — there is no synthetic "connected" indicator,
 * because the only honest evidence that an integration works is data it
 * actually delivered.
 */
export function Channels() {
  const projectId = useProjectId();
  const { canManage } = useProject();

  const docsQuery = useQuery({
    queryKey: ["documents", projectId, "channels"],
    queryFn: () => documentsApi.list(projectId, { limit: 200 }),
  });

  const { whatsapp, voice } = useMemo(() => {
    const items = docsQuery.data?.items ?? [];
    return {
      whatsapp: items.filter((d) => d.original_filename === WHATSAPP_FILENAME),
      voice: items.filter((d) => d.original_filename === VAPI_FILENAME),
    };
  }, [docsQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Voice & WhatsApp"
        subtitle="Low-friction reporting for the field: a supervisor sends a WhatsApp message or talks to the voice assistant, and it lands in the same extraction and matching pipeline as an uploaded DPR."
      />

      <Card className="mb-6 border-brand/20 bg-brand/5 dark:border-brand/30 dark:bg-brand/10">
        <CardHeader 
          title="Field Communication Hub" 
          subtitle="Connect with the AI Assistant or receive instant project reports via WhatsApp" 
          icon={<PhoneCall className="text-brand h-4 w-4" />} 
        />
        <div className="px-6 pb-6 flex gap-4 items-center">
          <Input id="vapi-phone" defaultValue="+91" placeholder="Phone number (e.g. +91...)" className="max-w-xs" />
          <Button onClick={async () => {
            const btn = document.getElementById('vapi-btn');
            const input = document.getElementById('vapi-phone') as HTMLInputElement;
            if(btn) btn.innerText = 'Calling...';
            try {
              await fetch("https://api.vapi.ai/call/phone", {
                method: "POST",
                headers: {
                  "Authorization": "Bearer 47f40f20-04d1-4925-9a00-cb26a19bc760",
                  "Content-Type": "application/json"
                },
                body: JSON.stringify({
                  phoneNumberId: "f662a968-e48c-4108-b465-c796b45b06a0",
                  assistantId: "3f8b2238-7fc3-4d0d-9324-e35f3f53af9b",
                  customer: { number: input.value }
                })
              });
              if(btn) btn.innerText = 'Call Me';
            } catch(e) {
              if(btn) btn.innerText = 'Call Me';
            }
          }} id="vapi-btn" variant="secondary">Call Me</Button>
          
          <Button onClick={async () => {
            const btn = document.getElementById('wa-btn');
            const input = document.getElementById('vapi-phone') as HTMLInputElement;
            if(btn) btn.innerText = 'Sending...';
            try {
              const res = await fetch("http://localhost:8000/api/v1/integrations/meta/send_demo", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json"
                },
                body: JSON.stringify({
                  phone: input.value,
                  project_id: projectId
                })
              });
              if (!res.ok) throw new Error("Failed");
              if(btn) btn.innerText = 'WhatsApp';
            } catch(e) {
              if(btn) btn.innerText = 'WhatsApp';
            }
          }} id="wa-btn" variant="secondary">
            <svg viewBox="0 0 24 24" className="h-4 w-4 mr-2 fill-current" xmlns="http://www.w3.org/2000/svg">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.82 9.82 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.81 11.81 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.88 11.88 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.82 11.82 0 0 0-3.48-8.413Z"/>
            </svg>
            WhatsApp
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <MetricTile
          label="WhatsApp reports"
          value={whatsapp.length}
          icon={<MessageSquare className="h-4 w-4" />}
          hint="ingested into this project"
          tone={whatsapp.length ? "positive" : "default"}
        />
        <MetricTile
          label="Call transcripts"
          value={voice.length}
          icon={<PhoneCall className="h-4 w-4" />}
          hint="from Vapi end-of-call"
          tone={voice.length ? "positive" : "default"}
          delay={0.05}
        />
        <MetricTile
          label="Assistant tools"
          value={5}
          icon={<Bot className="h-4 w-4" />}
          hint="callable by voice"
          delay={0.1}
        />
        <MetricTile
          label="Webhook auth"
          value={<span className="text-lg">HMAC + secret</span>}
          icon={<ShieldCheck className="h-4 w-4" />}
          hint="both fail closed"
          delay={0.15}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChannelCard
          icon={<MessageSquare className="h-4 w-4" />}
          title="WhatsApp (Meta Cloud API)"
          blurb="Supervisors message the project number. Each text is stored as a site report, queued for extraction, then matched to schedule activities. Repeat deliveries of the same message are ignored, so a Meta retry can't double-count the work."
          endpoint="/integrations/meta/webhook"
          authNote="Verified with X-Hub-Signature-256 (HMAC-SHA256 over the raw body, keyed by META_APP_SECRET). Unsigned or wrongly-signed calls get 403; with no secret configured the endpoint refuses everything with 503 rather than trusting the caller."
          items={whatsapp}
          loading={docsQuery.isLoading}
          emptyText="No WhatsApp messages have reached this project yet."
        />

        <ChannelCard
          icon={<Phone className="h-4 w-4" />}
          title="Vapi voice assistant"
          blurb="A phone call to the assistant. It resolves the caller by their registered number, answers questions against this project's live data, and files the end-of-call transcript as a site report."
          endpoint="/integrations/vapi/webhook"
          authNote="Shared secret compared with hmac.compare_digest, accepted as X-Vapi-Secret or Authorization: Bearer. With no secret configured every call is refused."
          items={voice}
          loading={docsQuery.isLoading}
          emptyText="No call transcripts ingested yet."
        />
      </div>

      <Card>
        <CardHeader
          title="What the assistant can answer on a call"
          subtitle="Each tool reads this project's live database — none of them return canned text."
          icon={<Sparkles className="h-4 w-4" />}
        />
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-b-xl bg-surface-raised sm:grid-cols-2">
          {[
            { name: "get_project_progress", ask: "“How is the project doing?”", returns: "Status and planned dates for every project the caller is a member of." },
            { name: "get_delayed_activities", ask: "“What's delayed?”", returns: "Activities past their planned finish that aren't reported complete, worst first, with days late and percent complete." },
            { name: "get_risk_summary", ask: "“What's at risk?”", returns: "High and critical delay forecasts, named by activity code, with probability and forecast slip." },
            { name: "get_activity_details", ask: "“Tell me about A1010.”", returns: "That activity's latest reported status and percent complete." },
            { name: "get_project_report", ask: "“Send me a report.”", returns: "Generates an executive overview PDF through the reporting service." },
          ].map((tool) => (
            <div key={tool.name} className="bg-surface-card p-4">
              <p className="font-mono text-2xs font-medium text-accent">{tool.name}</p>
              <p className="mt-1.5 text-sm text-content-1">{tool.ask}</p>
              <p className="mt-1 text-xs leading-relaxed text-content-3">{tool.returns}</p>
            </div>
          ))}
          <div className="bg-surface-card p-4" />
        </div>
      </Card>

      {canManage && <NotifyCard projectId={projectId} />}
    </div>
  );
}

function ChannelCard({
  icon,
  title,
  blurb,
  endpoint,
  authNote,
  items,
  loading,
  emptyText,
}: {
  icon: React.ReactNode;
  title: string;
  blurb: string;
  endpoint: string;
  authNote: string;
  items: UploadedFileRead[];
  loading: boolean;
  emptyText: string;
}) {
  const [copied, setCopied] = useState(false);
  const url = `${API_BASE_URL}${endpoint}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — the URL is visible on screen regardless */
    }
  };

  return (
    <Card className="flex flex-col">
      <CardHeader
        title={title}
        icon={icon}
        action={
          items.length > 0 ? (
            <Badge tone="green">{items.length} received</Badge>
          ) : (
            <Badge tone="slate">awaiting traffic</Badge>
          )
        }
      />
      <div className="space-y-3 p-4">
        <p className="text-xs leading-relaxed text-content-2">{blurb}</p>

        <div>
          <p className="mb-1 text-2xs font-medium text-content-2">Webhook URL</p>
          <div className="flex items-center gap-2 rounded-[10px] border border-line bg-surface-raised px-2.5 py-1.5">
            <code className="min-w-0 flex-1 truncate font-mono text-2xs text-content-1">{url}</code>
            <button
              onClick={copy}
              className="shrink-0 rounded p-1 text-content-2 transition-colors hover:bg-surface-card hover:text-content-1"
              title="Copy"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-teal-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        <p className="flex gap-2 rounded-[10px] bg-surface-raised p-2.5 text-2xs leading-relaxed text-content-2">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-600" />
          {authNote}
        </p>

        <div>
          <p className="mb-1.5 text-2xs font-medium text-content-2">
            Recent inbound
          </p>
          {loading && <LoadingRows rows={2} />}
          {!loading && items.length === 0 && <EmptyState compact title={emptyText} />}
          {!loading && items.length > 0 && (
            <ul className="space-y-1.5">
              {items.slice(0, 5).map((item) => (
                <li
                  key={item.id}
                  className="flex items-center justify-between gap-2 rounded-[10px] border border-line px-2.5 py-2"
                >
                  <span className="truncate text-2xs text-content-2">
                    {item.size_bytes} bytes · {item.document_type.replaceAll("_", " ").toLowerCase()}
                  </span>
                  <span className="shrink-0 text-2xs text-content-2">
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

interface NotifyForm {
  channel: NotificationChannel;
  notification_type: string;
  title: string;
  body: string;
  recipient_address: string;
  recipient_user_id: string;
}

function NotifyCard({ projectId }: { projectId: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { register, handleSubmit, reset, watch, setValue } = useForm<NotifyForm>({
    defaultValues: {
      channel: "WHATSAPP",
      notification_type: "site_update",
      title: "",
      body: "",
      recipient_address: "",
      recipient_user_id: "",
    },
  });
  const channel = watch("channel");
  const notificationType = watch("notification_type");
  const recipientUserId = watch("recipient_user_id");

  // In-app notifications are addressed to a user id, the other channels to an
  // address, so the recipient control changes with the channel.
  const membersQuery = useQuery({
    queryKey: ["members", projectId],
    queryFn: () => projectsApi.listMembers(projectId),
    enabled: channel === "IN_APP",
  });

  const sendMutation = useMutation({
    mutationFn: (values: NotifyForm) =>
      notificationsApi.sendProjectNotification(projectId, {
        channel: values.channel,
        notification_type: values.notification_type,
        title: values.title,
        body: values.body,
        recipient_address:
          values.channel === "IN_APP" ? undefined : values.recipient_address.trim() || undefined,
        recipient_user_id: values.channel === "IN_APP" ? values.recipient_user_id || undefined : undefined,
      }),
    onSuccess: (created) => {
      // A dry run and a real Cloud API send both come back DELIVERED, and the
      // response carries nothing that separates them — so the WhatsApp caveat
      // is stated every time rather than claiming a delivery we can't confirm.
      const failed = created.status === "FAILED";
      toast.success(
        failed ? "Notification not delivered" : "Notification accepted",
        `Backend reported status: ${created.status}.` +
          (created.channel === "WHATSAPP" && !failed
            ? " If META_ACCESS_TOKEN and META_PHONE_NUMBER_ID aren't set, this was recorded as a dry run rather than sent through Meta."
            : ""),
      );
      reset({
        channel: created.channel,
        notification_type: "site_update",
        title: "",
        body: "",
        recipient_address: "",
        recipient_user_id: "",
      });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) =>
      toast.error(
        "Could not send",
        err instanceof ApiError ? err.message : "The notification was not accepted.",
      ),
  });

  return (
    <Card>
      <CardHeader
        title="Send a notification"
        subtitle="Delivery status is shown exactly as the backend reports it — nothing is presented as delivered unless it says so."
        icon={<Send className="h-4 w-4" />}
      />
      <form
        className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
        onSubmit={handleSubmit((values) => sendMutation.mutate(values))}
      >
        <Field label="Channel">
          <input type="hidden" {...register("channel")} />
          <SelectMenu<NotificationChannel>
            value={channel}
            width="w-56"
            options={[
              {
                value: "WHATSAPP",
                label: "WhatsApp",
                icon: <MessageSquare className="h-3.5 w-3.5" />,
              },
              { value: "EMAIL", label: "Email", icon: <Mail className="h-3.5 w-3.5" /> },
              { value: "IN_APP", label: "In-app", icon: <Monitor className="h-3.5 w-3.5" /> },
            ]}
            onChange={(v) => v && setValue("channel", v, { shouldDirty: true })}
          />
        </Field>

        {channel === "IN_APP" ? (
          <Field label="Recipient" hint="Must be a member of this project.">
            <input type="hidden" {...register("recipient_user_id")} />
            <SelectMenu
              value={recipientUserId}
              width="w-72"
              placeholder={membersQuery.isLoading ? "Loading members…" : "Choose a member…"}
              options={(membersQuery.data ?? []).map((m) => ({
                value: m.user_id,
                label: m.full_name,
                hint: m.email,
              }))}
              onChange={(v) => setValue("recipient_user_id", v, { shouldDirty: true })}
            />
          </Field>
        ) : (
          <Field
            label={channel === "WHATSAPP" ? "Recipient number" : "Recipient email"}
            hint={
              channel === "WHATSAPP"
                ? "Full international format, e.g. +919876543210."
                : "Where the message should be delivered."
            }
          >
            <Input
              placeholder={channel === "WHATSAPP" ? "+91 98765 43210" : "name@example.com"}
              {...register("recipient_address", { required: true })}
            />
          </Field>
        )}

        <Field label="Type" hint="Free text — it is stored on the notification record.">
          <div className="flex gap-2">
            <Input className="flex-1" {...register("notification_type", { required: true })} />
            <Dropdown label="Presets" width="w-56" align="right">
              {(close) => (
                <>
                  <DropdownLabel>Common types</DropdownLabel>
                  {["site_update", "delay_alert", "match_review", "schedule_change"].map((t) => (
                    <DropdownItem
                      key={t}
                      selected={t === notificationType}
                      onSelect={() => {
                        setValue("notification_type", t, { shouldDirty: true });
                        close();
                      }}
                    >
                      {t}
                    </DropdownItem>
                  ))}
                </>
              )}
            </Dropdown>
          </div>
        </Field>
        <Field label="Title">
          <Input placeholder="Concrete pour rescheduled" {...register("title", { required: true })} />
        </Field>
        <Field label="Message" className="sm:col-span-2">
          <Textarea rows={2} {...register("body", { required: true })} />
        </Field>

        <div className="sm:col-span-2">
          {channel === "WHATSAPP" && (
            <p className="mb-2 flex items-start gap-1.5 rounded-[10px] bg-amber-50 p-2.5 text-2xs leading-relaxed text-amber-800">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              A real message is only sent once META_ACCESS_TOKEN and META_PHONE_NUMBER_ID are set;
              until then the dispatcher records a dry run. Note the backend does not currently check
              that this number belongs to a project member — see the deployment note before pointing
              it at live Meta credentials.
            </p>
          )}
          <Button type="submit" loading={sendMutation.isPending}>
            <Send className="h-4 w-4" />
            Send notification
          </Button>
        </div>
      </form>
    </Card>
  );
}
