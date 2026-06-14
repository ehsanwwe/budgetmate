"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import OnboardingLayout from "@/components/onboarding/OnboardingLayout";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const INCOME_OPTIONS = [
  { value: "lt10", label: "کمتر از ۱۰ میلیون تومان" },
  { value: "10to20", label: "۱۰ تا ۲۰ میلیون" },
  { value: "20to40", label: "۲۰ تا ۴۰ میلیون" },
  { value: "40to80", label: "۴۰ تا ۸۰ میلیون" },
  { value: "gt80", label: "بیشتر از ۸۰ میلیون" },
  { value: "prefer_not", label: "ترجیح می‌دم نگم" },
];

const JALALI_YEARS = Array.from({ length: 60 }, (_, i) => 1404 - i);
const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];
const JALALI_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

export default function OnboardingProfilePage() {
  const router = useRouter();
  const { token, setUser } = useAuthStore();

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    api
        .get("/iran/provinces")
        .then((r) => setProvinces(r.data.provinces))
        .catch(() => {});
  }, [token, router]);

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
            setCities(r.data.cities);
            setCity("");
          })
          .catch(() => {});
    });
  }, [province]);

  function jalaliToGregorian(jy: number, jm: number, jd: number): string {
    // Simple approximation: Jalali → Gregorian offset
    const gy = jy + 621;
    const gm = jm <= 6 ? jm + 3 : jm - 6;
    const isSecondHalf = jm > 6;
    return `${gy + (isSecondHalf ? 1 : 0)}-${String(gm).padStart(2, "0")}-${String(jd).padStart(2, "0")}`;
  }

  async function handleSubmit() {
    if (!name.trim() || !familyName.trim()) {
      setError("نام و نام خانوادگی الزامی است");
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

      await api.post("/onboarding/profile", body);
      // Also update users/me for display_name
      const meRes = await api.get("/users/me");
      setUser(meRes.data);
      router.push("/onboarding/agreement");
    } catch {
      setError("خطا در ذخیره اطلاعات. دوباره تلاش کنید");
    } finally {
      setLoading(false);
    }
  }

  const labelCls = "block text-[11px] font-medium leading-none text-[#2d1812]/65";
  const inputCls =
      "h-8 w-full rounded-[12px] border border-[#2d1812]/10 bg-white px-3 text-[12px] leading-none text-[#2d1812] outline-none transition placeholder:text-gray-300 focus:border-[#2d1812]/25 focus:ring-2 focus:ring-[#2d1812]/5 sm:h-10 sm:rounded-[14px] sm:text-[13px]";
  const selectCls = `${inputCls} cursor-pointer appearance-none disabled:cursor-not-allowed disabled:bg-white/50 disabled:text-gray-400`;

  return (
      <OnboardingLayout
          backHref="/login/otp"
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
          <p className="text-[11px] font-semibold text-[#2d1812]/45 sm:text-xs">مرحله ۱ از ۵</p>
          <h1 className="text-[22px] font-[800] leading-tight tracking-[-0.02em] text-[#2d1812] sm:text-[26px]">
            تکمیل پروفایل
          </h1>
          <p className="max-w-[330px] text-[12px] leading-5 text-gray-500 sm:text-[13px] sm:leading-6">
            فقط نام و نام خانوادگی اجباری است؛ بقیه موارد برای شخصی‌سازی تجربه
            مالی استفاده می‌شود.
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
                    اطلاعات اصلی
                  </h2>
                  <span className="rounded-full bg-[#2d1812]/5 px-2 py-0.5 text-[10px] font-medium text-[#2d1812]/60 sm:px-2.5 sm:py-1 sm:text-[11px]">
                  ضروری
                </span>
                </div>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3">
                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>نام</span>
                    <input
                        className={inputCls}
                        placeholder="مثلاً علی"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                  </label>

                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>نام خانوادگی</span>
                    <input
                        className={inputCls}
                        placeholder="مثلاً رضایی"
                        value={familyName}
                        onChange={(e) => setFamilyName(e.target.value)}
                    />
                  </label>
                </div>
              </section>

              <div className="h-px bg-[#2d1812]/[0.07] sm:bg-[#2d1812]/10" />

              <section className="space-y-2 sm:space-y-3">
                <h2 className="text-[12px] font-bold text-[#2d1812] sm:text-[13px]">
                  اطلاعات تکمیلی
                </h2>

                <label className="space-y-1 sm:space-y-1.5">
                  <span className={labelCls}>تاریخ تولد</span>
                  <div className="grid grid-cols-3 gap-1.5 sm:gap-2">
                    <select
                        className={selectCls}
                        value={birthDay}
                        onChange={(e) => setBirthDay(e.target.value)}
                    >
                      <option value="">روز</option>
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
                      <option value="">ماه</option>
                      {JALALI_MONTHS.map((m, i) => (
                          <option key={i} value={i + 1}>
                            {m}
                          </option>
                      ))}
                    </select>
                    <select
                        className={selectCls}
                        value={birthYear}
                        onChange={(e) => setBirthYear(e.target.value)}
                    >
                      <option value="">سال</option>
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
                    <span className={labelCls}>استان</span>
                    <select
                        className={selectCls}
                        value={province}
                        onChange={(e) => setProvince(e.target.value)}
                    >
                      <option value="">انتخاب استان</option>
                      {provinces.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                      ))}
                    </select>
                  </label>

                  <label className="space-y-1 sm:space-y-1.5">
                    <span className={labelCls}>شهر</span>
                    <select
                        className={selectCls}
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        disabled={!province || cities.length === 0}
                    >
                      <option value="">انتخاب شهر</option>
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
                    میانگین درآمد ماهانه
                  </h2>
                  <span className="text-[10px] text-gray-400 sm:text-[11px]">اختیاری</span>
                </div>

                <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
                  {INCOME_OPTIONS.map((opt) => {
                    const selected = incomeRange === opt.value;
                    return (
                        <button
                            key={opt.value}
                            type="button"
                            onClick={() => setIncomeRange(selected ? "" : opt.value)}
                            className={`min-h-8 rounded-[12px] border px-2.5 py-1.5 text-right text-[11px] font-medium leading-4 transition-all sm:min-h-10 sm:rounded-[15px] sm:px-3 sm:py-2 sm:text-[12px] sm:leading-5 ${
                                selected
                                    ? "border-[#2d1812] bg-[#2d1812] text-white shadow-[0_8px_20px_rgba(45,24,18,0.16)]"
                                    : "border-[#2d1812]/10 bg-white/75 text-[#2d1812]/75 hover:border-[#2d1812]/20 hover:bg-white"
                            }`}
                        >
                          {opt.label}
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
            ادامه
          </button>
        </div>
      </OnboardingLayout>
  );
}
