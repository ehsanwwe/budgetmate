"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  ArrowLeftRight,
  Target,
  MessageCircle,
  User,
  Wallet,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "داشبورد", icon: LayoutDashboard },
  { href: "/transactions", label: "تراکنش‌ها", icon: ArrowLeftRight },
  { href: "/budget", label: "بودجه", icon: Wallet },
  { href: "/goals", label: "اهداف", icon: Target },
  { href: "/chat", label: "دستیار", icon: MessageCircle },
  { href: "/profile", label: "پروفایل", icon: User },
];

const mobileNavItems = [
  { href: "/dashboard", label: "داشبورد", icon: LayoutDashboard },
  { href: "/transactions", label: "تراکنش‌ها", icon: ArrowLeftRight },
  { href: "/budget", label: "بودجه", icon: Wallet },
  { href: "/chat", label: "دستیار", icon: MessageCircle },
  { href: "/profile", label: "پروفایل", icon: User },
];

function isNavItemActive(pathname: string, href: string) {
  if (href === "/profile") {
    return pathname === "/profile" || pathname.startsWith("/billing");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function NavBar() {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const displayName = user?.first_name
    ? [user.first_name, user.last_name].filter(Boolean).join(" ")
    : user?.name || user?.phone || "کاربر";

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-64 min-h-screen bg-white border-e border-border p-4 gap-2 fixed top-0 end-0">
        <div className="flex items-center gap-3 p-2 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary shadow">
            <Wallet className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="font-bold text-sm">جیبیار</p>
            <p className="text-xs text-muted-foreground">{displayName}</p>
          </div>
        </div>
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              isNavItemActive(pathname, href)
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            {label}
          </Link>
        ))}
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 start-0 end-0 bg-white border-t border-border flex justify-around py-2 z-40">
        {mobileNavItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-label={label}
            className={cn(
              "flex flex-col items-center gap-0.5 p-2 rounded-lg transition-colors",
              isNavItemActive(pathname, href)
                ? "text-primary"
                : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            <span className="text-[10px]">{label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
