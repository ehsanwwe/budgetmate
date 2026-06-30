export type Locale = "fa" | "ar" | "en" | "de" | "zh";

export const SUPPORTED_LOCALES: Locale[] = ["fa", "ar", "en", "de", "zh"];
export const DEFAULT_LOCALE: Locale = "fa";
export const RTL_LOCALES: Locale[] = ["fa", "ar"];

export interface LocaleMeta {
  name: string;
  nativeName: string;
  emoji: string;
  direction: "rtl" | "ltr";
  defaultCurrency: string;
  isDefault: boolean;
}

export const LOCALE_META: Record<Locale, LocaleMeta> = {
  fa: {
    name: "Persian",
    nativeName: "فارسی",
    emoji: "🇮🇷",
    direction: "rtl",
    defaultCurrency: "IRT",
    isDefault: true,
  },
  ar: {
    name: "Arabic",
    nativeName: "العربية",
    emoji: "🇸🇦",
    direction: "rtl",
    defaultCurrency: "AED",
    isDefault: false,
  },
  en: {
    name: "English",
    nativeName: "English",
    emoji: "🇬🇧",
    direction: "ltr",
    defaultCurrency: "USD",
    isDefault: false,
  },
  de: {
    name: "German",
    nativeName: "Deutsch",
    emoji: "🇩🇪",
    direction: "ltr",
    defaultCurrency: "EUR",
    isDefault: false,
  },
  zh: {
    name: "Chinese",
    nativeName: "中文",
    emoji: "🇨🇳",
    direction: "ltr",
    defaultCurrency: "CNY",
    isDefault: false,
  },
};

export const SUPPORTED_CURRENCIES = ["IRT", "USD", "EUR", "CNY", "AED", "SAR"] as const;
export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];

export function isValidLocale(l: string): l is Locale {
  return (SUPPORTED_LOCALES as string[]).includes(l);
}

export function getDirection(locale: Locale): "rtl" | "ltr" {
  return LOCALE_META[locale]?.direction ?? "rtl";
}

export function isRTL(locale: Locale): boolean {
  return getDirection(locale) === "rtl";
}
