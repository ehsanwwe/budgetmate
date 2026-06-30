import type { Locale } from "@/i18n/config";
import type { AxiosInstance } from "axios";

type Catalog = Record<string, string[]>;

const CATALOGS: Record<Locale, Catalog> = {
  fa: {}, // Delegated to the existing complete Iran API catalog.
  en: {
    California: ["Los Angeles", "San Francisco", "San Diego"],
    "New York": ["New York City", "Buffalo", "Rochester"],
    Texas: ["Houston", "Austin", "Dallas"],
    Florida: ["Miami", "Orlando", "Tampa"],
    Illinois: ["Chicago", "Springfield", "Aurora"],
  },
  de: {
    Bayern: ["München", "Nürnberg", "Augsburg"],
    Berlin: ["Berlin"],
    Hamburg: ["Hamburg"],
    Hessen: ["Frankfurt am Main", "Wiesbaden", "Kassel"],
    "Nordrhein-Westfalen": ["Köln", "Düsseldorf", "Dortmund"],
  },
  zh: {
    北京市: ["北京市"],
    上海市: ["上海市"],
    广东省: ["广州市", "深圳市", "珠海市"],
    浙江省: ["杭州市", "宁波市", "温州市"],
    四川省: ["成都市", "绵阳市", "乐山市"],
  },
  ar: {
    "منطقة الرياض": ["الرياض", "الخرج", "الدرعية"],
    "منطقة مكة المكرمة": ["مكة المكرمة", "جدة", "الطائف"],
    "المنطقة الشرقية": ["الدمام", "الخبر", "الأحساء"],
    "منطقة المدينة المنورة": ["المدينة المنورة", "ينبع"],
    "منطقة عسير": ["أبها", "خميس مشيط"],
  },
};

export async function loadLocationRegions(locale: Locale, api: AxiosInstance): Promise<string[]> {
  if (locale === "fa") {
    const response = await api.get("/iran/provinces");
    return response.data.provinces;
  }
  return Object.keys(CATALOGS[locale]);
}

export async function loadLocationCities(
  locale: Locale,
  region: string,
  api: AxiosInstance
): Promise<string[]> {
  if (locale === "fa") {
    const response = await api.get(`/iran/cities?province=${encodeURIComponent(region)}`);
    return response.data.cities;
  }
  return CATALOGS[locale][region] ?? [];
}
