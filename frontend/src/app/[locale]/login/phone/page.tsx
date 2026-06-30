"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import { isValidPhoneNumber } from "react-phone-number-input";
import api from "@/lib/api";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";
import InternationalPhoneInput from "@/components/auth/InternationalPhoneInput";
import { getApiOrigin } from "@/lib/api-config";
import { clearLoginFlowAndAuthState } from "@/lib/login-flow";

export default function LoginPhonePage() {
  const router = useRouter();
  const { locale, dict } = useLocale();
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const t = dict.auth.phonePage;

  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isValid = phone ? isValidPhoneNumber(phone) : false;

  async function handleContinue() {
    if (!isValid) {
      setError(t.invalidPhone);
      return;
    }
    setLoading(true);
    setError("");
    try {
      // phone is already in E.164 format (e.g. +989121234567)
      await api.post("/auth/request-otp", { phone });
      router.push(`/${locale}/login/otp?phone=${encodeURIComponent(phone)}`);
    } catch {
      setError(t.sendError);
    } finally {
      setLoading(false);
    }
  }

  function handleChange(val: string) {
    setPhone(val);
    if (error) setError("");
  }

  function startGoogleLogin() {
    window.location.assign(`${getApiOrigin()}/api/auth/google/login?locale=${locale}`);
  }

  function exitLoginFlow() {
    clearLoginFlowAndAuthState();
    router.replace("/");
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
          onClick={exitLoginFlow}
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
          <button
            type="button"
            onClick={startGoogleLogin}
            className="w-full py-4 rounded-full bg-white border border-[#2d1812]/15 text-[#2d1812] font-semibold text-base shadow-sm hover:bg-white/80 active:scale-[0.98] transition-all flex items-center justify-center gap-3"
          >
            <span className="font-bold text-lg text-[#4285F4]" aria-hidden="true">G</span>
            {dict.auth.landing.googleButton}
          </button>

          <div className="flex items-center gap-3 py-6">
            <div className="h-px flex-1 bg-[#2d1812]/10" />
            <span className="shrink-0 text-xs text-[#2d1812]/45">{t.phoneDivider}</span>
            <div className="h-px flex-1 bg-[#2d1812]/10" />
          </div>

          <p className="mb-3 text-sm leading-relaxed text-[#2d1812]/60">
            {t.phoneSectionHelper}
          </p>

          <InternationalPhoneInput
            value={phone}
            onChange={handleChange}
            locale={locale}
            error={error}
            disabled={loading}
            placeholder={t.placeholder}
            countrySearchPlaceholder={t.countrySearchPlaceholder}
          />
          {!error && phone && !isValid && (
            <p className={`mt-2 text-sm text-gray-400 ${dir === "rtl" ? "text-right" : "text-left"}`}>
              {t.helper}
            </p>
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
