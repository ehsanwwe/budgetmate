import type { Locale } from "./config";

const LOCALE_NUMBER_FORMAT: Record<Locale, string> = {
  fa: "fa-IR",
  ar: "ar-SA",
  en: "en-US",
  de: "de-DE",
  zh: "zh-CN",
};

const CURRENCY_DISPLAY: Record<string, { code: string; name: Record<Locale, string> }> = {
  IRT: {
    code: "IRT",
    name: { fa: "تومان", ar: "تومان", en: "Toman", de: "Toman", zh: "托曼" },
  },
  USD: {
    code: "USD",
    name: { fa: "دلار", ar: "دولار", en: "USD", de: "USD", zh: "美元" },
  },
  EUR: {
    code: "EUR",
    name: { fa: "یورو", ar: "يورو", en: "EUR", de: "EUR", zh: "欧元" },
  },
  CNY: {
    code: "CNY",
    name: { fa: "یوان", ar: "يوان", en: "CNY", de: "CNY", zh: "人民币" },
  },
  AED: {
    code: "AED",
    name: { fa: "درهم", ar: "درهم", en: "AED", de: "AED", zh: "迪拉姆" },
  },
  SAR: {
    code: "SAR",
    name: { fa: "ریال سعودی", ar: "ريال سعودي", en: "SAR", de: "SAR", zh: "沙特里亚尔" },
  },
};

export function formatNumber(value: number, locale: Locale): string {
  const numberLocale = LOCALE_NUMBER_FORMAT[locale] ?? "en-US";
  return new Intl.NumberFormat(numberLocale).format(value);
}

export function formatCurrency(value: number, locale: Locale, currency = "IRT"): string {
  const numberLocale = LOCALE_NUMBER_FORMAT[locale] ?? "en-US";
  const formatted = new Intl.NumberFormat(numberLocale).format(value);
  const currencyName = CURRENCY_DISPLAY[currency]?.name[locale] ?? currency;
  // For RTL locales, append currency after number (natural for Persian/Arabic)
  if (locale === "fa" || locale === "ar") {
    return `${formatted} ${currencyName}`;
  }
  // For LTR locales, prepend currency symbol or use standard format
  if (currency === "USD") {
    return `$${formatted}`;
  }
  if (currency === "EUR") {
    return `€${formatted}`;
  }
  return `${formatted} ${currencyName}`;
}

export function formatDate(isoDate: string, locale: Locale): string {
  try {
    const date = new Date(isoDate);
    const numberLocale = LOCALE_NUMBER_FORMAT[locale] ?? "en-US";
    return new Intl.DateTimeFormat(numberLocale, {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return isoDate;
  }
}
