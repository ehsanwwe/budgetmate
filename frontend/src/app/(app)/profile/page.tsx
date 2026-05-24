"use client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { LogOut, User, Loader2 } from "lucide-react";

const profileSchema = z.object({
  name: z.string().min(2, "نام باید حداقل ۲ کاراکتر باشد"),
});
type ProfileForm = z.infer<typeof profileSchema>;

export default function ProfilePage() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    defaultValues: { name: user?.name || "" },
  });

  useEffect(() => {
    reset({ name: user?.name || "" });
  }, [user, reset]);

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
            <p className="font-bold text-lg">{user?.name || "کاربر"}</p>
            <p className="text-sm text-muted-foreground" dir="ltr">{user?.phone}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">ویرایش اطلاعات</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label>نام</Label>
              <Input {...register("name")} placeholder="نام خود را وارد کنید" />
              {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
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
