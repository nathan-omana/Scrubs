import type { Metadata } from "next";
import { Noto_Sans, Noto_Sans_Mono } from "next/font/google";
import "./theme.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scrubs",
  description: "Pseudonymize patient documents before using AI",
};

// Noto Sans is the open base of BC Sans, the BC government typeface the mockups follow.
const sans = Noto_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-noto-sans" });
const mono = Noto_Sans_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-noto-mono" });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Browser extensions (Grammarly, ColorZilla, password managers) add attributes to <html> and
  // <body> before React loads. This only ignores mismatches on those two tags, not their children.
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
