"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { LOCALE_META, SUPPORTED_LOCALES } from "@/i18n/config";
import type { Locale } from "@/i18n/config";

export default function LocaleHome() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const { locale } = useLocale();

  useEffect(() => {
    if (token) {
      router.replace(`/${locale}/dashboard`);
    }
    // If no token, show the language selector page below
  }, [token, router, locale]);

  if (token) return null;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#f5f1eb] gap-8 p-6">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-extrabold text-[#2d1812]">جیبیار</h1>
        <p className="text-[#2d1812]/70 text-lg">مدیریت مالی هوشمند</p>
      </div>

      {/* Language selector */}
      <div className="flex items-center gap-3 bg-white rounded-2xl shadow p-4">
        {SUPPORTED_LOCALES.map((loc: Locale) => {
          const meta = LOCALE_META[loc];
          return (
            <button
              key={loc}
              onClick={() => router.push(`/${loc}`)}
              title={meta.nativeName}
              className={`text-2xl rounded-xl p-2 transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                loc === locale ? "ring-2 ring-emerald-500 bg-emerald-50" : "hover:bg-gray-100"
              }`}
              aria-label={meta.name}
            >
              {meta.emoji}
            </button>
          );
        })}
      </div>

      <button
        onClick={() => router.push(`/${locale}/login`)}
        className="w-full max-w-xs py-4 rounded-full bg-[#2d1812] text-white font-bold text-lg hover:bg-[#2d1812]/90 transition"
      >
        {locale === "fa" ? "ورود" : locale === "ar" ? "تسجيل الدخول" : locale === "de" ? "Anmelden" : locale === "zh" ? "登录" : "Login"}
      </button>
    </div>
  );
}
