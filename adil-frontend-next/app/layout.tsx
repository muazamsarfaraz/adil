import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Nav from "@/components/nav";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Ask Aisha — Islamic Library AI",
  description:
    "Search 12,000+ classical Islamic texts. Get scholarly answers with source citations from Maktaba Shamela and Usul.ai.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased bg-[#fafbfc] text-gray-900`}>
        <Nav />
        <main>{children}</main>
      </body>
    </html>
  );
}
