"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Wallet, Loader2 } from "lucide-react";

type Step = "phone" | "otp" | "profile";

export default function LoginPage() {
  const router = useRouter();
  const { setToken, setUser, token } = useAuthStore();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [loading, setLoading] = useState(false);
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (token) router.replace("/dashboard");
  }, [token, router]);

  async function handleRequestOtp(e: React.FormEvent) {
    e.preventDefault();
    if (phone.length !== 11) {
      toast.error("شماره موبایل باید ۱۱ رقم باشد");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/request-otp", { phone });
      setStep("otp");
      toast.success("کد تایید ارسال شد");
      setTimeout(() => otpRefs.current[0]?.focus(), 100);
    } catch {
      toast.error("خطا در ارسال کد. دوباره تلاش کنید");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    const code = otp.join("");
    if (code.length !== 6) {
      toast.error("کد باید ۶ رقم باشد");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/verify-otp", { phone, code });
      setToken(res.data.access_token);
      setUser(res.data.user);
      if (res.data.needs_profile) {
        setStep("profile");
      } else {
        toast.success("ورود موفق");
        router.replace("/dashboard");
      }
    } catch {
      toast.error("کد نادرست است");
    } finally {
      setLoading(false);
    }
  }

  async function handleCompleteProfile(e: React.FormEvent) {
    e.preventDefault();
    if (!firstName.trim()) {
      toast.error("نام الزامی است");
      return;
    }
    setLoading(true);
    try {
      const res = await api.patch("/users/me", {
        first_name: firstName.trim(),
        last_name: lastName.trim() || undefined,
      });
      setUser(res.data);
      toast.success("خوش آمدید!");
      router.replace("/dashboard");
    } catch {
      toast.error("خطا در ذخیره اطلاعات");
    } finally {
      setLoading(false);
    }
  }

  function handleOtpChange(index: number, value: string) {
    const v = value.replace(/[^0-9۰-۹]/g, "").slice(-1);
    const normalized = v.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));
    const newOtp = [...otp];
    newOtp[index] = normalized;
    setOtp(newOtp);
    if (normalized && index < 5) otpRefs.current[index + 1]?.focus();
    if (!normalized && index > 0) otpRefs.current[index - 1]?.focus();
  }

  function handleOtpKeyDown(index: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 to-emerald-50 p-4">
      <div className="w-full max-w-md space-y-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary shadow-lg">
            <Wallet className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">ورود به بادجت‌میت</h1>
          <p className="text-sm text-muted-foreground">مدیریت هوشمند مالی شخصی</p>
        </div>

        <Card className="shadow-xl border-0 bg-white/90 backdrop-blur-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">
              {step === "phone" && "شماره موبایل"}
              {step === "otp" && "کد تایید"}
              {step === "profile" && "تکمیل پروفایل"}
            </CardTitle>
            <CardDescription>
              {step === "phone" && "شماره موبایل خود را وارد کنید"}
              {step === "otp" && `کد ارسال شده به ${phone} را وارد کنید`}
              {step === "profile" && "برای تکمیل ثبت‌نام نام خود را وارد کنید"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {step === "phone" && (
              <form onSubmit={handleRequestOtp} className="space-y-4">
                <Input
                  type="tel"
                  placeholder="۰۹۱۲۰۰۰۰۰۰۱"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  maxLength={11}
                  dir="ltr"
                  className="text-center text-lg tracking-widest"
                  autoFocus
                />
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                  دریافت کد
                </Button>
              </form>
            )}

            {step === "otp" && (
              <form onSubmit={handleVerifyOtp} className="space-y-4">
                <div className="flex justify-center gap-2 flex-row-reverse">
                  {otp.map((digit, i) => (
                    <input
                      key={i}
                      ref={(el) => { otpRefs.current[i] = el; }}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleOtpChange(i, e.target.value)}
                      onKeyDown={(e) => handleOtpKeyDown(i, e)}
                      className="h-12 w-12 rounded-xl border-2 border-input bg-background text-center text-xl font-bold focus:border-primary focus:outline-none transition-colors"
                    />
                  ))}
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                  تایید و ورود
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={() => { setStep("phone"); setOtp(["","","","","",""]); }}
                >
                  تغییر شماره
                </Button>
              </form>
            )}

            {step === "profile" && (
              <form onSubmit={handleCompleteProfile} className="space-y-4">
                <div className="space-y-1.5">
                  <Label>نام *</Label>
                  <Input
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="نام"
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>نام خانوادگی</Label>
                  <Input
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="نام خانوادگی (اختیاری)"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                  شروع کنید
                </Button>
              </form>
            )}

            {step !== "profile" && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm text-amber-700">
                <span className="font-semibold">کد آزمایشی: </span>
                <span dir="ltr">۱۲۳۴۵۶</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
