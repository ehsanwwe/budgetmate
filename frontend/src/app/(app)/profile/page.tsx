"use client";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import Link from "next/link";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { LogOut, User, Loader2, Coins, ShoppingCart, Zap } from "lucide-react";

const profileSchema = z.object({
  first_name: z.string().min(1, "نام الزامی است"),
  last_name: z.string().optional(),
});
type ProfileForm = z.infer<typeof profileSchema>;

interface Wallet {
  balance_tokens: number;
  total_granted_tokens: number;
  total_purchased_tokens: number;
  total_consumed_tokens: number;
}

function fmtNum(n: number) {
  return new Intl.NumberFormat("fa-IR").format(n);
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      first_name: user?.first_name || user?.name || "",
      last_name: user?.last_name || "",
    },
  });

  useEffect(() => {
    reset({
      first_name: user?.first_name || user?.name || "",
      last_name: user?.last_name || "",
    });
  }, [user, reset]);

  useEffect(() => {
    api.get("/billing/wallet")
      .then((res) => setWallet(res.data))
      .catch(() => {});
  }, []);

  async function onSubmit(data: ProfileForm) {
    try {
      const res = await api.patch("/users/me", data);
      setUser(res.data);
      toast.success("پروفایل بروزرسانی شد");
    } catch {
      toast.error("خطا در بروزرسانی پروفایل");
    }
  }

  function handleLogout() {
    logout();
    router.replace("/login");
    toast.success("با موفقیت خارج شدید");
  }

  const displayName = user?.first_name
    ? [user.first_name, user.last_name].filter(Boolean).join(" ")
    : user?.name || "کاربر";

  return (
    <div className="space-y-6 max-w-md">
      <h1 className="text-2xl font-bold">پروفایل</h1>

      <Card>
        <CardContent className="pt-6 flex flex-col items-center gap-3">
          <Avatar className="h-20 w-20">
            <AvatarFallback className="bg-primary text-white text-2xl">
              <User className="h-10 w-10" />
            </AvatarFallback>
          </Avatar>
          <div className="text-center">
            <p className="font-bold text-lg">{displayName}</p>
            <p className="text-sm text-muted-foreground" dir="ltr">{user?.phone}</p>
          </div>
        </CardContent>
      </Card>

      {wallet && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Coins className="h-4 w-4 text-primary" />
              کیف توکن
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-primary/5 p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">موجودی</p>
                <p className="text-lg font-bold text-primary">{fmtNum(wallet.balance_tokens)}</p>
              </div>
              <div className="rounded-xl bg-rose-50 p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">مصرف شده</p>
                <p className="text-lg font-bold text-rose-600">{fmtNum(wallet.total_consumed_tokens)}</p>
              </div>
              <div className="rounded-xl bg-emerald-50 p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">هدیه</p>
                <p className="text-lg font-bold text-emerald-600">{fmtNum(wallet.total_granted_tokens)}</p>
              </div>
              <div className="rounded-xl bg-blue-50 p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">خریداری شده</p>
                <p className="text-lg font-bold text-blue-600">{fmtNum(wallet.total_purchased_tokens)}</p>
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <Link href="/billing/tokens" className="flex-1">
                <Button variant="outline" className="w-full gap-2" size="sm">
                  <ShoppingCart className="h-4 w-4" />
                  خرید توکن
                </Button>
              </Link>
              <Link href="/billing/subscription" className="flex-1">
                <Button variant="outline" className="w-full gap-2" size="sm">
                  <Zap className="h-4 w-4" />
                  خرید اشتراک
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">ویرایش اطلاعات</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label>نام</Label>
              <Input {...register("first_name")} placeholder="نام" />
              {errors.first_name && <p className="text-xs text-destructive">{errors.first_name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label>نام خانوادگی</Label>
              <Input {...register("last_name")} placeholder="نام خانوادگی (اختیاری)" />
            </div>
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              ذخیره تغییرات
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="border-destructive/30">
        <CardContent className="pt-6">
          <Button variant="destructive" className="w-full" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            خروج از حساب
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
