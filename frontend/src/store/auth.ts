"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: number;
  phone: string;
  name?: string;
  is_blocked: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  adminToken: string | null;
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  setAdminToken: (token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      adminToken: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      setAdminToken: (adminToken) => set({ adminToken }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: "auth-storage" }
  )
);
