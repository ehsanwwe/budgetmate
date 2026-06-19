"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, CheckCircle2, Clock3, XCircle } from "lucide-react";
import api from "@/lib/api";
import { toman, jDate } from "@/lib/fmt";
import { cn } from "@/lib/utils";
import { useLocale } from "@/i18n/LocaleContext";
import { t } from "@/i18n/getDictionary";
import { getDirection } from "@/i18n/config";
import type { Locale } from "@/i18n/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type CommitmentStatus = "pending" | "paid" | "cancelled";
type FilterKey = "pending" | "paid" | "cancelled" | "next_month" | "until_next_year";

interface FutureCommitment {
  id: number;
  title: string;
  amount: number;
  due_date?: string | null;
  due_month?: string | null;
  description?: string | null;
  status: CommitmentStatus;
  related_transaction_id?: number | null;
  related_goal_id?: number | null;
}

function statusIcon(status: CommitmentStatus) {
  if (status === "paid") return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  if (status === "cancelled") return <XCircle className="h-4 w-4 text-red-500" />;
  return <Clock3 className="h-4 w-4 text-amber-600" />;
}

export default function FutureCommitmentsPage() {
  const { locale, dict } = useLocale();
  const dir = getDirection(locale as Locale);

  const filters: { key: FilterKey; label: string }[] = [
    { key: "pending", label: t(dict, "futureCommitments.pending") },
    { key: "paid", label: t(dict, "futureCommitments.paid") },
    { key: "cancelled", label: t(dict, "futureCommitments.cancelled") },
    { key: "next_month", label: t(dict, "futureCommitments.nextMonth") },
    { key: "until_next_year", label: t(dict, "futureCommitments.untilNextYear") },
  ];

  const [rows, setRows] = useState<FutureCommitment[]>([]);
  const [filter, setFilter] = useState<FilterKey>("pending");
  const [loading, setLoading] = useState(true);

  const total = useMemo(() => rows.reduce((sum, row) => sum + Number(row.amount || 0), 0), [rows]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const params =
          filter === "next_month" || filter === "until_next_year"
            ? { period: filter }
            : { status: filter };
        const res = await api.get("/future-commitments", { params });
        setRows(res.data);
      } catch {
        toast.error(t(dict, "futureCommitments.loadError"));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [filter, dict]);

  function statusLabel(status: CommitmentStatus): string {
    if (status === "paid") return t(dict, "futureCommitments.paid");
    if (status === "cancelled") return t(dict, "futureCommitments.cancelled");
    return t(dict, "futureCommitments.pending");
  }

  return (
    <div className="space-y-4" dir={dir}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2d1812]">{t(dict, "futureCommitments.title")}</h1>
          <p className="text-sm text-muted-foreground">{t(dict, "futureCommitments.subtitle")}</p>
        </div>
        <Card className="sm:min-w-56">
          <CardContent className="py-3">
            <p className="text-xs text-muted-foreground">{t(dict, "futureCommitments.filterTotal")}</p>
            <p className="text-lg font-bold text-[#2d1812]">{toman(total)}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {filters.map((item) => (
          <Button
            key={item.key}
            variant={filter === item.key ? "default" : "outline"}
            size="sm"
            className="shrink-0 rounded-full"
            onClick={() => setFilter(item.key)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <CalendarClock className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
            <p className="font-medium text-[#2d1812]">{t(dict, "futureCommitments.emptyTitle")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t(dict, "futureCommitments.emptyHint")}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => (
            <Card key={row.id}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="text-base">{row.title}</CardTitle>
                    <p className="mt-1 text-sm font-bold text-[#2d1812]">{toman(row.amount)}</p>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn(
                      "shrink-0 gap-1 rounded-full",
                      row.status === "pending" && "border-amber-200 bg-amber-50 text-amber-700",
                      row.status === "paid" && "border-emerald-200 bg-emerald-50 text-emerald-700",
                      row.status === "cancelled" && "border-red-200 bg-red-50 text-red-700"
                    )}
                  >
                    {statusIcon(row.status)}
                    {statusLabel(row.status)}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {row.due_date && (
                    <span>{t(dict, "futureCommitments.dueDateLabel").replace("{date}", jDate(row.due_date))}</span>
                  )}
                  {!row.due_date && row.due_month && (
                    <span>{t(dict, "futureCommitments.dueMonthLabel").replace("{month}", row.due_month)}</span>
                  )}
                  {row.related_transaction_id && (
                    <span>{t(dict, "futureCommitments.relatedTx").replace("{id}", String(row.related_transaction_id))}</span>
                  )}
                  {row.related_goal_id && (
                    <span>{t(dict, "futureCommitments.relatedGoal").replace("{id}", String(row.related_goal_id))}</span>
                  )}
                </div>
                {row.description && <p className="leading-7 text-[#2d1812]/75">{row.description}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
