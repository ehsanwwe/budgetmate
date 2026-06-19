import type { Locale } from "./config";
import { DEFAULT_LOCALE } from "./config";

// Type shape — keeps all keys available for autocompletion
export type Dictionary = typeof import("./dictionaries/fa.json");

const dictionaries: Record<Locale, () => Promise<Dictionary>> = {
  fa: () => import("./dictionaries/fa.json").then((m) => m.default),
  ar: () => import("./dictionaries/ar.json").then((m) => m.default),
  en: () => import("./dictionaries/en.json").then((m) => m.default),
  de: () => import("./dictionaries/de.json").then((m) => m.default),
  zh: () => import("./dictionaries/zh.json").then((m) => m.default),
};

export async function getDictionary(locale: Locale): Promise<Dictionary> {
  try {
    return await (dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE])();
  } catch {
    return await dictionaries[DEFAULT_LOCALE]();
  }
}

// Synchronous getter for client components using the context
export function t(dict: Dictionary, key: string, params?: Record<string, string | number>): string {
  const parts = key.split(".");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let node: any = dict;
  for (const part of parts) {
    if (node == null || typeof node !== "object") {
      if (process.env.NODE_ENV === "development") {
        console.warn(`[i18n] Missing key: ${key}`);
      }
      return key;
    }
    node = node[part];
  }
  if (typeof node !== "string") {
    if (process.env.NODE_ENV === "development") {
      console.warn(`[i18n] Key not a string: ${key}`);
    }
    return key;
  }
  if (!params) return node;
  return node.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
}
