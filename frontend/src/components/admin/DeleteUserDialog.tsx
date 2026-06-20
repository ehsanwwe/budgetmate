"use client";
import { useState } from "react";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";

interface Props {
  user: { id: number; phone: string; name?: string };
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}

export default function DeleteUserDialog({ user, open, onOpenChange, onDeleted }: Props) {
  const { dict } = useLocale();
  const t = dict.admin.deleteDialog;
  const [phoneInput, setPhoneInput] = useState("");
  const [loading, setLoading] = useState(false);

  const confirmed = phoneInput === user.phone;

  async function handleDelete() {
    if (!confirmed) return;
    setLoading(true);
    try {
      await adminApi.delete(`/admin/users/${user.id}`);
      toast.success(t.deleted);
      onOpenChange(false);
      onDeleted();
    } catch {
      toast.error(t.deleteError);
    } finally {
      setLoading(false);
    }
  }

  const intro = tDict(dict, "admin.deleteDialog.confirmIntro", { name: user.name || user.phone });

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!loading) { setPhoneInput(""); onOpenChange(v); } }}>
      <DialogContent className="max-w-md" closeLabel={dict.common.close}>
        <DialogHeader>
          <DialogTitle className="text-rose-600">{t.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm text-slate-700 leading-relaxed">
          <p>{intro}</p>
          <p>
            {t.consequence}{" "}
            <span className="font-bold text-rose-600">{t.irreversible}</span>.
          </p>
          <div className="space-y-1.5">
            <p className="text-slate-500">{t.phonePrompt}</p>
            <Input
              dir="ltr"
              placeholder={user.phone}
              value={phoneInput}
              onChange={(e) => setPhoneInput(e.target.value)}
              className="font-mono"
              autoComplete="off"
            />
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => { setPhoneInput(""); onOpenChange(false); }}
            disabled={loading}
          >
            {t.cancel}
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={!confirmed || loading}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t.delete}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
