"use client";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import api from "@/lib/api";
import { toman, toFa, jDate } from "@/lib/fmt";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { MoneyInput } from "@/components/money-input";
import { Plus, Target, PlusCircle, Loader2 } from "lucide-react";

const goalSchema = z.object({
  title: z.string().min(1, "عنوان الزامی است"),
  target_amount: z.number().positive("مبلغ هدف باید مثبت باشد"),
  deadline: z.string().optional(),
});
type GoalForm = z.infer<typeof goalSchema>;

const contributeSchema = z.object({
  amount: z.number().positive("مبلغ باید مثبت باشد"),
});
type ContributeForm = z.infer<typeof contributeSchema>;

interface Goal {
  id: number;
  title: string;
  target_amount: number;
  current_amount: number;
  deadline?: string;
}

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [contributeGoal, setContributeGoal] = useState<Goal | null>(null);

  const goalForm = useForm<GoalForm>({ resolver: zodResolver(goalSchema) });
  const contributeForm = useForm<ContributeForm>({ resolver: zodResolver(contributeSchema) });

  async function load() {
    try {
      const res = await api.get("/goals");
      setGoals(res.data);
    } catch {
      toast.error("خطا در بارگذاری اهداف");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    queueMicrotask(() => {
      void load();
    });
  }, []);

  async function onCreateGoal(data: GoalForm) {
    try {
      await api.post("/goals", data);
      toast.success("هدف ایجاد شد");
      setOpen(false);
      goalForm.reset();
      load();
    } catch {
      toast.error("خطا در ایجاد هدف");
    }
  }

  async function onContribute(data: ContributeForm) {
    if (!contributeGoal) return;
    try {
      await api.post(`/goals/${contributeGoal.id}/contribute`, data);
      toast.success("مبلغ افزوده شد");
      setContributeGoal(null);
      contributeForm.reset();
      load();
    } catch {
      toast.error("خطا در افزودن مبلغ");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">اهداف مالی</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4" />هدف جدید</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>ایجاد هدف مالی</DialogTitle></DialogHeader>
            <form onSubmit={goalForm.handleSubmit(onCreateGoal)} className="space-y-4 mt-2">
              <div className="space-y-1.5">
                <Label>عنوان هدف</Label>
                <Input {...goalForm.register("title")} placeholder="مثال: خرید لپ‌تاپ" />
                {goalForm.formState.errors.title && <p className="text-xs text-destructive">{goalForm.formState.errors.title.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>مبلغ هدف (تومان)</Label>
                <Controller
                  name="target_amount"
                  control={goalForm.control}
                  render={({ field }) => (
                    <MoneyInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder="مثال: ۳۰,۰۰۰,۰۰۰"
                      error={!!goalForm.formState.errors.target_amount}
                    />
                  )}
                />
                {goalForm.formState.errors.target_amount && <p className="text-xs text-destructive">{goalForm.formState.errors.target_amount.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>مهلت (اختیاری)</Label>
                <Input {...goalForm.register("deadline")} type="date" />
              </div>
              <Button type="submit" className="w-full" disabled={goalForm.formState.isSubmitting}>
                {goalForm.formState.isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                ایجاد هدف
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Contribute dialog */}
      <Dialog open={!!contributeGoal} onOpenChange={(o) => !o && setContributeGoal(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>افزودن مبلغ به: {contributeGoal?.title}</DialogTitle></DialogHeader>
          <form onSubmit={contributeForm.handleSubmit(onContribute)} className="space-y-4 mt-2">
            <div className="space-y-1.5">
              <Label>مبلغ (تومان)</Label>
              <Controller
                name="amount"
                control={contributeForm.control}
                render={({ field }) => (
                  <MoneyInput
                    value={field.value}
                    onChange={field.onChange}
                    placeholder="مقدار پس‌انداز"
                    error={!!contributeForm.formState.errors.amount}
                  />
                )}
              />
              {contributeForm.formState.errors.amount && <p className="text-xs text-destructive">{contributeForm.formState.errors.amount.message}</p>}
            </div>
            <Button type="submit" className="w-full" disabled={contributeForm.formState.isSubmitting}>
              {contributeForm.formState.isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              افزودن
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}
        </div>
      ) : goals.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Target className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">هنوز هدف مالی تعریف نشده</p>
            <Button className="mt-4" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" />ایجاد هدف
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {goals.map((goal) => {
            const pct = goal.target_amount > 0 ? Math.min(100, Math.round((goal.current_amount / goal.target_amount) * 100)) : 0;
            return (
              <Card key={goal.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{goal.title}</CardTitle>
                    <Button size="sm" variant="outline" onClick={() => setContributeGoal(goal)}>
                      <PlusCircle className="h-3.5 w-3.5" />
                      افزودن مبلغ
                    </Button>
                  </div>
                  {goal.deadline && <p className="text-xs text-muted-foreground">مهلت: {jDate(goal.deadline)}</p>}
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">پیشرفت</span>
                    <span className="font-bold">{toFa(pct)}٪</span>
                  </div>
                  <Progress value={pct} />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{toman(goal.current_amount)}</span>
                    <span>از {toman(goal.target_amount)}</span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
