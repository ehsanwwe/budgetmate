"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { isRTL } from "@/i18n/config";

const AGREEMENT_VERSION = "1.0.0";
const SUPPORT_EMAIL = "support@budgetmate.ir";

export default function OnboardingAgreementPage() {
  const router = useRouter();
  const { token, logout } = useAuthStore();
  const { locale, dict } = useLocale();
  const dir = isRTL(locale) ? "rtl" : "ltr";
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const t = dict.onboarding.agreementPage;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sections = (t as any).sections;

  useEffect(() => {
    if (!token) router.replace(`/${locale}/login`);
  }, [token, router, locale]);

  async function handleAccept() {
    setLoading(true);
    try {
      await api.post("/onboarding/agreement", { version: AGREEMENT_VERSION });
      router.push(`/${locale}/onboarding/welcome`);
    } catch {
      setLoading(false);
    }
  }

  function handleDecline() {
    logout();
    router.replace(`/${locale}/login`);
  }

  return (
    <motion.div
      initial={{ x: 50, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen bg-[#f5f1eb] flex flex-col max-w-[440px] mx-auto w-full"
      dir={dir}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 pt-12 pb-4 shrink-0">
        <button
          onClick={() => router.push(`/${locale}/onboarding/intro`)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/70 shadow-sm hover:bg-white"
          aria-label={dict.onboarding.back ?? dict.common.back}
        >
          <ArrowRight className={`h-5 w-5 text-[#2d1812] ${dir === "ltr" ? "rotate-180" : ""}`} />
        </button>
        {/* Logo pill */}
        <div className="flex items-center gap-2 bg-[#2d1812] text-white text-sm font-semibold px-4 py-2 rounded-full">
          {dict.common.appName}
        </div>
        <button
          onClick={handleDecline}
          className="text-sm text-gray-500 hover:text-red-500 transition-colors font-medium"
        >
          {t.rejectButton}
        </button>
      </div>

      {/* Heading */}
      <div className="px-6 pb-4 shrink-0">
        <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight mb-2">
          {t.title}
        </h1>
        <p className="text-base text-gray-600 leading-relaxed mb-2">
          {t.subtitle}
        </p>
        <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-100 text-emerald-700 text-xs px-3 py-1.5 rounded-full">
          <span>{t.updatedBadge}</span>
        </div>
      </div>

      {/* Scrollable T&C content */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 pb-4 min-h-0"
      >
        <div className="prose prose-sm max-w-none text-gray-700 space-y-5 pb-6">

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.intro.title}</h2>
          <p>{sections.intro.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.useTitle}</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.age.title}</h3>
          <p>{sections.age.body}</p>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.allowed.title}</h3>
          <p>{sections.allowed.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.privacyTitle}</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.collect.title}</h3>
          <p dangerouslySetInnerHTML={{ __html: sections.collect.intro }} />
          <ul className={`list-disc ${dir === "rtl" ? "pr-5" : "pl-5"} space-y-1`}>
            {(sections.collect.items as string[]).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.use.title}</h3>
          <p>{sections.use.body}</p>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.security.title}</h3>
          <p>{sections.security.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.aiTitle}</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.aiAdvice.title}</h3>
          <p dangerouslySetInnerHTML={{ __html: sections.aiAdvice.body }} />

          <h3 className="text-base font-semibold text-[#2d1812]">{sections.aiLimit.title}</h3>
          <p>{sections.aiLimit.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.subscription.title}</h2>
          <p>{sections.subscription.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.changes.title}</h2>
          <p>{sections.changes.body}</p>

          <h2 className="text-lg font-bold text-[#2d1812]">{sections.contact.title}</h2>
          <p>
            {(sections.contact.body as string).split("{email}").map((part: string, i: number, arr: string[]) => (
              <span key={i}>
                {part}
                {i < arr.length - 1 && (
                  <span dir="ltr" className="font-mono text-[#2d1812]">{SUPPORT_EMAIL}</span>
                )}
              </span>
            ))}
          </p>

        </div>
      </div>

      {/* Sticky bottom */}
      <div className="px-6 pt-3 pb-10 shrink-0 bg-gradient-to-t from-[#f5f1eb] to-transparent">
        <p className="text-center text-xs text-gray-400 italic mb-4 leading-relaxed">
          {t.acceptDisclaimer}
        </p>
        <button
          onClick={handleAccept}
          disabled={loading}
          className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base disabled:opacity-40 hover:bg-[#3d2218] active:scale-[0.98] transition-all flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          {t.acceptButton}
        </button>
      </div>
    </motion.div>
  );
}
