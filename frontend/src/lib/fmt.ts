import dayjs from "dayjs";
import jalaliday from "jalaliday";

dayjs.extend(jalaliday);

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
const PERSIAN_TO_LATIN: Record<string, string> = {
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
  "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
};

export function toFa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => FA_DIGITS[parseInt(d)]);
}

export function toman(n: number): string {
  const formatted = n.toLocaleString("fa-IR");
  return `${formatted} تومان`;
}

/** Convert Gregorian ISO date → Jalali yyyy-mm-dd with Persian digits. */
export function jDate(iso: string): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = (dayjs(iso) as any).calendar("jalali");
    return toFa(d.format("YYYY-MM-DD"));
  } catch {
    return toFa(dayjs(iso).format("YYYY-MM-DD"));
  }
}

/** Convert Gregorian ISO date → Jalali yyyy-mm-dd with Persian digits (alias). */
export function isoToJalali(iso: string): string {
  return jDate(iso);
}

/** Convert Gregorian ISO date to numeric Jalali selector parts. */
export function isoToJalaliParts(iso: string): { year: string; month: string; day: string } | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = (dayjs(iso) as any).calendar("jalali");
    if (!d.isValid()) return null;
    return {
      year: d.format("YYYY"),
      month: String(Number(d.format("MM"))),
      day: String(Number(d.format("DD"))),
    };
  } catch {
    return null;
  }
}

/**
 * Convert a Jalali date string (yyyy-mm-dd, accepts Persian or Latin digits,
 * and / or - as separator) to a Gregorian ISO string (yyyy-mm-dd).
 * Returns "" if the input is invalid or incomplete.
 */
export function jalaliToIso(jalaliStr: string): string {
  if (!jalaliStr) return "";
  // Normalize Persian digits and accept both / and - separators
  const normalized = jalaliStr
    .replace(/[۰-۹]/g, (d) => PERSIAN_TO_LATIN[d] ?? d)
    .replace(/\//g, "-")
    .trim();

  // Must be YYYY-M-D or YYYY-MM-DD
  if (!/^\d{4}-\d{1,2}-\d{1,2}$/.test(normalized)) return "";

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = dayjs(normalized, { jalali: true } as any);
    if (!d.isValid()) return "";
    return d.format("YYYY-MM-DD");
  } catch {
    return "";
  }
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "همین الان";
  if (diff < 3600) return `${toFa(Math.floor(diff / 60))} دقیقه پیش`;
  if (diff < 86400) return `${toFa(Math.floor(diff / 3600))} ساعت پیش`;
  const days = Math.floor(diff / 86400);
  if (days < 30) return `${toFa(days)} روز پیش`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${toFa(months)} ماه پیش`;
  return `${toFa(Math.floor(months / 12))} سال پیش`;
}
