"use client";

const TARGETS = [
  { id: "bmt",            label: "British Muslim Trust",  desc: "Government-appointed anti-Muslim hatred partner" },
  { id: "police-uk",      label: "Police UK",             desc: "National hate crime · England & Wales" },
  { id: "police-scot",    label: "Police Scotland",       desc: "Hate crime · Scotland" },
  { id: "iru",            label: "IRU",                   desc: "Islamophobia Response Unit · UK-wide" },
  { id: "islamophobiaUK", label: "Islamophobia UK",       desc: "Anonymous tracker · UK-wide" },
  { id: "eass",           label: "EASS",                  desc: "Equality Advisory Support Service · email" },
  { id: "stop-hate-uk",   label: "Stop Hate UK",          desc: "24/7 hate-crime support · email" },
  { id: "tellmama",       label: "Tell MAMA",             desc: "Anti-Muslim hate · UK-wide" },
];

export default function ReportTargetPicker({ onSelect }: { onSelect: (targetId: string) => void }) {
  return (
    <div className="my-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
      {TARGETS.map((t, i) => (
        <button
          key={t.id}
          onClick={() => onSelect(t.id)}
          className="group text-left p-4 transition-all relative overflow-hidden"
          style={{
            background: "var(--color-paper-warm)",
            border: "1px solid rgba(15,62,41,0.18)",
            borderRadius: 16,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--color-gold)";
            e.currentTarget.style.boxShadow = "0 8px 24px rgba(15,62,41,0.08)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "rgba(15,62,41,0.18)";
            e.currentTarget.style.boxShadow = "none";
          }}
        >
          <span
            className="absolute top-2 right-3 font-display"
            style={{
              fontSize: 11,
              color: "var(--color-gold)",
              fontVariantNumeric: "oldstyle-nums",
              letterSpacing: "0.05em",
            }}
            aria-hidden
          >
            {String(i + 1).padStart(2, "0")}
          </span>
          <h3
            className="font-display text-[16px] leading-tight"
            style={{ fontWeight: 600, color: "var(--color-ink)", marginBottom: 4 }}
          >
            {t.label}
          </h3>
          <p
            className="font-body text-[12px] italic"
            style={{ color: "var(--color-ink-faded)", lineHeight: 1.5 }}
          >
            {t.desc}
          </p>
        </button>
      ))}
    </div>
  );
}
