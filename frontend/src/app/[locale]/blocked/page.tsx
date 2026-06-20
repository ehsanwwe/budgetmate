"use client";
import Link from "next/link";
import { useLocale } from "@/i18n/LocaleContext";

export default function BlockedPage() {
  const { locale, dict } = useLocale();
  const t = dict.auth.blockedPage;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-rose-50 p-8 text-center">
      <div className="text-6xl mb-6">🔒</div>
      <h1 className="text-2xl font-bold text-rose-700 mb-3">{t.title}</h1>
      <p className="text-rose-600 max-w-sm mb-6">
        {t.description}
      </p>
      <Link href={`/${locale}/login`} className="text-sm text-rose-500 underline hover:text-rose-700">
        {t.backButton}
      </Link>
    </div>
  );
}
