import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Shell } from "@/components/shell";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "DEEPTERMINAL", template: "%s · DEEPTERMINAL" },
  description: "Evidence-first equity research terminal: business quality, intrinsic value and market expectations.",
};
export const viewport: Viewport = { themeColor: "#07090d", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><Providers><Shell>{children}</Shell></Providers></body>
    </html>
  );
}
