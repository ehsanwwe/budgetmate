"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { toFa } from "@/lib/fmt";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Shield, ShieldOff, ChevronLeft, Loader2, Trash2 } from "lucide-react";
import DeleteUserDialog from "@/components/admin/DeleteUserDialog";

interface User {
  id: number;
  phone: string;
  name?: string;
  is_blocked: boolean;
  created_at: string;
}

export default function AdminUsersPage() {
  const { dict } = useLocale();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const t = dict.admin.usersPage;
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  const perPage = 20;

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(perPage) });
      if (search) params.append("q", search);
      const res = await adminApi.get(`/admin/users?${params}`);
      setUsers(res.data.users || res.data.items || []);
      setTotal(res.data.total || 0);
    } catch {
      toast.error(t.loadError);
    } finally {
      setLoading(false);
    }
  }, [page, search, t.loadError]);

  useEffect(() => {
    queueMicrotask(() => { void load(); });
  }, [load]);

  async function toggleBlock(user: User) {
    setActionLoading(user.id);
    try {
      const action = user.is_blocked ? "unblock" : "block";
      await adminApi.post(`/admin/users/${user.id}/${action}`);
      toast.success(user.is_blocked ? t.actions.unblocked : t.actions.blocked);
      void load();
    } catch {
      toast.error(t.actions.actionError);
    } finally {
      setActionLoading(null);
    }
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t.title}</h1>
        <span className="text-sm text-muted-foreground">{toFa(total)} {t.totalSuffix}</span>
      </div>

      <div className="relative">
        <Search className="absolute start-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          className="ps-9"
          placeholder={t.searchPlaceholder}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-4 space-y-2">
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
            </div>
          ) : users.length === 0 ? (
            <p className="text-center text-muted-foreground py-12">{t.empty}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-start px-4 py-3 font-medium">{t.table.phone}</th>
                  <th className="text-start px-4 py-3 font-medium">{t.table.name}</th>
                  <th className="text-start px-4 py-3 font-medium">{t.table.status}</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono" dir="ltr">{user.phone}</td>
                    <td className="px-4 py-3">{user.name || "—"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={user.is_blocked ? "destructive" : "success"}>
                        {user.is_blocked ? t.table.blocked : t.table.active}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        <Button
                          size="sm"
                          variant={user.is_blocked ? "outline" : "destructive"}
                          onClick={() => toggleBlock(user)}
                          disabled={actionLoading === user.id}
                        >
                          {actionLoading === user.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : user.is_blocked ? (
                            <><ShieldOff className="h-3.5 w-3.5" />{t.actions.unblock}</>
                          ) : (
                            <><Shield className="h-3.5 w-3.5" />{t.actions.block}</>
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-rose-500 hover:text-rose-600 hover:bg-rose-50"
                          onClick={() => setDeleteTarget(user)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" asChild>
                          <Link href={`/${locale}/admin/users/${user.id}`}>
                            <ChevronLeft className="h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            {t.pagination.previous}
          </Button>
          <span className="flex items-center text-sm px-3">
            {tDict(dict, "admin.usersPage.pagination.pageOf", { current: toFa(page), total: toFa(totalPages) })}
          </span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
            {t.pagination.next}
          </Button>
        </div>
      )}

      {deleteTarget && (
        <DeleteUserDialog
          user={{ id: deleteTarget.id, phone: deleteTarget.phone, name: deleteTarget.name }}
          open={!!deleteTarget}
          onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
          onDeleted={() => { setDeleteTarget(null); void load(); }}
        />
      )}
    </div>
  );
}
