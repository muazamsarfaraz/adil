import Link from "next/link";

export default function Nav() {
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="font-semibold text-brand-900 text-lg">
          AskAdil <span className="font-normal text-gray-500">(عادل)</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className="text-gray-700 hover:text-brand-700">New chat</Link>
          <Link href="/privacy" className="text-gray-700 hover:text-brand-700">Privacy</Link>
        </nav>
      </div>
    </header>
  );
}
