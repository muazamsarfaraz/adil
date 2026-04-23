import type { Source } from "@/lib/types";

export default function SourceCard({ source }: { source: Source }) {
  const typeBadge = {
    statute: { label: "Statute", color: "bg-brand-100 text-brand-900" },
    case_law: { label: "Case law", color: "bg-scale-50 text-amber-900" },
    echr_judgment: { label: "ECHR", color: "bg-blue-50 text-blue-900" },
  }[source.type];

  const inner = (
    <>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${typeBadge.color}`}>{typeBadge.label}</span>
        <span className="text-xs text-gray-400">{source.citation}</span>
      </div>
      <div className="text-sm font-semibold text-gray-900">{source.title}</div>
      {source.excerpt && <div className="text-xs text-gray-600 mt-1 line-clamp-3">{source.excerpt}</div>}
    </>
  );

  return source.url ? (
    <a href={source.url} target="_blank" rel="noopener noreferrer"
       className="block p-3 border border-gray-200 rounded-lg hover:border-brand-500 transition-colors">
      {inner}
    </a>
  ) : (
    <div className="block p-3 border border-gray-200 rounded-lg">{inner}</div>
  );
}
