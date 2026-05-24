"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import api from "@/lib/api";
import { toman, toFa, jDate } from "@/lib/fmt";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Legend
} from "recharts";
import { MessageCircle, TrendingDown, TrendingUp, Wallet, Target } from "lucide-react";

interface Summary {
  total_income: number;
  total_expense: number;
  budget_amount: number;
  remaining: number;
  by_category: { category: string; amount: number }[];
  daily: { date: string; amount: number }[];
}

interface Transaction {
  id: number;
  amount: number;
  type: string;
  description: string;
  category_name: string;
  date: string;
}

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#64748b"];

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [sumRes, txRes] = await Promise.all([
          api.get("/transactions/summary"),
          api.get("/transactions?limit=5"),
        ]);
        setSummary(sumRes.data);
        setTransactions(txRes.data.items || txRes.data);
      } catch {
        toast.error("خطا در بارگذاری اطلاعات");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <DashboardSkeleton />;

  const budget = summary?.budget_amount || 0;
  const spent = summary?.total_expense || 0;
  const remaining = summary?.remaining ?? (budget - spent);
  const percent = budget > 0 ? Math.min(100, Math.round((spent / budget) * 100)) : 0;

  const pieData = (summary?.by_category || []).slice(0, 6).map((c) => ({
    name: c.category,
    value: c.amount,
  }));
  const otherSum = (summary?.by_category || []).slice(6).reduce((a, b) => a + b.amount, 0);
  if (otherSum > 0) pieData.push({ name: "سایر", value: otherSum });

  const lineData = (summary?.daily || []).map((d) => ({
    name: jDate(d.date),
    مبلغ: d.amount,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">داشبورد</h1>
        <Button asChild>
          <Link href="/chat">
            <MessageCircle className="h-4 w-4" />
            گفت‌وگو با دستیار
          </Link>
        </Button>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="بودجه ماهانه"
          value={toman(budget)}
          icon={<Wallet className="h-5 w-5 text-indigo-500" />}
          color="bg-indigo-50"
        />
        <StatCard
          title="خرج این ماه"
          value={toman(spent)}
          icon={<TrendingDown className="h-5 w-5 text-rose-500" />}
          color="bg-rose-50"
        />
        <StatCard
          title="باقی‌مانده"
          value={toman(remaining)}
          icon={<TrendingUp className="h-5 w-5 text-emerald-500" />}
          color="bg-emerald-50"
        />
        <Card className="col-span-2 lg:col-span-1">
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50">
                <Target className="h-5 w-5 text-amber-500" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">درصد مصرف</p>
                <p className="text-lg font-bold">{toFa(percent)}٪</p>
              </div>
            </div>
            <Progress value={percent} className={percent > 90 ? "[&>div]:bg-rose-500" : percent > 70 ? "[&>div]:bg-amber-500" : ""} />
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-4">
        {pieData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">هزینه‌ها بر اساس دسته</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={false} labelLine={false}>
                    {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => toman(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {lineData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">هزینه‌های ۷ روز اخیر</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={lineData}>
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => toFa(Math.round(v / 1000) + "ک")} />
                  <Tooltip formatter={(v) => toman(Number(v))} />
                  <Legend />
                  <Line type="monotone" dataKey="مبلغ" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Recent Transactions */}
      {transactions.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">آخرین تراکنش‌ها</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/transactions">مشاهده همه</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {transactions.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-2 border-b last:border-0">
                <div className="flex items-center gap-2">
                  <Badge variant={tx.type === "expense" ? "destructive" : "success"}>
                    {tx.type === "expense" ? "هزینه" : "درآمد"}
                  </Badge>
                  <span className="text-sm font-medium">{tx.description}</span>
                  <span className="text-xs text-muted-foreground">{tx.category_name}</span>
                </div>
                <div className="text-end">
                  <p className={`text-sm font-bold ${tx.type === "expense" ? "text-rose-600" : "text-emerald-600"}`}>
                    {tx.type === "expense" ? "-" : "+"}{toman(tx.amount)}
                  </p>
                  <p className="text-xs text-muted-foreground">{jDate(tx.date)}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({ title, value, icon, color }: { title: string; value: string; icon: React.ReactNode; color: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${color}`}>{icon}</div>
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            <p className="text-sm font-bold truncate">{value}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-40" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Skeleton className="h-64 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    </div>
  );
}
