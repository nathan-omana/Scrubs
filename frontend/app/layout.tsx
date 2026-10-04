import type { Metadata } from "next";
import "@uswds/uswds/css/uswds.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scrubs",
  description: "De-identify patient documents before using AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
