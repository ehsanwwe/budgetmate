"use client";
import { useEffect, useState, useCallback } from "react";
import { adminApi } from "@/lib/api";
import { toast } from "sonner";
import { jDate, toFa } from "@/lib/fmt";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

interface ChatMsg {
  id: number;
  role: string;
  content: string;
  created_at: string;
}

interface ChatHistoryResp {
  items: ChatMsg[];
  page: number;
  page_size: number;
  total: number;
}

export default function UserChatHistory({ userId }: { userId: string | number }) {
  const { dict } = useLocale();
  const t = dict.admin.chatHistory;
  const [data, setData] = useState<ChatHistoryResp | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.get<ChatHistoryResp>(
        `/admin/users/${userId}/chats?page=${page}&page_size=20`
      );
      setData(res.data);
    } catch {
      toast.error(t.loadError);
    } finally {
      setLoading(false);
    }
  }, [userId, page, t.loadError]);

  useEffect(() => {
    queueMicrotask(() => {
      void load();
    });
  }, [load]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  if (loading) {
    return (
      <div className="space-y-3 p-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
            <Skeleton className={`h-16 rounded-2xl ${i % 2 === 0 ? "w-2/3" : "w-1/2"}`} />
          </div>
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        {t.empty}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="space-y-3 p-2">
        {data.items.map((msg) => {
          const isUser = msg.role === "user";
          return (
            <div key={msg.id} className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
              <span className="text-xs text-slate-500 px-1">
                {isUser ? t.userLabel : t.assistantLabel} · {jDate(msg.created_at)}
              </span>
              <div
                className={`max-w-[70%] rounded-2xl px-4 py-2.5 whitespace-pre-wrap text-sm ${
                  isUser
                    ? "bg-indigo-100 text-indigo-900"
                    : "bg-emerald-50 text-emerald-900"
                }`}
              >
                {msg.content}
              </div>
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            {t.prevPage}
          </Button>
          <span className="text-sm text-slate-600">
            {tDict(dict, "admin.chatHistory.pageOf", { current: toFa(page), total: toFa(totalPages) })}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            {t.nextPage}
          </Button>
        </div>
      )}
    </div>
  );
}
