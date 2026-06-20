"use client";
import { useEffect } from "react";
import { useRouter, usePathname, useParams } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Users, Shield, LogOut } from "lucide-react";

export default function LocaleAdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams();
  const locale = (params?.locale as string) || "fa";
  const { dict } = useLocale();
  const { adminToken, logout } = useAuthStore();

  const adminRoot = `/${locale}/admin`;

  useEffect(() => {
    if (pathname !== adminRoot && !adminToken) {
      router.replace(adminRoot);
    }
  }, [adminToken, pathname, router, adminRoot]);

  if (pathname === adminRoot) return <>{children}</>;
  if (!adminToken) return null;

  const t = dict.admin.layout;

  const navItems = [
    { href: `${adminRoot}/dashboard`, label: t.navDashboard, icon: LayoutDashboard },
    { href: `${adminRoot}/users`, label: t.navUsers, icon: Users },
  ];

  return (
    <div className="min-h-screen flex">
      <aside className="w-60 bg-slate-900 text-slate-200 flex flex-col fixed top-0 end-0 bottom-0 p-4 gap-2">
        <div className="flex items-center gap-2 p-2 mb-4">
          <Shield className="h-6 w-6 text-indigo-400" />
          <span className="font-bold text-sm">{t.panelLabel}</span>
        </div>
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              pathname?.startsWith(href) ? "bg-slate-700 text-white" : "text-slate-400 hover:bg-slate-800 hover:text-white"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
        <button
          onClick={() => { logout(); router.replace(adminRoot); }}
          className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-colors mt-auto"
        >
          <LogOut className="h-4 w-4" />
          {t.logout}
        </button>
      </aside>
      <main className="flex-1 me-60 p-6 bg-slate-50">
        {children}
      </main>
    </div>
  );
}
