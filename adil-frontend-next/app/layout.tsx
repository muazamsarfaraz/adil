import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/nav";

export const metadata: Metadata = {
  title: "AskAdil — UK discrimination & mental capacity law guidance",
  description: "Free AI-powered UK legal education for British Muslims — covering discrimination, hate crime, and mental capacity / Court of Protection. A Muslim Council of Britain initiative.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full flex flex-col">
        <Nav />
        <main className="flex-1 flex flex-col overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
