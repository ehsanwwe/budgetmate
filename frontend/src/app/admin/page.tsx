"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Shield, Loader2 } from "lucide-react";

export default function AdminLoginPage() {
  const router = useRouter();
  const setAdminToken = useAuthStore((s) => s.setAdminToken);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post("/auth/admin/login", { username, password });
      setAdminToken(res.data.access_token);
      toast.success("ورود موفق");
      router.replace("/admin/dashboard");
    } catch {
      toast.error("نام کاربری یا رمز عبور اشتباه است");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <Card className="w-full max-w-sm shadow-2xl">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800 shadow-lg">
              <Shield className="h-7 w-7 text-indigo-400" />
            </div>
          </div>
          <CardTitle>پنل مدیریت</CardTitle>
          <CardDescription>ورود به بخش مدیریت بادجت‌میت</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1.5">
              <Label>نام کاربری</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" dir="ltr" />
            </div>
            <div className="space-y-1.5">
              <Label>رمز عبور</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" dir="ltr" />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              ورود
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
