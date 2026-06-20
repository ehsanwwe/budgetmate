"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { jDate, relativeTime, toFa } from "@/lib/fmt";
import { incomeRangeLabelI18n, chatModeLabelI18n } from "@/lib/labels";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { LOCALE_META } from "@/i18n/config";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, ShieldOff, Loader2 } from "lucide-react";
import DeleteUserDialog from "@/components/admin/DeleteUserDialog";
import UserChatHistory from "@/components/admin/UserChatHistory";

interface UserDetail {
  id: number;
  phone: string;
  name?: string;
  family_name?: string;
  birthdate?: string;
  province?: string;
  city?: string;
  income_range?: string;
  agreement_accepted_at?: string;
  agreement_version?: string;
  onboarding_completed: boolean;
  onboarding_completed_at?: string;
  chat_mode?: string;
  language: string;
  created_at: string;
  is_blocked: boolean;
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr className="even:bg-slate-50 odd:bg-white">
      <td className="text-slate-500 text-sm font-medium px-4 py-3 w-1/3">{label}</td>
      <td className="text-slate-900 font-medium px-4 py-3">{children}</td>
    </tr>
  );
}

export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const router = useRouter();
  const { dict } = useLocale();
  const t = dict.admin.userDetailPage;
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [blockLoading, setBlockLoading] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const loadUser = useCallback(async () => {
    try {
      const res = await adminApi.get<UserDetail>(`/admin/users/${id}`);
      setUser(res.data);
    } catch {
      toast.error(t.loadError);
    } finally {
      setLoading(false);
    }
  }, [id, t.loadError]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadUser();
    });
  }, [loadUser]);

  async function toggleBlock() {
    if (!user) return;
    setBlockLoading(true);
    try {
      const action = user.is_blocked ? "unblock" : "block";
      await adminApi.post(`/admin/users/${user.id}/${action}`);
      toast.success(user.is_blocked ? t.actions.unblocked : t.actions.blocked);
      await loadUser();
    } catch {
      toast.error(t.actions.actionError);
    } finally {
      setBlockLoading(false);
    }
  }

  if (loading) return <Skeleton className="h-96 rounded-2xl" />;
  if (!user) return <p className="text-center py-16 text-muted-foreground">{t.notFound}</p>;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const langMeta = (LOCALE_META as any)[user.language];
  const languageDisplay = langMeta?.nativeName ?? user.language;

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">{t.title}</h1>

      <Tabs defaultValue="info">
        <TabsList className="mb-4">
          <TabsTrigger value="info">{t.tabInfo}</TabsTrigger>
          <TabsTrigger value="chats">{t.tabChats}</TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <div className="rounded-2xl border overflow-hidden">
            <table className="w-full">
              <tbody>
                <InfoRow label={t.fields.id}>#{toFa(user.id)}</InfoRow>
                <InfoRow label={t.fields.phone}>
                  <span dir="ltr" className="font-mono">{user.phone}</span>
                </InfoRow>
                <InfoRow label={t.fields.firstName}>{user.name || "—"}</InfoRow>
                <InfoRow label={t.fields.lastName}>{user.family_name || "—"}</InfoRow>
                <InfoRow label={t.fields.birthdate}>
                  {user.birthdate ? jDate(user.birthdate) : "—"}
                </InfoRow>
                <InfoRow label={t.fields.province}>{user.province || "—"}</InfoRow>
                <InfoRow label={t.fields.city}>{user.city || "—"}</InfoRow>
                <InfoRow label={t.fields.incomeRange}>{incomeRangeLabelI18n(dict, user.income_range)}</InfoRow>
                <InfoRow label={t.fields.onboardingStatus}>
                  {user.onboarding_completed ? (
                    <Badge variant="success">{t.fields.onboardingDone}</Badge>
                  ) : (
                    <Badge variant="warning">{t.fields.onboardingPending}</Badge>
                  )}
                </InfoRow>
                <InfoRow label={t.fields.agreement}>
                  {user.agreement_accepted_at
                    ? tDict(dict, "admin.userDetailPage.fields.agreementValue", {
                        date: jDate(user.agreement_accepted_at),
                        version: user.agreement_version ?? "—",
                      })
                    : t.fields.agreementNone}
                </InfoRow>
                <InfoRow label={t.fields.chatMode}>{chatModeLabelI18n(dict, user.chat_mode)}</InfoRow>
                <InfoRow label={t.fields.language}>{languageDisplay}</InfoRow>
                <InfoRow label={t.fields.createdAt}>
                  {jDate(user.created_at)}{" "}
                  <span className="text-slate-500 text-xs">({relativeTime(user.created_at)})</span>
                </InfoRow>
                <InfoRow label={t.fields.statusLabel}>
                  {user.is_blocked ? (
                    <Badge variant="destructive">{t.fields.statusBlocked}</Badge>
                  ) : (
                    <Badge variant="success">{t.fields.statusActive}</Badge>
                  )}
                </InfoRow>
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-3 mt-4">
            <Button
              variant={user.is_blocked ? "outline" : "secondary"}
              onClick={toggleBlock}
              disabled={blockLoading}
            >
              {blockLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : user.is_blocked ? (
                <><ShieldOff className="h-4 w-4 me-1.5" />{t.actions.unblock}</>
              ) : (
                <><Shield className="h-4 w-4 me-1.5" />{t.actions.block}</>
              )}
            </Button>
            <Button
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            >
              {t.actions.delete}
            </Button>
            <Button variant="outline" onClick={() => router.push(`/${locale}/admin/users`)}>
              {t.actions.back}
            </Button>
          </div>

          <DeleteUserDialog
            user={{ id: user.id, phone: user.phone, name: user.name }}
            open={deleteOpen}
            onOpenChange={setDeleteOpen}
            onDeleted={() => router.push(`/${locale}/admin/users`)}
          />
        </TabsContent>

        <TabsContent value="chats">
          <div className="rounded-2xl border p-4 min-h-64">
            <UserChatHistory userId={id} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
