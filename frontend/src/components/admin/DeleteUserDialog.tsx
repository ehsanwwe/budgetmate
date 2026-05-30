"use client";
import { useState } from "react";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
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
  const [phoneInput, setPhoneInput] = useState("");
  const [loading, setLoading] = useState(false);

  const confirmed = phoneInput === user.phone;

  async function handleDelete() {
    if (!confirmed) return;
    setLoading(true);
    try {
      await adminApi.delete(`/admin/users/${user.id}`);
      toast.success("کاربر حذف شد");
      onOpenChange(false);
      onDeleted();
    } catch {
      toast.error("حذف کاربر ناموفق بود");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!loading) { setPhoneInput(""); onOpenChange(v); } }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-rose-600">حذف کاربر</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm text-slate-700 leading-relaxed">
          <p>
            آیا مطمئنی می‌خوای کاربر «<span className="font-bold">{user.name || user.phone}</span>» رو حذف کنی؟
          </p>
          <p>
            این کار تمام داده‌های کاربر (تراکنش‌ها، بودجه، اهداف، گفت‌وگوها و لاگ‌ها) رو حذف می‌کنه و قابل بازگشت{" "}
            <span className="font-bold text-rose-600">نیست</span>.
          </p>
          <div className="space-y-1.5">
            <p className="text-slate-500">برای تأیید، شماره موبایل کاربر رو دقیق وارد کن:</p>
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
            انصراف
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={!confirmed || loading}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "حذف"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
