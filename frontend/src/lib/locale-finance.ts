import { LOCALE_META, type Locale, type SupportedCurrency } from "@/i18n/config";

export type IncomeRangeKey = "lt10" | "10to20" | "20to40" | "40to80" | "gt80" | "prefer_not";

export interface LocaleFinanceProfile {
  locale: Locale;
  currency: SupportedCurrency;
  currencySymbol: string;
  incomeRanges: Array<{ value: IncomeRangeKey; label: string }>;
}

const LABELS: Record<Locale, Record<IncomeRangeKey, string>> = {
  fa: {
    lt10: "کمتر از ۱۰ میلیون تومان", "10to20": "۱۰ تا ۲۰ میلیون تومان",
    "20to40": "۲۰ تا ۴۰ میلیون تومان", "40to80": "۴۰ تا ۸۰ میلیون تومان",
    gt80: "بیشتر از ۸۰ میلیون تومان", prefer_not: "ترجیح می‌دم نگم",
  },
  en: {
    lt10: "Less than $1,000", "10to20": "$1,000 to $2,000", "20to40": "$2,000 to $4,000",
    "40to80": "$4,000 to $8,000", gt80: "More than $8,000", prefer_not: "Prefer not to say",
  },
  de: {
    lt10: "Weniger als 1.000 €", "10to20": "1.000 € bis 2.000 €", "20to40": "2.000 € bis 4.000 €",
    "40to80": "4.000 € bis 8.000 €", gt80: "Mehr als 8.000 €", prefer_not: "Keine Angabe",
  },
  zh: {
    lt10: "低于 ¥7,000", "10to20": "¥7,000 至 ¥14,000", "20to40": "¥14,000 至 ¥28,000",
    "40to80": "¥28,000 至 ¥56,000", gt80: "高于 ¥56,000", prefer_not: "不想透露",
  },
  ar: {
    lt10: "أقل من 4,000 د.إ", "10to20": "4,000 إلى 8,000 د.إ", "20to40": "8,000 إلى 16,000 د.إ",
    "40to80": "16,000 إلى 32,000 د.إ", gt80: "أكثر من 32,000 د.إ", prefer_not: "أفضل عدم الإفصاح",
  },
};

const SYMBOLS: Record<SupportedCurrency, string> = {
  IRT: "تومان", USD: "$", EUR: "€", CNY: "¥", AED: "د.إ", SAR: "ر.س",
};

export function getLocalizedFinanceProfile(locale: Locale): LocaleFinanceProfile {
  const currency = LOCALE_META[locale].defaultCurrency as SupportedCurrency;
  return {
    locale,
    currency,
    currencySymbol: SYMBOLS[currency],
    incomeRanges: Object.entries(LABELS[locale]).map(([value, label]) => ({
      value: value as IncomeRangeKey,
      label,
    })),
  };
}
