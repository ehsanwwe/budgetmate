"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const AGREEMENT_VERSION = "1.0.0";

export default function OnboardingAgreementPage() {
  const router = useRouter();
  const { token, logout } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) router.replace("/login");
  }, [token, router]);

  async function handleAccept() {
    setLoading(true);
    try {
      await api.post("/onboarding/agreement", { version: AGREEMENT_VERSION });
      router.push("/onboarding/welcome");
    } catch {
      setLoading(false);
    }
  }

  function handleDecline() {
    logout();
    router.replace("/login");
  }

  return (
    <motion.div
      initial={{ x: 50, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen bg-[#f5f1eb] flex flex-col max-w-[440px] mx-auto w-full"
      dir="rtl"
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 pt-12 pb-4 shrink-0">
        {/* Logo pill */}
        <div className="flex items-center gap-2 bg-[#2d1812] text-white text-sm font-semibold px-4 py-2 rounded-full">
          بادجت‌میت
        </div>
        <button
          onClick={handleDecline}
          className="text-sm text-gray-500 hover:text-red-500 transition-colors font-medium"
        >
          رد می‌کنم
        </button>
      </div>

      {/* Heading */}
      <div className="px-6 pb-4 shrink-0">
        <h1 className="text-4xl font-[800] text-[#2d1812] leading-tight tracking-tight mb-2">
          شرایط و قوانین
        </h1>
        <p className="text-base text-gray-600 leading-relaxed mb-2">
          قبل از شروع، این متن کوتاه رو بخون
        </p>
        <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-100 text-emerald-700 text-xs px-3 py-1.5 rounded-full">
          <span>آخرین به‌روزرسانی: ۱۴۰۳/۰۹/۱۹ — نسخه ۱.۰.۰</span>
        </div>
      </div>

      {/* Scrollable T&C content */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 pb-4 min-h-0"
      >
        <div className="prose prose-sm max-w-none text-gray-700 space-y-5 pb-6">

          <h2 className="text-lg font-bold text-[#2d1812]">۱. معرفی سرویس</h2>
          <p>
            بادجت‌میت یک نرم‌افزار مدیریت مالی شخصی است که به کاربران کمک می‌کند بودجه ماهانه، هزینه‌ها و اهداف مالی خود را ردیابی و مدیریت کنند. همچنین یک دستیار هوش مصنوعی فارسی‌زبان برای مشاوره مالی ارائه می‌دهد. با استفاده از این سرویس، شما شرایط و ضوابط زیر را پذیرفته‌اید.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۲. شرایط استفاده</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">۲.۱ سن استفاده</h3>
          <p>
            استفاده از بادجت‌میت برای افراد بالای ۱۸ سال مجاز است. با ثبت‌نام در این سرویس، تأیید می‌کنید که حداقل ۱۸ سال سن دارید. اگر والدین یا سرپرستی برای کاربر زیر ۱۸ سال ثبت‌نام می‌کنند، مسئولیت استفاده کودک بر عهده سرپرست قانونی است.
          </p>

          <h3 className="text-base font-semibold text-[#2d1812]">۲.۲ استفاده مجاز</h3>
          <p>
            شما متعهد می‌شوید که از این سرویس صرفاً برای اهداف قانونی و شخصی استفاده کنید. استفاده تجاری، انتقال اطلاعات به ثالث، کپی‌برداری غیرمجاز از محتوا یا هرگونه تلاش برای دسترسی غیرمجاز به سیستم‌های ما ممنوع است.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۳. حریم خصوصی و داده‌ها</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">۳.۱ داده‌هایی که جمع‌آوری می‌کنیم</h3>
          <p>
            بادجت‌میت <strong>هیچ‌گونه اتصالی به حساب‌های بانکی شما ندارد</strong>. تمامی اطلاعات مالی (تراکنش‌ها، بودجه‌ها، اهداف) به صورت دستی توسط خود شما وارد می‌شود. ما اطلاعات زیر را جمع‌آوری می‌کنیم:
          </p>
          <ul className="list-disc pr-5 space-y-1">
            <li>شماره موبایل برای احراز هویت</li>
            <li>اطلاعات پروفایل (نام، محل سکونت، بازه درآمدی) که خودتان وارد می‌کنید</li>
            <li>تراکنش‌ها و بودجه‌هایی که شما ثبت می‌کنید</li>
            <li>پیام‌های گفتگو با دستیار هوشمند</li>
          </ul>

          <h3 className="text-base font-semibold text-[#2d1812]">۳.۲ نحوه استفاده از داده‌ها</h3>
          <p>
            از اطلاعات شما برای ارائه خدمات بهتر، شخصی‌سازی مشاوره‌های مالی و بهبود تجربه کاربری استفاده می‌شود. اطلاعات شما به هیچ شخص ثالثی فروخته یا واگذار نمی‌شود، مگر در موارد الزام قانونی.
          </p>

          <h3 className="text-base font-semibold text-[#2d1812]">۳.۳ امنیت داده‌ها</h3>
          <p>
            از روش‌های رمزنگاری استاندارد صنعتی برای حفاظت از اطلاعات شما استفاده می‌کنیم. با این حال، هیچ سیستمی صد در صد امن نیست و ما نمی‌توانیم امنیت مطلق را تضمین کنیم.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۴. دستیار هوش مصنوعی</h2>

          <h3 className="text-base font-semibold text-[#2d1812]">۴.۱ ماهیت مشاوره</h3>
          <p>
            دستیار هوشمند بادجت‌میت اطلاعات عمومی و پیشنهادهای آموزشی ارائه می‌دهد. این پیشنهادها <strong>مشاوره مالی حرفه‌ای محسوب نمی‌شوند</strong> و جایگزین مشاور مالی مجاز نیستند. برای تصمیمات مالی مهم، حتماً با کارشناس مالی معتبر مشورت کنید.
          </p>

          <h3 className="text-base font-semibold text-[#2d1812]">۴.۲ محدودیت مسئولیت</h3>
          <p>
            بادجت‌میت در قبال هیچ‌گونه خسارت مالی ناشی از تصمیماتی که بر اساس پیشنهادهای دستیار هوشمند گرفته‌اید، مسئولیتی نمی‌پذیرد.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۵. خدمات اشتراک</h2>
          <p>
            برخی از قابلیت‌های پیشرفته دستیار هوشمند نیازمند خرید اشتراک یا توکن است. قیمت‌ها به وضوح پیش از خرید نمایش داده می‌شوند. تمامی خریدها قطعی بوده و استرداد وجه تنها در موارد خاص و با بررسی تیم پشتیبانی امکان‌پذیر است.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۶. تغییرات در شرایط</h2>
          <p>
            ما این حق را داریم که شرایط استفاده را در هر زمان به‌روز کنیم. تغییرات مهم از طریق اعلان‌های درون‌برنامه‌ای به اطلاع شما خواهد رسید. استفاده مستمر از سرویس پس از اعلام تغییرات به معنای پذیرش شرایط جدید است.
          </p>

          <h2 className="text-lg font-bold text-[#2d1812]">۷. تماس با ما</h2>
          <p>
            در صورت داشتن سؤال یا نگرانی درباره این شرایط، می‌توانید از طریق ایمیل <span dir="ltr" className="font-mono text-[#2d1812]">support@budgetmate.ir</span> یا از طریق بخش پشتیبانی در برنامه با ما در ارتباط باشید. تیم ما آماده پاسخگویی است.
          </p>

        </div>
      </div>

      {/* Sticky bottom */}
      <div className="px-6 pt-3 pb-10 shrink-0 bg-gradient-to-t from-[#f5f1eb] to-transparent">
        <p className="text-center text-xs text-gray-400 italic mb-4 leading-relaxed">
          با کلیک روی «می‌پذیرم» تأیید می‌کنی که شرایط رو خوندی و قبول کردی
        </p>
        <button
          onClick={handleAccept}
          disabled={loading}
          className="w-full py-4 rounded-full bg-[#2d1812] text-white font-semibold text-base disabled:opacity-40 hover:bg-[#3d2218] active:scale-[0.98] transition-all flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          می‌پذیرم
        </button>
      </div>
    </motion.div>
  );
}
