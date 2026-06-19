import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    try {
      const raw = localStorage.getItem("auth-storage");
      if (raw) {
        const parsed = JSON.parse(raw);
        const token = parsed?.state?.token;
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        // Send user's preferred language so backend can use it
        const lang = parsed?.state?.user?.language;
        if (lang) {
          config.headers["Accept-Language"] = lang;
        }
      }
    } catch {
      // ignore
    }
    // Also read locale from URL path
    const pathLocale = window.location.pathname.split("/")[1];
    if (["fa", "ar", "en", "de", "zh"].includes(pathLocale)) {
      config.headers["X-Locale"] = pathLocale;
    }
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (typeof window !== "undefined") {
      if (err.response?.status === 401) {
        const isAdminRoute = window.location.pathname.startsWith("/admin");
        if (isAdminRoute) {
          window.location.href = "/admin";
        } else {
          localStorage.removeItem("auth-storage");
          window.location.href = "/login";
        }
      } else if (err.response?.status === 403) {
        window.location.href = "/blocked";
      }
    }
    return Promise.reject(err);
  }
);

export const adminApi = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
});

adminApi.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    try {
      const raw = localStorage.getItem("auth-storage");
      if (raw) {
        const parsed = JSON.parse(raw);
        const token = parsed?.state?.adminToken;
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
      }
    } catch {
      // ignore
    }
  }
  return config;
});

adminApi.interceptors.response.use(
  (res) => res,
  (err) => {
    if (typeof window !== "undefined") {
      if (err.response?.status === 401) {
        const isAdminRoute = window.location.pathname.startsWith("/admin");
        localStorage.removeItem("auth-storage");
        window.location.href = isAdminRoute ? "/admin" : "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
