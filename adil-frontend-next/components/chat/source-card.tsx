import type { V2Source } from "@/lib/types";
import Link from "next/link";

interface SourceCardProps {
  index: number;
  source: V2Source;
  highlighted?: boolean;
}

export default function SourceCard({ index, source, highlighted }: SourceCardProps) {
  return (
    <div
      id={`source-${index}`}
      className={`bg-white border rounded-lg p-3 transition-colors ${
        highlighted
          ? "border-brand-500 border-l-4 ring-1 ring-brand-200"
          : "border-gray-200 border-l-4 border-l-brand-400"
      }`}
    >
      <div className="text-xs font-medium text-gray-900">
        [{index}]{" "}
        {source.url ? (
          <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-600">
            {source.title}
          </a>
        ) : (
          source.title
        )}
      </div>
      {source.author_name && (
        <div className="text-xs text-gray-500 mt-0.5">
          {source.author_name}
          {source.author_death_year && ` (d. ${source.author_death_year} AH)`}
        </div>
      )}
      {source.excerpt && (
        <p className="text-xs text-gray-400 mt-1.5 line-clamp-3">{source.excerpt}</p>
      )}
      <div className="flex items-center gap-2 mt-2">
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
            source.source_type === "usul"
              ? "bg-blue-50 text-blue-600"
              : source.source_type === "shamela"
                ? "bg-green-50 text-green-600"
                : source.source_type === "waqfeya"
                  ? "bg-amber-50 text-amber-700"
                  : source.source_type === "prophet_mosque"
                    ? "bg-purple-50 text-purple-700"
                    : source.source_type === "custom"
                      ? "bg-teal-50 text-teal-700"
                      : "bg-gray-100 text-gray-500"
          }`}
        >
          {source.source_type === "prophet_mosque" ? "prophet-mosque" : source.source_type}
        </span>
        {source.book_id && source.book_id !== "unknown" && (
          <Link
            href={`/library/${encodeURIComponent(source.book_id)}`}
            className="text-[10px] text-gray-400 hover:text-brand-500"
          >
            View in library
          </Link>
        )}
      </div>
    </div>
  );
}
