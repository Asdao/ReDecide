import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@fontsource-variable/noto-sans";
import "@fontsource-variable/saira";
import "@fontsource/saira-condensed/600.css";
import "@fontsource/saira-condensed/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "RE:DECIDE — Outcome-blind CS2 coaching",
  description: "Replay the decision, not the match outcome.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
