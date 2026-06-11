import Link from "next/link";

function ScalesMark({ className = "" }: { className?: string }) {
  // Hand-drawn scales of justice — refined line art, not emoji
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <line x1="24" y1="8" x2="24" y2="40" />
      <line x1="8" y1="14" x2="40" y2="14" />
      <line x1="12" y1="14" x2="8" y2="26" />
      <line x1="12" y1="14" x2="16" y2="26" />
      <line x1="36" y1="14" x2="32" y2="26" />
      <line x1="36" y1="14" x2="40" y2="26" />
      <path d="M5 26 Q12 32 19 26" />
      <path d="M29 26 Q36 32 43 26" />
      <line x1="18" y1="40" x2="30" y2="40" />
      <circle cx="24" cy="6" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

export default function Nav() {
  return (
    <header className="relative border-b border-[color:var(--color-ink)]/15 bg-[color:var(--color-paper)]/85 backdrop-blur-sm">
      <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3 group">
          <span
            className="text-[color:var(--color-emerald)] transition-colors group-hover:text-[color:var(--color-ink)]"
            style={{ width: 28, height: 28 }}
          >
            <ScalesMark className="w-full h-full" />
          </span>
          <span className="flex items-baseline gap-2">
            <span
              className="font-display leading-none tracking-tight text-[color:var(--color-ink)]"
              style={{ fontWeight: 600, fontSize: "22px" }}
            >
              AskAdil
            </span>
            <span
              className="font-arabic text-[color:var(--color-emerald)] leading-none"
              style={{ fontSize: "18px" }}
              dir="rtl"
            >
              عادل
            </span>
          </span>
        </Link>
        <nav className="font-ui flex items-center gap-7 text-[13px] uppercase text-[color:var(--color-ink-faded)]" style={{ letterSpacing: "0.12em" }}>
          <Link href="/" className="hover:text-[color:var(--color-ink)] transition-colors">
            New enquiry
          </Link>
          <a
            href="https://ansarpool.org/pool/donate?client=askadil"
            target="_blank"
            rel="noopener"
            aria-label="Donate to AskAdil via AnsarPool (opens in new tab)"
            className="hover:text-[color:var(--color-ink)] transition-colors"
          >
            Donate
          </a>
          <Link href="/privacy" className="hover:text-[color:var(--color-ink)] transition-colors">
            Privacy
          </Link>
        </nav>
      </div>
      <div
        aria-hidden
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(to right, transparent 0%, var(--color-gold) 20%, var(--color-gold) 80%, transparent 100%)",
          opacity: 0.45,
        }}
      />
    </header>
  );
}
