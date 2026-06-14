import { NextResponse } from "next/server";
import { verifyEditToken, signFirmSession, FIRM_COOKIE, FIRM_SESSION_TTL_MS, publicOrigin } from "@/lib/edit-links";

// GET /api/listing/verify?token=... — consumes a magic link, sets a 24h firm
// session cookie, and redirects to the management page.
export async function GET(req: Request) {
  const token = new URL(req.url).searchParams.get("token");
  const origin = publicOrigin(req);
  const result = verifyEditToken(token);

  if (!result.valid || !result.claims) {
    const reason = result.expired ? "expired" : "invalid";
    return NextResponse.redirect(`${origin}/manage-listing?error=${reason}`);
  }

  const session = signFirmSession(result.claims.slug, result.claims.email);
  const res = NextResponse.redirect(`${origin}/manage-listing`);
  res.cookies.set({
    name: FIRM_COOKIE,
    value: session,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: Math.floor(FIRM_SESSION_TTL_MS / 1000),
  });
  return res;
}
