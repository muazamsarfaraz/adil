"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Chat" },
    { href: "/library", label: "Library" },
    { href: "/hadith", label: "Hadith Grader" },
  ];

  return (
    <nav className="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-white">
      <Link href="/" className="text-lg font-semibold text-gray-900">
        Ask Aisha
      </Link>
      <div className="flex gap-6">
        {links.map((link) => {
          const isActive =
            link.href === "/"
              ? pathname === "/" || pathname.startsWith("/chat")
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm ${
                isActive
                  ? "text-brand-500 font-medium"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
