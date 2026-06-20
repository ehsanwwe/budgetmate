"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { formatNumber } from "@/i18n/formatters";
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

export default function SubscriptionPage() {
  const { locale, dict } = useLocale();
  const t = dict.billing.subscription;
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
      toast.success(
        tDict(dict, "billing.subscription.buySuccess", {
          title: res.data.title,
          count: formatNumber(res.data.tokens_added, locale),
        })
      );
    } catch {
      toast.error(t.buyError);
    } finally {
      setBuying(null);
    }
  }

  return (
    <div className="space-y-6 max-w-lg">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Zap className="h-6 w-6 text-primary" />
          {t.title}
        </h1>
        {wallet && (
          <p className="text-sm text-muted-foreground mt-1">
            {t.currentBalance} <span className="font-semibold text-primary">{formatNumber(wallet.balance_tokens, locale)}</span> {dict.common.token}
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
              <CardDescription>
                {tDict(dict, "billing.subscription.monthlyTokens", { count: formatNumber(plan.monthly_token_quota, locale) })}
              </CardDescription>
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
                <span className="text-lg font-bold">
                  {tDict(dict, "billing.subscription.perMonth", { amount: formatNumber(plan.amount_toman, locale) })}
                </span>
                <Button
                  onClick={() => handlePurchase(plan.plan_id)}
                  disabled={buying === plan.plan_id}
                  size="sm"
                  variant={bought === plan.plan_id ? "outline" : "default"}
                >
                  {buying === plan.plan_id && <Loader2 className="h-4 w-4 animate-spin" />}
                  {bought === plan.plan_id ? t.activatedButton : t.activateButton}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        {t.trialNote}
      </p>
    </div>
  );
}
