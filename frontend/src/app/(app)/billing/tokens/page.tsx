"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
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

function fmtNum(n: number) {
  return new Intl.NumberFormat("fa-IR").format(n);
}

export default function TokensPage() {
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
      toast.success(`${fmtNum(res.data.tokens_added)} توکن به کیف پول شما اضافه شد`);
    } catch {
      toast.error("خطا در خرید. دوباره تلاش کنید");
    } finally {
      setBuying(null);
    }
  }

  return (
    <div className="space-y-6 max-w-lg">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Coins className="h-6 w-6 text-primary" />
          خرید توکن
        </h1>
        {wallet && (
          <p className="text-sm text-muted-foreground mt-1">
            موجودی فعلی: <span className="font-semibold text-primary">{fmtNum(wallet.balance_tokens)}</span> توکن
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
                {fmtNum(pack.tokens)} توکن
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <span className="text-lg font-bold">{fmtNum(pack.amount_toman)} تومان</span>
              <Button
                onClick={() => handlePurchase(pack.plan_id)}
                disabled={buying === pack.plan_id}
                size="sm"
                variant={bought === pack.plan_id ? "outline" : "default"}
              >
                {buying === pack.plan_id && <Loader2 className="h-4 w-4 animate-spin" />}
                {bought === pack.plan_id ? "خریداری شد" : "خرید"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        خرید آزمایشی — توکن‌ها فوری به کیف پول اضافه می‌شوند
      </p>
    </div>
  );
}
