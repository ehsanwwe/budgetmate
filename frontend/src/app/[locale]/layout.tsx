import { notFound } from "next/navigation";
import { getDictionary } from "@/i18n/getDictionary";
import { LocaleProvider } from "@/i18n/LocaleContext";
import type { Locale } from "@/i18n/config";
import { isValidLocale } from "@/i18n/config";

export function generateStaticParams() {
  return [
    { locale: "fa" },
    { locale: "ar" },
    { locale: "en" },
    { locale: "de" },
    { locale: "zh" },
  ];
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isValidLocale(locale)) notFound();

  const dict = await getDictionary(locale as Locale);

  return (
    <LocaleProvider locale={locale as Locale} dict={dict}>
      {children}
    </LocaleProvider>
  );
}
