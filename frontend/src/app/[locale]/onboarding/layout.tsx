"use client";
import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuthStore } from "@/store/auth";

export default function LocaleOnboardingLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const token = useAuthStore((s) => s.token);
  const onboardingCompleted = useAuthStore((s) => s.onboardingCompleted);

  useEffect(() => {
    if (!token) {
      router.replace(`/${locale}/login`);
      return;
    }
    if (onboardingCompleted) {
      router.replace(`/${locale}/chat`);
    }
  }, [token, onboardingCompleted, router, locale]);

  if (!token) return null;
  return <>{children}</>;
}
