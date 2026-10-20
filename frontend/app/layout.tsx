import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CircuitPilot — From circuit to connection",
  description:
    "Plan reference breadboard layouts, follow precise pin mappings, and align circuit photos with clear uncertainty.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
