"use client";
import { useEffect, useState, useCallback } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import api from "@/lib/api";
import { toman, jDate } from "@/lib/fmt";
import { useLocale } from "@/i18n/LocaleContext";
import { t } from "@/i18n/getDictionary";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { MoneyInput } from "@/components/money-input";
import { Plus, Trash2, Search, Loader2 } from "lucide-react";

const txSchema = z.object({
  amount: z.number().positive(),
  type: z.enum(["expense", "income"]),
  category_id: z.number(),
  description: z.string().min(1),
  date: z.string().min(1),
});
type TxForm = z.infer<typeof txSchema>;

interface Transaction {
  id: number;
  amount: number;
  type: string;
  description: string;
  category_name: string;
  category_id: number;
  date: string;
}

interface Category { id: number; name: string; }

export default function TransactionsPage() {
  const { dict } = useLocale();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [deleting, setDeleting] = useState<number | null>(null);

  const { control, register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<TxForm>({
    resolver: zodResolver(txSchema),
    defaultValues: { date: new Date().toISOString().split("T")[0] },
  });

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterType) params.append("type", filterType);
      if (filterCat) params.append("category_id", filterCat);
      if (search) params.append("q", search);
      const [txRes, catRes] = await Promise.all([
        api.get(`/transactions?${params}`),
        api.get("/categories"),
      ]);
      setTransactions(txRes.data.items || txRes.data);
      setCategories(catRes.data);
    } catch {
      toast.error(t(dict, "transactions.loadError"));
    } finally {
      setLoading(false);
    }
  }, [filterType, filterCat, search, dict]);

  useEffect(() => {
    queueMicrotask(() => {
      void load();
    });
  }, [load]);

  async function onSubmit(data: TxForm) {
    try {
      await api.post("/transactions", data);
      toast.success(t(dict, "transactions.addSuccess"));
      setOpen(false);
      reset({ date: new Date().toISOString().split("T")[0] });
      load();
    } catch {
      toast.error(t(dict, "transactions.addError"));
    }
  }

  async function handleDelete(id: number) {
    setDeleting(id);
    try {
      await api.delete(`/transactions/${id}`);
      toast.success(t(dict, "transactions.deleteSuccess"));
      setTransactions((prev) => prev.filter((tx) => tx.id !== id));
    } catch {
      toast.error(t(dict, "transactions.deleteError"));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t(dict, "transactions.title")}</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4" />
              {t(dict, "transactions.addNew")}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t(dict, "transactions.newTransactionTitle")}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-2">
              <div className="space-y-1.5">
                <Label>{t(dict, "transactions.typeLabel")}</Label>
                <select {...register("type")} className="flex h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <option value="">{t(dict, "transactions.selectType")}</option>
                  <option value="expense">{t(dict, "transactions.expense")}</option>
                  <option value="income">{t(dict, "transactions.income")}</option>
                </select>
                {errors.type && <p className="text-xs text-destructive">{errors.type.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t(dict, "transactions.categoryLabel")}</Label>
                <select {...register("category_id", { valueAsNumber: true })} className="flex h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <option value="">{t(dict, "transactions.selectCategory")}</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {errors.category_id && <p className="text-xs text-destructive">{errors.category_id.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t(dict, "transactions.amountLabel")}</Label>
                <Controller
                  name="amount"
                  control={control}
                  render={({ field }) => (
                    <MoneyInput
                      value={field.value}
                      onChange={field.onChange}
                      placeholder={t(dict, "transactions.amountEx")}
                      error={!!errors.amount}
                    />
                  )}
                />
                {errors.amount && <p className="text-xs text-destructive">{errors.amount.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t(dict, "transactions.descLabel")}</Label>
                <Input {...register("description")} placeholder={t(dict, "transactions.descPlaceholder")} />
                {errors.description && <p className="text-xs text-destructive">{errors.description.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t(dict, "transactions.dateLabel")}</Label>
                <Input {...register("date")} type="date" />
                {errors.date && <p className="text-xs text-destructive">{errors.date.message}</p>}
              </div>
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {t(dict, "transactions.submitBtn")}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-48">
            <Search className="absolute start-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="ps-9" placeholder={t(dict, "transactions.searchPlaceholder")} value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)} className="h-10 rounded-xl border border-input bg-background px-3 text-sm focus-visible:outline-none">
            <option value="">{t(dict, "transactions.allTypes")}</option>
            <option value="expense">{t(dict, "transactions.expense")}</option>
            <option value="income">{t(dict, "transactions.income")}</option>
          </select>
          <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)} className="h-10 rounded-xl border border-input bg-background px-3 text-sm focus-visible:outline-none">
            <option value="">{t(dict, "transactions.allCategories")}</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t(dict, "transactions.list")}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-4 space-y-2">
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
            </div>
          ) : transactions.length === 0 ? (
            <p className="text-center text-muted-foreground py-12">{t(dict, "transactions.noTransactions")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-start px-4 py-3 font-medium">{t(dict, "common.date")}</th>
                    <th className="text-start px-4 py-3 font-medium">{t(dict, "common.category")}</th>
                    <th className="text-start px-4 py-3 font-medium">{t(dict, "common.description")}</th>
                    <th className="text-start px-4 py-3 font-medium">{t(dict, "common.type")}</th>
                    <th className="text-end px-4 py-3 font-medium">{t(dict, "common.amount")}</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 text-muted-foreground">{jDate(tx.date)}</td>
                      <td className="px-4 py-3">{tx.category_name}</td>
                      <td className="px-4 py-3">{tx.description}</td>
                      <td className="px-4 py-3">
                        <Badge variant={tx.type === "expense" ? "destructive" : "success"}>
                          {tx.type === "expense" ? t(dict, "transactions.expense") : t(dict, "transactions.income")}
                        </Badge>
                      </td>
                      <td className={`px-4 py-3 text-end font-bold ${tx.type === "expense" ? "text-rose-600" : "text-emerald-600"}`}>
                        {toman(tx.amount)}
                      </td>
                      <td className="px-4 py-3 text-end">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t(dict, "transactions.ariaDelete")}
                          onClick={() => handleDelete(tx.id)}
                          disabled={deleting === tx.id}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          {deleting === tx.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
