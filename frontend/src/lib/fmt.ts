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
