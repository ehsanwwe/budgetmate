"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import OnboardingLayout from "@/components/onboarding/OnboardingLayout";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { onboardingDraft, OnboardingDraft } from "@/hooks/useOnboardingDraft";

const INCOME_VALUES = ["lt10", "10to20", "20to40", "40to80", "gt80", "prefer_not"] as const;
const FINANCIAL_STATUS_VALUES = [
  "stable_income", "irregular_income", "overspending", "in_debt",
  "saving_for_goal", "low_income_pressure", "planning_only", "other",
] as const;
type FinancialStatusValue = typeof FINANCIAL_STATUS_VALUES[number];

const JALALI_YEARS = Array.from({ length: 60 }, (_, i) => 1404 - i);
const JALALI_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

export default function OnboardingProfilePage() {
  const router = useRouter();
  const { token, setUser } = useAuthStore();
  const userId = useAuthStore((s) => s.user?.id);
  const { locale, dict } = useLocale();
  const t = dict.onboarding.profilePage;

  const [name, setName] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [birthMonth, setBirthMonth] = useState("");
  const [birthDay, setBirthDay] = useState("");
  const [provinces, setProvinces] = useState<string[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [province, setProvince] = useState("");
  const [city, setCity] = useState("");
  const [incomeRange, setIncomeRange] = useState("");
  const [financialStatus, setFinancialStatus] = useState<FinancialStatusValue | "">("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // Becomes true after backend/draft hydration completes, gates auto-save
  const [hydrated, setHydrated] = useState(false);
  // Holds city to restore once cities list loads after province is set
  const pendingCityRef = useRef<string>("");

  // On mount: fetch provinces + backend status, merge with local draft
  useEffect(() => {
    if (!token) {
      router.replace(`/${locale}/login`);
      return;
    }

    api.get("/iran/provinces").then((r) => setProvinces(r.data.provinces)).catch(() => {});

    api
      .get("/onboarding/status")
      .then((r) => {
        const status = r.data;
        const draft: OnboardingDraft = userId ? onboardingDraft.read(userId) : {
          name: "", familyName: "", birthYear: "", birthMonth: "", birthDay: "",
          province: "", city: "", incomeRange: "", financialStatus: "",
        };

        // Backend wins for saved fields; draft fills unsaved optional fields
        const mergedName = (status.name ?? status.first_name) || draft.name;
        const mergedFamily = status.family_name || draft.familyName;
        const mergedProvince = status.province || draft.province;
        const mergedCity = status.city || draft.city;
        const mergedIncome = status.income_range || draft.incomeRange;
        const mergedStatus = status.current_financial_status || draft.financialStatus;

        // Birthdate: backend status doesn't expose Jalali components — use draft only
        setName(mergedName);
        setFamilyName(mergedFamily);
        setBirthYear(draft.birthYear);
        setBirthMonth(draft.birthMonth);
        setBirthDay(draft.birthDay);
        setIncomeRange(mergedIncome);
        setFinancialStatus(mergedStatus as FinancialStatusValue | "");

        if (mergedProvince) {
          // City will be restored after cities list loads
          pendingCityRef.current = mergedCity;
          setProvince(mergedProvince);
        } else {
          setCity(mergedCity);
        }
      })
      .catch(() => {
        // Network failure: fall back to draft only
        if (userId) {
          const draft = onboardingDraft.read(userId);
          setName(draft.name);
          setFamilyName(draft.familyName);
          setBirthYear(draft.birthYear);
          setBirthMonth(draft.birthMonth);
          setBirthDay(draft.birthDay);
          setIncomeRange(draft.incomeRange);
          setFinancialStatus(draft.financialStatus as FinancialStatusValue | "");
          if (draft.province) {
            pendingCityRef.current = draft.city;
            setProvince(draft.province);
          } else {
            setCity(draft.city);
          }
        }
      })
      .finally(() => setHydrated(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, locale, userId]);

  // Load cities when province changes; restore pending city if valid
  useEffect(() => {
    queueMicrotask(() => {
      if (!province) {
        setCities([]);
        setCity("");
        return;
      }
      api
        .get(`/iran/cities?province=${encodeURIComponent(province)}`)
        .then((r) => {
          const loaded: string[] = r.data.cities;
          setCities(loaded);
          const pending = pendingCityRef.current;
          pendingCityRef.current = "";
          setCity(pending && loaded.includes(pending) ? pending : "");
        })
        .catch(() => {});
    });
  }, [province]);

  // Auto-save all form fields to localStorage draft after hydration
  useEffect(() => {
    if (!hydrated || !userId) return;
    onboardingDraft.save(userId, {
      name, familyName, birthYear, birthMonth, birthDay,
      province, city, incomeRange, financialStatus,
    });
  }, [hydrated, userId, name, familyName, birthYear, birthMonth, birthDay, province, city, incomeRange, financialStatus]);

  function jalaliToGregorian(jy: number, jm: number, jd: number): string {
    // Simple approximation: Jalali → Gregorian offset
    const gy = jy + 621;
    const gm = jm <= 6 ? jm + 3 : jm - 6;
    const isSecondHalf = jm > 6;
    return `${gy + (isSecondHalf ? 1 : 0)}-${String(gm).padStart(2, "0")}-${String(jd).padStart(2, "0")}`;
  }

  async function handleSubmit() {
    if (!name.trim() || !familyName.trim()) {
      setError(t.errors.nameRequired);
      return;
    }
    setError("");
    setLoading(true);
    try {
      const body: Record<string, string> = {
        name: name.trim(),
        family_name: familyName.trim(),
      };
      if (birthYear && birthMonth && birthDay) {
        body.birthdate = jalaliToGregorian(+birthYear, +birthMonth, +birthDay);
      }
      if (province) body.province = province;
      if (city) body.city = city;
      if (incomeRange) body.income_range = incomeRange;
      if (financialStatus) body.current_financial_status = financialStatus;

      await api.post("/onboarding/profile", body);
      const meRes = await api.get("/users/me");
      setUser(meRes.data);

      // Clear draft — all values are now saved in backend
      if (userId) onboardingDraft.clear(userId);

      router.push(`/${locale}/onboarding/agreement`);
    } catch {
      setError(t.errors.saveFailed);
    } finally {
      setLoading(false);
    }
  }

  const labelCls = "block text-[11px] font-medium leading-none text-[#2d1812]/65";
  const inputCls =
      "h-8 w-full rounded-[12px] border border-[#2d1812]/10 bg-white px-3 text-[12px] leading-none text-[#2d1812] outline-none transition placeholder:text-gray-300 focus:border-[#2d1812]/25 focus:ring-2 focus:ring-[#2d1812]/5 sm:h-10 sm:rounded-[14px] sm:text-[13px]";
  const selectCls = `${inputCls} cursor-pointer appearance-none disabled:cursor-not-allowed disabled:bg-white/50 disabled:text-gray-400`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const monthsMap = (dict as any).jalaliMonths as Record<string, string>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const incomeMap = (dict as any).incomeRanges as Record<string, string>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const financialStatusMap = (dict as any).financialStatus as Record<string, string> | undefined;

  return (
      <OnboardingLayout
          backHref={`/${locale}/login/otp`}
          totalSteps={5}
          currentStep={1}
          showBack={false}
      >
        <motion.div
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.25 }}
            className="mb-3 space-y-1 sm:mb-5 sm:space-y-1.5"
        >
          <p className="text-[11px] font-semibold text-[#2d1812]/45 sm:text-xs">
            {tDict(dict, "onboarding.profilePage.stepIndicator", { current: 1, total: 5 })}
          </p>
          <h1 className="text-[22px] font-[800] leading-tight tracking-[-0.02em] text-[#2d1812] sm:text-[26px]">
            {t.title}
          </h1>
          <p className="max-w-[330px] text-[12px] leading-5 text-gray-500 sm:text-[13px] sm:leading-6">
            {t.subtitle}
          </p>
        </motion.div>

        <motion.div
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.18, duration: 0.25 }}
            className="min-h-0 flex-1 overflow-y-auto pb-2 sm:pb-3"
        >
          <div className="p-0 sm:rounded-[22px] sm:border sm:border-white/75 sm:bg-white/50 sm:p-3 sm:shadow-[0_18px_45px_rgba(45,24,18,0.06)] sm:backdrop-blur-sm">
            <div className="space-y-3 sm:space-y-4">
              <section className="space-y-2 sm:space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-[12px] font-bold text-[#2d1812] sm:text-[13px]">
                    {t.sectionMain}
                  </h2>
                  <span className="rounded-full bg-[#2d1812]/5 px-2 py-0.5 text-[10px] font-medium text-[#2d1812]/60 sm:px-2.5 sm:py-1 sm:text-[11px]">
                    {t.required}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3">
                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>{t.firstNameLabel}</span>
                    <input
                        className={inputCls}
                        placeholder={t.firstNamePlaceholder}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                  </label>

                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>{t.lastNameLabel}</span>
                    <input
                        className={inputCls}
                        placeholder={t.lastNamePlaceholder}
                        value={familyName}
                        onChange={(e) => setFamilyName(e.target.value)}
                    />
                  </label>
                </div>
              </section>

              <div className="h-px bg-[#2d1812]/[0.07] sm:bg-[#2d1812]/10" />

              <section className="space-y-2 sm:space-y-3">
                <h2 className="text-[12px] font-bold text-[#2d1812] sm:text-[13px]">
                  {t.sectionExtra}
                </h2>

                <label className="space-y-1 sm:space-y-1.5">
                  <span className={labelCls}>{t.birthdateLabel}</span>
                  <div className="grid grid-cols-3 gap-1.5 sm:gap-2">
                    <select
                        className={selectCls}
                        value={birthDay}
                        onChange={(e) => setBirthDay(e.target.value)}
                    >
                      <option value="">{t.dayPlaceholder}</option>
                      {JALALI_DAYS.map((d) => (
                          <option key={d} value={d}>
                            {d}
                          </option>
                      ))}
                    </select>
                    <select
                        className={selectCls}
                        value={birthMonth}
                        onChange={(e) => setBirthMonth(e.target.value)}
                    >
                      <option value="">{t.monthPlaceholder}</option>
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                          <option key={m} value={m}>
                            {monthsMap?.[String(m)] ?? m}
                          </option>
                      ))}
                    </select>
                    <select
                        className={selectCls}
                        value={birthYear}
                        onChange={(e) => setBirthYear(e.target.value)}
                    >
                      <option value="">{t.yearPlaceholder}</option>
                      {JALALI_YEARS.map((y) => (
                          <option key={y} value={y}>
                            {y}
                          </option>
                      ))}
                    </select>
                  </div>
                </label>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3">
                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>{t.provinceLabel}</span>
                    <select
                        className={selectCls}
                        value={province}
                        onChange={(e) => setProvince(e.target.value)}
                    >
                      <option value="">{t.selectProvince}</option>
                      {provinces.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                      ))}
                    </select>
                  </label>

                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>{t.cityLabel}</span>
                    <select
                        className={selectCls}
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        disabled={!province || cities.length === 0}
                    >
                      <option value="">{t.selectCity}</option>
                      {cities.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                      ))}
                    </select>
                  </label>
                </div>
              </section>

              <div className="h-px bg-[#2d1812]/[0.07] sm:bg-[#2d1812]/10" />

              <section className="space-y-2 sm:space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-[12px] font-bold text-[#2d1812] sm:text-[13px]">
                    {t.sectionIncome}
                  </h2>
                  <span className="text-[10px] text-gray-400 sm:text-[11px]">{t.optional}</span>
                </div>

                <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
                  {INCOME_VALUES.map((value) => {
                    const selected = incomeRange === value;
                    const label = incomeMap?.[value] ?? value;
                    return (
                        <button
                            key={value}
                            type="button"
                            onClick={() => setIncomeRange(selected ? "" : value)}
                            className={`min-h-8 rounded-[12px] border px-2.5 py-1.5 text-right text-[11px] font-medium leading-4 transition-all sm:min-h-10 sm:rounded-[15px] sm:px-3 sm:py-2 sm:text-[12px] sm:leading-5 ${
                                selected
                                    ? "border-[#2d1812] bg-[#2d1812] text-white shadow-[0_8px_20px_rgba(45,24,18,0.16)]"
                                    : "border-[#2d1812]/10 bg-white/75 text-[#2d1812]/75 hover:border-[#2d1812]/20 hover:bg-white"
                            }`}
                        >
                          {label}
                        </button>
                    );
                  })}
                </div>
              </section>

              <div className="h-px bg-[#2d1812]/[0.07] sm:bg-[#2d1812]/10" />

              <section className="space-y-2 sm:space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-[12px] font-bold text-[#2d1812] sm:text-[13px]">
                    {t.sectionFinancialStatus ?? "وضعیت مالی فعلی"}
                  </h2>
                  <span className="text-[10px] text-gray-400 sm:text-[11px]">{t.optional}</span>
                </div>

                <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
                  {FINANCIAL_STATUS_VALUES.map((value) => {
                    const selected = financialStatus === value;
                    const label = financialStatusMap?.[value] ?? value;
                    return (
                        <button
                            key={value}
                            type="button"
                            onClick={() => setFinancialStatus(selected ? "" : value)}
                            className={`min-h-8 rounded-[12px] border px-2.5 py-1.5 text-right text-[11px] font-medium leading-4 transition-all sm:min-h-10 sm:rounded-[15px] sm:px-3 sm:py-2 sm:text-[12px] sm:leading-5 ${
                                selected
                                    ? "border-[#10b981] bg-[#10b981] text-white shadow-[0_8px_20px_rgba(16,185,129,0.16)]"
                                    : "border-[#2d1812]/10 bg-white/75 text-[#2d1812]/75 hover:border-[#2d1812]/20 hover:bg-white"
                            }`}
                        >
                          {label}
                        </button>
                    );
                  })}
                </div>
              </section>
            </div>
          </div>
        </motion.div>

        <div className="shrink-0 border-t border-[#2d1812]/5 bg-[#f5f1eb] pt-2 pb-1.5 sm:pt-3 sm:pb-2">
          {error && (
              <p className="mb-2 rounded-[12px] border border-red-100 bg-red-50 px-3 py-1.5 text-[11px] text-red-600 sm:text-[12px]">
                {error}
              </p>
          )}

          <button
              onClick={handleSubmit}
              disabled={loading || !name.trim() || !familyName.trim()}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-[14px] bg-[#2d1812] text-[13px] font-semibold text-white shadow-[0_10px_22px_rgba(45,24,18,0.14)] transition-all hover:bg-[#3d2218] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 sm:h-12 sm:rounded-[18px] sm:text-sm"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {t.nextButton}
          </button>
        </div>
      </OnboardingLayout>
  );
}
