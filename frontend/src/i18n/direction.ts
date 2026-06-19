import type { Locale } from "./config";
import { RTL_LOCALES } from "./config";

export function getDir(locale: Locale): "rtl" | "ltr" {
  return (RTL_LOCALES as string[]).includes(locale) ? "rtl" : "ltr";
}

export function isRTL(locale: Locale): boolean {
  return getDir(locale) === "rtl";
}
