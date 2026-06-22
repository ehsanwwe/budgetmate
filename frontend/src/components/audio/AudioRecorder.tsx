"use client";
import { useCallback } from "react";
import { Mic, Square, X, Send, RotateCcw } from "lucide-react";
import AudioWaveform from "./AudioWaveform";
import { useAudioRecorder, type RecorderError } from "@/hooks/useAudioRecorder";

interface RecorderDict {
  recordButton: string;
  stopButton: string;
  cancelButton: string;
  uploading: string;
}

interface Props {
  onSend: (blob: Blob, mimeType: string, durationSeconds: number) => Promise<void>;
  uploading?: boolean;
  dict: RecorderDict;
}

function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function errorLabel(err: RecorderError | null): string {
  switch (err) {
    case "unsupported": return "مرورگر از ضبط صدا پشتیبانی نمی‌کند";
    case "permission_denied": return "دسترسی به میکروفون داده نشد";
    case "no_microphone": return "میکروفونی یافت نشد";
    default: return "خطا در ضبط صدا";
  }
}

export default function AudioRecorder({ onSend, uploading = false, dict }: Props) {
  const { state, error, elapsedSeconds, audioBlob, analyserNode, start, stop, cancel, reset } =
    useAudioRecorder();

  const handleSend = useCallback(async () => {
    if (!audioBlob) return;
    const mime = audioBlob.type || "audio/webm";
    await onSend(audioBlob, mime, elapsedSeconds);
  }, [audioBlob, elapsedSeconds, onSend]);

  if (state === "error") {
    return (
      <div className="rounded-[14px] border border-red-100 bg-red-50 px-4 py-3 text-center">
        <p className="mb-2 text-[12px] text-red-600">{errorLabel(error)}</p>
        <button
          onClick={reset}
          className="mx-auto flex items-center gap-1 text-[11px] text-red-500 hover:text-red-700"
        >
          <RotateCcw className="h-3 w-3" />
          تلاش مجدد
        </button>
      </div>
    );
  }

  if (state === "idle" || state === "requesting") {
    return (
      <button
        onClick={start}
        disabled={state === "requesting" || uploading}
        className="flex h-11 w-full items-center justify-center gap-2 rounded-[14px] border border-[#2d1812]/15 bg-white/60 text-[12px] font-medium text-[#2d1812]/70 transition hover:border-[#2d1812]/30 hover:bg-white disabled:opacity-50"
      >
        <Mic className="h-4 w-4 text-[#10b981]" />
        {state === "requesting" ? "در حال اتصال..." : dict.recordButton}
      </button>
    );
  }

  if (state === "recording") {
    return (
      <div className="space-y-2 rounded-[14px] border border-[#10b981]/30 bg-white/70 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
            <span className="font-mono text-[11px] text-[#2d1812]/70">{formatSeconds(elapsedSeconds)}</span>
          </div>
          <button
            onClick={cancel}
            className="flex items-center gap-1 text-[11px] text-[#2d1812]/45 hover:text-red-500"
          >
            <X className="h-3.5 w-3.5" />
            {dict.cancelButton}
          </button>
        </div>
        <AudioWaveform analyserNode={analyserNode} isActive={true} />
        <button
          onClick={stop}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-[12px] bg-[#2d1812] text-[12px] font-medium text-white"
        >
          <Square className="h-3.5 w-3.5 fill-white" />
          {dict.stopButton}
        </button>
      </div>
    );
  }

  if (state === "stopped" && audioBlob) {
    return (
      <div className="space-y-2 rounded-[14px] border border-[#2d1812]/10 bg-white/70 p-3">
        <audio src={URL.createObjectURL(audioBlob)} controls className="h-8 w-full" />
        <div className="flex gap-2">
          <button
            onClick={reset}
            disabled={uploading}
            className="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-[12px] border border-[#2d1812]/15 text-[11px] text-[#2d1812]/60 hover:bg-white/80 disabled:opacity-50"
          >
            <RotateCcw className="h-3 w-3" />
            {dict.cancelButton}
          </button>
          <button
            onClick={handleSend}
            disabled={uploading}
            className="flex h-9 flex-[2] items-center justify-center gap-1.5 rounded-[12px] bg-[#10b981] text-[12px] font-medium text-white disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
            {uploading ? dict.uploading : "ارسال صدا"}
          </button>
        </div>
      </div>
    );
  }

  return null;
}
