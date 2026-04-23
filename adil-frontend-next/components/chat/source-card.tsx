import type { Source } from "@/lib/types";

const TYPE_META = {
  statute:       { label: "Statute",    abbr: "S" },
  case_law:      { label: "Case law",   abbr: "C" },
  echr_judgment: { label: "ECHR",       abbr: "E" },
} as const;

export default function SourceCard({ source, index }: { source: Source; index?: number }) {
  const meta = TYPE_META[source.type];

  const body = (
    <div className="flex items-start gap-4">
      {/* Illuminated initial — gold letter inside a square */}
      <div
        className="flex-shrink-0 flex items-center justify-center font-display"
        style={{
          width: 44,
          height: 44,
          background: "rgba(200, 155, 60, 0.12)",
          border: "1px solid var(--color-gold)",
          color: "var(--color-gold)",
          fontWeight: 600,
          fontSize: 22,
          letterSpacing: 0,
        }}
        aria-hidden
      >
        {meta.abbr}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-1">
          <span
            className="font-ui text-[9px] uppercase"
            style={{ letterSpacing: "0.22em", color: "var(--color-emerald)" }}
          >
            {meta.label}
          </span>
          <span
            className="font-display text-[12px]"
            style={{ color: "var(--color-gold)", fontVariantNumeric: "oldstyle-nums" }}
          >
            {source.citation}
          </span>
        </div>
        <h4
          className="font-display text-[15px] leading-snug"
          style={{ fontWeight: 600, color: "var(--color-ink)" }}
        >
          {source.title}
        </h4>
        {source.excerpt && (
          <p
            className="font-body text-[13px] mt-1.5 line-clamp-3 italic"
            style={{ color: "var(--color-ink-faded)", lineHeight: 1.6 }}
          >
            {source.excerpt}
          </p>
        )}
      </div>
    </div>
  );

  const baseClass = "block p-4 border transition-colors";
  const borderStyle = {
    border: "1px solid rgba(15,62,41,0.15)",
    background: "rgba(255,255,255,0.35)",
  };

  return source.url ? (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`${baseClass} hover:!border-[color:var(--color-emerald)] group`}
      style={borderStyle}
    >
      {body}
      <div className="mt-3 flex items-center gap-1.5 font-ui text-[10px] uppercase text-[color:var(--color-ink-faded)] group-hover:text-[color:var(--color-emerald)]" style={{ letterSpacing: "0.16em" }}>
        <span>View source</span>
        <span aria-hidden>→</span>
      </div>
    </a>
  ) : (
    <div className={baseClass} style={borderStyle}>{body}</div>
  );
  // Keep index param for upstream consumers (sources-panel); not rendered here.
  void index;
}
