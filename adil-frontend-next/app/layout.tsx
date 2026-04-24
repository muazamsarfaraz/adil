import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/nav";

const SITE_URL = "https://askadil.org";
const TITLE = "AskAdil — Free UK legal guidance for British Muslims";
const DESCRIPTION =
  "Free, citation-backed UK legal education for British Muslims — discrimination, hate crime, and Mental Capacity / Court of Protection. A Muslim Council of Britain initiative.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: TITLE,
    template: "%s · AskAdil",
  },
  description: DESCRIPTION,
  applicationName: "AskAdil",
  authors: [{ name: "Muslim Council of Britain" }],
  keywords: [
    "UK discrimination law",
    "Equality Act 2010",
    "hate crime",
    "Mental Capacity Act",
    "Court of Protection",
    "British Muslims",
    "legal aid",
  ],
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "AskAdil",
    title: TITLE,
    description: DESCRIPTION,
    locale: "en_GB",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "AskAdil — Free citation-backed UK legal guidance for British Muslims",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og-image.png"],
  },
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400&family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Inter+Tight:wght@400;500;600&family=Amiri:wght@400;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-full flex flex-col relative">
        <Nav />
        <main className="flex-1 flex flex-col overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
