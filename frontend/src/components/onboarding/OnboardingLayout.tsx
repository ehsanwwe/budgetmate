"use client";
import { motion } from "framer-motion";
import { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

interface Props {
  children: ReactNode;
  back?: boolean;
  backHref?: string;
  totalSteps?: number;
  currentStep?: number;
  showBack?: boolean;
}

export default function OnboardingLayout({
  children,
  back = false,
  backHref,
  totalSteps,
  currentStep,
  showBack = true,
}: Props) {
  const router = useRouter();
  const dir = back ? -1 : 1;

  function handleBack() {
    if (backHref) router.push(backHref);
    else router.back();
  }

  return (
    <motion.div
      initial={{ x: 50 * dir, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -50 * dir, opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="min-h-screen bg-[#f5f1eb] flex flex-col"
      dir="rtl"
    >
      {/* Top bar: back + progress dots */}
      <div className="flex items-center justify-between px-5 pt-12 pb-4">
        {showBack ? (
          <button
            onClick={handleBack}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/70 shadow-sm hover:bg-white transition-colors"
            aria-label="بازگشت"
          >
            <ArrowRight className="w-5 h-5 text-[#2d1812]" />
          </button>
        ) : (
          <div className="w-10" />
        )}

        {totalSteps && currentStep ? (
          <div className="flex gap-1.5">
            {Array.from({ length: totalSteps }).map((_, i) => (
              <div
                key={i}
                className={`rounded-full transition-all duration-300 ${
                  i < currentStep
                    ? "w-6 h-2 bg-[#2d1812]"
                    : i === currentStep - 1
                    ? "w-6 h-2 bg-[#2d1812]"
                    : "w-2 h-2 bg-[#2d1812]/20"
                }`}
              />
            ))}
          </div>
        ) : (
          <div />
        )}

        <div className="w-10" />
      </div>

      {/* Page content */}
      <div className="flex-1 flex flex-col px-6 pb-8 max-w-[440px] mx-auto w-full">
        {children}
      </div>
    </motion.div>
  );
}
