"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Play, FileText, Mic } from "lucide-react";
import OnboardingLayout from "@/components/onboarding/OnboardingLayout";
import AudioRecorder from "@/components/audio/AudioRecorder";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { t as tDict } from "@/i18n/getDictionary";
import { introDraft } from "@/hooks/useIntroDraft";

const VIDEO_URL = process.env.NEXT_PUBLIC_INTRO_VIDEO_URL ?? "";

export default function OnboardingIntroPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const userId = useAuthStore((s) => s.user?.id);
  const { locale, dict } = useLocale();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const t = (dict.onboarding as any).introPage as Record<string, string>;

  const [text, setText] = useState("");
  const [audioTranscript, setAudioTranscript] = useState("");
  const [audioDuration, setAudioDuration] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Auth guard
  useEffect(() => {
    if (!token) router.replace(`/${locale}/login`);
  }, [token, router, locale]);

  // Restore draft on mount (async to satisfy react-hooks/set-state-in-effect)
  useEffect(() => {
    if (!userId) return;
    queueMicrotask(() => {
      const draft = introDraft.read(userId);
      if (draft.text) setText(draft.text);
      if (draft.audioTranscript) setAudioTranscript(draft.audioTranscript);
      if (draft.audioDurationSeconds !== null) setAudioDuration(draft.audioDurationSeconds);
    });
  }, [userId]);

  // Save text to draft on change
  useEffect(() => {
    if (!userId) return;
    introDraft.save(userId, { text });
  }, [userId, text]);

  const handleAudioSend = useCallback(
    async (blob: Blob, mimeType: string, durationSeconds: number) => {
      setUploading(true);
      setAudioError(false);
      try {
        const ext = mimeType.includes("ogg") ? "ogg" : mimeType.includes("mp4") ? "mp4" : "webm";
        const formData = new FormData();
        formData.append("file", blob, `audio.${ext}`);
        formData.append("duration_seconds", String(durationSeconds));
        const res = await api.post("/onboarding/intro/audio", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        const transcript: string = res.data?.transcript ?? "";
        setAudioTranscript(transcript);
        setAudioDuration(durationSeconds);
        if (userId) introDraft.save(userId, { audioTranscript: transcript, audioDurationSeconds: durationSeconds });
      } catch {
        setAudioError(true);
      } finally {
        setUploading(false);
      }
    },
    [userId]
  );

  function determineSource(): "text" | "audio" | "mixed" | null {
    const hasText = text.trim().length > 0;
    const hasAudio = audioTranscript.trim().length > 0;
    if (hasText && hasAudio) return "mixed";
    if (hasText) return "text";
    if (hasAudio) return "audio";
    return null;
  }

  async function handleContinue() {
    setSaveError("");
    setSaving(true);
    try {
      await api.post("/onboarding/intro", {
        text: text.trim() || null,
        audio_transcript: audioTranscript.trim() || null,
        audio_duration_seconds: audioDuration,
        source: determineSource(),
      });
      if (userId) introDraft.clear(userId);
      router.push(`/${locale}/onboarding/agreement`);
    } catch {
      setSaveError(t.saveFailed ?? "خطا در ذخیره. لطفاً دوباره تلاش کن");
    } finally {
      setSaving(false);
    }
  }

  function handleSkip() {
    if (userId) introDraft.clear(userId);
    router.push(`/${locale}/onboarding/agreement`);
  }

  return (
    <OnboardingLayout
      backHref={`/${locale}/onboarding/profile`}
      totalSteps={5}
      currentStep={2}
      showBack={true}
    >
      <motion.div
        initial={{ y: 12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1, duration: 0.25 }}
        className="mb-3 space-y-1 sm:mb-4 sm:space-y-1.5"
      >
        <p className="text-[11px] font-semibold text-[#2d1812]/45 sm:text-xs">
          {tDict(dict, "onboarding.profilePage.stepIndicator", { current: 2, total: 5 })}
        </p>
        <h1 className="text-[20px] font-[800] leading-tight tracking-[-0.02em] text-[#2d1812] sm:text-[24px]">
          {t.title ?? "خودت را به BudgetMate معرفی کن"}
        </h1>
        <p className="max-w-[340px] text-[12px] leading-5 text-gray-500 sm:text-[13px] sm:leading-6">
          {t.subtitle ?? "هر چیزی که روی تصمیم‌های مالی‌ات اثر دارد بنویس یا با صدا بگو."}
        </p>
      </motion.div>

      <motion.div
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.18, duration: 0.25 }}
        className="min-h-0 flex-1 overflow-y-auto pb-2 sm:pb-3"
      >
        <div className="space-y-3">
          {/* Video card */}
          <div className="overflow-hidden rounded-[18px] border border-[#2d1812]/10 bg-white/60 shadow-[0_8px_24px_rgba(45,24,18,0.06)]">
            {VIDEO_URL ? (
              <video
                src={VIDEO_URL}
                controls
                playsInline
                className="w-full"
                style={{ maxHeight: 200 }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 px-4 py-8">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#2d1812]/8">
                  <Play className="h-6 w-6 text-[#2d1812]/50" />
                </div>
                <p className="text-[13px] font-semibold text-[#2d1812]">
                  {t.videoTitle ?? "یک دقیقه وقت بگذار"}
                </p>
                <p className="text-center text-[11px] leading-5 text-gray-400">
                  {t.videoDescription ?? "ببین چطور می‌تونم بهت کمک کنم"}
                </p>
              </div>
            )}
          </div>

          {/* Text card */}
          <div className="rounded-[18px] border border-[#2d1812]/10 bg-white/60 p-4 shadow-[0_8px_24px_rgba(45,24,18,0.06)]">
            <div className="mb-2 flex items-center gap-2">
              <FileText className="h-4 w-4 text-[#2d1812]/50" />
              <h2 className="text-[13px] font-bold text-[#2d1812]">
                {t.textTitle ?? "خودت را معرفی کن"}
              </h2>
              <span className="ml-auto text-[10px] text-gray-400">{t.optional ?? "اختیاری"}</span>
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                t.textPlaceholder ??
                "مثلاً: من آدم ولخرجی هستم، وقتی استرس دارم خرید می‌کنم، درآمدم نامنظم است..."
              }
              rows={4}
              className="w-full resize-none rounded-[12px] border border-[#2d1812]/10 bg-white px-3 py-2.5 text-[12px] leading-6 text-[#2d1812] outline-none transition placeholder:text-gray-300 focus:border-[#2d1812]/25 focus:ring-2 focus:ring-[#2d1812]/5 sm:text-[13px]"
            />
          </div>

          {/* Audio card */}
          <div className="rounded-[18px] border border-[#2d1812]/10 bg-white/60 p-4 shadow-[0_8px_24px_rgba(45,24,18,0.06)]">
            <div className="mb-2 flex items-center gap-2">
              <Mic className="h-4 w-4 text-[#10b981]" />
              <h2 className="text-[13px] font-bold text-[#2d1812]">
                {t.audioTitle ?? "یا با صدا بگو"}
              </h2>
              <span className="ml-auto text-[10px] text-gray-400">{t.optional ?? "اختیاری"}</span>
            </div>
            <p className="mb-3 text-[11px] leading-5 text-gray-400">
              {t.audioDescription ?? "اگر راحت‌تری، می‌تونی ضبط صدا کنی"}
            </p>

            <AudioRecorder
              onSend={handleAudioSend}
              uploading={uploading}
              dict={{
                recordButton: t.recordButton ?? "شروع ضبط",
                stopButton: t.stopButton ?? "پایان ضبط",
                cancelButton: t.cancelButton ?? "لغو",
                uploading: t.uploading ?? "در حال بارگذاری...",
              }}
            />

            {audioError && (
              <p className="mt-2 text-[11px] text-amber-600">
                {t.audioFailedNotice ?? "آپلود صدا با خطا مواجه شد؛ می‌تونی ادامه بدی"}
              </p>
            )}

            {audioTranscript && !audioError && (
              <div className="mt-3 rounded-[10px] border border-[#10b981]/20 bg-[#10b981]/5 p-2.5">
                <p className="mb-1 text-[10px] font-semibold text-[#10b981]/80">
                  {t.transcriptTitle ?? "متن ضبط شده"}
                </p>
                <p className="text-[11px] leading-5 text-[#2d1812]/80">{audioTranscript}</p>
              </div>
            )}

            {!audioTranscript && !audioError && uploading === false && (
              <p className="mt-2 text-[10px] text-gray-400">
                {t.emptyTranscriptNotice ?? ""}
              </p>
            )}
          </div>
        </div>
      </motion.div>

      {/* Footer */}
      <div className="shrink-0 border-t border-[#2d1812]/5 bg-[#f5f1eb] pt-2 pb-1.5 sm:pt-3 sm:pb-2">
        {saveError && (
          <p className="mb-2 rounded-[12px] border border-red-100 bg-red-50 px-3 py-1.5 text-[11px] text-red-600 sm:text-[12px]">
            {saveError}
          </p>
        )}
        <div className="flex gap-2">
          <button
            onClick={handleSkip}
            disabled={saving}
            className="flex h-10 flex-1 items-center justify-center rounded-[14px] border border-[#2d1812]/15 text-[12px] font-medium text-[#2d1812]/55 transition hover:bg-white/50 disabled:opacity-40 sm:h-12 sm:rounded-[18px]"
          >
            {t.skipButton ?? "رد کردن"}
          </button>
          <button
            onClick={handleContinue}
            disabled={saving || uploading}
            className="flex h-10 flex-[2] items-center justify-center gap-2 rounded-[14px] bg-[#2d1812] text-[13px] font-semibold text-white shadow-[0_10px_22px_rgba(45,24,18,0.14)] transition-all hover:bg-[#3d2218] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 sm:h-12 sm:rounded-[18px] sm:text-sm"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {t.nextButton ?? "ادامه"}
          </button>
        </div>
      </div>
    </OnboardingLayout>
  );
}
