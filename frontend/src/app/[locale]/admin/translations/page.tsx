"use client";
import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { adminApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

interface TranslationEntry {
  id: number;
  namespace: string;
  key: string;
  locale: string;
  value: string;
  is_active: boolean;
  updated_at: string | null;
}

const LOCALES = ["fa", "ar", "en", "de", "zh"];

export default function AdminTranslationsPage() {
  const { adminToken } = useAuthStore();
  const router = useRouter();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const { dict } = useLocale();
  const t = dict.admin.translationsPage;

  const [entries, setEntries] = useState<TranslationEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [filterLocale, setFilterLocale] = useState("fa");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newEntry, setNewEntry] = useState({ namespace: "", key: "", locale: "fa", value: "" });

  useEffect(() => {
    if (!adminToken) { router.replace(`/${locale}/admin`); return; }
    fetchEntries();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterLocale, search]);

  async function fetchEntries() {
    setLoading(true);
    try {
      const params: Record<string, string> = { locale: filterLocale };
      if (search) params.search = search;
      const r = await adminApi.get("/admin/translations", { params });
      setEntries(r.data.items);
      setTotal(r.data.total);
    } catch { toast.error(t.toasts.loadError); }
    finally { setLoading(false); }
  }

  async function handleSave(id: number) {
    try {
      await adminApi.patch(`/admin/translations/${id}`, { value: editValue });
      toast.success(t.toasts.saved);
      setEditId(null);
      fetchEntries();
    } catch { toast.error(t.toasts.saveError); }
  }

  async function handleToggle(entry: TranslationEntry) {
    try {
      await adminApi.patch(`/admin/translations/${entry.id}`, { is_active: !entry.is_active });
      fetchEntries();
    } catch { toast.error(t.toasts.toggleError); }
  }

  async function handleCreate() {
    try {
      await adminApi.post("/admin/translations", newEntry);
      toast.success(t.toasts.created);
      setShowAdd(false);
      setNewEntry({ namespace: "", key: "", locale: "fa", value: "" });
      fetchEntries();
    } catch { toast.error(t.toasts.createError); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t.title}</h1>
        <Button size="sm" onClick={() => setShowAdd(!showAdd)}>{t.addButton}</Button>
      </div>

      {showAdd && (
        <div className="border rounded-xl p-4 space-y-2 bg-white">
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder={t.namespacePlaceholder} value={newEntry.namespace} onChange={e => setNewEntry(p => ({ ...p, namespace: e.target.value }))} />
            <Input placeholder={t.keyPlaceholder} value={newEntry.key} onChange={e => setNewEntry(p => ({ ...p, key: e.target.value }))} />
            <select className="border rounded-lg px-3 py-2 text-sm" value={newEntry.locale} onChange={e => setNewEntry(p => ({ ...p, locale: e.target.value }))}>
              {LOCALES.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            <Input placeholder={t.valuePlaceholder} value={newEntry.value} onChange={e => setNewEntry(p => ({ ...p, value: e.target.value }))} />
          </div>
          <Button size="sm" onClick={handleCreate}>{t.saveButton}</Button>
        </div>
      )}

      <div className="flex gap-2">
        <select className="border rounded-lg px-3 py-2 text-sm" value={filterLocale} onChange={e => setFilterLocale(e.target.value)}>
          {LOCALES.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <Input placeholder={t.searchPlaceholder} className="max-w-xs" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      <div className="text-sm text-muted-foreground">{total} {t.totalSuffix}</div>

      <div className="border rounded-xl overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="p-3 text-start">{t.tableKey}</th>
              <th className="p-3 text-start">{t.tableValue}</th>
              <th className="p-3 text-start">{t.tableStatus}</th>
              <th className="p-3 text-start">{t.tableActions}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} className="p-6 text-center text-muted-foreground">{t.loadingRow}</td></tr>
            ) : entries.length === 0 ? (
              <tr><td colSpan={4} className="p-6 text-center text-muted-foreground">{t.emptyRow}</td></tr>
            ) : entries.map(entry => (
              <tr key={entry.id} className="border-t hover:bg-muted/20">
                <td className="p-3 font-mono text-xs">{entry.namespace}.{entry.key}</td>
                <td className="p-3">
                  {editId === entry.id ? (
                    <Input className="text-sm" value={editValue} onChange={e => setEditValue(e.target.value)} autoFocus />
                  ) : (
                    <span>{entry.value}</span>
                  )}
                </td>
                <td className="p-3">
                  <Badge variant={entry.is_active ? "default" : "secondary"} className="cursor-pointer" onClick={() => handleToggle(entry)}>
                    {entry.is_active ? t.active : t.inactive}
                  </Badge>
                </td>
                <td className="p-3">
                  {editId === entry.id ? (
                    <div className="flex gap-1">
                      <Button size="sm" onClick={() => handleSave(entry.id)}>{t.saveButton}</Button>
                      <Button size="sm" variant="outline" onClick={() => setEditId(null)}>{t.cancel}</Button>
                    </div>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => { setEditId(entry.id); setEditValue(entry.value); }}>{t.edit}</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
