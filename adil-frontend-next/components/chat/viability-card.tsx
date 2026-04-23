import type { Viability } from "@/lib/types";

function ScoreDial({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className="relative flex items-center justify-center" style={{ width: 108, height: 108 }}>
      <svg width="108" height="108" viewBox="0 0 108 108" className="rotate-[-90deg]">
        <circle
          cx="54"
          cy="54"
          r={radius}
          fill="none"
          stroke="rgba(15,62,41,0.12)"
          strokeWidth="4"
        />
        <circle
          cx="54"
          cy="54"
          r={radius}
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.65, 0, 0.35, 1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-display leading-none"
          style={{
            fontSize: 34,
            fontWeight: 600,
            color: "var(--color-ink)",
            fontVariantNumeric: "oldstyle-nums",
          }}
        >
          {score}
        </span>
        <span
          className="font-ui mt-1 text-[10px] uppercase"
          style={{ letterSpacing: "0.18em", color: "var(--color-ink-faded)" }}
        >
          out of 100
        </span>
      </div>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span
        className="flex-shrink-0 flex items-center justify-center font-ui text-[11px]"
        style={{
          width: 20,
          height: 20,
          border: `1px solid ${ok ? "var(--color-emerald)" : "rgba(139,60,30,0.4)"}`,
          color: ok ? "var(--color-emerald)" : "var(--color-rust)",
          background: ok ? "rgba(31,111,74,0.08)" : "rgba(139,60,30,0.04)",
        }}
      >
        {ok ? "✓" : "–"}
      </span>
      <span
        className="font-body text-[14px]"
        style={{ color: ok ? "var(--color-ink)" : "var(--color-ink-faded)" }}
      >
        {label}
      </span>
    </div>
  );
}

export default function ViabilityCard({ viability }: { viability: Viability }) {
  const quantumLabel = { low: "Low", moderate: "Moderate", high: "High" }[viability.quantum_potential];

  return (
    <div className="paper-card mt-6 p-6 md:p-7 max-w-3xl mx-auto">
      {/* Header row */}
      <div className="flex items-center gap-2 mb-5">
        <span
          className="font-ui text-[10px] uppercase"
          style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
        >
          ❃ Assessment
        </span>
        <div
          className="flex-1 h-px"
          style={{
            background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
            opacity: 0.5,
          }}
        />
        <span
          className="font-ui text-[11px]"
          style={{ color: "var(--color-ink-faded)", letterSpacing: "0.08em" }}
        >
          {viability.vento_band} band
        </span>
      </div>

      <div className="flex flex-col md:flex-row gap-6 md:gap-8 items-start">
        <ScoreDial score={viability.score} />

        <div className="flex-1 min-w-0 w-full">
          <h3 className="font-display text-[18px] mb-1" style={{ fontWeight: 600, color: "var(--color-ink)" }}>
            Case viability
          </h3>
          <p className="font-body text-[13px] italic mb-4" style={{ color: "var(--color-ink-faded)" }}>
            An indicative score based on statute, precedent, and quantum potential.
          </p>

          <div className="space-y-0.5">
            <Check ok={viability.statutory_footing} label="Statutory footing present" />
            <Check ok={viability.case_law_precedent} label="Case-law precedent identified" />
            <div className="flex items-center gap-3 py-1">
              <span
                className="flex-shrink-0 flex items-center justify-center font-ui text-[10px]"
                style={{
                  width: 20,
                  height: 20,
                  border: "1px solid var(--color-gold)",
                  color: "var(--color-gold)",
                  background: "rgba(200,155,60,0.1)",
                }}
              >
                £
              </span>
              <span className="font-body text-[14px]" style={{ color: "var(--color-ink)" }}>
                Quantum potential:{" "}
                <span className="font-display" style={{ fontWeight: 600 }}>{quantumLabel}</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      {viability.evidence_checklist.length > 0 && (
        <>
          <div className="gold-rule my-6" />
          <div>
            <h4
              className="font-ui text-[11px] uppercase mb-3"
              style={{ letterSpacing: "0.22em", color: "var(--color-emerald)" }}
            >
              Evidence to gather
            </h4>
            <ul className="space-y-2">
              {viability.evidence_checklist.map((item, i) => (
                <li key={i} className="flex gap-3 font-body text-[14px]" style={{ color: "var(--color-ink-soft)" }}>
                  <span
                    className="flex-shrink-0 font-display"
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: "var(--color-gold)",
                      fontVariantNumeric: "oldstyle-nums",
                      minWidth: "1.4em",
                    }}
                  >
                    {i + 1}.
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
