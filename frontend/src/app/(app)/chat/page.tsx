"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Send, Bot, User, Trash2, Mic, MicOff, X, ArrowUp } from "lucide-react";
import ChatEmptyState from "@/components/chat/ChatEmptyState";

interface Message { id?: number; role: "user" | "assistant"; content: string; }

const BAR_COUNT = 28;

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br/>");
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

function MessageBubble({ message, isStreaming }: { message: Message; isStreaming?: boolean }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-2 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <Avatar className="h-7 w-7 shrink-0">
        <AvatarFallback className={isUser ? "bg-[#2d1812] text-white" : "bg-emerald-100 text-emerald-700"}>
          {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </AvatarFallback>
      </Avatar>
      <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
        isUser
          ? "bg-[#2d1812] text-white rounded-tr-sm"
          : "bg-white text-[#2d1812] rounded-tl-sm shadow-sm border border-gray-100"
      }`}>
        <SimpleMarkdown text={message.content} />
        {isStreaming && <span className="inline-block w-1.5 h-3.5 bg-current animate-pulse ms-0.5 align-text-bottom" />}
      </div>
    </motion.div>
  );
}

function WaveformVisualizer({ bars }: { bars: number[] }) {
  return (
    <div className="flex items-center justify-center gap-[3px] h-16">
      {bars.map((h, i) => (
        <motion.div
          key={i}
          animate={{ scaleY: h }}
          transition={{ duration: 0.08, ease: "easeOut" }}
          className="w-[3px] rounded-full bg-emerald-500 origin-center"
          style={{ height: "40px" }}
        />
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [voiceMode, setVoiceMode] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSecs, setRecordingSecs] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [waveformBars, setWaveformBars] = useState<number[]>(Array(BAR_COUNT).fill(0.15));
  const [sendingVoice, setSendingVoice] = useState(false);
  const [hasBudget, setHasBudget] = useState<boolean | null>(null);

  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  const bottomRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    async function loadHistory() {
      try {
        const [histRes, budgetRes] = await Promise.allSettled([
          api.get("/chat/history"),
          api.get("/budgets/current"),
        ]);

        if (budgetRes.status === "fulfilled") {
          setHasBudget(!!budgetRes.value.data);
        } else {
          setHasBudget(false);
        }

        if (histRes.status === "fulfilled") {
          const rows = histRes.value.data.messages || [];
          const hist: Message[] = rows.slice().reverse().map((m: { role: string; content: string }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
          }));
          setMessages(hist);
        } else {
          setMessages([]);
        }
      } catch {
        setMessages([]);
        setHasBudget(false);
      } finally {
        setLoading(false);
      }
    }
    loadHistory();
  }, [user]);

  useEffect(() => { scrollToBottom(); }, [messages, streamingText, scrollToBottom]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecording(false);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function sendMessage(text?: string) {
    const userMsg = (text || input).trim();
    if (!userMsg || streaming) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setStreaming(true);
    setStreamingText("");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiBase}/chat/stream?content=${encodeURIComponent(userMsg)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok || !res.body) throw new Error("streaming failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let currentEventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (line.startsWith("event: ")) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") { currentEventType = ""; continue; }
            try {
              const parsed = JSON.parse(data);
              if (currentEventType === "complete") {
                // Replace accumulated with canonical processed text (confirmations appended, action blocks stripped)
                accumulated = parsed.text || parsed.content || accumulated;
                setStreamingText(accumulated);
              } else {
                accumulated += parsed.chunk || parsed.text || parsed.content || "";
                setStreamingText(accumulated);
              }
            } catch {
              if (currentEventType !== "complete") {
                accumulated += data;
                setStreamingText(accumulated);
              }
            }
            currentEventType = "";
          }
        }
      }

      if (accumulated) setMessages((prev) => [...prev, { role: "assistant", content: accumulated }]);
    } catch {
      try {
        const res = await api.post("/chat/message", { content: userMsg });
        setMessages((prev) => [...prev, { role: "assistant", content: res.data.reply || "پاسخی دریافت نشد" }]);
      } catch {
        toast.error("خطا در ارسال پیام");
        setMessages((prev) => [...prev, { role: "assistant", content: "متأسفم، مشکلی پیش آمده. دوباره تلاش کنید." }]);
      }
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  }

  function animateWaveform() {
    if (!analyserRef.current) return;
    const analyser = analyserRef.current;
    const buf = new Uint8Array(analyser.frequencyBinCount);
    function frame() {
      analyser.getByteFrequencyData(buf);
      const step = Math.floor(buf.length / BAR_COUNT);
      const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
        const val = buf[i * step] / 255;
        return Math.max(0.08, val);
      });
      setWaveformBars(bars);
      animFrameRef.current = requestAnimationFrame(frame);
    }
    frame();
  }

  function animateRandomWaveform() {
    let phase = 0;
    function frame() {
      phase += 0.15;
      const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
        const base = 0.1 + 0.6 * Math.abs(Math.sin((i / BAR_COUNT) * Math.PI + phase));
        return base + (Math.random() - 0.5) * 0.1;
      });
      setWaveformBars(bars);
      animFrameRef.current = requestAnimationFrame(frame);
    }
    frame();
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      try {
        const ctx = new AudioContext();
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        analyserRef.current = analyser;
        animateWaveform();
      } catch {
        animateRandomWaveform();
      }

      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioBlob(blob);
      };
      mr.start(100);
      mediaRecorderRef.current = mr;

      setRecording(true);
      setRecordingSecs(0);
      setAudioBlob(null);
      timerRef.current = setInterval(() => setRecordingSecs((s) => s + 1), 1000);
    } catch {
      toast.error("دسترسی به میکروفون رد شد");
    }
  }

  function stopRecording(keepBlob = true) {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (animFrameRef.current) { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = 0; }
    analyserRef.current = null;
    setWaveformBars(Array(BAR_COUNT).fill(0.15));

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setRecording(false);
    if (!keepBlob) setAudioBlob(null);
  }

  async function sendVoice() {
    if (!audioBlob) return;
    setSendingVoice(true);
    try {
      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.webm");
      const res = await api.post("/chat/voice", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const { transcript, reply } = res.data;
      if (transcript) setMessages((prev) => [...prev, { role: "user", content: `🎤 ${transcript}` }]);
      if (reply) setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      cancelVoice();
    } catch {
      toast.error("خطا در ارسال صدا");
    } finally {
      setSendingVoice(false);
    }
  }

  function cancelVoice() {
    stopRecording(false);
    setVoiceMode(false);
    setAudioBlob(null);
  }

  async function clearHistory() {
    try {
      await api.delete("/chat/history");
      setMessages([]);
      toast.success("تاریخچه پاک شد");
    } catch {
      toast.error("خطا در پاک کردن تاریخچه");
    }
  }

  const firstName = user?.first_name || user?.name || "";
  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  // Loading state
  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden" dir="rtl">
        <div className="shrink-0 h-[57px] border-b bg-white/80" />
        <div className="flex-1 overflow-y-auto px-4 py-4 bg-[#f5f1eb]/40">
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14 rounded-2xl" />)}
          </div>
        </div>
      </div>
    );
  }

  // Empty state — no messages, not in voice mode
  if (messages.length === 0 && !voiceMode) {
    return (
      <ChatEmptyState
        firstName={firstName}
        hasBudget={hasBudget}
        input={input}
        onInputChange={setInput}
        onSend={() => sendMessage()}
        onPromptClick={(text) => sendMessage(text)}
        onVoiceModeClick={() => { setVoiceMode(true); setAudioBlob(null); }}
        streaming={streaming}
      />
    );
  }

  // Normal chat layout (messages exist, or voice mode active)
  return (
    <div className="flex flex-col h-[calc(100dvh-4rem)] md:h-[calc(100dvh-2rem)] " dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-white/80 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100">
            <Bot className="h-4.5 w-4.5 text-emerald-600" />
          </div>
          <div>
            <p className="font-bold text-[#2d1812] text-sm">دستیار مالی</p>
            <p className="text-[11px] text-gray-400">جیبیار · آنلاین</p>
          </div>
        </div>
        <button onClick={clearHistory} className="p-2 rounded-full hover:bg-gray-100 transition-colors">
          <Trash2 className="h-4 w-4 text-gray-400" />
        </button>
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-[#f5f1eb]/40">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {streaming && streamingText && (
          <MessageBubble message={{ role: "assistant", content: streamingText }} isStreaming />
        )}
        {streaming && !streamingText && (
          <div className="flex gap-2">
            <Avatar className="h-7 w-7 shrink-0">
              <AvatarFallback className="bg-emerald-100 text-emerald-700"><Bot className="h-3.5 w-3.5" /></AvatarFallback>
            </Avatar>
            <div className="flex items-center gap-1 bg-white rounded-2xl rounded-tl-sm px-4 py-2.5 shadow-sm border border-gray-100">
              {[0, 150, 300].map((d) => (
                <span key={d} className="h-2 w-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: `${d}ms` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 px-4 pb-4 pt-2 bg-white border-t border-gray-100">
        <AnimatePresence mode="wait">
          {!voiceMode ? (
            /* TEXT MODE */
            <motion.div
              key="text"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="flex items-end gap-2"
            >
              <button
                onClick={() => sendMessage()}
                disabled={!input.trim() || streaming}
                className="flex-shrink-0 w-10 h-10 rounded-full bg-[#2d1812] text-white flex items-center justify-center disabled:opacity-30 hover:bg-[#3d2218] transition-colors"
              >
                <ArrowUp className="w-4 h-4" />
              </button>

              <div className="flex-1 relative">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                  placeholder="از من بپرس..."
                  disabled={streaming}
                  className="w-full rounded-2xl bg-gray-100 border-0 px-4 py-3 text-sm text-[#2d1812] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#2d1812]/20 resize-none"
                />
              </div>

              <button
                onClick={() => { setVoiceMode(true); setAudioBlob(null); }}
                className="flex-shrink-0 w-10 h-10 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center hover:bg-emerald-100 hover:text-emerald-600 transition-colors"
              >
                <Mic className="w-4 h-4" />
              </button>
            </motion.div>
          ) : (
            /* VOICE MODE */
            <motion.div
              key="voice"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="space-y-3"
            >
              <WaveformVisualizer bars={waveformBars} />

              <p className="text-center text-xs text-gray-500">
                {recording
                  ? `در حال ضبط… ${formatTime(recordingSecs)}`
                  : audioBlob
                  ? "ضبط متوقف شد — ارسال یا لغو؟"
                  : "روی دکمه بزن تا ضبط شروع شه"}
              </p>

              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={cancelVoice}
                  className="w-10 h-10 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center hover:bg-gray-200 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>

                <button
                  onClick={recording ? () => stopRecording(true) : startRecording}
                  className={`w-16 h-16 rounded-full flex items-center justify-center shadow-lg transition-all active:scale-95 ${
                    recording
                      ? "bg-red-500 hover:bg-red-600 text-white animate-pulse"
                      : "bg-emerald-500 hover:bg-emerald-600 text-white"
                  }`}
                >
                  {recording ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                </button>

                {audioBlob ? (
                  <button
                    onClick={sendVoice}
                    disabled={sendingVoice}
                    className="w-10 h-10 rounded-full bg-[#2d1812] text-white flex items-center justify-center hover:bg-[#3d2218] disabled:opacity-40 transition-colors"
                  >
                    {sendingVoice
                      ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      : <Send className="w-4 h-4" />
                    }
                  </button>
                ) : (
                  <div className="w-10 h-10" />
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
