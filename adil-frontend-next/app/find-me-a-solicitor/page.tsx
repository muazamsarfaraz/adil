import type { Metadata } from "next";
import SolicitorFinder from "./solicitor-finder";

// Verbatim from adil-rag-api solicitor_directory.DISCLAIMER — rendered in the
// initial HTML so it is present for crawlers and no-JS users, and surfaced
// again (live, from the API response) inside the client finder.
const ENDORSEMENT_DISCLAIMER =
  "AskAdil does not endorse or guarantee any solicitor. All firms listed are " +
  "pending outreach — none have consented to be listed yet. Contact details are " +
  "from publicly available sources only. Firm data includes information supplied " +
  "by the Solicitors Regulation Authority.";

export const metadata: Metadata = {
  title: "Find a solicitor",
  description:
    "Search regulated UK solicitors by practice area, language and location. " +
    "A free directory from AskAdil, a Muslim Council of Britain initiative. " +
    "Information only — not legal advice.",
  alternates: { canonical: "https://askadil.org/find-me-a-solicitor" },
  openGraph: {
    title: "Find a solicitor · AskAdil",
    description:
      "Search regulated UK solicitors by practice area, language and location. Information only — not legal advice.",
    url: "https://askadil.org/find-me-a-solicitor",
  },
};

export default function FindASolicitorPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-10 sm:py-14">
        {/* Hero */}
        <header className="mb-8">
          <p
            className="font-ui uppercase text-[11px] tracking-[0.18em] text-[color:var(--color-emerald)] mb-3"
          >
            Solicitor directory
          </p>
          <h1 className="font-display text-[color:var(--color-ink)] text-3xl sm:text-4xl font-semibold leading-tight">
            Find a solicitor
          </h1>
          <p className="font-body text-[color:var(--color-ink-soft)] text-base sm:text-lg mt-3 max-w-2xl">
            Search regulated UK solicitors by practice area, language and location.
            Every firm is regulated by the Solicitors Regulation Authority (SRA) and
            its SRA number is shown so you can verify it independently.
          </p>
        </header>

        {/* Interactive finder (client) */}
        <SolicitorFinder />

        {/* Static disclaimers — always in the initial HTML for SEO / no-JS. */}
        <section aria-label="Important information" className="mt-12 space-y-4">
          <div
            className="rounded-lg border-l-4 border-[color:var(--color-gold)] bg-[color:var(--color-paper-warm)]/60 px-5 py-4"
          >
            <h2 className="font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-1.5">
              Listing disclaimer
            </h2>
            <p className="font-body text-sm text-[color:var(--color-ink-soft)] leading-relaxed">
              {ENDORSEMENT_DISCLAIMER}
            </p>
          </div>
          <div
            className="rounded-lg border-l-4 border-[color:var(--color-emerald)] bg-[color:var(--color-paper-warm)]/60 px-5 py-4"
          >
            <h2 className="font-ui text-[11px] uppercase tracking-[0.16em] text-[color:var(--color-ink-faded)] mb-1.5">
              Not legal advice
            </h2>
            <p className="font-body text-sm text-[color:var(--color-ink-soft)] leading-relaxed">
              This directory is <strong>information only — not legal advice</strong>.
              AskAdil helps you find a regulated solicitor; we do not represent you and
              cannot recommend a specific firm. Always check a solicitor&rsquo;s current
              standing on the{" "}
              <a
                href="https://www.sra.org.uk/consumers/register/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[color:var(--color-emerald)] underline underline-offset-2 hover:text-[color:var(--color-emerald-bright)]"
              >
                official SRA register
              </a>{" "}
              before instructing them.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
