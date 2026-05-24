"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { toman, jDate } from "@/lib/fmt";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight } from "lucide-react";

interface UserDetail {
  id: number;
  phone: string;
  name?: string;
  is_blocked: boolean;
  created_at: string;
  transactions?: { id: number; amount: number; type: string; description: string; date: string }[];
  activity?: { action: string; created_at: string }[];
}

export default function UserDetailPage() {
  const { id } = useParams();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await adminApi.get(`/admin/users/${id}`);
        setUser(res.data);
      } catch {
        toast.error("خطا در بارگذاری اطلاعات کاربر");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) return <Skeleton className="h-96 rounded-2xl" />;
  if (!user) return <p className="text-center py-16 text-muted-foreground">کاربر یافت نشد</p>;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" asChild aria-label="بازگشت">
          <Link href="/admin/users"><ArrowRight className="h-5 w-5" /></Link>
        </Button>
        <h1 className="text-2xl font-bold">اطلاعات کاربر</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">پروفایل</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="text-muted-foreground">شماره: </span><span dir="ltr">{user.phone}</span></div>
          <div><span className="text-muted-foreground">نام: </span>{user.name || "—"}</div>
          <div><span className="text-muted-foreground">وضعیت: </span><Badge variant={user.is_blocked ? "destructive" : "success"}>{user.is_blocked ? "مسدود" : "فعال"}</Badge></div>
          <div><span className="text-muted-foreground">تاریخ عضویت: </span>{jDate(user.created_at)}</div>
        </CardContent>
      </Card>

      {user.transactions && user.transactions.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">آخرین تراکنش‌ها</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-start py-2 font-medium">تاریخ</th>
                  <th className="text-start py-2 font-medium">توضیح</th>
                  <th className="text-start py-2 font-medium">نوع</th>
                  <th className="text-end py-2 font-medium">مبلغ</th>
                </tr>
              </thead>
              <tbody>
                {user.transactions.map((tx) => (
                  <tr key={tx.id} className="border-b last:border-0">
                    <td className="py-2">{jDate(tx.date)}</td>
                    <td className="py-2">{tx.description}</td>
                    <td className="py-2"><Badge variant={tx.type === "expense" ? "destructive" : "success"}>{tx.type === "expense" ? "هزینه" : "درآمد"}</Badge></td>
                    <td className={`py-2 text-end font-bold ${tx.type === "expense" ? "text-rose-600" : "text-emerald-600"}`}>{toman(tx.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {user.activity && user.activity.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">گزارش فعالیت</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {user.activity.map((a, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 border-b last:border-0 text-sm">
                  <span>{a.action}</span>
                  <span className="text-xs text-muted-foreground">{jDate(a.created_at)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {(!user.transactions || user.transactions.length === 0) && (!user.activity || user.activity.length === 0) && (
        <p className="text-center text-muted-foreground py-8">سابقه فعالیتی یافت نشد</p>
      )}
    </div>
  );
}
