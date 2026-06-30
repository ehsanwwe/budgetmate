"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { useAuthStore } from "@/store/auth";

export default function GoogleCallbackPage() {
  const router = useRouter();
  const { locale, dict } = useLocale();
  const { setToken, setUser, setNeedsProfile, setOnboardingCompleted } = useAuthStore();
  const [message, setMessage] = useState(dict.auth.landing.googleCompleting);

  useEffect(() => {
    const completeLogin = async () => {
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const token = hash.get("access_token");
      window.history.replaceState(null, "", window.location.pathname);
      if (!token) {
        router.replace(`/${locale}/login?google_error=missing_token`);
        return;
      }

      try {
        setToken(token);
        const response = await api.get("/users/me");
        const user = response.data;
        setUser(user);
        setNeedsProfile(!user.first_name);
        setOnboardingCompleted(Boolean(user.onboarding_completed));
        router.replace(
          user.onboarding_completed
            ? `/${locale}/chat`
            : `/${locale}/onboarding/profile`
        );
      } catch {
        useAuthStore.getState().logout();
        setMessage(dict.auth.landing.googleError);
        router.replace(`/${locale}/login?google_error=profile_load_failed`);
      }
    };
    void completeLogin();
  }, [dict.auth.landing.googleError, locale, router, setNeedsProfile, setOnboardingCompleted, setToken, setUser]);

  return (
    <main className="min-h-screen bg-[#f5f1eb] flex flex-col items-center justify-center gap-4 px-6 text-[#2d1812]">
      <Loader2 className="h-8 w-8 animate-spin" />
      <p className="text-center">{message}</p>
    </main>
  );
}
