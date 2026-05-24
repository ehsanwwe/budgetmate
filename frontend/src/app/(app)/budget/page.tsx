"use client";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import api from "@/lib/api";
import { toman, toFa } from "@/lib/fmt";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { MoneyInput } from "@/components/money-input";
import { Wallet, Loader2 } from "lucide-react";

const budgetSchema = z.object({
  amount: z.number({ message: "مبلغ معتبر وارد کنید" }).positive("مبلغ باید مثبت باشد"),
});
type BudgetForm = z.infer<typeof budgetSchema>;

interface Budget { id: number; amount: number; month: number; year: number; }
interface Summary { total_expense: number; }

export default function BudgetPage() {
  const [budget, setBudget] = useState<Budget | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);

  const { control, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<BudgetForm>({
    resolver: zodResolver(budgetSchema),
  });

  useEffect(() => {
    async function load() {
      try {
        const [budRes, sumRes] = await Promise.all([
          api.get("/budgets/current").catch(() => ({ data: null })),
          api.get("/transactions/summary"),
        ]);
        setBudget(budRes.data);
        setSummary(sumRes.data);
        if (budRes.data) reset({ amount: budRes.data.amount });
      } catch {
        toast.error("خطا در بارگذاری بودجه");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [reset]);

  async function onSubmit(data: BudgetForm) {
    try {
      let res;
      if (budget) {
        res = await api.put(`/budgets/${budget.id}`, data);
      } else {
        res = await api.post("/budgets", data);
      }
      setBudget(res.data);
      toast.success("بودجه ذخیره شد");
      setEditing(false);
    } catch {
      toast.error("خطا در ذخیره بودجه");
    }
  }

  if (loading) return <Skeleton className="h-64 rounded-2xl" />;

  const spent = summary?.total_expense || 0;
  const budgetAmount = budget?.amount || 0;
  const remaining = budgetAmount - spent;
  const percent = budgetAmount > 0 ? Math.min(100, Math.round((spent / budgetAmount) * 100)) : 0;

  const now = new Date();
  const persianMonths = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور","مهر","آبان","آذر","دی","بهمن","اسفند"];
  const monthName = persianMonths[now.getMonth()];

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold">بودجه ماهانه</h1>

      <Card className="bg-gradient-to-br from-indigo-50 to-purple-50 border-indigo-100">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary shadow-lg">
              <Wallet className="h-6 w-6 text-white" />
            </div>
            <div>
              <CardTitle>بودجه {monthName}</CardTitle>
              <CardDescription>ماه جاری</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {budget ? (
            <>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="rounded-xl bg-white/80 p-3">
                  <p className="text-xs text-muted-foreground">بودجه</p>
                  <p className="font-bold text-sm">{toman(budgetAmount)}</p>
                </div>
                <div className="rounded-xl bg-white/80 p-3">
                  <p className="text-xs text-muted-foreground">خرج شده</p>
                  <p className="font-bold text-sm text-rose-600">{toman(spent)}</p>
                </div>
                <div className="rounded-xl bg-white/80 p-3">
                  <p className="text-xs text-muted-foreground">باقی‌مانده</p>
                  <p className={`font-bold text-sm ${remaining < 0 ? "text-rose-600" : "text-emerald-600"}`}>{toman(Math.abs(remaining))}</p>
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>مصرف بودجه</span>
                  <span>{toFa(percent)}٪</span>
                </div>
                <Progress value={percent} className={percent > 90 ? "[&>div]:bg-rose-500" : percent > 70 ? "[&>div]:bg-amber-500" : ""} />
              </div>
              <Button variant="outline" className="w-full" onClick={() => setEditing(!editing)}>
                {editing ? "انصراف" : "ویرایش بودجه"}
              </Button>
            </>
          ) : (
            <p className="text-center text-muted-foreground py-4">هنوز بودجه‌ای تعریف نشده</p>
          )}
        </CardContent>
      </Card>

      {(!budget || editing) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{budget ? "ویرایش بودجه" : "تعریف بودجه ماهانه"}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="space-y-1.5">
                <Label>مبلغ بودجه (تومان)</Label>
                <Controller
                  name="amount"
                  control={control}
                  render={({ field }) => (
                    <MoneyInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder="مثال: ۵,۰۰۰,۰۰۰"
                      error={!!errors.amount}
                    />
                  )}
                />
                {errors.amount && <p className="text-xs text-destructive">{errors.amount.message}</p>}
              </div>
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                ذخیره بودجه
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
