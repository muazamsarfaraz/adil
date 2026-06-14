import type { Metadata } from "next";
import { cookies } from "next/headers";
import { verifyFirmSession, FIRM_COOKIE } from "@/lib/edit-links";
import RequestLinkForm from "./request-form";
import EditListingForm from "./edit-form";

// Reads cookies + the magic-link secret per request.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Manage your listing",
  description: "Solicitors: manage your AskAdil directory listing.",
  robots: { index: false, follow: false },
};

export default async function ManageListingPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const cookieStore = await cookies();
  const session = verifyFirmSession(cookieStore.get(FIRM_COOKIE)?.value);
  const error = typeof sp.error === "string" ? sp.error : undefined;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <p
          className="font-ui text-[12px] uppercase text-[color:var(--color-emerald)] mb-3"
          style={{ letterSpacing: "0.16em" }}
        >
          For solicitors
        </p>
        <h1 className="font-display text-3xl sm:text-4xl leading-tight mb-3">Manage your listing</h1>
        <p className="font-body text-[color:var(--color-ink-soft)] mb-8">
          Sign in with a secure link — no password needed. Changes are reviewed by the AskAdil team before
          they go live.
        </p>

        {session.valid && session.claims ? (
          <EditListingForm slug={session.claims.slug} email={session.claims.email} />
        ) : (
          <RequestLinkForm error={error} />
        )}
      </div>
    </div>
  );
}
