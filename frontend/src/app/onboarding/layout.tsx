"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";

export default function OnboardingRootLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const onboardingCompleted = useAuthStore((s) => s.onboardingCompleted);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    // Already onboarded — send to the app
    if (onboardingCompleted) {
      router.replace("/chat");
    }
  }, [token, onboardingCompleted, router]);

  if (!token) return null;

  return <>{children}</>;
}
