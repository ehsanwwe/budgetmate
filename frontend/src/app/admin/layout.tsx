"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Users, Shield, LogOut } from "lucide-react";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { adminToken, logout } = useAuthStore();

  useEffect(() => {
    if (pathname !== "/admin" && !adminToken) {
      router.replace("/admin");
    }
  }, [adminToken, pathname, router]);

  if (pathname === "/admin") return <>{children}</>;
  if (!adminToken) return null;

  const navItems = [
    { href: "/admin/dashboard", label: "داشبورد", icon: LayoutDashboard },
    { href: "/admin/users", label: "کاربران", icon: Users },
  ];

  return (
    <div className="min-h-screen flex">
      <aside className="w-60 bg-slate-900 text-slate-200 flex flex-col fixed top-0 end-0 bottom-0 p-4 gap-2">
        <div className="flex items-center gap-2 p-2 mb-4">
          <Shield className="h-6 w-6 text-indigo-400" />
          <span className="font-bold text-sm">پنل مدیریت</span>
        </div>
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              pathname.startsWith(href) ? "bg-slate-700 text-white" : "text-slate-400 hover:bg-slate-800 hover:text-white"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
        <button
          onClick={() => { logout(); router.replace("/admin"); }}
          className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-colors mt-auto"
        >
          <LogOut className="h-4 w-4" />
          خروج
        </button>
      </aside>
      <main className="flex-1 me-60 p-6 bg-slate-50">
        {children}
      </main>
    </div>
  );
}
