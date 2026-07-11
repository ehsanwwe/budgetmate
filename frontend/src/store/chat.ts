import { create } from "zustand";

export interface Message {
  id?: number;
  localId?: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatState {
  messages: Message[];
  streaming: boolean;
  streamingText: string;
  loading: boolean;
  hasBudget: boolean | null;
  scrollY: number;
  historyUserId: number | null;

  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  setStreaming: (streaming: boolean) => void;
  setStreamingText: (text: string) => void;
  setLoading: (loading: boolean) => void;
  setHasBudget: (v: boolean | null) => void;
  setScrollY: (y: number) => void;
  setHistoryUserId: (id: number | null) => void;
  reset: () => void;
}

const initialState = {
  messages: [] as Message[],
  streaming: false,
  streamingText: "",
  loading: true,
  hasBudget: null as boolean | null,
  scrollY: 0,
  historyUserId: null as number | null,
};

export const useChatStore = create<ChatState>()((set) => ({
  ...initialState,

  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  setStreaming: (streaming) => set({ streaming }),
  setStreamingText: (streamingText) => set({ streamingText }),
  setLoading: (loading) => set({ loading }),
  setHasBudget: (hasBudget) => set({ hasBudget }),
  setScrollY: (scrollY) => set({ scrollY }),
  setHistoryUserId: (historyUserId) => set({ historyUserId }),
  reset: () => set(initialState),
}));
