"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import Link from "next/link";
import api from "@/lib/api";
import { useAuthStore, type User as AuthUser } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { t } from "@/i18n/getDictionary";
import { SUPPORTED_LOCALES, LOCALE_META, SUPPORTED_CURRENCIES } from "@/i18n/config";
import type { Locale, SupportedCurrency } from "@/i18n/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  CalendarDays,
  Coins,
  Globe,
  Loader2,
  LogOut,
  MapPin,
  ShoppingCart,
  User,
  Zap,
} from "lucide-react";

const JALALI_YEARS = Array.from({ length: 60 }, (_, i) => 1404 - i);
const JALALI_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

interface Wallet {
  balance_tokens: number;
  total_granted_tokens: number;
  total_purchased_tokens: number;
  total_consumed_tokens: number;
}

function fmtNum(n: number) {
  return new Intl.NumberFormat("fa-IR").format(n);
}

function jalaliToGregorian(jy: number, jm: number, jd: number): string {
  const gy = jy + 621;
  const gm = jm <= 6 ? jm + 3 : jm - 6;
  const isSecondHalf = jm > 6;
  return `${gy + (isSecondHalf ? 1 : 0)}-${String(gm).padStart(2, "0")}-${String(jd).padStart(2, "0")}`;
}

function fillProfileFromUser(user: AuthUser | null) {
  return {
    name: user?.first_name || user?.name || "",
    familyName: user?.family_name || user?.last_name || "",
    birthdate: user?.birthdate || "",
    province: user?.province || "",
    city: user?.city || "",
    incomeRange: user?.income_range || "",
  };
}

function splitBirthdate(birthdate?: string) {
  if (!birthdate) return { birthYear: "", birthMonth: "", birthDay: "" };
  const [gyRaw, gmRaw, gdRaw] = birthdate.split("-").map(Number);
  if (!gyRaw || !gmRaw || !gdRaw) return { birthYear: "", birthMonth: "", birthDay: "" };

  const jm = gmRaw <= 6 ? gmRaw + 6 : gmRaw - 3;
  const jy = gmRaw <= 6 ? gyRaw - 622 : gyRaw - 621;
  return {
    birthYear: String(jy),
    birthMonth: String(jm),
    birthDay: String(gdRaw),
  };
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const { locale, dict } = useLocale();

  const initialProfile = useMemo(() => fillProfileFromUser(user), [user]);
  const initialBirth = useMemo(() => splitBirthdate(initialProfile.birthdate), [initialProfile.birthdate]);

  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [name, setName] = useState(initialProfile.name);
  const [familyName, setFamilyName] = useState(initialProfile.familyName);
  const [birthYear, setBirthYear] = useState(initialBirth.birthYear);
  const [birthMonth, setBirthMonth] = useState(initialBirth.birthMonth);
  const [birthDay, setBirthDay] = useState(initialBirth.birthDay);
  const [provinces, setProvinces] = useState<string[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [province, setProvince] = useState(initialProfile.province);
  const [city, setCity] = useState(initialProfile.city);
  const [incomeRange, setIncomeRange] = useState(initialProfile.incomeRange);
  const [chatMode, setChatMode] = useState<string>(user?.chat_mode || "normal");
  const [savingMode, setSavingMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prefLanguage, setPrefLanguage] = useState<Locale>(locale as Locale);
  const [prefCurrency, setPrefCurrency] = useState<SupportedCurrency>("IRT");
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    api.get("/billing/wallet").then((res) => setWallet(res.data)).catch(() => {});
    api.get("/iran/provinces").then((res) => setProvinces(res.data.provinces || [])).catch(() => {});
    api.get("/users/me/preferences").then((res) => {
      if (res.data.language) setPrefLanguage(res.data.language as Locale);
      if (res.data.preferred_currency) setPrefCurrency(res.data.preferred_currency as SupportedCurrency);
    }).catch(() => {});
    api
      .get("/users/me")
      .then((res) => {
        const nextUser = res.data as AuthUser;
        const nextProfile = fillProfileFromUser(nextUser);
        const nextBirth = splitBirthdate(nextProfile.birthdate);
        setUser(nextUser);
        setName(nextProfile.name);
        setFamilyName(nextProfile.familyName);
        setBirthYear(nextBirth.birthYear);
        setBirthMonth(nextBirth.birthMonth);
        setBirthDay(nextBirth.birthDay);
        setProvince(nextProfile.province);
        setCity(nextProfile.city);
        setIncomeRange(nextProfile.incomeRange);
        setChatMode(nextUser.chat_mode || "normal");
      })
      .catch(() => {});
  }, [setUser]);

  useEffect(() => {
    queueMicrotask(() => {
      if (!province) {
        setCities([]);
        setCity("");
        return;
      }

      const selectedCity = city;
      api
        .get(`/iran/cities?province=${encodeURIComponent(province)}`)
        .then((res) => {
          const rows = res.data.cities || [];
          setCities(rows);
          setCity(selectedCity && rows.includes(selectedCity) ? selectedCity : "");
        })
        .catch(() => setCities([]));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [province]);

  async function handleSaveProfile() {
    if (!name.trim() || !familyName.trim()) {
      toast.error(t(dict, "profile.nameRequired"));
      return;
    }

    setSaving(true);
    try {
      const userPayload = {
        first_name: name.trim(),
        last_name: familyName.trim(),
      };

      const onboardingPayload: Record<string, string> = {
        name: name.trim(),
        family_name: familyName.trim(),
      };

      if (birthYear && birthMonth && birthDay) {
        onboardingPayload.birthdate = jalaliToGregorian(+birthYear, +birthMonth, +birthDay);
      }
      if (province) onboardingPayload.province = province;
      if (city) onboardingPayload.city = city;
      if (incomeRange) onboardingPayload.income_range = incomeRange;

      await api.patch("/users/me", userPayload);
      await api.post("/onboarding/profile", onboardingPayload);

      const meRes = await api.get("/users/me");
      setUser(meRes.data);
      toast.success(t(dict, "profile.saveSuccess"));
    } catch {
      toast.error(t(dict, "profile.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleChatModeChange(mode: string) {
    if (mode === chatMode) return;
    setChatMode(mode);
    setSavingMode(true);
    try {
      await api.patch("/users/me", { chat_mode: mode });
      const meRes = await api.get("/users/me");
      setUser(meRes.data);
      toast.success(t(dict, "profile.chatModeSuccess"));
    } catch {
      toast.error(t(dict, "profile.chatModeError"));
    } finally {
      setSavingMode(false);
    }
  }

  async function handleSavePreferences() {
    setSavingPrefs(true);
    try {
      await api.patch("/users/me/preferences", {
        language: prefLanguage,
        preferred_currency: prefCurrency,
      });
      toast.success(t(dict, "profile.preferencesSaved"));
      if (prefLanguage !== locale) {
        router.replace(`/${prefLanguage}/profile`);
      }
    } catch {
      toast.error(t(dict, "profile.preferencesError"));
    } finally {
      setSavingPrefs(false);
    }
  }

  function handleLogout() {
    logout();
    router.replace("/login");
    toast.success(t(dict, "profile.logoutSuccess"));
  }

  const displayName = user?.first_name
    ? [user.first_name, user.last_name].filter(Boolean).join(" ")
    : user?.name || t(dict, "profile.userDefault");

  const fieldClass =
    "h-9 rounded-xl border-gray-200 bg-white px-3 text-sm focus-visible:ring-1 focus-visible:ring-primary/30";
  const selectClass =
    "h-9 w-full rounded-xl border border-gray-200 bg-white px-3 text-sm outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 disabled:bg-muted disabled:text-muted-foreground";

  const INCOME_RANGE_KEYS = ["lt10", "10to20", "20to40", "40to80", "gt80", "prefer_not"] as const;
  const CHAT_MODE_KEYS = [
    { value: "normal", emoji: "😊" },
    { value: "roast", emoji: "🔥" },
    { value: "hype", emoji: "🎉" },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-4 pb-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground">{t(dict, "profile.title")}</h1>
          <p className="mt-1 text-xs text-muted-foreground">{t(dict, "profile.subtitle")}</p>
        </div>
        <Avatar className="h-11 w-11 shrink-0">
          <AvatarFallback className="bg-primary text-white">
            <User className="h-5 w-5" />
          </AvatarFallback>
        </Avatar>
      </div>

      <Card className="rounded-2xl">
        <CardContent className="flex items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-bold">{displayName}</p>
            <p className="mt-0.5 text-xs text-muted-foreground" dir="ltr">{user?.phone}</p>
          </div>
          {wallet && (
            <div className="rounded-xl bg-primary/10 px-3 py-2 text-center">
              <p className="text-[11px] text-muted-foreground">{t(dict, "profile.tokenBalance")}</p>
              <p className="text-sm font-bold text-primary">{fmtNum(wallet.balance_tokens)}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Coins className="h-4 w-4 text-primary" />
            {t(dict, "profile.accountPayment")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0">
          {wallet && (
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-muted px-2 py-2">
                <p className="text-[11px] text-muted-foreground">{t(dict, "profile.consumed")}</p>
                <p className="mt-0.5 text-xs font-bold">{fmtNum(wallet.total_consumed_tokens)}</p>
              </div>
              <div className="rounded-xl bg-muted px-2 py-2">
                <p className="text-[11px] text-muted-foreground">{t(dict, "profile.gifted")}</p>
                <p className="mt-0.5 text-xs font-bold">{fmtNum(wallet.total_granted_tokens)}</p>
              </div>
              <div className="rounded-xl bg-muted px-2 py-2">
                <p className="text-[11px] text-muted-foreground">{t(dict, "profile.purchased")}</p>
                <p className="mt-0.5 text-xs font-bold">{fmtNum(wallet.total_purchased_tokens)}</p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button asChild variant="outline" size="sm" className="h-9 justify-between px-3">
              <Link href={`/${locale}/billing/tokens`}>
                <span className="flex items-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  {t(dict, "profile.buyTokens")}
                </span>
                <span className="text-muted-foreground">←</span>
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-9 justify-between px-3">
              <Link href={`/${locale}/billing/subscription`}>
                <span className="flex items-center gap-2">
                  <Zap className="h-4 w-4" />
                  {t(dict, "profile.charge")}
                </span>
                <span className="text-muted-foreground">←</span>
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base">{t(dict, "profile.editInfo")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-4 pt-0">
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">{t(dict, "profile.firstName")}</Label>
              <Input className={fieldClass} value={name} onChange={(e) => setName(e.target.value)} placeholder={t(dict, "profile.namePlaceholder")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t(dict, "profile.lastName")}</Label>
              <Input
                className={fieldClass}
                value={familyName}
                onChange={(e) => setFamilyName(e.target.value)}
                placeholder={t(dict, "profile.familyNamePlaceholder")}
              />
            </div>
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <CalendarDays className="h-3.5 w-3.5" />
              {t(dict, "profile.birthDate")}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <select className={selectClass} value={birthDay} onChange={(e) => setBirthDay(e.target.value)}>
                <option value="">{t(dict, "profile.day")}</option>
                {JALALI_DAYS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <select className={selectClass} value={birthMonth} onChange={(e) => setBirthMonth(e.target.value)}>
                <option value="">{t(dict, "profile.month")}</option>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>{t(dict, `months.${m}`)}</option>
                ))}
              </select>
              <select className={selectClass} value={birthYear} onChange={(e) => setBirthYear(e.target.value)}>
                <option value="">{t(dict, "profile.year")}</option>
                {JALALI_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" />
              {t(dict, "profile.residence")}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <select className={selectClass} value={province} onChange={(e) => setProvince(e.target.value)}>
                <option value="">{t(dict, "profile.selectProvince")}</option>
                {provinces.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <select
                className={selectClass}
                value={city}
                onChange={(e) => setCity(e.target.value)}
                disabled={!province || cities.length === 0}
              >
                <option value="">{t(dict, "profile.selectCity")}</option>
                {cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </section>

          <section className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold text-muted-foreground">{t(dict, "profile.avgMonthlyIncome")}</p>
              <span className="text-[11px] text-muted-foreground">{t(dict, "profile.optional")}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {INCOME_RANGE_KEYS.map((key) => {
                const selected = incomeRange === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setIncomeRange(selected ? "" : key)}
                    className={`min-h-9 rounded-xl border px-2 py-1.5 text-right text-[11px] font-medium transition-colors ${
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-gray-200 bg-white text-muted-foreground hover:border-primary/30 hover:text-foreground"
                    }`}
                  >
                    {t(dict, `incomeRanges.${key}`)}
                  </button>
                );
              })}
            </div>
          </section>

          <Button className="h-10 w-full" onClick={handleSaveProfile} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {t(dict, "profile.saveChanges")}
          </Button>
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base">{t(dict, "profile.assistantMode")}</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="grid grid-cols-3 gap-2">
            {CHAT_MODE_KEYS.map((opt) => {
              const selected = chatMode === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  disabled={savingMode}
                  onClick={() => handleChatModeChange(opt.value)}
                  className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-3 text-center transition-colors disabled:opacity-60 ${
                    selected
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-gray-200 bg-white text-muted-foreground hover:border-primary/30 hover:text-foreground"
                  }`}
                >
                  <span className="text-xl">{opt.emoji}</span>
                  <span className="text-xs font-semibold">{t(dict, `chatModes.${opt.value}.label`)}</span>
                  <span className={`text-[10px] leading-tight ${selected ? "text-primary-foreground/80" : "text-muted-foreground"}`}>
                    {t(dict, `chatModes.${opt.value}.desc`)}
                  </span>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Language & Currency */}
      <Card className="rounded-2xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe className="h-4 w-4 text-primary" />
            {t(dict, "profile.languageSettings")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-4 pt-0">
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">{t(dict, "profile.languageLabel")}</Label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {SUPPORTED_LOCALES.map((loc) => {
                const meta = LOCALE_META[loc];
                const selected = prefLanguage === loc;
                return (
                  <button
                    key={loc}
                    type="button"
                    onClick={() => setPrefLanguage(loc)}
                    className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-center transition-colors ${
                      selected
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-gray-200 bg-white text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    <span className="text-lg">{meta.emoji}</span>
                    <span className="text-[11px] font-medium">{meta.nativeName}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">{t(dict, "profile.currencyLabel")}</Label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {SUPPORTED_CURRENCIES.map((cur) => {
                const selected = prefCurrency === cur;
                return (
                  <button
                    key={cur}
                    type="button"
                    onClick={() => setPrefCurrency(cur)}
                    className={`rounded-xl border px-2 py-2 text-center text-xs font-medium transition-colors ${
                      selected
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-gray-200 bg-white text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    {cur}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted-foreground">{t(dict, "profile.currencyNote")}</p>
          </div>

          <Button className="h-10 w-full" onClick={handleSavePreferences} disabled={savingPrefs}>
            {savingPrefs && <Loader2 className="h-4 w-4 animate-spin" />}
            {t(dict, "profile.saveChanges")}
          </Button>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-destructive/30">
        <CardContent className="p-4">
          <Button variant="destructive" className="h-10 w-full" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            {t(dict, "profile.logoutBtn")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
