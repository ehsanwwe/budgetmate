export interface IntroDraft {
  text: string;
  audioTranscript: string;
  audioDurationSeconds: number | null;
  updatedAt: string;
}

const EMPTY: IntroDraft = {
  text: "",
  audioTranscript: "",
  audioDurationSeconds: null,
  updatedAt: "",
};

function draftKey(userId: number): string {
  return `budgetmate:onboarding:intro-draft:${userId}`;
}

export const introDraft = {
  read(userId: number): IntroDraft {
    if (typeof window === "undefined") return { ...EMPTY };
    try {
      const raw = localStorage.getItem(draftKey(userId));
      if (!raw) return { ...EMPTY };
      return { ...EMPTY, ...JSON.parse(raw) };
    } catch {
      return { ...EMPTY };
    }
  },

  save(userId: number, patch: Partial<Omit<IntroDraft, "updatedAt">>): void {
    if (typeof window === "undefined") return;
    try {
      const existing = this.read(userId);
      localStorage.setItem(
        draftKey(userId),
        JSON.stringify({ ...existing, ...patch, updatedAt: new Date().toISOString() })
      );
    } catch {
      // ignore quota errors
    }
  },

  clear(userId: number): void {
    if (typeof window === "undefined") return;
    try {
      localStorage.removeItem(draftKey(userId));
    } catch {
      // ignore
    }
  },
};
