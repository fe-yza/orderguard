import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { TourProvider } from "@/lib/tour/TourContext";
import { TourOverlay } from "@/components/tour/TourOverlay";
import { IntroModal } from "@/components/tour/IntroModal";
import { SummaryModal } from "@/components/tour/SummaryModal";
import { TourNavButton } from "@/components/tour/TourNavButton";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OrderGuard",
  description:
    "OrderGuard operations console — synthetic marketplace simulation, no real company data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <TourProvider>
          <header className="flex items-center gap-6 px-5 py-3 border-b border-[var(--border)]">
            <span className="font-semibold tracking-tight text-sm">
              OrderGuard
            </span>
            <nav className="flex gap-4 text-[13px]">
              <Link href="/" className="text-[var(--text-dim)] hover:text-[var(--text)]">
                Overview
              </Link>
              <Link
                href="/simulation-lab"
                className="text-[var(--text-dim)] hover:text-[var(--text)]"
              >
                Simulation Lab
              </Link>
              <TourNavButton />
            </nav>
            <span className="ml-auto text-[11px] text-[var(--text-faint)]">
              synthetic marketplace — no real company data
            </span>
          </header>
          <main className="flex-1 p-5">{children}</main>
          <IntroModal />
          <SummaryModal />
          <TourOverlay />
        </TourProvider>
      </body>
    </html>
  );
}
