const PRODUCTION_FRONTEND_HOST = "jibyar.digent24.com";
const PRODUCTION_API_ORIGIN = "https://apijibyar.digent24.com";

export function getApiOrigin(): string {
  if (typeof window !== "undefined" && window.location.hostname === PRODUCTION_FRONTEND_HOST) {
    return PRODUCTION_API_ORIGIN;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

export function getApiUrl(): string {
  if (typeof window !== "undefined" && window.location.hostname === PRODUCTION_FRONTEND_HOST) {
    return `${PRODUCTION_API_ORIGIN}/api/v1`;
  }
  return process.env.NEXT_PUBLIC_API_URL || `${getApiOrigin()}/api/v1`;
}
