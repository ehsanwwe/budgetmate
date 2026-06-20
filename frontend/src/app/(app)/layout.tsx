"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";

// Non-localized (app) layout. All internal app pages now live under /[locale]/(app)/...
// Redirect any visit here to the /fa-prefixed equivalent so old bookmarks keep working.
export default function AppLegacyLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (pathname && !/^\/(fa|ar|en|de|zh)(\/|$)/.test(pathname)) {
      router.replace(`/fa${pathname}`);
    }
  }, [pathname, router]);

  return <>{children}</>;
}
