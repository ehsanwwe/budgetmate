"use client";
import { motion } from "framer-motion";
import { Smile, MessageCircle, Settings, Sparkles, Mic, ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";

const SUGGESTED_PROMPTS = [
  "ماهانه چقدر پس‌انداز کنم؟",
  "خرج‌های این ماهم رو خلاصه کن",
  "برای خرید لپ‌تاپ ۸۰ میلیونی بودجه‌بندی کن",
  "چطور هزینه‌های غیرضروری رو کم کنم؟",
  "نکات پس‌انداز برای دانشجو",
];

interface ChatEmptyStateProps {
  firstName: string;
  hasBudget: boolean | null;
  input: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  onPromptClick: (text: string) => void;
  onVoiceModeClick: () => void;
  streaming: boolean;
}

export default function ChatEmptyState({
                                         firstName,
                                         hasBudget,
                                         input,
                                         onInputChange,
                                         onSend,
                                         onPromptClick,
                                         onVoiceModeClick,
                                         streaming,
                                       }: ChatEmptyStateProps) {
  const router = useRouter();

  return (
      <div
          className="flex h-[calc(100dvh-5rem)] min-h-0 w-full max-w-full flex-col overflow-hidden bg-[#f5f1eb] md:h-[calc(100dvh-2rem)]"
          dir="rtl"
      >
        {/* 1. Top header — minimal, two icon buttons */}
        <div className="flex items-center justify-between px-4 py-3 shrink-0">
          <motion.button
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
              className="w-10 h-10 rounded-full bg-white shadow-sm flex items-center justify-center hover:shadow-md transition-shadow"
              aria-label="تاریخچه گفتگو"
          >
            <MessageCircle className="w-5 h-5 text-[#2d1812]" />
          </motion.button>

          <motion.button
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
              className="w-10 h-10 rounded-full bg-white shadow-sm flex items-center justify-center hover:shadow-md transition-shadow"
              aria-label="تنظیمات"
              onClick={() => router.push("/profile")}
          >
            <Settings className="w-5 h-5 text-[#2d1812]" />
          </motion.button>
        </div>

        {/* 2. Center hero — vertically centered */}
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-hidden px-6 py-2 text-center">
          {/* Yellow smiley circle */}
          <motion.div
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.45, delay: 0.1, type: "spring", stiffness: 200, damping: 16 }}
              className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-yellow-400 shadow-md sm:mb-6 sm:h-20 sm:w-20"
          >
            <Smile className="h-8 w-8 text-yellow-900 sm:h-10 sm:w-10" strokeWidth={2.2} />
          </motion.div>

          {/* Greeting heading */}
          <motion.h1
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.22 }}
              className="mb-2 text-2xl font-extrabold text-[#2d1812] sm:mb-3 sm:text-3xl"
          >
            سلام{firstName ? ` ${firstName}` : ""}!
          </motion.h1>

          {/* Subtitle */}
          <motion.p
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.34 }}
              className="max-w-xs text-sm leading-relaxed text-gray-600 sm:text-base"
          >
            من جیبیارم،{" "}
            <span className="text-emerald-500 font-semibold">دستیار مالی هوشمندت</span>.
            <br />
            هر سوالی درباره بودجه، خرج‌ها یا پس‌اندازت داری بپرس.
          </motion.p>
        </div>

        {/* 3. Bottom action area — sticky above tab bar */}
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.46 }}
            className="w-full max-w-full shrink-0 space-y-2 px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2 sm:space-y-3 md:pb-4"
        >
          {/* Budget onboarding card — only when no budget for current month */}
          {hasBudget === false && (
              <button
                  onClick={() => router.push("/budget")}
                  className="w-full flex items-center gap-3 bg-white rounded-2xl p-4 border border-gray-200/80 shadow-sm hover:shadow-md transition-shadow text-start"
              >
                <div className="w-9 h-9 rounded-full bg-[#2d1812] flex items-center justify-center shrink-0">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-[#2d1812] text-sm">بودجه ماهانه‌ات رو تنظیم کن</p>
                  <p className="text-xs text-gray-500 mt-0.5">برای مشاوره دقیق‌تر، بودجه‌ت رو وارد کن ←</p>
                </div>
              </button>
          )}

          {/* Suggested prompt chips — horizontal scroll, no scrollbar */}
          <div
              className="flex max-w-full gap-2 overflow-x-auto overscroll-x-contain pb-1 [-webkit-overflow-scrolling:touch] [&::-webkit-scrollbar]:hidden"
              style={{ scrollbarWidth: "none", msOverflowStyle: "none" } as React.CSSProperties}
          >
            {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                    key={prompt}
                    onClick={() => onPromptClick(prompt)}
                    className="shrink-0 text-xs bg-white border border-gray-200 text-[#2d1812] px-4 py-2 rounded-full shadow-sm hover:shadow-md hover:border-gray-300 transition-all whitespace-nowrap"
                >
                  {prompt}
                </button>
            ))}
          </div>

          {/* Text input bar */}
          <div className="flex w-full min-w-0 items-center gap-2">
            <button
                onClick={onSend}
                disabled={!input.trim() || streaming}
                className="flex-shrink-0 w-10 h-10 rounded-full bg-[#2d1812] text-white flex items-center justify-center disabled:opacity-30 hover:bg-[#3d2218] transition-colors"
            >
              <ArrowUp className="w-4 h-4" />
            </button>

            <input
                value={input}
                onChange={(e) => onInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
                placeholder="از من بپرس..."
                disabled={streaming}
                className="min-w-0 flex-1 rounded-full border border-gray-200 bg-white px-5 py-3 text-sm text-[#2d1812] shadow-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#2d1812]/20"
            />

            <button
                onClick={onVoiceModeClick}
                className="flex-shrink-0 w-10 h-10 rounded-full bg-white border border-gray-200 shadow-sm text-gray-500 flex items-center justify-center hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
            >
              <Mic className="w-4 h-4" />
            </button>
          </div>
        </motion.div>
      </div>
  );
}
