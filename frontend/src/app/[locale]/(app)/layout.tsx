"use client";
import { useEffect } from "react";
import { useRouter, usePathname, useParams } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import NavBar from "@/components/layout/NavBar";

export default function LocaleAppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const token = useAuthStore((s) => s.token);
  const onboardingCompleted = useAuthStore((s) => s.onboardingCompleted);
  const pathname = usePathname();
  const isChatPage = pathname?.endsWith("/chat");

  useEffect(() => {
    if (!token) {
      router.replace(`/${locale}/login`);
      return;
    }
    if (!onboardingCompleted) {
      router.replace(`/${locale}/onboarding/profile`);
    }
  }, [token, onboardingCompleted, router, locale]);

  if (!token || !onboardingCompleted) return null;

  return (
    <div className={isChatPage ? "h-dvh overflow-hidden bg-muted/30" : "min-h-screen bg-muted/30"}>
      <NavBar locale={locale} />
      <main className={isChatPage ? "md:me-64 h-dvh overflow-hidden pb-0" : "md:me-64 pb-20 md:pb-0"}>
        <div
          className={
            isChatPage
              ? "h-[calc(100dvh-4rem)] md:h-dvh max-w-none p-0 overflow-hidden"
              : "max-w-5xl mx-auto p-4 md:p-6"
          }
        >
          {children}
        </div>
      </main>
    </div>
  );
}
