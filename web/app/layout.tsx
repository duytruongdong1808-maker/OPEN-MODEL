import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Open Model Workspace",
    template: "%s · Open Model",
  },
  description: "Local-first chat workspace with live runtime steps and citations.",
  applicationName: "Open Model Workspace",
  robots: { index: false, follow: false },
  openGraph: {
    title: "Open Model Workspace",
    description: "Threaded chat, live runtime steps, and citations in one focused surface.",
    type: "website",
  },
  formatDetection: { telephone: false, email: false, address: false },
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: dark)", color: "#08090c" }],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-accent="cyan" className={`${inter.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
