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
  "فروردین", "اردیبهشت", "خرداد",
  "تیر", "مرداد", "شهریور",
  "مهر", "آبان", "آذر",
  "دی", "بهمن", "اسفند",
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
    if (!token) { router.replace("/login"); return; }
    api.get("/iran/provinces").then((r) => setProvinces(r.data.provinces)).catch(() => {});
  }, [token, router]);

  useEffect(() => {
    if (!province) { setCities([]); setCity(""); return; }
    api.get(`/iran/cities?province=${encodeURIComponent(province)}`)
      .then((r) => { setCities(r.data.cities); setCity(""); })
      .catch(() => {});
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

  const selectCls = "w-full bg-white border-0 rounded-xl px-4 py-3 text-[#2d1812] focus:outline-none focus:ring-2 focus:ring-[#2d1812]/20 appearance-none shadow-sm cursor-pointer";
  const inputCls = "w-full bg-white border-0 rounded-xl px-4 py-3 text-[#2d1812] placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-[#2d1812]/20 shadow-sm";

  return (
    <OnboardingLayout backHref="/login/otp" totalSteps={5} currentStep={1} showBack={false}>
      <motion.div
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1, duration: 0.3 }}
        className="space-y-2 mb-8"
      >
        <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight">
          بذار بیشتر بشناسیمت
        </h1>
        <p className="text-base text-gray-600 leading-relaxed">
          این اطلاعات کمک می‌کنه مشاوره دقیق‌تری بهت بدیم
        </p>
      </motion.div>

      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.3 }}
        className="space-y-4 flex-1"
      >
        {/* Name */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-gray-600 pr-1">نام</label>
          <input
            className={inputCls}
            placeholder="نام"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* Family name */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-gray-600 pr-1">نام خانوادگی</label>
          <input
            className={inputCls}
            placeholder="نام خانوادگی"
            value={familyName}
            onChange={(e) => setFamilyName(e.target.value)}
          />
        </div>

        {/* Birthdate — 3 selects */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-gray-600 pr-1">تاریخ تولد (اختیاری)</label>
          <div className="grid grid-cols-3 gap-2">
            <select className={selectCls} value={birthYear} onChange={(e) => setBirthYear(e.target.value)}>
              <option value="">سال</option>
              {JALALI_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <select className={selectCls} value={birthMonth} onChange={(e) => setBirthMonth(e.target.value)}>
              <option value="">ماه</option>
              {JALALI_MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select>
            <select className={selectCls} value={birthDay} onChange={(e) => setBirthDay(e.target.value)}>
              <option value="">روز</option>
              {JALALI_DAYS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
        </div>

        {/* Province */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-gray-600 pr-1">استان (اختیاری)</label>
          <select className={selectCls} value={province} onChange={(e) => setProvince(e.target.value)}>
            <option value="">انتخاب استان</option>
            {provinces.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        {/* City */}
        {cities.length > 0 && (
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-gray-600 pr-1">شهر (اختیاری)</label>
            <select className={selectCls} value={city} onChange={(e) => setCity(e.target.value)}>
              <option value="">انتخاب شهر</option>
              {cities.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        )}

        {/* Income range */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-600 pr-1">میانگین درآمد ماهانه (اختیاری)</label>
          <div className="grid grid-cols-2 gap-2">
            {INCOME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setIncomeRange(incomeRange === opt.value ? "" : opt.value)}
                className={`py-3 px-3 rounded-xl text-sm font-medium text-right transition-all border-2 ${
                  incomeRange === opt.value
                    ? "bg-[#2d1812] text-white border-[#2d1812]"
                    : "bg-white text-[#2d1812] border-transparent shadow-sm hover:border-[#2d1812]/20"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
      </motion.div>

      {/* Bottom button */}
      <div className="pt-6 pb-2">
        <button
          onClick={handleSubmit}
          disabled={loading || !name.trim() || !familyName.trim()}
          className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#3d2218] active:scale-[0.98] transition-all flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          ادامه
        </button>
      </div>
    </OnboardingLayout>
  );
}
