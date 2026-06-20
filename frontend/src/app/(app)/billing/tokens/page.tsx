"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { formatNumber } from "@/i18n/formatters";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Coins, CheckCircle2, Loader2 } from "lucide-react";

interface TokenPack {
  plan_id: string;
  title: string;
  tokens: number;
  amount_toman: number;
}

interface Wallet {
  balance_tokens: number;
}

export default function TokensPage() {
  const { locale, dict } = useLocale();
  const t = dict.billing.tokens;
  const [packs, setPacks] = useState<TokenPack[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [buying, setBuying] = useState<string | null>(null);
  const [bought, setBought] = useState<string | null>(null);

  useEffect(() => {
    api.get("/billing/plans").then((res) => setPacks(res.data.token_packs));
    api.get("/billing/wallet").then((res) => setWallet(res.data));
  }, []);

  async function handlePurchase(planId: string) {
    setBuying(planId);
    try {
      const res = await api.post("/billing/purchase-token-pack", { plan_id: planId });
      setWallet(res.data.wallet);
      setBought(planId);
      toast.success(
        tDict(dict, "billing.tokens.buySuccess", { count: formatNumber(res.data.tokens_added, locale) })
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
          <Coins className="h-6 w-6 text-primary" />
          {t.title}
        </h1>
        {wallet && (
          <p className="text-sm text-muted-foreground mt-1">
            {t.currentBalance} <span className="font-semibold text-primary">{formatNumber(wallet.balance_tokens, locale)}</span> {dict.common.token}
          </p>
        )}
      </div>

      <div className="space-y-3">
        {packs.map((pack) => (
          <Card key={pack.plan_id} className={bought === pack.plan_id ? "border-emerald-400 bg-emerald-50/40" : ""}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                {pack.title}
                {bought === pack.plan_id && <CheckCircle2 className="h-5 w-5 text-emerald-500" />}
              </CardTitle>
              <CardDescription>
                {formatNumber(pack.tokens, locale)} {t.tokensSuffix}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <span className="text-lg font-bold">{formatNumber(pack.amount_toman, locale)} {t.tomanLabel}</span>
              <Button
                onClick={() => handlePurchase(pack.plan_id)}
                disabled={buying === pack.plan_id}
                size="sm"
                variant={bought === pack.plan_id ? "outline" : "default"}
              >
                {buying === pack.plan_id && <Loader2 className="h-4 w-4 animate-spin" />}
                {bought === pack.plan_id ? t.purchasedButton : t.buyButton}
              </Button>
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
