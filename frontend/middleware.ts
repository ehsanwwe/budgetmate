import { NextResponse, type NextRequest } from "next/server";

const SUPPORTED_LOCALES = ["fa", "ar", "en", "de", "zh"] as const;
const DEFAULT_LOCALE = "fa";

function getLocaleFromPath(pathname: string): string | null {
  const segment = pathname.split("/")[1];
  return (SUPPORTED_LOCALES as readonly string[]).includes(segment) ? segment : null;
}

function isStaticOrApi(pathname: string): boolean {
  return (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/enamad") ||
    /\.\w+$/.test(pathname)
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip static assets, API routes, and Next.js internals
  if (isStaticOrApi(pathname)) {
    return NextResponse.next();
  }

  const localeFromPath = getLocaleFromPath(pathname);

  // Set x-locale header so root layout can read it for lang/dir
  const response = NextResponse.next();
  const locale = localeFromPath ?? DEFAULT_LOCALE;
  response.headers.set("x-locale", locale);

  // / → /fa
  if (pathname === "/") {
    const url = request.nextUrl.clone();
    url.pathname = `/${DEFAULT_LOCALE}`;
    return NextResponse.redirect(url);
  }

  // Paths without locale prefix that map to app pages → redirect to /fa/...
  // e.g. /dashboard → /fa/dashboard, /chat → /fa/chat
  if (!localeFromPath && pathname !== "/") {
    // Check if this looks like an app path (not an API or static)
    const url = request.nextUrl.clone();
    url.pathname = `/${DEFAULT_LOCALE}${pathname}`;
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|enamad|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|woff|woff2|ttf|eot)).*)",
  ],
};
