"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types — mirror adil-rag-api SOLICITOR_PUBLIC_FIELDS and the /facets payload.
// ---------------------------------------------------------------------------
type Solicitor = {
  sra_id?: string;
  name?: string;
  firm?: string;
  role?: string;
  address?: string;
  postcode?: string;
  telephone?: string;
  email?: string;
  areas?: string[];
  languages?: string[];
  accreditations?: string[];
  muslim_language?: boolean;
};

type AreaGroup = { group: string; wave: number; count: number };
type Facets = { areas: string[]; area_groups: AreaGroup[]; languages: string[] };

const PAGE_SIZE = 24;
const SEARCH_LIMIT = 200; // backend hard-caps at 200
const SRA_REGISTER_URL = "https://www.sra.org.uk/consumers/register/";
// Deep-link straight to an individual's record on the SRA register. The
// /person/ path is the live one — the older /solicitor/ path 404s. The
// prevSearch* params mirror the SRA register's own search breadcrumbs.
const sraPersonUrl = (sraId: string) =>
  `https://www.sra.org.uk/consumers/register/person/?sraNumber=${encodeURIComponent(sraId)}` +
  `&prevSearchText=${encodeURIComponent(sraId)}&prevSearchFilter=`;

// WAVE-3 GATE — Criminal Defence, Personal Injury and Conveyancing (wave 3) are
// intentionally NOT offered as filter tiles. Their public-facing outreach is
// gated behind MCB sign-off (DECIDE task 869djm527 / the wave-3 business case in
// adil-rag-api/docs/plans). We surface only area_groups with wave < 3; when the
// legal opinion green-lights wave 3, dropping this filter is the only change
// needed here. This mirrors the gate already shipped on askadil.com.
const WAVE_GATE = 3;

function buildSearchUrl(params: {
  area: string;
  language: string;
  postcode: string;
  muslimOnly: boolean;
}): string {
  const sp = new URLSearchParams();
  if (params.area) sp.set("area", params.area);
  if (params.language) sp.set("language", params.language);
  if (params.postcode) sp.set("postcode", params.postcode);
  if (params.muslimOnly) sp.set("muslim_only", "true");
  sp.set("limit", String(SEARCH_LIMIT));
  return `/api/solicitors/search?${sp.toString()}`;
}

export default function SolicitorFinder() {
  // --- filter state ---
  const [area, setArea] = useState("");
  const [language, setLanguage] = useState("");
  const [postcode, setPostcode] = useState("");
  const [query, setQuery] = useState(""); // firm-or-name, filtered client-side
  const [muslimOnly, setMuslimOnly] = useState(false);

  // --- data state ---
  const [facets, setFacets] = useState<Facets | null>(null);
  const [results, setResults] = useState<Solicitor[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(PAGE_SIZE);

  const didPrefill = useRef(false);

  // --- prefill filters from the URL (deep links / shared searches) ---
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const a = sp.get("area");
    const l = sp.get("language");
    const p = sp.get("postcode");
    const q = sp.get("q");
    const m = sp.get("muslim_only");
    if (a) setArea(a);
    if (l) setLanguage(l);
    if (p) setPostcode(p.toUpperCase());
    if (q) setQuery(q);
    if (m === "true" || m === "1") setMuslimOnly(true);
    didPrefill.current = true;
  }, []);

  // --- load filter facets once ---
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/solicitors/facets");
        if (!res.ok) throw new Error(`facets ${res.status}`);
        const data: Facets = await res.json();
        if (!cancelled) setFacets(data);
      } catch {
        // Non-fatal: the finder still works with free-text + postcode filters.
        if (!cancelled) setFacets({ areas: [], area_groups: [], languages: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // --- debounced search whenever a server-side filter changes ---
  useEffect(() => {
    const handle = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(buildSearchUrl({ area, language, postcode, muslimOnly }));
        if (!res.ok) throw new Error(`search ${res.status}`);
        const data = await res.json();
        setResults(Array.isArray(data.solicitors) ? data.solicitors : []);
        setTotal(typeof data.total === "number" ? data.total : 0);
      } catch {
        setError("We couldn't load the directory just now. Please try again in a moment.");
        setResults([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [area, language, postcode, muslimOnly]);

  // --- keep the URL in sync so a search can be shared / bookmarked ---
  useEffect(() => {
    if (!didPrefill.current) return;
    const sp = new URLSearchParams();
    if (area) sp.set("area", area);
    if (language) sp.set("language", language);
    if (postcode) sp.set("postcode", postcode);
    if (query) sp.set("q", query);
    if (muslimOnly) sp.set("muslim_only", "true");
    const qs = sp.toString();
    const next = qs ? `?${qs}` : window.location.pathname;
    window.history.replaceState(null, "", next);
  }, [area, language, postcode, query, muslimOnly]);

  // --- reset pagination when the displayed set changes ---
  useEffect(() => {
    setVisible(PAGE_SIZE);
  }, [area, language, postcode, query, muslimOnly]);

  // --- firm-or-name substring filter + alphabetical sort (client-side) ---
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = q
      ? results.filter(
          (s) =>
            (s.firm ?? "").toLowerCase().includes(q) ||
            (s.name ?? "").toLowerCase().includes(q),
        )
      : results.slice();
    out.sort((a, b) =>
      (a.firm || a.name || "").localeCompare(b.firm || b.name || "", "en", {
        sensitivity: "base",
      }),
    );
    return out;
  }, [results, query]);

  const areaGroups = useMemo(
    () => (facets?.area_groups ?? []).filter((g) => g.wave < WAVE_GATE),
    [facets],
  );

  const hasAnyFilter = !!(area || language || postcode || query || muslimOnly);

  const clearAll = useCallback(() => {
    setArea("");
    setLanguage("");
    setPostcode("");
    setQuery("");
    setMuslimOnly(false);
  }, []);

  const shown = filtered.slice(0, visible);
  const countLabel = loading
    ? "Searching the directory…"
    : `${filtered.length.toLocaleString("en-GB")} solicitor${filtered.length === 1 ? "" : "s"} found`;

  return (
    <div>
      {/* ------------------------------------------------------------------ */}
      {/* Filters                                                            */}
      {/* ------------------------------------------------------------------ */}
      <section
        aria-label="Filter solicitors"
        className="rounded-xl border border-[color:var(--color-ink)]/12 bg-[color:var(--color-paper-warm)]/40 p-5 sm:p-6"
      >
        {/* Practice-area tiles */}
        <fieldset>
          <legend className="font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-3">
            Practice area
          </legend>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={area === ""}
              onClick={() => setArea("")}
              className={tileClass(area === "")}
            >
              All areas
            </button>
            {areaGroups.map((g) => (
              <button
                key={g.group}
                type="button"
                aria-pressed={area === g.group}
                onClick={() => setArea(area === g.group ? "" : g.group)}
                className={tileClass(area === g.group)}
              >
                {g.group}
                <span className="ml-1.5 opacity-60">{g.count}</span>
              </button>
            ))}
          </div>
        </fieldset>

        {/* Text / select filters */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-5">
          <div>
            <label
              htmlFor="sol-search"
              className="block font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-1.5"
            >
              Firm or name
            </label>
            <input
              id="sol-search"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Smith, or Gull Law"
              className={inputClass}
            />
          </div>

          <div>
            <label
              htmlFor="sol-postcode"
              className="block font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-1.5"
            >
              Postcode
            </label>
            <input
              id="sol-postcode"
              type="text"
              inputMode="text"
              autoComplete="postal-code"
              value={postcode}
              onChange={(e) => setPostcode(e.target.value.toUpperCase())}
              placeholder="e.g. M1, E1, EC2N"
              className={inputClass}
            />
          </div>

          <div>
            <label
              htmlFor="sol-language"
              className="block font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-1.5"
            >
              Language
            </label>
            <select
              id="sol-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className={inputClass}
            >
              <option value="">Any language</option>
              {(facets?.languages ?? []).map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Muslim-community toggle + clear */}
        <div className="flex flex-wrap items-center justify-between gap-3 mt-5">
          <label className="inline-flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={muslimOnly}
              onChange={(e) => setMuslimOnly(e.target.checked)}
              className="h-4 w-4 accent-[color:var(--color-emerald)]"
            />
            <span className="font-ui text-sm text-[color:var(--color-ink-soft)]">
              Speaks a Muslim-community language
            </span>
          </label>
          {hasAnyFilter && (
            <button
              type="button"
              onClick={clearAll}
              className="font-ui text-[13px] text-[color:var(--color-emerald)] hover:text-[color:var(--color-emerald-bright)] underline underline-offset-2"
            >
              Clear all filters
            </button>
          )}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Results                                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-baseline justify-between mt-8 mb-4">
        <p
          role="status"
          aria-live="polite"
          className="font-ui text-sm text-[color:var(--color-ink-faded)]"
        >
          {countLabel}
        </p>
        {!loading && total >= SEARCH_LIMIT && (
          <p className="font-ui text-[12px] text-[color:var(--color-ink-faded)]">
            Showing the first {SEARCH_LIMIT} — narrow your filters for more
          </p>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border-l-4 border-[color:var(--color-rust)] bg-[color:var(--color-paper-warm)]/60 px-5 py-4 font-body text-sm text-[color:var(--color-ink-soft)]"
        >
          {error}
        </div>
      )}

      {!error && !loading && filtered.length === 0 && (
        <div className="rounded-lg border border-[color:var(--color-ink)]/12 px-5 py-8 text-center">
          <p className="font-body text-[color:var(--color-ink-soft)]">
            No solicitors match those filters. Try widening your search — remove the
            postcode, choose &ldquo;All areas&rdquo;, or clear the language filter.
          </p>
        </div>
      )}

      <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" aria-label="Search results">
        {shown.map((s, i) => (
          <SolicitorCard key={`${s.sra_id ?? "x"}-${i}`} s={s} />
        ))}
      </ul>

      {!loading && filtered.length > visible && (
        <div className="flex justify-center mt-8">
          <button
            type="button"
            onClick={() => setVisible((v) => v + PAGE_SIZE)}
            className="font-ui text-sm px-6 py-2.5 rounded-full border border-[color:var(--color-emerald)] text-[color:var(--color-emerald)] hover:bg-[color:var(--color-emerald)] hover:text-[color:var(--color-paper)] transition-colors"
          >
            Show next {Math.min(PAGE_SIZE, filtered.length - visible)}
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Verify-an-SRA-ID tool                                              */}
      {/* ------------------------------------------------------------------ */}
      <VerifySraId />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Solicitor card
// ---------------------------------------------------------------------------
function SolicitorCard({ s }: { s: Solicitor }) {
  const location = s.address || s.postcode || "";
  return (
    <li className="flex flex-col rounded-xl border border-[color:var(--color-ink)]/12 bg-[color:var(--color-paper)]/70 p-5 hover:border-[color:var(--color-gold)]/60 transition-colors">
      <h3 className="font-display text-lg font-semibold text-[color:var(--color-ink)] leading-snug">
        {s.firm || s.name || "Unnamed firm"}
      </h3>
      {s.name && s.firm && (
        <p className="font-body text-sm text-[color:var(--color-ink-soft)] mt-0.5">
          {s.name}
          {s.role ? ` · ${s.role}` : ""}
        </p>
      )}

      {s.muslim_language && (
        <span className="self-start mt-2 font-ui text-[11px] uppercase tracking-[0.1em] px-2 py-0.5 rounded-full bg-[color:var(--color-emerald)]/12 text-[color:var(--color-emerald)]">
          Muslim-community language
        </span>
      )}

      {!!(s.areas && s.areas.length) && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {dedupeAreas(s.areas).slice(0, 4).map((a) => (
            <span
              key={a}
              className="font-ui text-[11px] px-2 py-0.5 rounded bg-[color:var(--color-paper-warm)] text-[color:var(--color-ink-soft)]"
            >
              {a}
            </span>
          ))}
        </div>
      )}

      <dl className="mt-3 space-y-1 font-body text-sm text-[color:var(--color-ink-soft)]">
        {location && (
          <div>
            <dt className="sr-only">Location</dt>
            <dd>{location}</dd>
          </div>
        )}
        {!!(s.languages && s.languages.length) && (
          <div>
            <dt className="sr-only">Languages</dt>
            <dd className="text-[color:var(--color-ink-faded)]">
              {s.languages.join(", ")}
            </dd>
          </div>
        )}
      </dl>

      <div className="mt-auto pt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-ui text-[13px]">
        {s.telephone && (
          <a
            href={`tel:${s.telephone.replace(/\s+/g, "")}`}
            className="text-[color:var(--color-emerald)] hover:text-[color:var(--color-emerald-bright)]"
          >
            {s.telephone}
          </a>
        )}
        {s.email && (
          <a
            href={`mailto:${s.email}`}
            className="text-[color:var(--color-emerald)] hover:text-[color:var(--color-emerald-bright)] break-all"
          >
            {s.email}
          </a>
        )}
      </div>

      {s.sra_id && (
        <p className="mt-2 font-ui text-[12px] text-[color:var(--color-ink-faded)]">
          SRA&nbsp;ID {s.sra_id} ·{" "}
          <a
            href={sraPersonUrl(String(s.sra_id))}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[color:var(--color-emerald)] underline underline-offset-2 hover:text-[color:var(--color-emerald-bright)]"
          >
            verify on SRA register ↗
          </a>
        </p>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Verify-an-SRA-ID tool — exercises GET /api/solicitors/verify/{sra_id}
// ---------------------------------------------------------------------------
function VerifySraId() {
  const [id, setId] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "found" | "missing" | "error">("idle");
  const [match, setMatch] = useState<Solicitor | null>(null);

  const verify = useCallback(async () => {
    const sra = id.trim();
    if (!sra) return;
    setState("loading");
    setMatch(null);
    try {
      const res = await fetch(`/api/solicitors/verify/${encodeURIComponent(sra)}`);
      if (res.status === 404) {
        setState("missing");
        return;
      }
      if (!res.ok) throw new Error(`verify ${res.status}`);
      const data = await res.json();
      setMatch(data.solicitor ?? null);
      setState(data.solicitor ? "found" : "missing");
    } catch {
      setState("error");
    }
  }, [id]);

  return (
    <section
      aria-label="Verify a solicitor by SRA ID"
      className="mt-12 rounded-xl border border-[color:var(--color-ink)]/12 bg-[color:var(--color-paper-warm)]/40 p-5 sm:p-6"
    >
      <h2 className="font-display text-xl font-semibold text-[color:var(--color-ink)]">
        Verify an SRA ID
      </h2>
      <p className="font-body text-sm text-[color:var(--color-ink-soft)] mt-1.5 max-w-2xl">
        Have an SRA number from a firm? Check whether it appears in AskAdil&rsquo;s
        directory. For full regulatory status, always confirm on the{" "}
        <a
          href={SRA_REGISTER_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[color:var(--color-emerald)] underline underline-offset-2 hover:text-[color:var(--color-emerald-bright)]"
        >
          official SRA register
        </a>
        .
      </p>
      <form
        className="flex flex-wrap gap-3 mt-4"
        onSubmit={(e) => {
          e.preventDefault();
          verify();
        }}
      >
        <label htmlFor="verify-sra" className="sr-only">
          SRA ID
        </label>
        <input
          id="verify-sra"
          type="text"
          inputMode="numeric"
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="e.g. 40991"
          className={`${inputClass} max-w-[220px]`}
        />
        <button
          type="submit"
          disabled={state === "loading"}
          className="font-ui text-sm px-5 py-2.5 rounded-full bg-[color:var(--color-emerald)] text-[color:var(--color-paper)] hover:bg-[color:var(--color-emerald-bright)] transition-colors disabled:opacity-60"
        >
          {state === "loading" ? "Checking…" : "Verify"}
        </button>
      </form>

      <div role="status" aria-live="polite" className="mt-3 font-body text-sm">
        {state === "found" && match && (
          <p className="text-[color:var(--color-emerald)]">
            ✓ Found in directory: <strong>{match.firm || match.name}</strong>
            {match.name && match.firm ? ` (${match.name})` : ""}.
          </p>
        )}
        {state === "missing" && (
          <p className="text-[color:var(--color-ink-soft)]">
            Not in AskAdil&rsquo;s directory. That doesn&rsquo;t mean the firm
            isn&rsquo;t regulated —{" "}
            <a
              href={sraPersonUrl(id.trim())}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[color:var(--color-emerald)] underline underline-offset-2 hover:text-[color:var(--color-emerald-bright)]"
            >
              look up SRA&nbsp;ID {id.trim()} on the SRA register ↗
            </a>
            .
          </p>
        )}
        {state === "error" && (
          <p className="text-[color:var(--color-rust)]">
            Couldn&rsquo;t verify just now. Please try again in a moment.
          </p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Helpers + shared class strings
// ---------------------------------------------------------------------------
function dedupeAreas(areas: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const a of areas) {
    const key = (a || "").trim();
    if (key && !seen.has(key.toLowerCase())) {
      seen.add(key.toLowerCase());
      out.push(key);
    }
  }
  return out;
}

const inputClass =
  "w-full font-body text-sm rounded-lg border border-[color:var(--color-ink)]/20 bg-[color:var(--color-paper)] px-3 py-2 text-[color:var(--color-ink)] placeholder:text-[color:var(--color-ink-faded)] focus-visible:outline-2 focus-visible:outline-[color:var(--color-gold)] focus-visible:outline-offset-1";

function tileClass(active: boolean): string {
  return [
    "font-ui text-[13px] px-3.5 py-1.5 rounded-full border transition-colors",
    active
      ? "bg-[color:var(--color-emerald)] text-[color:var(--color-paper)] border-[color:var(--color-emerald)]"
      : "bg-[color:var(--color-paper)] text-[color:var(--color-ink-soft)] border-[color:var(--color-ink)]/20 hover:border-[color:var(--color-emerald)]",
  ].join(" ");
}
