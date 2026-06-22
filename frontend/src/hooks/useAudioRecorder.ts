"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "requesting" | "recording" | "stopped" | "error";
export type RecorderError = "unsupported" | "permission_denied" | "no_microphone" | "unknown";

export interface UseAudioRecorderReturn {
  state: RecorderState;
  error: RecorderError | null;
  elapsedSeconds: number;
  audioBlob: Blob | null;
  analyserNode: AnalyserNode | null;
  start: () => Promise<void>;
  stop: () => void;
  cancel: () => void;
  reset: () => void;
}

const MIME_PREFERENCE = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
  "audio/mpeg",
];

function getSupportedMime(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  for (const mime of MIME_PREFERENCE) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return null;
}

export function useAudioRecorder(): UseAudioRecorderReturn {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<RecorderError | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function cleanup() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setAnalyserNode(null);
  }

  useEffect(() => () => cleanup(), []);

  const start = useCallback(async () => {
    if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
      setError("unsupported");
      setState("error");
      return;
    }
    const mime = getSupportedMime();
    if (!mime) {
      setError("unsupported");
      setState("error");
      return;
    }

    setState("requesting");
    setError(null);
    setAudioBlob(null);
    setElapsedSeconds(0);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ctx = new AudioContext();
      audioContextRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      setAnalyserNode(analyser);

      const recorder = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime });
        setAudioBlob(blob);
        cleanup();
        setState("stopped");
      };
      recorder.start(250);
      setState("recording");

      timerRef.current = setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } catch (err: unknown) {
      cleanup();
      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          setError("permission_denied");
        } else if (err.name === "NotFoundError") {
          setError("no_microphone");
        } else {
          setError("unknown");
        }
      } else {
        setError("unknown");
      }
      setState("error");
    }
  }, []);

  const stop = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      mediaRecorderRef.current.stop();
    }
  }, []);

  const cancel = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.ondataavailable = null;
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    cleanup();
    setAudioBlob(null);
    setElapsedSeconds(0);
    chunksRef.current = [];
    setState("idle");
    setError(null);
  }, []);

  const reset = useCallback(() => {
    cleanup();
    setAudioBlob(null);
    setElapsedSeconds(0);
    chunksRef.current = [];
    setState("idle");
    setError(null);
  }, []);

  return { state, error, elapsedSeconds, audioBlob, analyserNode, start, stop, cancel, reset };
}
