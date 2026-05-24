import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: "TransparentPolitics",
  description:
    "Source-driven political intelligence. Every fact cites its source.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <Providers>
          <header className="border-b bg-white">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
              <Link href="/" className="text-lg font-bold tracking-tight">
                TransparentPolitics
              </Link>
              <nav className="text-sm text-gray-500">
                <Link href="/" className="hover:text-gray-900">
                  Members of Congress
                </Link>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
