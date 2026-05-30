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
