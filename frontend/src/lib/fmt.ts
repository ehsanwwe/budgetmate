import dayjs from "dayjs";
import jalaliday from "jalaliday";

dayjs.extend(jalaliday);

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

export function toFa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => FA_DIGITS[parseInt(d)]);
}

export function toman(n: number): string {
  const formatted = n.toLocaleString("fa-IR");
  return `${formatted} تومان`;
}

export function jDate(iso: string): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = (dayjs(iso) as any).calendar("jalali");
    return toFa(d.format("YYYY/MM/DD"));
  } catch {
    return toFa(dayjs(iso).format("YYYY/MM/DD"));
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
