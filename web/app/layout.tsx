import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Open Model Workspace",
    template: "%s · Open Model",
  },
  description: "Implementation-focused Open Model chat workspace with live steps and citations.",
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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0c" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
