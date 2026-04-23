import type { Viability } from "@/lib/types";

export default function ViabilityCard({ viability }: { viability: Viability }) {
  const bandColor = {
    Lower: "bg-green-50 border-green-200 text-green-900",
    Middle: "bg-yellow-50 border-yellow-200 text-yellow-900",
    Upper: "bg-orange-50 border-orange-200 text-orange-900",
    Exceptional: "bg-red-50 border-red-200 text-red-900",
  }[viability.vento_band];

  return (
    <div className={`mt-3 p-4 border rounded-lg ${bandColor}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">Viability: {viability.score}/100</div>
        <div className="text-xs font-medium">{viability.vento_band} band</div>
      </div>
      <ul className="text-xs space-y-1">
        <li>{viability.statutory_footing ? "✅" : "❌"} Statutory footing</li>
        <li>{viability.case_law_precedent ? "✅" : "❌"} Case law precedent</li>
        <li>💰 Quantum potential: <strong>{viability.quantum_potential}</strong></li>
      </ul>
      {viability.evidence_checklist.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-semibold mb-1">Evidence to gather:</div>
          <ul className="text-xs space-y-1">
            {viability.evidence_checklist.map((item, i) => (<li key={i}>• {item}</li>))}
          </ul>
        </div>
      )}
    </div>
  );
}
