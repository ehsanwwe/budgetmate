"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useChatStore } from "./chat";

export interface User {
  id: number;
  phone?: string;
  email?: string;
  auth_provider?: string;
  google_sub?: string;
  avatar_url?: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  family_name?: string;
  birthdate?: string;
  province?: string;
  city?: string;
  income_range?: string;
  chat_mode?: string;
  is_blocked: boolean;
  onboarding_completed?: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  adminToken: string | null;
  needsProfile: boolean;
  onboardingCompleted: boolean;
  hasHydrated: boolean;
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  setAdminToken: (token: string) => void;
  setNeedsProfile: (v: boolean) => void;
  setOnboardingCompleted: (v: boolean) => void;
  setHasHydrated: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      adminToken: null,
      needsProfile: false,
      onboardingCompleted: false,
      hasHydrated: false,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      setAdminToken: (adminToken) => set({ adminToken }),
      setNeedsProfile: (needsProfile) => set({ needsProfile }),
      setOnboardingCompleted: (onboardingCompleted) => set({ onboardingCompleted }),
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
      logout: () => {
        useChatStore.getState().reset();
        set({ token: null, user: null, adminToken: null, needsProfile: false, onboardingCompleted: false });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        adminToken: state.adminToken,
        needsProfile: state.needsProfile,
        onboardingCompleted: state.onboardingCompleted,
      }),
      onRehydrateStorage: () => (state) => state?.setHasHydrated(true),
    }
  )
);
