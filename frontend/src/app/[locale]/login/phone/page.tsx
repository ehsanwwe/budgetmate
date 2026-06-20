"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";

export default function LoginPhonePage() {
  const router = useRouter();
  const { locale, dict } = useLocale();
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const t = dict.auth.phonePage;

  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // User types 10 digits without leading 0 (e.g. 9120000001); we prepend "0" for the backend
  const isValid = /^9\d{9}$/.test(phone);

  async function handleContinue() {
    if (!isValid) return;
    setLoading(true);
    setError("");
    const fullPhone = "0" + phone;
    try {
      await api.post("/auth/request-otp", { phone: fullPhone });
      router.push(`/${locale}/login/otp?phone=${encodeURIComponent(fullPhone)}`);
    } catch {
      setError(t.sendError);
    } finally {
      setLoading(false);
    }
  }

  function handleInput(val: string) {
    // Strip non-digits; cap at 10 (user types without leading 0)
    const digits = val.replace(/\D/g, "").slice(0, 10);
    setPhone(digits);
    if (error) setError("");
  }

  return (
    <motion.div
      initial={{ x: 50, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen bg-[#f5f1eb] flex flex-col max-w-[440px] mx-auto w-full px-6"
      dir={dir}
    >
      {/* Back */}
      <div className="pt-12 pb-6">
        <button
          onClick={() => router.back()}
          className="flex items-center justify-center w-10 h-10 rounded-full bg-white/70 shadow-sm hover:bg-white transition-colors"
          aria-label={dict.common.back}
        >
          <ArrowRight className={`w-5 h-5 text-[#2d1812] ${dir === "ltr" ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 pt-4 space-y-4">
        <motion.div
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.3 }}
        >
          <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight mb-3">
            {t.title}
          </h1>
          <p className="text-base text-gray-600 leading-relaxed">
            {t.subtitle}
          </p>
        </motion.div>

        <motion.div
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.3 }}
          className="pt-4"
        >
          {/* Phone input with prefix — dir="ltr" so +98 stays on the left */}
          <div
            dir="ltr"
            className={`flex items-center rounded-2xl bg-white shadow-sm border-2 overflow-hidden transition-colors ${
              error ? "border-red-400" : isValid ? "border-emerald-400" : "border-transparent focus-within:border-[#2d1812]/30"
            }`}
          >
            <div className="flex items-center justify-center px-4 py-4 bg-[#2d1812]/5 border-r border-[#2d1812]/10 shrink-0">
              <span className="text-base font-semibold text-[#2d1812] font-mono">+98</span>
            </div>
            <input
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={(e) => handleInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && isValid && handleContinue()}
              placeholder={t.placeholder}
              className="flex-1 px-4 py-4 bg-transparent text-xl font-mono tabular-nums text-[#2d1812] placeholder:text-gray-300 focus:outline-none"
              dir="ltr"
              autoFocus
              maxLength={10}
            />
          </div>
          {error && <p className={`mt-2 text-sm text-red-500 ${dir === "rtl" ? "text-right" : "text-left"}`}>{error}</p>}
          {!isValid && phone.length > 0 && !error && (
            <p className={`mt-2 text-sm text-gray-400 ${dir === "rtl" ? "text-right" : "text-left"}`}>{t.helper}</p>
          )}
        </motion.div>
      </div>

      {/* Sticky bottom button */}
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.3, duration: 0.3 }}
        className="pb-12 pt-6"
      >
        <button
          onClick={handleContinue}
          disabled={!isValid || loading}
          className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#3d2218] active:scale-[0.98] transition-all flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          {t.submitButton}
        </button>
      </motion.div>
    </motion.div>
  );
}
