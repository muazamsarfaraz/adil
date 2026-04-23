export default function SearchingIndicator() {
  return (
    <div className="max-w-3xl mx-auto px-6 md:px-4 py-4 flex items-center gap-4">
      <span
        className="inline-block"
        style={{
          width: 18,
          height: 18,
          color: "var(--color-gold)",
          animation: "star-spin 4s linear infinite",
        }}
        aria-hidden
      >
        <span className="star-mark" style={{ width: "100%", height: "100%", display: "block" }} />
      </span>
      <span
        className="font-ui text-[12px] uppercase"
        style={{
          letterSpacing: "0.22em",
          color: "var(--color-ink-faded)",
        }}
      >
        Consulting legislation &amp; case law
        <span className="inline-block ml-1">
          <span className="dot-pulse" style={{ animationDelay: "0s" }}>·</span>
          <span className="dot-pulse" style={{ animationDelay: "0.2s" }}>·</span>
          <span className="dot-pulse" style={{ animationDelay: "0.4s" }}>·</span>
        </span>
      </span>
      <style>{`
        .dot-pulse {
          animation: dotblink 1.4s ease-in-out infinite;
          display: inline-block;
          margin-right: 1px;
        }
        @keyframes dotblink {
          0%, 40%, 100% { opacity: 0.3; }
          20% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
