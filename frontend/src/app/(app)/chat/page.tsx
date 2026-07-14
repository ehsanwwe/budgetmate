"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useChatStore } from "@/store/chat";
import type { Message } from "@/store/chat";
import { useLocale } from "@/i18n/LocaleContext";
import { t } from "@/i18n/getDictionary";
import type { Dictionary } from "@/i18n/getDictionary";
import { getDirection } from "@/i18n/config";
import type { Locale } from "@/i18n/config";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Send, Bot, User, Trash2, Mic, MicOff, X, ArrowUp, Check, Copy, Pencil, RotateCcw } from "lucide-react";
import ChatEmptyState from "@/components/chat/ChatEmptyState";

const BAR_COUNT = 28;

interface StreamResult {
  text: string;
  userMessageId?: number;
  assistantMessageId?: number;
}

async function readChatStream(
  response: Response,
  onText: (text: string) => void,
  onMetadata?: (userMessageId: number) => void,
): Promise<StreamResult> {
  if (!response.body) throw new Error("streaming failed");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let accumulated = "";
  let userMessageId: number | undefined;
  let assistantMessageId: number | undefined;

  function processEvent(rawEvent: string) {
    if (!rawEvent.trim()) return;
    let eventType = "message";
    const dataLines: string[] = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) eventType = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    const data = dataLines.join("\n").trim();
    if (!data || data === "[DONE]") return;

    const parsed = JSON.parse(data) as {
      chunk?: string;
      text?: string;
      content?: string;
      user_message_id?: number;
      assistant_message_id?: number;
    };
    if (eventType === "error") throw new Error("generation failed");
    if (eventType === "metadata") {
      if (parsed.user_message_id) {
        userMessageId = parsed.user_message_id;
        onMetadata?.(parsed.user_message_id);
      }
      return;
    }
    if (eventType === "complete") {
      accumulated = parsed.text || parsed.content || accumulated;
      assistantMessageId = parsed.assistant_message_id;
      onText(accumulated);
      return;
    }
    const chunk = parsed.chunk || parsed.text || parsed.content || "";
    if (chunk) {
      accumulated += chunk;
      onText(accumulated);
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      processEvent(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) processEvent(buffer);
  return { text: accumulated, userMessageId, assistantMessageId };
}

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/\n/g, "<br/>");
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

interface MessageBubbleProps {
  message: Message;
  dict: Dictionary;
  dir: "rtl" | "ltr";
  isStreaming?: boolean;
  copied?: boolean;
  isEditing?: boolean;
  editDraft?: string;
  editSubmitting?: boolean;
  onCopy?: () => void;
  onEdit?: () => void;
  onEditDraftChange?: (value: string) => void;
  onEditSend?: () => void;
  onEditCancel?: () => void;
  onRetry?: () => void;
}

function InlineMessageEditor({
  value,
  dir,
  dict,
  submitting,
  onChange,
  onSend,
  onCancel,
}: {
  value: string;
  dir: "rtl" | "ltr";
  dict: Dictionary;
  submitting: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 320)}px`;
  }, [value]);

  return (
    <div
      className="w-full min-w-[min(72vw,22rem)] rounded-2xl rounded-se-sm bg-[#2d1812] p-3 text-white"
      aria-label={t(dict, "chat.editingMessage")}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
        dir={dir}
        rows={1}
        disabled={submitting}
        aria-label={t(dict, "chat.editingMessage")}
        className="max-h-80 min-h-20 w-full resize-none overflow-y-auto rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-start text-sm leading-relaxed text-white outline-none focus:ring-2 focus:ring-white/30 disabled:opacity-70"
      />
      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-full px-3 py-1.5 text-xs text-white/80 transition-colors hover:bg-white/10 disabled:opacity-50"
        >
          {t(dict, "chat.cancel")}
        </button>
        <button
          type="button"
          onClick={onSend}
          disabled={!value.trim() || submitting}
          className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-[#2d1812] transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t(dict, "chat.send")}
        </button>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  dict,
  dir,
  isStreaming,
  copied,
  isEditing,
  editDraft = "",
  editSubmitting = false,
  onCopy,
  onEdit,
  onEditDraftChange,
  onEditSend,
  onEditCancel,
  onRetry,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const avatar = (
    <Avatar className="h-7 w-7 shrink-0">
      <AvatarFallback className={isUser ? "bg-[#2d1812] text-white" : "bg-emerald-100 text-emerald-700"}>
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </AvatarFallback>
    </Avatar>
  );

  return (
      <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="flex w-full"
          dir={dir}
      >
        <div className={`flex max-w-[86%] items-start gap-2 ${isUser ? "ms-auto" : "me-auto"}`}>
          {!isUser && avatar}
          <div className="min-w-0">
            {isEditing ? (
              <InlineMessageEditor
                value={editDraft}
                dir={dir}
                dict={dict}
                submitting={editSubmitting}
                onChange={onEditDraftChange!}
                onSend={onEditSend!}
                onCancel={onEditCancel!}
              />
            ) : (
              <div
                  dir={dir}
                  className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-start text-sm leading-relaxed ${
                      isUser
                          ? "rounded-se-sm bg-[#2d1812] text-white"
                          : "rounded-ss-sm border border-gray-100 bg-white text-[#2d1812] shadow-sm"
                  }`}
              >
                <SimpleMarkdown text={message.content} />
                {isStreaming && <span className="ms-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-current align-text-bottom" />}
              </div>
            )}
            {!isStreaming && !isEditing && (
              <div className={`flex min-h-7 items-center gap-1 pt-1 ${isUser ? "justify-end" : "justify-start"}`}>
                <button
                  type="button"
                  onClick={onCopy}
                  aria-label={copied ? t(dict, "chat.copied") : t(dict, "chat.copy")}
                  title={copied ? t(dict, "chat.copied") : t(dict, "chat.copy")}
                  className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-[11px] text-gray-400 transition-colors hover:bg-black/5 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied && <span>{t(dict, "chat.copied")}</span>}
                </button>
                {isUser && (
                  <button
                    type="button"
                    onClick={onEdit}
                    disabled={!message.id || editSubmitting}
                    aria-label={t(dict, "chat.edit")}
                    title={t(dict, "chat.edit")}
                    className="inline-flex min-h-8 items-center rounded-md px-2 text-gray-400 transition-colors hover:bg-black/5 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-[11px] text-gray-500 transition-colors hover:bg-black/5 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    <span>{t(dict, "chat.retry")}</span>
                  </button>
                )}
              </div>
            )}
          </div>
          {isUser && avatar}
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
  const { locale, dict } = useLocale();
  const dir = getDirection(locale as Locale);

  // Global chat state — persists across route navigation
  const {
    messages,
    streaming,
    streamingText,
    loading,
    hasBudget,
    scrollY,
    historyUserId,
    setMessages,
    addMessage,
    updateMessageId,
    editMessageAndTruncate,
    setStreaming,
    setStreamingText,
    setLoading,
    setHasBudget,
    setScrollY,
    setHistoryUserId,
  } = useChatStore();

  // Local UI state — ephemeral, fine to reset on navigation
  const [input, setInput] = useState("");
  const [voiceMode, setVoiceMode] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSecs, setRecordingSecs] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [waveformBars, setWaveformBars] = useState<number[]>(Array(BAR_COUNT).fill(0.15));
  const [sendingVoice, setSendingVoice] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [copiedMessageKey, setCopiedMessageKey] = useState<string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [retryEdit, setRetryEdit] = useState<{ messageId: number; content: string } | null>(null);

  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // Synchronous guard against double-submit (React state updates are async,
  // so checking `streaming` alone is not enough for rapid double presses).
  const sendingRef = useRef(false);
  const streamAbortRef = useRef<AbortController | null>(null);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tracks whether we have already done the one-time scroll restore this mount
  const skipNextAutoScrollRef = useRef(false);
  const shouldAutoScrollRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Load chat history only once per user session
  useEffect(() => {
    if (user?.id === historyUserId) return;

    async function loadHistory() {
      setLoading(true);
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
          const hist: Message[] = rows.slice().reverse().map((m: { id: number; role: string; content: string }) => ({
            id: m.id,
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
        setHistoryUserId(user?.id ?? null);
      }
    }
    loadHistory();
  }, [user]);

  // One-time scroll restoration when mounting on a return visit.
  // If streaming is active, jump to bottom so the user sees live output.
  // Otherwise restore the saved position from before navigation.
  useEffect(() => {
    if (loading) return;

    if (streaming) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" as ScrollBehavior });
    } else if (scrollY > 0 && messagesContainerRef.current) {
      skipNextAutoScrollRef.current = true;
      messagesContainerRef.current.scrollTop = scrollY;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // Auto-scroll to bottom when new content arrives.
  // Skips once after a scroll-restore to avoid overriding it.
  useEffect(() => {
    if (skipNextAutoScrollRef.current) {
      skipNextAutoScrollRef.current = false;
      return;
    }
    if (shouldAutoScrollRef.current) scrollToBottom();
  }, [messages, streamingText, scrollToBottom]);

  // Save scroll position when navigating away
  useEffect(() => {
    return () => {
      if (messagesContainerRef.current) {
        setScrollY(messagesContainerRef.current.scrollTop);
      }
    };
  }, [setScrollY]);

  // Cleanup audio resources on unmount — streaming fetch is intentionally NOT cancelled
  useEffect(() => {
    return () => {
      stopRecording(false);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, []);

  async function sendMessage(text?: string) {
    const userMsg = (text || input).trim();
    if (!userMsg || streaming || sendingRef.current) return;
    sendingRef.current = true;
    shouldAutoScrollRef.current = true;

    // Generate idempotency key — same key reused on stream + fallback POST.
    const clientMsgId = crypto.randomUUID();
    const controller = new AbortController();
    streamAbortRef.current = controller;

    setInput("");
    addMessage({ role: "user", content: userMsg, localId: clientMsgId });
    setStreaming(true);
    setStreamingText("");

    let backendResponded = false;
    let backendAcknowledged = false;

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const streamUrl = `${apiBase}/chat/stream?content=${encodeURIComponent(userMsg)}&client_message_id=${encodeURIComponent(clientMsgId)}`;
      const res = await fetch(streamUrl, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });

      if (!res.ok) throw new Error("streaming failed");
      const result = await readChatStream(
        res,
        (value) => {
          backendResponded = true;
          setStreamingText(value);
        },
        (userMessageId) => {
          backendAcknowledged = true;
          updateMessageId(clientMsgId, userMessageId);
        },
      );

      if (result.text) {
        addMessage({
          id: result.assistantMessageId,
          role: "assistant",
          content: result.text,
          localId: `assistant-${clientMsgId}`,
        });
      }
    } catch {
      if (controller.signal.aborted) return;
      if (!backendResponded && !backendAcknowledged) {
        try {
          const res = await api.post("/chat/message", { content: userMsg, client_message_id: clientMsgId });
          if (res.data.user_message_id) updateMessageId(clientMsgId, res.data.user_message_id);
          addMessage({
            id: res.data.assistant_message_id,
            role: "assistant",
            content: res.data.reply || t(dict, "chat.fallback"),
            localId: `assistant-${clientMsgId}`,
          });
        } catch {
          toast.error(t(dict, "chat.errorSend"));
          addMessage({ role: "assistant", content: t(dict, "chat.retryMessage"), localId: `send-error-${clientMsgId}` });
        }
      } else {
        toast.error(t(dict, "chat.connectionDropped"));
      }
    } finally {
      setStreaming(false);
      setStreamingText("");
      sendingRef.current = false;
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
    }
  }

  function messageKey(message: Message): string {
    return message.id ? `message-${message.id}` : `local-${message.localId}`;
  }

  async function copyMessage(message: Message) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(message.content);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = message.content;
        textarea.style.position = "fixed";
        textarea.style.insetInlineStart = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) throw new Error("copy failed");
      }
      setCopiedMessageKey(messageKey(message));
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = setTimeout(() => setCopiedMessageKey(null), 1800);
    } catch {
      toast.error(t(dict, "chat.copyFailed"));
    }
  }

  function beginEditing(message: Message) {
    if (!message.id || message.role !== "user") {
      toast.error(t(dict, "chat.messageCannotBeEdited"));
      return;
    }
    streamAbortRef.current?.abort();
    setRetryEdit(null);
    setEditingMessageId(message.id);
    setEditDraft(message.content);
  }

  function cancelEditing() {
    if (editSubmitting) return;
    setEditingMessageId(null);
    setEditDraft("");
  }

  async function submitEditedMessage(
    messageId = editingMessageId,
    content = editDraft,
  ) {
    if (!messageId || !content.trim() || editSubmitting || sendingRef.current) return;

    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    const clientMessageId = crypto.randomUUID();
    let backendAcknowledged = false;
    let cannotEdit = false;

    sendingRef.current = true;
    setEditSubmitting(true);
    setRetryEdit(null);
    setStreamingText("");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${apiBase}/chat/messages/${messageId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "Accept-Language": locale,
        },
        body: JSON.stringify({ content, client_message_id: clientMessageId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 422) {
          cannotEdit = true;
          toast.error(t(dict, "chat.messageCannotBeEdited"));
        }
        throw new Error(`edit failed: ${response.status}`);
      }

      backendAcknowledged = true;
      editMessageAndTruncate(messageId, content);
      setEditingMessageId(null);
      setEditDraft("");
      setStreaming(true);

      const result = await readChatStream(response, setStreamingText);
      if (result.text) {
        addMessage({
          id: result.assistantMessageId,
          role: "assistant",
          content: result.text,
          localId: `assistant-edit-${clientMessageId}`,
        });
      }
    } catch {
      if (controller.signal.aborted) return;
      if (backendAcknowledged) {
        setRetryEdit({ messageId, content });
        addMessage({
          role: "assistant",
          content: t(dict, "chat.retryMessage"),
          localId: `edit-error-${clientMessageId}`,
        });
      } else if (!cannotEdit) {
        toast.error(t(dict, "chat.editFailed"));
      }
    } finally {
      if (backendAcknowledged) {
        setStreaming(false);
        setStreamingText("");
      }
      setEditSubmitting(false);
      sendingRef.current = false;
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
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
      toast.error(t(dict, "chat.micDenied"));
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
      streamRef.current.getTracks().forEach((trk) => trk.stop());
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
      const voiceLocalId = crypto.randomUUID();
      if (transcript) addMessage({ id: res.data.user_message_id, role: "user", content: `🎤 ${transcript}`, localId: `voice-user-${voiceLocalId}` });
      if (reply) addMessage({ id: res.data.message_id, role: "assistant", content: reply, localId: `voice-assistant-${voiceLocalId}` });
      cancelVoice();
    } catch {
      toast.error(t(dict, "chat.voiceError"));
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
    if (clearingHistory) return;
    setClearingHistory(true);
    try {
      await api.delete("/chat/history");
      setMessages([]);
      setEditingMessageId(null);
      setEditDraft("");
      setRetryEdit(null);
      toast.success(t(dict, "chat.historyCleared"));
    } catch {
      toast.error(t(dict, "chat.historyClearError"));
    } finally {
      setClearingHistory(false);
    }
  }

  const firstName = user?.first_name || user?.name || "";
  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const recordingLabel = recording
    ? t(dict, "chat.recording").replace("{time}", formatTime(recordingSecs))
    : audioBlob
      ? t(dict, "chat.recordStopped")
      : t(dict, "chat.pressToRecord");

  // Loading state
  if (loading) {
    return (
        <div className="flex h-full min-h-0 flex-col overflow-hidden" dir={dir}>
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
      <div className="flex flex-col h-[calc(100dvh-4rem)] md:h-[calc(100dvh-2rem)]" dir={dir}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b bg-white/80 backdrop-blur-sm shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100">
              <Bot className="h-4.5 w-4.5 text-emerald-600" />
            </div>
            <div>
              <p className="font-bold text-[#2d1812] text-sm">{t(dict, "chat.assistantName")}</p>
              <p className="text-[11px] text-gray-400">{t(dict, "chat.appNameOnline")}</p>
            </div>
          </div>
          <button
              onClick={clearHistory}
              disabled={clearingHistory}
              aria-label={t(dict, "chat.clearHistory")}
              title={t(dict, "chat.clearHistory")}
              className="p-2 rounded-full hover:bg-gray-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Trash2 className="h-4 w-4 text-gray-400" />
          </button>
        </div>

        {/* Messages */}
        <div
            ref={messagesContainerRef}
            onScroll={(event) => {
              const element = event.currentTarget;
              shouldAutoScrollRef.current =
                element.scrollHeight - element.scrollTop - element.clientHeight < 120;
            }}
            className="min-h-0 flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-[#f5f1eb]/40"
        >
          {messages.map((msg) => (
              <MessageBubble
                key={messageKey(msg)}
                message={msg}
                dict={dict}
                dir={dir}
                copied={copiedMessageKey === messageKey(msg)}
                isEditing={msg.id === editingMessageId}
                editDraft={editDraft}
                editSubmitting={editSubmitting || streaming}
                onCopy={() => copyMessage(msg)}
                onEdit={() => beginEditing(msg)}
                onEditDraftChange={setEditDraft}
                onEditSend={() => submitEditedMessage()}
                onEditCancel={cancelEditing}
                onRetry={retryEdit && msg.localId?.startsWith("edit-error-")
                  ? () => submitEditedMessage(retryEdit.messageId, retryEdit.content)
                  : undefined}
              />
          ))}
          {streaming && streamingText && (
              <MessageBubble
                message={{ role: "assistant", content: streamingText, localId: "streaming-assistant" }}
                dict={dict}
                dir={dir}
                isStreaming
              />
          )}
          {streaming && !streamingText && (
              <div className="flex w-full" dir={dir} aria-label={t(dict, "chat.thinking")}>
                <div className="me-auto flex gap-2">
                  <Avatar className="h-7 w-7 shrink-0">
                    <AvatarFallback className="bg-emerald-100 text-emerald-700"><Bot className="h-3.5 w-3.5" /></AvatarFallback>
                  </Avatar>
                  <div className="flex items-center gap-1 rounded-2xl rounded-ss-sm border border-gray-100 bg-white px-4 py-2.5 shadow-sm">
                    {[0, 150, 300].map((d) => (
                        <span key={d} className="h-2 w-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
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
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key !== "Enter") return;
                          if (e.shiftKey) return;
                          e.preventDefault();
                          if (!input.trim() || streaming) return;
                          sendMessage();
                        }}
                        placeholder={t(dict, "chat.inputPlaceholder")}
                        disabled={streaming}
                        rows={1}
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

                  <p className="text-center text-xs text-gray-500">{recordingLabel}</p>

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
