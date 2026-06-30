"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import BgImageScreen from "@/components/onboarding/BgImageScreen";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { onboardingDraft } from "@/hooks/useOnboardingDraft";
import { introDraft } from "@/hooks/useIntroDraft";

const CELEBRATION_IMAGE = "https://images.unsplash.com/photo-1530021232320-687d8e3dba54?w=900&q=80";

const EMOJI_PARTICLES = ["🎉", "✨", "🌟", "💫", "🎊", "⭐", "🥳"];

const PARTICLES = Array.from({ length: 20 }, (_, i) => ({
  id: i,
  emoji: EMOJI_PARTICLES[i % EMOJI_PARTICLES.length],
  x: (i * 37) % 100,
  delay: ((i * 13) % 8) / 10,
  duration: 1.2 + ((i * 17) % 10) / 10,
}));

function ConfettiParticles() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-20">
      {PARTICLES.map((p) => (
        <motion.div
          key={p.id}
          initial={{ y: "-10%", x: `${p.x}vw`, opacity: 1, scale: 0.5 }}
          animate={{ y: "110vh", opacity: [1, 1, 0], scale: [0.5, 1.2, 0.8] }}
          transition={{ delay: p.delay, duration: p.duration, ease: "easeIn" }}
          className="absolute text-2xl"
          style={{ left: `${p.x}%` }}
        >
          {p.emoji}
        </motion.div>
      ))}
    </div>
  );
}

export default function OnboardingWelcomePage() {
  const router = useRouter();
  const { token, user, setOnboardingCompleted } = useAuthStore();
  const { locale, dict } = useLocale();
  const [loading, setLoading] = useState(false);
  const [showParticles, setShowParticles] = useState(true);

  useEffect(() => {
    if (!token) router.replace(`/${locale}/login`);
    const timer = setTimeout(() => setShowParticles(false), 3000);
    return () => clearTimeout(timer);
  }, [token, router, locale]);

  async function handleStart() {
    setLoading(true);
    try {
      await api.post("/onboarding/complete");
      if (user?.id) {
        onboardingDraft.clear(user.id);
        introDraft.clear(user.id);
      }
      setOnboardingCompleted(true);
      router.replace(`/${locale}/chat`);
    } catch {
      setLoading(false);
    }
  }

  const firstName = user?.first_name || user?.name || "";
  const titleText = firstName
    ? tDict(dict, "onboarding.welcomePage.titleWithName", { name: firstName })
    : tDict(dict, "onboarding.welcomePage.titleNoName");

  return (
    <>
      {showParticles && <ConfettiParticles />}

      <BgImageScreen imageUrl={CELEBRATION_IMAGE}>
        <div className="space-y-6">
          <motion.div
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.4, ease: "easeOut" }}
            className="space-y-3"
          >
            <h1 className="text-4xl font-[800] text-white leading-tight tracking-tight whitespace-pre-line">
              {titleText}
            </h1>
            <p className="text-base text-white/80 leading-relaxed">
              {dict.onboarding.welcomePage.subtitle}
            </p>
          </motion.div>

          <motion.button
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.4, ease: "easeOut" }}
            onClick={handleStart}
            disabled={loading}
            className="w-full py-4 rounded-full bg-white text-[#2d1812] font-semibold text-base disabled:opacity-60 hover:bg-white/90 active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-lg"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {dict.onboarding.welcomePage.startButton}
          </motion.button>
        </div>
      </BgImageScreen>
    </>
  );
}
