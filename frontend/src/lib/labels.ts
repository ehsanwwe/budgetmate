import type { Dictionary } from "@/i18n/getDictionary";

// Legacy Persian-only fallbacks (kept for backward compat with non-locale-aware code paths).
export function incomeRangeLabel(code?: string | null): string {
  const map: Record<string, string> = {
    lt10: "کمتر از ۱۰ میلیون تومان",
    "10to20": "۱۰ تا ۲۰ میلیون تومان",
    "20to40": "۲۰ تا ۴۰ میلیون تومان",
    "40to80": "۴۰ تا ۸۰ میلیون تومان",
    gt80: "بیشتر از ۸۰ میلیون تومان",
    prefer_not: "ترجیح می‌دم نگم",
  };
  return code ? (map[code] ?? code) : "—";
}

export function chatModeLabel(mode?: string | null): string {
  const map: Record<string, string> = {
    normal: "عادی",
    roast: "طعنه‌آمیز",
    hype: "پرانرژی",
  };
  return mode ? (map[mode] ?? mode) : "عادی";
}

// Locale-aware versions — preferred when a dictionary is available.
export function incomeRangeLabelI18n(dict: Dictionary, code?: string | null): string {
  if (!code) return "—";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const full = (dict as any).incomeRangesFull as Record<string, string> | undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const base = (dict as any).incomeRanges as Record<string, string> | undefined;
  return full?.[code] ?? base?.[code] ?? code;
}

export function chatModeLabelI18n(dict: Dictionary, mode?: string | null): string {
  const effective = mode || "normal";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const modes = (dict as any).chatModes as Record<string, { label: string }> | undefined;
  return modes?.[effective]?.label ?? effective;
}
