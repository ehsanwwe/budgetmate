"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface User {
  id: number;
  phone: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  is_blocked: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  adminToken: string | null;
  needsProfile: boolean;
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  setAdminToken: (token: string) => void;
  setNeedsProfile: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      adminToken: null,
      needsProfile: false,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      setAdminToken: (adminToken) => set({ adminToken }),
      setNeedsProfile: (needsProfile) => set({ needsProfile }),
      logout: () => set({ token: null, user: null, needsProfile: false }),
    }),
    { name: "auth-storage" }
  )
);
