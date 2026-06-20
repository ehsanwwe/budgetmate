"use client";
import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2, X } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";
import { t as tDict } from "@/i18n/getDictionary";

const RESEND_SECONDS = 60;

function OtpPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const phone = params.get("phone") ?? "";

  const { locale, dict } = useLocale();
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const t = dict.auth.otpPage;

  const { setToken, setUser, setOnboardingCompleted } = useAuthStore();

  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [countdown, setCountdown] = useState(RESEND_SECONDS);
  const [showHint, setShowHint] = useState(true);
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    refs.current[0]?.focus();
  }, []);

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const verify = useCallback(async (code: string) => {
    if (code.length !== 6) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/verify-otp", { phone, code });
      setToken(res.data.access_token);
      setUser(res.data.user);
      setOnboardingCompleted(res.data.onboarding_completed ?? false);
      if (res.data.onboarding_completed) {
        router.replace(`/${locale}/chat`);
      } else {
        router.replace(`/${locale}/onboarding/profile`);
      }
    } catch {
      setError(t.wrongCode);
      setLoading(false);
      setOtp(["", "", "", "", "", ""]);
      setTimeout(() => refs.current[0]?.focus(), 50);
    }
  }, [phone, router, setToken, setUser, setOnboardingCompleted, locale, t.wrongCode]);

  function handleChange(index: number, value: string) {
    const raw = value.replace(/[^0-9۰-۹]/g, "");
    // Handle paste of full code
    if (raw.length > 1) {
      const digits = raw
        .split("")
        .map((d) => d.replace(/[۰-۹]/g, (c) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(c))))
        .slice(0, 6);
      const newOtp = [...otp];
      digits.forEach((d, i) => { newOtp[i] = d; });
      setOtp(newOtp);
      const filled = digits.length;
      refs.current[Math.min(filled, 5)]?.focus();
      if (filled === 6) verify(digits.join(""));
      return;
    }
    const digit = raw
      .slice(-1)
      .replace(/[۰-۹]/g, (c) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(c)));
    const newOtp = [...otp];
    newOtp[index] = digit;
    setOtp(newOtp);
    if (digit && index < 5) {
      refs.current[index + 1]?.focus();
    }
    const fullCode = newOtp.join("");
    if (fullCode.length === 6 && !newOtp.includes("")) {
      verify(fullCode);
    }
  }

  function handleKeyDown(index: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace") {
      if (otp[index]) {
        const newOtp = [...otp];
        newOtp[index] = "";
        setOtp(newOtp);
      } else if (index > 0) {
        refs.current[index - 1]?.focus();
      }
    }
  }

  async function handleResend() {
    if (countdown > 0) return;
    try {
      await api.post("/auth/request-otp", { phone });
      setCountdown(RESEND_SECONDS);
      setOtp(["", "", "", "", "", ""]);
      setError("");
      setTimeout(() => refs.current[0]?.focus(), 50);
    } catch {
      setError(t.resendError);
    }
  }

  const filled = otp.filter(Boolean).length;

  return (
    <motion.div
      initial={{ x: 50, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen bg-[#f5f1eb] flex flex-col max-w-[440px] mx-auto w-full px-6"
      dir={dir}
    >
      {/* Hint pill */}
      <AnimatePresence>
        {showHint && (
          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -20, opacity: 0 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium px-4 py-2 rounded-full shadow-sm whitespace-nowrap"
          >
            <span>{t.testHint}</span>
            <button onClick={() => setShowHint(false)} className="text-emerald-500 hover:text-emerald-700" aria-label={dict.common.close}>
              <X className="w-3 h-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Back */}
      <div className="pt-12 pb-6">
        <button
          onClick={() => router.push(`/${locale}/login/phone`)}
          className="flex items-center justify-center w-10 h-10 rounded-full bg-white/70 shadow-sm hover:bg-white transition-colors"
          aria-label={dict.common.back}
        >
          <ArrowRight className={`w-5 h-5 text-[#2d1812] ${dir === "ltr" ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* Heading */}
      <motion.div
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1, duration: 0.3 }}
        className="space-y-2 mb-8"
      >
        <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight">
          {t.title}
        </h1>
        <p className="text-base text-gray-600">
          {t.subtitle}{" "}
          <span className="font-mono text-[#2d1812]" dir="ltr">{phone}</span>
        </p>
        <button
          onClick={() => router.push(`/${locale}/login/phone`)}
          className="text-sm text-[#2d1812] underline underline-offset-2 font-medium"
        >
          {t.changePhone}
        </button>
      </motion.div>

      {/* OTP boxes — LTR order so digit 1 is leftmost visually */}
      <motion.div
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.3 }}
        className="flex gap-2 justify-center mb-4"
        dir="ltr"
      >
        {otp.map((digit, i) => (
          <input
            key={i}
            ref={(el) => { refs.current[i] = el; }}
            type="text"
            inputMode="numeric"
            maxLength={6}
            value={digit}
            onChange={(e) => handleChange(i, e.target.value)}
            onKeyDown={(e) => handleKeyDown(i, e)}
            disabled={loading}
            className={`w-12 h-14 rounded-2xl border-2 bg-white text-center text-2xl font-bold font-mono text-[#2d1812] focus:outline-none transition-all disabled:opacity-50 ${
              error
                ? "border-red-400 bg-red-50"
                : digit
                ? "border-emerald-400 bg-emerald-50/30"
                : "border-transparent shadow-sm focus:border-[#2d1812]/40"
            }`}
          />
        ))}
      </motion.div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="text-center text-sm text-red-500 mb-4"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>

      {/* Helper text */}
      <p className="text-center text-xs text-gray-400 leading-relaxed mb-3">
        {t.helper}
      </p>

      {/* Resend */}
      <div className="text-center mb-auto">
        <button
          onClick={handleResend}
          disabled={countdown > 0}
          className={`text-sm font-medium underline underline-offset-2 transition-colors ${
            countdown > 0 ? "text-gray-300 cursor-default no-underline" : "text-[#2d1812]"
          }`}
        >
          {countdown > 0 ? tDict(dict, "auth.otpPage.countdown", { seconds: countdown }) : t.resend}
        </button>
      </div>

      {/* Sticky bottom verify button */}
      <div className="pb-12 pt-6">
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base flex items-center justify-center gap-3"
            >
              <Loader2 className="w-4 h-4 animate-spin" />
              {t.verifying}
            </motion.div>
          ) : (
            <motion.button
              key="verify"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => verify(otp.join(""))}
              disabled={filled !== 6}
              className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#3d2218] active:scale-[0.98] transition-all"
            >
              {t.verifyButton}
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export default function OtpPage() {
  return (
    <Suspense>
      <OtpPageInner />
    </Suspense>
  );
}
