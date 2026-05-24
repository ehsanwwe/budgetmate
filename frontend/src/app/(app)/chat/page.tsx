"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Send, Bot, User, Trash2 } from "lucide-react";

interface Message { id?: number; role: "user" | "assistant"; content: string; }

const GREETING = "سلام! من بادجت‌میتم. می‌تونم در مورد بودجه، خرج‌ها و پس‌اندازت کمکت کنم. چه سوالی داری؟";

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br/>");
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const token = useAuthStore((s) => s.token);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    async function loadHistory() {
      try {
        const res = await api.get("/chat/history");
        const hist: Message[] = res.data.map((m: { role: string; content: string }) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }));
        setMessages(hist.length > 0 ? hist : [{ role: "assistant", content: GREETING }]);
      } catch {
        setMessages([{ role: "assistant", content: GREETING }]);
      } finally {
        setLoading(false);
      }
    }
    loadHistory();
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, streamingText, scrollToBottom]);

  async function sendMessage() {
    if (!input.trim() || streaming) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setStreaming(true);
    setStreamingText("");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiBase}/chat/stream?message=${encodeURIComponent(userMsg)}&token=${token}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok || !res.body) {
        throw new Error("streaming failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              const text = parsed.text || parsed.content || parsed.delta || data;
              accumulated += text;
              setStreamingText(accumulated);
            } catch {
              accumulated += data;
              setStreamingText(accumulated);
            }
          }
        }
      }

      if (accumulated) {
        setMessages((prev) => [...prev, { role: "assistant", content: accumulated }]);
      }
    } catch {
      // Fallback: use regular message endpoint
      try {
        const res = await api.post("/chat/message", { message: userMsg });
        setMessages((prev) => [...prev, { role: "assistant", content: res.data.response || res.data.content || "پاسخی دریافت نشد" }]);
      } catch {
        toast.error("خطا در ارسال پیام");
        setMessages((prev) => [...prev, { role: "assistant", content: "متأسفم، در حال حاضر مشکلی پیش آمده. لطفاً دوباره تلاش کنید." }]);
      }
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  }

  async function clearHistory() {
    try {
      await api.delete("/chat/history");
      setMessages([{ role: "assistant", content: GREETING }]);
      toast.success("تاریخچه پاک شد");
    } catch {
      toast.error("خطا در پاک کردن تاریخچه");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] md:h-[calc(100vh-2rem)]">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary shadow">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold">دستیار مالی</h1>
            <p className="text-xs text-muted-foreground">بادجت‌میت</p>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={clearHistory} aria-label="پاک کردن تاریخچه">
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {streaming && streamingText && (
              <MessageBubble message={{ role: "assistant", content: streamingText }} isStreaming />
            )}
            {streaming && !streamingText && (
              <div className="flex gap-3">
                <Avatar className="h-8 w-8 shrink-0">
                  <AvatarFallback className="bg-primary text-white text-xs"><Bot className="h-4 w-4" /></AvatarFallback>
                </Avatar>
                <div className="flex items-center gap-1 bg-white rounded-2xl rounded-ss-sm px-4 py-3 border shadow-sm">
                  <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t pt-4">
        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="از وضعیت مالی‌ات بپرس..."
            className="min-h-[48px] max-h-32 resize-none"
            disabled={streaming}
          />
          <Button
            onClick={sendMessage}
            disabled={!input.trim() || streaming}
            size="icon"
            className="h-12 w-12 shrink-0"
            aria-label="ارسال پیام"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground text-center mt-2">Enter برای ارسال | Shift+Enter برای خط جدید</p>
      </div>
    </div>
  );
}

function MessageBubble({ message, isStreaming }: { message: Message; isStreaming?: boolean }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={isUser ? "bg-secondary" : "bg-primary text-white"}>
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>
      <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm border ${isUser ? "bg-primary text-white border-primary/20 rounded-se-sm" : "bg-white rounded-ss-sm"}`}>
        <SimpleMarkdown text={message.content} />
        {isStreaming && <span className="inline-block w-1.5 h-4 bg-current animate-pulse ms-0.5 align-text-bottom" />}
      </div>
    </div>
  );
}
