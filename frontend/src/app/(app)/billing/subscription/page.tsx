"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Zap, CheckCircle2, Loader2 } from "lucide-react";

interface SubscriptionPlan {
  plan_id: string;
  title: string;
  monthly_token_quota: number;
  amount_toman: number;
  benefits: string[];
}

interface Wallet {
  balance_tokens: number;
}

function fmtNum(n: number) {
  return new Intl.NumberFormat("fa-IR").format(n);
}

export default function SubscriptionPage() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [buying, setBuying] = useState<string | null>(null);
  const [bought, setBought] = useState<string | null>(null);

  useEffect(() => {
    api.get("/billing/plans").then((res) => setPlans(res.data.subscription_plans));
    api.get("/billing/wallet").then((res) => setWallet(res.data));
  }, []);

  async function handlePurchase(planId: string) {
    setBuying(planId);
    try {
      const res = await api.post("/billing/purchase-subscription", { plan_id: planId });
      setWallet(res.data.wallet);
      setBought(planId);
      toast.success(`اشتراک ${res.data.title} فعال شد و ${fmtNum(res.data.tokens_added)} توکن اضافه شد`);
    } catch {
      toast.error("خطا در خرید اشتراک. دوباره تلاش کنید");
    } finally {
      setBuying(null);
    }
  }

  return (
    <div className="space-y-6 max-w-lg">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Zap className="h-6 w-6 text-primary" />
          خرید اشتراک
        </h1>
        {wallet && (
          <p className="text-sm text-muted-foreground mt-1">
            موجودی فعلی: <span className="font-semibold text-primary">{fmtNum(wallet.balance_tokens)}</span> توکن
          </p>
        )}
      </div>

      <div className="space-y-4">
        {plans.map((plan) => (
          <Card key={plan.plan_id} className={bought === plan.plan_id ? "border-emerald-400 bg-emerald-50/40" : ""}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                {plan.title}
                {bought === plan.plan_id && <CheckCircle2 className="h-5 w-5 text-emerald-500" />}
              </CardTitle>
              <CardDescription>{fmtNum(plan.monthly_token_quota)} توکن ماهانه</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1">
                {plan.benefits.map((b, i) => (
                  <li key={i} className="text-sm text-muted-foreground flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                    {b}
                  </li>
                ))}
              </ul>
              <div className="flex items-center justify-between pt-1">
                <span className="text-lg font-bold">{fmtNum(plan.amount_toman)} تومان / ماه</span>
                <Button
                  onClick={() => handlePurchase(plan.plan_id)}
                  disabled={buying === plan.plan_id}
                  size="sm"
                  variant={bought === plan.plan_id ? "outline" : "default"}
                >
                  {buying === plan.plan_id && <Loader2 className="h-4 w-4 animate-spin" />}
                  {bought === plan.plan_id ? "فعال شد" : "فعال‌سازی"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        اشتراک آزمایشی — توکن‌های ماهانه فوری به کیف پول اضافه می‌شوند
      </p>
    </div>
  );
}
