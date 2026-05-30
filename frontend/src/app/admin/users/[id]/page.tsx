"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { jDate, relativeTime, toFa } from "@/lib/fmt";
import { incomeRangeLabel, chatModeLabel } from "@/lib/labels";
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
  const router = useRouter();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [blockLoading, setBlockLoading] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  async function loadUser() {
    try {
      const res = await adminApi.get<UserDetail>(`/admin/users/${id}`);
      setUser(res.data);
    } catch {
      toast.error("خطا در بارگذاری اطلاعات کاربر");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadUser(); }, [id]);

  async function toggleBlock() {
    if (!user) return;
    setBlockLoading(true);
    try {
      const action = user.is_blocked ? "unblock" : "block";
      await adminApi.post(`/admin/users/${user.id}/${action}`);
      toast.success(user.is_blocked ? "کاربر رفع مسدودی شد" : "کاربر مسدود شد");
      await loadUser();
    } catch {
      toast.error("خطا در انجام عملیات");
    } finally {
      setBlockLoading(false);
    }
  }

  if (loading) return <Skeleton className="h-96 rounded-2xl" />;
  if (!user) return <p className="text-center py-16 text-muted-foreground">کاربر یافت نشد</p>;

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">اطلاعات کاربر</h1>

      <Tabs defaultValue="info">
        <TabsList className="mb-4">
          <TabsTrigger value="info">اطلاعات کاربر</TabsTrigger>
          <TabsTrigger value="chats">گفت‌وگوها</TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <div className="rounded-2xl border overflow-hidden">
            <table className="w-full">
              <tbody>
                <InfoRow label="شناسه">#{toFa(user.id)}</InfoRow>
                <InfoRow label="شماره موبایل">
                  <span dir="ltr" className="font-mono">{user.phone}</span>
                </InfoRow>
                <InfoRow label="نام">{user.name || "—"}</InfoRow>
                <InfoRow label="نام خانوادگی">{user.family_name || "—"}</InfoRow>
                <InfoRow label="تاریخ تولد">
                  {user.birthdate ? jDate(user.birthdate) : "—"}
                </InfoRow>
                <InfoRow label="استان">{user.province || "—"}</InfoRow>
                <InfoRow label="شهر">{user.city || "—"}</InfoRow>
                <InfoRow label="بازه درآمد">{incomeRangeLabel(user.income_range)}</InfoRow>
                <InfoRow label="وضعیت آنبوردینگ">
                  {user.onboarding_completed ? (
                    <Badge variant="success">تکمیل شده</Badge>
                  ) : (
                    <Badge variant="warning">ناتمام</Badge>
                  )}
                </InfoRow>
                <InfoRow label="موافقت با قوانین">
                  {user.agreement_accepted_at
                    ? `${jDate(user.agreement_accepted_at)} — نسخه ${user.agreement_version ?? "—"}`
                    : "ثبت نشده"}
                </InfoRow>
                <InfoRow label="حالت دستیار">{chatModeLabel(user.chat_mode)}</InfoRow>
                <InfoRow label="زبان">
                  {user.language === "fa" ? "فارسی" : user.language}
                </InfoRow>
                <InfoRow label="تاریخ ثبت‌نام">
                  {jDate(user.created_at)}{" "}
                  <span className="text-slate-500 text-xs">({relativeTime(user.created_at)})</span>
                </InfoRow>
                <InfoRow label="وضعیت">
                  {user.is_blocked ? (
                    <Badge variant="destructive">مسدود</Badge>
                  ) : (
                    <Badge variant="success">فعال</Badge>
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
                <><ShieldOff className="h-4 w-4 me-1.5" />رفع مسدودی</>
              ) : (
                <><Shield className="h-4 w-4 me-1.5" />مسدود کردن</>
              )}
            </Button>
            <Button
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            >
              حذف کاربر
            </Button>
            <Button variant="outline" onClick={() => router.push("/admin/users")}>
              بازگشت
            </Button>
          </div>

          <DeleteUserDialog
            user={{ id: user.id, phone: user.phone, name: user.name }}
            open={deleteOpen}
            onOpenChange={setDeleteOpen}
            onDeleted={() => router.push("/admin/users")}
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
