"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import NavBar from "@/components/layout/NavBar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const onboardingCompleted = useAuthStore((s) => s.onboardingCompleted);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    if (!onboardingCompleted) {
      router.replace("/onboarding/profile");
    }
  }, [token, onboardingCompleted, router]);

  if (!token || !onboardingCompleted) return null;

  return (
    <div className="min-h-screen bg-muted/30">
      <NavBar />
      <main className="md:me-64 pb-20 md:pb-0">
        <div className="max-w-5xl mx-auto p-4 md:p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
