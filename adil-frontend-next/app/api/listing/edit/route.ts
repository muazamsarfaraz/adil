import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifyFirmSession, FIRM_COOKIE } from "@/lib/edit-links";

// POST /api/listing/edit — requires a valid firm session. Records a proposed
// edit for operator review (does NOT mutate the live listing directly).
export async function POST(req: Request) {
  const cookieStore = await cookies();
  const session = verifyFirmSession(cookieStore.get(FIRM_COOKIE)?.value);
  if (!session.valid || !session.claims) {
    return NextResponse.json({ ok: false, error: "Not signed in." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Bad request." }, { status: 400 });
  }

  // TODO(persist): insert a `listing_edits` row (status='pending') keyed by
  // session.claims.slug, then surface it in an operator review queue before it
  // goes live — mirroring the mcb-ai-agm-ready-reckoner moderation flow
  // (pending → /admin approve → write to the live record). For now, log it.
  console.log(
    `[listing] pending edit from SRA ${session.claims.slug} (${session.claims.email}):`,
    JSON.stringify(body).slice(0, 800),
  );

  return NextResponse.json({ ok: true, status: "pending_review" });
}
