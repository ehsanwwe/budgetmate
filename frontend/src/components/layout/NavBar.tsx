"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useLocale } from "@/i18n/LocaleContext";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  ArrowLeftRight,
  Target,
  MessageCircle,
  User,
  Wallet,
  CalendarClock,
} from "lucide-react";
import type { Dictionary } from "@/i18n/getDictionary";

interface NavItem {
  path: string;
  label: string;
  icon: React.ElementType;
}

function buildNavItems(locale: string, dict: Dictionary): NavItem[] {
  const base = `/${locale}`;
  const n = dict.nav;
  return [
    { path: `${base}/dashboard`, label: n.dashboard, icon: LayoutDashboard },
    { path: `${base}/transactions`, label: n.transactions, icon: ArrowLeftRight },
    { path: `${base}/budget`, label: n.budgets, icon: Wallet },
    { path: `${base}/goals`, label: n.goals, icon: Target },
    { path: `${base}/future-commitments`, label: n.futureCommitments, icon: CalendarClock },
    { path: `${base}/chat`, label: n.chat, icon: MessageCircle },
    { path: `${base}/profile`, label: n.profile, icon: User },
  ];
}

function isNavItemActive(pathname: string, href: string) {
  if (href.endsWith("/profile")) {
    return pathname === href || pathname.includes("/billing");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function NavBar({ locale = "fa" }: { locale?: string }) {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const { dict } = useLocale();
  const displayName = user?.first_name
    ? [user.first_name, user.last_name].filter(Boolean).join(" ")
    : user?.name || user?.phone || dict.nav.userDefault;

  const navItems = buildNavItems(locale, dict);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-64 min-h-screen bg-white border-e border-border p-4 gap-2 fixed top-0 end-0">
        <div className="flex items-center gap-3 p-2 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary shadow">
            <Wallet className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="font-bold text-sm">{dict.nav.appName}</p>
            <p className="text-xs text-muted-foreground">{displayName}</p>
          </div>
        </div>
        {navItems.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            href={path}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              isNavItemActive(pathname ?? "", path)
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
      <nav className="md:hidden fixed bottom-0 start-0 end-0 bg-white border-t border-border flex justify-around px-1 py-2 z-40">
        {navItems.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            href={path}
            aria-label={label}
            className={cn(
              "min-w-0 flex-1 flex flex-col items-center gap-0.5 rounded-lg px-1 py-2 transition-colors",
              isNavItemActive(pathname ?? "", path)
                ? "text-primary"
                : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            <span className="max-w-full truncate text-[10px]">{label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
