import { useForm } from "react-hook-form";
import { useMutation } from "@tanstack/react-query";
import { KeyRound, Mail, Phone, Save, ShieldCheck, UserRound } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useToast } from "@/components/ui/Toast";
import { Badge } from "@/components/common/Badge";
import { Button, Card, CardHeader, Field, Input, PageHeader } from "@/components/ui/Primitives";

interface ProfileForm {
  full_name: string;
  phone: string;
}
interface PasswordForm {
  current_password: string;
  password: string;
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function Profile() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();

  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    formState: { errors: profileErrors },
  } = useForm<ProfileForm>({
    values: { full_name: user?.full_name ?? "", phone: user?.phone ?? "" },
  });

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    reset: resetPassword,
    formState: { errors: passwordErrors },
  } = useForm<PasswordForm>();

  const profileMutation = useMutation({
    mutationFn: (values: ProfileForm) => authApi.updateProfile(user!.id, values),
    onSuccess: async () => {
      await refreshUser();
      toast.success("Profile updated", "Your name and contact details are saved.");
    },
    onError: (err) =>
      toast.error("Could not update profile", err instanceof ApiError ? err.message : undefined),
  });

  const passwordMutation = useMutation({
    mutationFn: (values: PasswordForm) => authApi.changePassword(values),
    onSuccess: () => {
      resetPassword();
      toast.success("Password changed", "Every other active session has been signed out.");
    },
    onError: (err) =>
      toast.error(
        "Could not change password",
        err instanceof ApiError
          ? err.status === 401
            ? "That current password wasn't accepted."
            : err.message
          : undefined,
      ),
  });

  if (!user) return null;

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Profile"
        subtitle="Your account details and the credentials you sign in with."
      />

      <div className="space-y-6">
        <Card>
          <div className="flex flex-wrap items-center gap-4 p-5">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[14px] bg-ink-900 text-base font-semibold text-white">
              {initials(user.full_name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.95rem] font-semibold tracking-[-0.01em] text-content-1">
                {user.full_name}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="flex items-center gap-1.5 text-xs text-content-3">
                  <Mail className="h-3.5 w-3.5 text-content-2" />
                  {user.email}
                </span>
                {user.phone && (
                  <span className="flex items-center gap-1.5 text-xs text-content-3">
                    <Phone className="h-3.5 w-3.5 text-content-2" />
                    {user.phone}
                  </span>
                )}
              </div>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <Badge tone="blue" icon={<ShieldCheck className="h-3 w-3" />}>
                {user.role.replaceAll("_", " ").toLowerCase()}
              </Badge>
              <Badge tone={user.is_active ? "green" : "slate"}>
                {user.is_active ? "Active" : "Inactive"}
              </Badge>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Account details"
            subtitle="Your email is set by an administrator and can't be changed here."
            icon={<UserRound className="h-4 w-4" />}
          />
          <form
            className="space-y-4 p-4"
            onSubmit={handleProfileSubmit((values) => profileMutation.mutate(values))}
          >
            <Field label="Full name" error={profileErrors.full_name?.message}>
              <Input
                placeholder="Anita Barua"
                {...registerProfile("full_name", { required: "Required" })}
              />
            </Field>

            <Field label="Phone" hint="Used for WhatsApp and voice alerts, if those channels are on.">
              <Input placeholder="+91 98765 43210" {...registerProfile("phone")} />
            </Field>

            <div className="flex justify-end border-t border-line pt-4">
              <Button type="submit" loading={profileMutation.isPending}>
                <Save className="h-4 w-4" />
                Save changes
              </Button>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader
            title="Change password"
            subtitle="Signs out every other active session, on every device."
            icon={<KeyRound className="h-4 w-4" />}
          />
          <form
            className="space-y-4 p-4"
            onSubmit={handlePasswordSubmit((values) => passwordMutation.mutate(values))}
          >
            <Field label="Current password" error={passwordErrors.current_password?.message}>
              <Input
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                {...registerPassword("current_password", { required: "Required" })}
              />
            </Field>

            <Field
              label="New password"
              error={passwordErrors.password?.message}
              hint="At least 8 characters, mixing letters and at least one number."
            >
              <Input
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                {...registerPassword("password", {
                  required: "Required",
                  minLength: { value: 8, message: "At least 8 characters" },
                })}
              />
            </Field>

            <div className="flex justify-end border-t border-line pt-4">
              <Button type="submit" loading={passwordMutation.isPending}>
                <KeyRound className="h-4 w-4" />
                Change password
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
