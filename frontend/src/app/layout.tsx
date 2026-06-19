import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { headers } from "next/headers";

export const metadata: Metadata = {
  title: "جیبیار",
  description: "مدیریت مالی شخصی",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const headersList = await headers();
  const locale = headersList.get("x-locale") || "fa";
  const dir = ["fa", "ar"].includes(locale) ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={dir}>
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
        <Toaster richColors position="top-center" dir={dir as "rtl" | "ltr"} />
      </body>
    </html>
  );
}
