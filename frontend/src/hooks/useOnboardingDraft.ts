export interface OnboardingDraft {
  name: string;
  familyName: string;
  birthYear: string;
  birthMonth: string;
  birthDay: string;
  province: string;
  city: string;
  incomeRange: string;
  financialStatus: string;
}

const EMPTY: OnboardingDraft = {
  name: "",
  familyName: "",
  birthYear: "",
  birthMonth: "",
  birthDay: "",
  province: "",
  city: "",
  incomeRange: "",
  financialStatus: "",
};

function draftKey(userId: number): string {
  return `budgetmate:onboarding:draft:${userId}`;
}

export const onboardingDraft = {
  read(userId: number): OnboardingDraft {
    if (typeof window === "undefined") return { ...EMPTY };
    try {
      const raw = localStorage.getItem(draftKey(userId));
      if (!raw) return { ...EMPTY };
      return { ...EMPTY, ...JSON.parse(raw) };
    } catch {
      return { ...EMPTY };
    }
  },

  save(userId: number, patch: Partial<OnboardingDraft>): void {
    if (typeof window === "undefined") return;
    try {
      const existing = this.read(userId);
      localStorage.setItem(draftKey(userId), JSON.stringify({ ...existing, ...patch }));
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
