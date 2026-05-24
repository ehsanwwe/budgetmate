"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { toFa } from "@/lib/fmt";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, ArrowLeftRight, Target, Wallet, Activity } from "lucide-react";

interface Stats {
  total_users: number;
  active_users: number;
  blocked_users: number;
  total_transactions: number;
  total_goals: number;
}

interface ActivityItem {
  id: number;
  action: string;
  created_at: string;
  user_phone?: string;
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [statsRes, actRes] = await Promise.all([
          adminApi.get("/admin/stats"),
          adminApi.get("/admin/activity?limit=10"),
        ]);
        setStats(statsRes.data);
        setActivity(actRes.data || []);
      } catch {
        toast.error("خطا در بارگذاری اطلاعات");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}</div>;

  const statCards = [
    { title: "کل کاربران", value: stats?.total_users || 0, icon: <Users className="h-5 w-5 text-indigo-500" />, color: "bg-indigo-50" },
    { title: "کاربران فعال", value: stats?.active_users || 0, icon: <Activity className="h-5 w-5 text-emerald-500" />, color: "bg-emerald-50" },
    { title: "کاربران مسدود", value: stats?.blocked_users || 0, icon: <Users className="h-5 w-5 text-rose-500" />, color: "bg-rose-50" },
    { title: "تراکنش‌ها", value: stats?.total_transactions || 0, icon: <ArrowLeftRight className="h-5 w-5 text-amber-500" />, color: "bg-amber-50" },
    { title: "اهداف", value: stats?.total_goals || 0, icon: <Target className="h-5 w-5 text-purple-500" />, color: "bg-purple-50" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">داشبورد مدیریت</h1>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {statCards.map((c, i) => (
          <Card key={i}>
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${c.color}`}>{c.icon}</div>
                <div>
                  <p className="text-xs text-muted-foreground">{c.title}</p>
                  <p className="text-xl font-bold">{toFa(c.value)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">آخرین فعالیت‌ها</CardTitle>
        </CardHeader>
        <CardContent>
          {activity.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">فعالیتی ثبت نشده</p>
          ) : (
            <div className="space-y-2">
              {activity.map((a, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <span className="text-sm">{a.action}</span>
                  {a.user_phone && <span className="text-xs text-muted-foreground" dir="ltr">{a.user_phone}</span>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
