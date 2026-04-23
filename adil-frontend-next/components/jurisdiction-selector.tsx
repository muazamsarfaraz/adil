"use client";

import type { Jurisdiction } from "@/lib/types";
import { writeJurisdictionClient } from "@/lib/jurisdiction";

export default function JurisdictionSelector({ onSelect }: { onSelect: (j: Jurisdiction) => void }) {
  const pick = (j: Jurisdiction) => {
    writeJurisdictionClient(j);
    onSelect(j);
  };
  return (
    <div className="flex flex-wrap gap-2 my-3">
      <button onClick={() => pick("england_wales")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🏴󠁧󠁢󠁥󠁮󠁧󠁿 England &amp; Wales
      </button>
      <button onClick={() => pick("scotland")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland
      </button>
      <button onClick={() => pick("northern_ireland")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🇬🇧 Northern Ireland
      </button>
    </div>
  );
}
