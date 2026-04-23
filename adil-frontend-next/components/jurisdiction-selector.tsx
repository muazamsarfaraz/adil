"use client";

import type { Jurisdiction } from "@/lib/types";
import { writeJurisdictionClient } from "@/lib/jurisdiction";

const OPTIONS: Array<{
  value: Jurisdiction;
  label: string;
  subtitle: string;
  statute: string;
}> = [
  {
    value: "england_wales",
    label: "England & Wales",
    subtitle: "Equality Act 2010 · Public Order Act 1986",
    statute: "Court of Protection",
  },
  {
    value: "scotland",
    label: "Scotland",
    subtitle: "Hate Crime Act 2021 · AWI (Scotland) 2000",
    statute: "Sheriff Court",
  },
  {
    value: "northern_ireland",
    label: "Northern Ireland",
    subtitle: "FETO 1998 · Race Relations Order 1997",
    statute: "NI MCA 2016",
  },
];

export default function JurisdictionSelector({ onSelect }: { onSelect: (j: Jurisdiction) => void }) {
  const pick = (j: Jurisdiction) => {
    writeJurisdictionClient(j);
    onSelect(j);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
      {OPTIONS.map((opt, i) => (
        <button
          key={opt.value}
          onClick={() => pick(opt.value)}
          className="group text-left p-4 transition-all relative overflow-hidden"
          style={{
            background: "var(--color-paper-warm)",
            border: "1px solid rgba(15,62,41,0.18)",
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
          {/* Corner docket number — illuminated-manuscript marginalia */}
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
            {`0${i + 1}`}
          </span>

          <h3
            className="font-display text-[18px] leading-tight"
            style={{
              fontWeight: 600,
              color: "var(--color-ink)",
              marginBottom: 4,
            }}
          >
            {opt.label}
          </h3>

          <p
            className="font-body text-[12px] italic mb-3"
            style={{ color: "var(--color-ink-faded)", lineHeight: 1.5 }}
          >
            {opt.subtitle}
          </p>

          <div className="gold-rule mb-2" style={{ opacity: 0.4 }} />

          <p
            className="font-ui text-[10px] uppercase"
            style={{
              letterSpacing: "0.18em",
              color: "var(--color-emerald)",
            }}
          >
            {opt.statute}
          </p>
        </button>
      ))}
    </div>
  );
}
