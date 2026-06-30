"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Wallet, ShieldCheck, X } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";

export default function LoginWelcomePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { token, onboardingCompleted } = useAuthStore();
  const { locale, dict } = useLocale();
  const [showInfo, setShowInfo] = useState(false);
  const googleError = searchParams.has("google_error");
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const t = dict.auth.landing;

  useEffect(() => {
    if (token) {
      if (onboardingCompleted) router.replace(`/${locale}/chat`);
      else router.replace(`/${locale}/onboarding/profile`);
    }
  }, [token, onboardingCompleted, router, locale]);

  const aboutPoints: string[] = Array.isArray(t.aboutPoints) ? t.aboutPoints : [];
  const startGoogleLogin = () => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
    window.location.assign(`${apiBase}/api/auth/google/login?locale=${locale}`);
  };

  return (
    <div className="min-h-screen bg-[#f5f1eb] flex flex-col max-w-[440px] mx-auto w-full px-6" dir={dir}>
      {/* Progress bar */}
      <div className="pt-14 pb-2">
        <div className="h-1 w-full bg-[#2d1812]/10 rounded-full overflow-hidden">
          <div className="h-full w-[10%] bg-[#2d1812] rounded-full" />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col justify-center items-center text-center gap-6 py-10">
        {/* Icon cluster */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.4, ease: "easeOut" }}
          className="relative inline-flex"
        >
          <div className="flex items-center justify-center w-24 h-24 rounded-full bg-emerald-100">
            <Wallet className="w-12 h-12 text-emerald-600" />
          </div>
          <div className="absolute -bottom-1 -left-1 flex items-center justify-center w-8 h-8 rounded-full bg-[#2d1812] shadow-md">
            <ShieldCheck className="w-4 h-4 text-white" />
          </div>
        </motion.div>

        {/* Heading */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.25, duration: 0.35, ease: "easeOut" }}
          className="space-y-3"
        >
          <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight whitespace-pre-line">
            {t.title}
          </h1>
          <p className="text-base text-gray-600 leading-relaxed max-w-[300px] mx-auto">
            {t.subtitle}
          </p>
        </motion.div>
      </div>

      {/* Bottom section */}
      <motion.div
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.35, duration: 0.35, ease: "easeOut" }}
        className="pb-12 space-y-3"
      >
        <p className="text-center text-xs text-gray-500 mb-4">{t.secureLogin}</p>

        <button
          onClick={() => router.push(`/${locale}/login/phone`)}
          className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base hover:bg-[#3d2218] active:scale-[0.98] transition-all"
        >
          {t.startButton}
        </button>

        <button
          onClick={startGoogleLogin}
          className="w-full py-4 rounded-full bg-white border border-gray-300 text-[#2d1812] font-semibold text-base hover:bg-gray-50 active:scale-[0.98] transition-all flex items-center justify-center gap-3"
        >
          <span className="font-bold text-lg text-[#4285F4]" aria-hidden="true">G</span>
          {t.googleButton}
        </button>

        {googleError && (
          <p role="alert" className="text-center text-sm text-red-600">
            {t.googleError}
          </p>
        )}

        <button
          onClick={() => setShowInfo(true)}
          className="w-full py-4 rounded-full bg-transparent border-2 border-[#2d1812] text-[#2d1812] font-semibold text-base hover:bg-[#2d1812]/5 active:scale-[0.98] transition-all"
        >
          {t.learnMore}
        </button>
      </motion.div>

      {/* Info sheet */}
      {showInfo && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setShowInfo(false)}
        >
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-[440px] bg-white rounded-t-3xl p-6 pb-10 space-y-4"
            dir={dir}
          >
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-bold text-[#2d1812]">{t.aboutTitle}</h2>
              <button onClick={() => setShowInfo(false)} className="p-1" aria-label={dict.common.close}>
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="space-y-3 text-gray-600 text-sm leading-relaxed">
              <p>{t.aboutBody}</p>
              <ul className="space-y-2 list-none">
                {aboutPoints.map((point: string, i: number) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">✓</span> {point}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-gray-400">{t.privacy}</p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
