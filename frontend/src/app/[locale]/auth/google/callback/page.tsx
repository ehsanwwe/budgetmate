"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import axios from "axios";
import { getApiUrl } from "@/lib/api-config";
import { useLocale } from "@/i18n/LocaleContext";
import { useAuthStore } from "@/store/auth";

export default function GoogleCallbackPage() {
  const router = useRouter();
  const { locale, dict } = useLocale();
  const { setToken, setUser, setNeedsProfile, setOnboardingCompleted } = useAuthStore();
  const [message, setMessage] = useState(dict.auth.landing.googleCompleting);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const completeLogin = async () => {
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const token = hash.get("access_token");
      window.history.replaceState(null, "", window.location.pathname);
      if (!token) {
        router.replace(`/${locale}/login?google_error=missing_token`);
        return;
      }

      try {
        const response = await axios.get(`${getApiUrl()}/users/me`, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 15000,
        });
        const user = response.data;
        setToken(token);
        setUser(user);
        setNeedsProfile(!user.first_name);
        setOnboardingCompleted(Boolean(user.onboarding_completed));
        router.replace(
          user.onboarding_completed
            ? `/${locale}/chat`
            : `/${locale}/onboarding/profile`
        );
      } catch (error) {
        const status = axios.isAxiosError(error) ? error.response?.status : undefined;
        if (process.env.NODE_ENV !== "production") {
          console.error("Google OAuth profile validation failed", { status, error });
        }
        useAuthStore.getState().logout();
        setMessage(dict.auth.landing.googleError);
        router.replace(`/${locale}/login?google_error=profile_load_failed${status ? `&status=${status}` : ""}`);
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
