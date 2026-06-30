const TEMP_LOGIN_STORAGE_KEYS = [
  "login-phone",
  "otp-phone",
  "otp-session",
  "pending-login",
  "pending-auth",
];

const TEMP_LOGIN_STORAGE_PREFIXES = ["budgetmate:login:", "budgetmate:otp:"];

const TEMP_LOGIN_COOKIE_NAMES = [
  "login_session",
  "otp_session",
  "phone_verification",
  "pending_login",
  "google_oauth_state",
];

function clearTemporaryStorage(storage: Storage): void {
  for (const key of TEMP_LOGIN_STORAGE_KEYS) storage.removeItem(key);
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key && TEMP_LOGIN_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix))) {
      storage.removeItem(key);
    }
  }
}

/** Clear only ephemeral login/OTP state; preserve auth, preferences, and onboarding drafts. */
export function clearTemporaryLoginFlowState(): void {
  if (typeof window === "undefined") return;

  clearTemporaryStorage(window.localStorage);
  clearTemporaryStorage(window.sessionStorage);

  for (const cookieName of TEMP_LOGIN_COOKIE_NAMES) {
    document.cookie = `${cookieName}=; Max-Age=0; Path=/; SameSite=Lax`;
  }
}

/** Fully exit authentication from the phone-login Back action. */
export function clearLoginFlowAndAuthState(): void {
  if (typeof window === "undefined") return;

  clearTemporaryLoginFlowState();
  useAuthStore.getState().logout();
  useAuthStore.persist.clearStorage();

  // Explicit removal keeps cleanup deterministic if the persistence adapter changes.
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.sessionStorage.removeItem(AUTH_STORAGE_KEY);
}
import { useAuthStore } from "@/store/auth";

const AUTH_STORAGE_KEY = "auth-storage";
