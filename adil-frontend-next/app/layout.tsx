import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AskAdil",
  description: "UK discrimination and mental capacity law guidance for British Muslims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en"><body>{children}</body></html>
  );
}
