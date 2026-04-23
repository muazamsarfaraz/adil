"use client";

const TARGETS = [
  { id: "bmt",           label: "🕌 British Muslim Trust", desc: "Government-appointed anti-Muslim hatred partner" },
  { id: "police-uk",     label: "🚔 Police UK",            desc: "National hate crime (England & Wales)" },
  { id: "police-scot",   label: "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Police Scotland",    desc: "Hate crime (Scotland)" },
  { id: "iru",           label: "🛡️ IRU",                  desc: "Islamophobia Response Unit (UK-wide)" },
  { id: "islamophobiaUK",label: "📍 Islamophobia UK",      desc: "Anonymous tracker (UK-wide)" },
  { id: "eass",          label: "📧 EASS",                 desc: "Equality Advisory Support Service (email)" },
  { id: "stop-hate-uk",  label: "📧 Stop Hate UK",         desc: "24/7 hate crime support (email)" },
  { id: "tellmama",      label: "🕌 Tell MAMA",            desc: "Anti-Muslim hate (UK-wide)" },
];

export default function ReportTargetPicker({ onSelect }: { onSelect: (targetId: string) => void }) {
  return (
    <div className="my-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
      {TARGETS.map((t) => (
        <button key={t.id} onClick={() => onSelect(t.id)}
                className="text-left p-3 border border-gray-200 rounded-lg hover:border-brand-500 transition-colors">
          <div className="text-sm font-semibold">{t.label}</div>
          <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
        </button>
      ))}
    </div>
  );
}
